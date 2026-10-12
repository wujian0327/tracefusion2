"""Additional exact libdft callbacks for the bounded cJSON string decoder.

The earlier calibrated adapter is left unchanged. MOVZX and shifts deliberately
retain upstream behavior, even where it differs from architectural bit routing.
"""
import json
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'libdft-offline'))
import build_core as base
from replay import REGS, ALIASES, require, run_core
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86_const import X86_OP_REG, X86_OP_IMM, X86_OP_MEM

LOW=dict(zip(('al','bl','cl','dl','sil','dil','bpl','spl'),
             ('rax','rbx','rcx','rdx','rsi','rdi','rbp','rsp')))
LOW.update({'r'+str(i)+'b':'r'+str(i) for i in range(8,16)})
ALIASES={**ALIASES,**LOW}
SUFFIX={1:'b_l',2:'w',4:'l',8:'q'}


def build(upstream,out):
    exe,report=base.build(upstream,out)
    functions=[]
    for kind,filename in [('xfer','ins_xfer_op.cpp'),('binary','ins_binary_op.cpp')]:
        for route in ('r2r','m2r','r2m'):
            functions.append((filename,route+'_'+kind+'_opb_l',
                              {'r2r':['reg','reg'],'m2r':['reg','addr'],'r2m':['addr','reg']}[route]))
    functions.append(('ins_clear_op.cpp','r_clrb_l',['reg']))
    for route in ('r2r','m2r'):
        for widths in ('wb','lb','qb','lw','qw','ql'):
            functions.append(('ins_movsx_op.cpp','_movsx_'+route+'_op'+widths+
                              ('_l' if route=='r2r' and widths.endswith('b') else ''),
                              ['reg','reg' if route=='r2r' else 'addr']))
    path=out/'callbacks.inc'
    text=path.read_text().replace('void dispatch(', 'void base_dispatch(')
    # Same helper macro definitions as upstream ins_helper.h; function bodies unchanged.
    text+='\n#define M16TAG(ADDR) { MTAG(ADDR), MTAG(ADDR + 1) }\n'
    text+='#define M32TAG(ADDR) { MTAG(ADDR), MTAG(ADDR + 1), MTAG(ADDR + 2), MTAG(ADDR + 3) }\n'
    registry=[]
    for filename,name,roles in functions:
        code,line=base.extract((out/'upstream'/filename).read_text(),name)
        text+='\n'+code+'\n'
        report['callbacks'].append(dict(name=name,source='src/'+filename,line=line,
                                       sha256=base.sha(code.encode()),body_unchanged=True))
        valid=[f'a.size()=={len(roles)}']+[f'{r}_ok(a[{i}])' for i,r in enumerate(roles)]
        registry.append(f'if(name=="{name}") {{ require({" && ".join(valid)},"operands"); '
                        +name+'(0,'+','.join(f'a[{i}]' for i in range(len(roles)))+'); return; }')
    text+='\nvoid dispatch(const std::string& name,const std::vector<uint64_t>& a) {\n'
    text+='\n'.join(registry)+'\nbase_dispatch(name,a);\n}\n'
    path.write_text(text)
    p=subprocess.run(report['command'],text=True,capture_output=True,timeout=120)
    require(p.returncode==0,p.stderr)
    report.update(generated_sha256=base.sha(text.encode()),executable_sha256=base.sha(exe.read_bytes()),
                  parser_builder_sha256=base.sha(Path(__file__).read_bytes()),
                  returncode=p.returncode,stdout=p.stdout,stderr=p.stderr,
                  native_calibration='pending for this expanded adapter')
    (out/'extraction.json').write_text(json.dumps(report,indent=2)+'\n')
    return exe,report


def decode(row):
    md=Cs(CS_ARCH_X86,CS_MODE_64);md.detail=True
    raw=bytes.fromhex(row['bytes']);xs=list(md.disasm(raw,row['pc']))
    require(len(xs)==1 and xs[0].size==len(raw),'instruction bytes')
    return xs[0]


