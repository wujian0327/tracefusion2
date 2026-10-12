"""Reuse our existing C bit dependency machine on the original decoder trace.

No libdft callbacks or reference tags are inputs. Concrete register states only
validate execution; provenance comes from instructions and source identities.
"""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from c_bit_machine import Machine, Value, value, EMPTY, UNKNOWN, ALIASES, REGS, check
from parser_core import decode
from capstone.x86_const import X86_OP_REG, X86_OP_IMM, X86_OP_MEM


def row_from_record(record):
    ins=decode(record);args=[]
    for x in ins.operands:
        if x.type==X86_OP_REG:
            name=ins.reg_name(x.reg);check(name in ALIASES,'unsupported register')
            args.append(dict(kind='reg',name=name,width=x.size*8))
        elif x.type==X86_OP_IMM:args.append(dict(kind='imm',value=x.imm,width=x.size*8))
        else:
            check(x.type==X86_OP_MEM,'operand type')
            b,i=ins.reg_name(x.mem.base),ins.reg_name(x.mem.index);offset=x.mem.disp
            if b=='rip':b='';offset+=ins.address+ins.size
            if x.mem.segment:
                check(ins.reg_name(x.mem.segment)=='fs','segment')
                offset+=record['fs_base']
            check((not b or b in REGS) and (not i or i in REGS),'address registers')
            args.append(dict(kind='mem',base=b,index=i,scale=x.mem.scale,offset=offset,width=x.size*8))
    return dict(address=ins.address,next=ins.address+ins.size,op='mov' if ins.mnemonic=='movabs' else ins.mnemonic,
                args=args)


class Decoder(Machine):
    def step(self,row):
        op,args=row['op'],row['args']
        if op in ('movsxd','movsx'):
            v=self.read(args[1]);width=args[0]['width']
            check(width>v.width,'sign extension')
            signed=v.number-(1<<v.width) if v.number>>(v.width-1) else v.number
            self.write(args[0],Value(signed&((1<<width)-1),v.bits+(v.bits[-1],)*(width-v.width)))
            self.steps.append(row['address']);return row['next']
        if op=='bt':
            a,b=map(self.read,args);check(args[0]['kind']=='reg','memory BT unsupported')
            self.flags=(a.number>>(b.number%a.width))&1
            self.flag_origins=a.origins|b.origins;self.control_origins.update(self.flag_origins)
            self.cf_only=True;self.steps.append(row['address']);return row['next']
        if op=='jmp' and args[0]['kind']!='imm':
            target=self.read(args[0]);self.control_origins.update(target.origins)
            self.steps.append(row['address']);return target.number
        if op=='call':
            target=self.read(args[0]);check('<unknown>' not in target.origins,'unknown call')
            sp=self.reg['rsp'].number-8;self.store(sp,value(row['next'],64));self.reg['rsp']=value(sp,64)
            self.steps.append(row['address']);return target.number
        if op=='ret':
            sp=self.reg['rsp'].number;target=self.load(sp,64)
            check('<unknown>' not in target.origins,'unknown return')
            self.reg['rsp']=value(sp+8,64);self.steps.append(row['address']);return target.number
        if op.startswith('j') and op!='jmp' and getattr(self,'cf_only',False):
            check(op in ('jae','jb'),'undefined flags after BT')
        if op in ('cmp','test','add','sub','xor','and','or','shl','shr','sar'):self.cf_only=False
        return super().step(row)


def infer(plan,trace):
    check(trace['complete'] and trace['instructions'],'incomplete trace')
    src=trace['source'];records=trace['instructions'];entry=records[0]['registers']
    m=Decoder(entry);m.reg={r:value(entry[r],64) for r in REGS}
    # The boundary explicitly treats caller/ABI state as metadata. Heap output is unknown until written.
    snapshots=[]
    for s in plan['segments']:
        if not s['flags']&2:
            address=s['address']+trace['load_bias'];data=s['data']
            if address==0:address=1;data=data[2:]  # Preserve the machine's null-address rejection.
            snapshots.append(dict(address=address,data=data))
    snapshots+=src['snapshots']+[dict(address=src['address'],data=src['data'])]
    intervals=[(s['address'],s['address']+len(bytes.fromhex(s['data']))) for s in snapshots]
    intervals.append((src['allocation'],src['allocation']+src['allocation_size']))
    merged=[]
    for a,b in sorted(intervals):
        if merged and a<=merged[-1][1]:merged[-1][1]=max(b,merged[-1][1])
        else:merged.append([a,b])
    for a,b in merged:m.region(a,b-a)
    for s in snapshots:m.seed(s['address'],bytes.fromhex(s['data']))
    m.seed(src['allocation'],bytes(src['allocation_size']),unknown=True)
    for i,b in enumerate(bytes.fromhex(src['data'])):m.store(src['address']+i,value(b,8,frozenset({i})))
    for i,record in enumerate(records):
        check(record['step']==i+1,'sequence')
        check(any(a<=record['pc']<b for a,b in trace['ranges']),'outside original decoder')
        check(all(m.reg[r].number==record['registers'][r] for r in REGS),f'concrete register mismatch at step {i+1}')
        row=row_from_record(record)
        if i==len(records)-1:
            check(row['op']=='ret' and m.reg['rsp'].number==src['root_sp'],'root return')
            check(m.load(src['root_sp'],64).number==src['return_pc'],'return address')
        else:
            next_pc=m.step(row)
            check(next_pc==records[i+1]['pc'],f'control path mismatch at step {i+1}')
    data=bytes.fromhex(trace['sink']['data']);labels=[]
    for i,b in enumerate(data+b'\0'):
        actual=m.load(src['allocation']+i,8)
        check(actual.number==b and '<unknown>' not in actual.origins,'unknown or wrong output')
        if i<len(data):labels.append(sorted(actual.origins))
    check(m.load(src['item']+32,64).number==src['allocation'],'output object pointer')
    return dict(status='reconstructed',byte_source_offsets=labels,source_offsets=sorted({x for b in labels for x in b}),
                control_source_offsets=sorted(m.control_origins),address_source_offsets=sorted(m.address_origins),
                engine='existing scripts/c_bit_machine.py with bounded decoder adapter',
                strategy='boundary state plus recorded instruction path; no selective-collection claim',
                oracle_used_for_inference=False,libdft_tags_used_for_inference=False)