def translate(row):
    ins=decode(row);op=ins.mnemonic;ops=ins.operands
    def reg(x):
        name=ins.reg_name(x.reg)
        require(name in ALIASES and x.size in SUFFIX,'unqualified register '+name)
        return REGS[ALIASES[name]]
    def address(x):
        def v(r):
            if not r:return 0
            name=ins.reg_name(r)
            if name=='rip':return ins.address+ins.size
            require(name in REGS,'address register')
            return row['registers'][name]
        addr=v(x.mem.base)+v(x.mem.index)*x.mem.scale+x.mem.disp
        if x.mem.segment:
            require(ins.reg_name(x.mem.segment)=='fs','segment')
            addr+=row['fs_base']
        require(0<addr<=0x7fffffffffff-32,'address range')
        return addr
    def call(name,*args):return 'call '+name+' '+' '.join(map(str,args))
    def clear(dst):
        require(dst.size in SUFFIX,'clear width')
        return call('r_clr'+SUFFIX[dst.size],reg(dst)) if dst.type==X86_OP_REG else f'clear {address(dst)} {dst.size}'
    if op in ('mov','movabs','add','sub','xor','and','or'):
        require(len(ops)==2,'operands');dst,src=ops
        if src.type==X86_OP_IMM:return [clear(dst)] if op in ('mov','movabs') else []
        require(dst.size==src.size and dst.size in SUFFIX,'width')
        if op in ('sub','xor') and dst.type==src.type==X86_OP_REG and dst.reg==src.reg:return [clear(dst)]
        route={(X86_OP_REG,X86_OP_REG):'r2r',(X86_OP_REG,X86_OP_MEM):'m2r',(X86_OP_MEM,X86_OP_REG):'r2m'}.get((dst.type,src.type))
        require(route is not None,'operand form')
        return [call(route+('_xfer_op' if op in ('mov','movabs') else '_binary_op')+SUFFIX[dst.size],
                     *[reg(x) if x.type==X86_OP_REG else address(x) for x in ops])]
    if op in ('movzx','movsx','movsxd'):
        dst,src=ops;require(dst.type==X86_OP_REG and src.type in (X86_OP_REG,X86_OP_MEM),'extend operands')
        require((dst.size,src.size) in ((2,1),(4,1),(8,1),(4,2),(8,2),(8,4)),'extend width')
        route='r2r' if src.type==X86_OP_REG else 'm2r'
        name='_movsx_'+route+'_op'+{2:'w',4:'l',8:'q'}[dst.size]+{1:'b',2:'w',4:'l'}[src.size]
        if route=='r2r' and src.size==1:name+='_l'
        return [call(name,reg(dst),reg(src) if route=='r2r' else address(src))]
    if op=='lea':
        dst,src=ops;require(dst.type==X86_OP_REG and src.type==X86_OP_MEM and not src.mem.segment,'lea form')
        names=[ins.reg_name(r) for r in (src.mem.base,src.mem.index) if r]
        # RIP maps to upstream's unused sentinel register; it stays clear under this scope.
        if names==['rip'] or not names:return [clear(dst)]
        require(all(n in REGS for n in names),'lea registers')
        suf=SUFFIX[dst.size]
        return [call('r2r_xfer_op'+suf,reg(dst),REGS[names[0]])] if len(names)==1 else [call('_lea_op'+suf,reg(dst),*[REGS[n] for n in names])]
    if op in ('push','pop'):
        require(len(ops)==1 and ops[0].type==X86_OP_REG and ops[0].size==8,'stack form')
        sp=row['registers']['rsp'];r=reg(ops[0])
        return [call('r2m_xfer_opq',sp-8,r)] if op=='push' else [call('m2r_xfer_opq',r,sp)]
    # Original dispatcher deliberately does not propagate these instructions.
    if op in ('cmp','test','bt','shl','shr','sar','nop','ret','call','jmp',
              'je','jne','ja','jae','jb','jbe','jg','jge','jl','jle','js','jns'):
        return []
    raise ValueError('unsupported parser instruction: '+op+' '+ins.op_str)


def replay(exe,trace):
    require(trace['complete'] and trace['schema']=='cjson-parser-trace-v1','trace completion')
    instructions=trace['instructions'];require(0<len(instructions)<=8192,'instruction budget')
    source=trace['source'];raw=bytes.fromhex(source['data']);n=source['allocation_size']
    require(0<len(raw)<=256 and 0<n<=32,'snapshot bounds')
    commands=[f"seed {source['address']+i} 1 {i+1}" for i in range(len(raw))]
    dispatch=[]
    for i,row in enumerate(instructions,1):
        require(row['step']==i and set(row['registers'])==set(REGS),'instruction sequence/state')
        require(any(a<=row['pc']<b for a,b in trace['ranges']),'PC outside decoder')
        commands.extend(f'register {r} 8' for r in REGS.values())
        commands.append(f"memory {source['allocation']} {n}")
        calls=translate(row);commands.extend(calls)
        dispatch.append(dict(pc=row['pc'],callbacks=calls))
    require(decode(instructions[-1]).mnemonic=='ret','missing parser return')
    commands.append(f"memory {source['allocation']} {n}")
    rows=run_core(exe,commands)
    require(len(rows)==len(instructions)*17+1,'shadow output count')
    length=len(bytes.fromhex(trace['sink']['data']))
    require(length<n,'missing output terminator capacity')
    return dict(byte_labels=rows[-1]['bytes'][:length],allocation_labels=rows[-1]['bytes'],
                intermediate_tags_before=rows[:-1],dispatch=dispatch,
                oracle_used_for_inference=False)
