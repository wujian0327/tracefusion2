"""Original PlaceOrder amount interval, nested MultiplySlow, and shared Sum model.

Caller copies are interpreted from verified ELF instructions, not a hand-written
"all items influence payment" summary. Runtime addresses bind indirect operands;
frame-relative stack state and a G-scoped call stack bind dynamic iterations.
"""
import copy
import ctypes as ct
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'experiments/checkout-money-sum')]
import sum_adapter
from go_byte_adapter import assembly_rows
from go_string_adapter import file_offset,physical_probes
from hybrid_model import require
from bounded_numeric_flow import branch_taken
from observed_copy_machine import Frame,GPRS,UNKNOWN,EMPTY,union,operands,indirect_operands
from string_capture import HEADER

BASE=sum_adapter.BASE
PLACE=BASE+'.(*checkoutService).PlaceOrder'
MULT=BASE+'/money.MultiplySlow'
SUM=BASE+'/money.Sum'
PREP=BASE+'.(*checkoutService).prepareOrderItemsAndShippingQuoteFromCart'
PAY=BASE+'.(*checkoutService).chargeCard'
AGG=('AX','BX','CX','DI','SI','R8','R9','R10','R11')
BRANCHES={'JE','JNE','JG','JGE','JL','JLE','JBE','JA'}
LIMIT=32


def plan_binary(binary,command,reader,out):
    sumdir=out/'sum-model';sumdir.mkdir()
    sp=sum_adapter.plan_binary(binary,command,reader,sumdir)
    data=binary.read_bytes();functions={};sites=[]
    def add(row,kind,fn,**kw):
        # One physical site can have several roles; continuation processing is
        # handled by the interpreter before executing the same instruction.
        existing=next((s for s in sites if s['address']==row['address']),None)
        if existing:
            existing['roles'].append(kind);existing.update(kw);return
        sites.append(dict(id=len(sites),address=row['address'],file_offset=file_offset(data,row['address']),
                          kind=kind,roles=[kind],function=fn,asm=row['asm'],**kw))
    for fn in (PLACE,MULT):
        asm=command(['tool','objdump','-s','^'+re.escape(fn)+'$',str(binary)])
        rows=assembly_rows(asm);require(rows,'Missing original function: '+fn)
        (out/(('PlaceOrder' if fn==PLACE else 'MultiplySlow')+'.asm')).write_text(asm)
        for r in rows:
            off=file_offset(data,r['address']);code=bytes.fromhex(r['code'])
            require(data[off:off+len(code)]==code,'ELF/disassembly mismatch')
        frames=[i for i,r in enumerate(rows) if re.fullmatch(r'SUBQ \$0x[0-9a-f]+, SP',r['asm'])]
        require(len(frames)==1,'Unsupported frame');fi=frames[0]
        frame=int(rows[fi]['asm'].split('$')[1].split(',')[0],0)
        require([r['asm'].split()[0] for r in rows[:fi+1]]==['LEAQ','CMPQ','JBE','PUSHQ','MOVQ','SUBQ'],'Unsupported Go prologue')
        if fn==PLACE:
            prep=[i for i,r in enumerate(rows) if r['asm']=='CALL '+PREP+'(SB)']
            pay=[i for i,r in enumerate(rows) if r['asm']=='CALL '+PAY+'(SB)']
            require(len(prep)==len(pay)==1,'Ambiguous source/sink callsite')
            start,end=prep[0]+1,pay[0]
            spills=[]
            for reg,r in zip(AGG[:7],rows[start:start+7]):
                m=re.fullmatch(r'MOVQ '+reg+r', (0x[0-9a-f]+)\(SP\)',r['asm'])
                require(m is not None,'Preparation-return register spill differs')
                spills.append(int(m[1],0))
            require(spills==list(range(spills[0],spills[0]+56,8)),'Noncontiguous orderPrep return spill')
            add(rows[start],'source',fn);add(rows[end],'sink',fn)
            for r in rows:
                if r['asm']=='RET':add(r,'end',fn)
        else:
            start=fi+1;end=next(i for i in range(start,len(rows)) if rows[i]['asm']=='RET')
            for i,reg in enumerate(AGG):
                require(rows[start+i]['asm']==f'MOV{"L" if i in (1,8) else "Q"} {reg}, {hex(frame+24+i*8)}(SP)',
                        'MultiplySlow aggregate ABI spill differs')
            add(rows[start],'multiply_entry',fn);add(rows[end],'multiply_exit',fn)
        region=copy.deepcopy(rows[start:end+1])
        for i,r in enumerate(region):
            r['next']=region[i+1]['address'] if i+1<len(region) else None
            op,args=operands(r['asm'])
            if op in BRANCHES:add(r,'branch',fn,op=op)
            if indirect_operands(r['asm']):add(r,'memory',fn)
            if op=='CALL' and not(fn==PLACE and i==len(region)-1):
                add(r,'call',fn,callee=args[0]);require(i+1<len(region),'Missing continuation')
                add(region[i+1],'continuation',fn)
        functions[fn]=dict(frame=frame,entry=region[0]['address'],exit=region[-1]['address'],rows=region)
    for s in sp['all_sites']:
        add(dict(address=s['address'],asm=s['asm']),'sum_'+s['kind'],SUM,**({'op':s['op']} if 'op' in s else {}))
    # Validate field/aggregate layouts used by the only manual boundary binding.
    types=[BASE+'/genproto.'+t for t in ('OrderItem','CartItem')]+[BASE+'.orderPrep']
    layout=json.loads(command(['run',str(reader),str(binary),*types]))
    expected={'OrderItem':{'Item':(40,8),'Cost':(48,8)},'CartItem':{'Quantity':(56,4)}}
    for name,wanted in expected.items():
        fields={f['name']:(f['offset'],f['size']) for f in layout[BASE+'/genproto.'+name]['fields']}
        require(all(fields.get(k)==v for k,v in wanted.items()),'Source object layout differs')
    prep_layout=layout[BASE+'.orderPrep']
    require(prep_layout['size']==56 and [(f['name'],f['offset'],f['size']) for f in prep_layout['fields']]==
            [('orderItems',0,24),('cartItems',24,24),('shippingCostLocalized',48,8)],'orderPrep ABI layout differs')
    plan=dict(adapter='original-checkout-payment-path-v1',binary_sha256=hashlib.sha256(data).hexdigest(),
              functions=functions,sum_model=sp,layouts=layout,all_sites=sites,source_limit=LIMIT,strategy='selected',
              scope='Original PlaceOrder preparation-return numeric fields to chargeCard amount argument; local mock gRPC peers; no network-field lineage claim',
              assumptions=['Pinned Go 1.25.4 Linux amd64 ABI and upstream v0.10.4; optimized test executable',
                'One PlaceOrder invocation/process; source objects distinct and immutable during the amount interval; <=32 items',
                'Source return aggregate ABI: AX/BX/CX item slice, R9 shipping pointer, R10/R11 error; chargeCard amount in DI',
                'Only explicit numeric data dependencies; quantity/branch decisions are control evidence',
                'runtime.newobject allocates fresh zeroed memory; gcWriteBarrierN preserves GPRs except R11 but may clobber SIMD; wbMove preserves application payload and stack storage',
                'Go stack relocation preserves frame-relative bytes; heap objects do not move; G pointer identifies the bounded invocation',
                'Selected versus all_branches differs only inside Sum; caller/multiply control and indirect addresses are retained in both',
                'Boundary-only mode reports unknown, not an artificially precise or exhaustive candidate set'])
    return strategy_plan(plan,'selected')


def strategy_plan(plan,strategy):
    require(strategy in ('selected','all_branches','boundaries'),'Unknown strategy')
    p=copy.deepcopy(plan);p['strategy']=strategy
    keep=set(p['sum_model']['flow']['selected_branches'])
    p['sites']=[s for s in p['all_sites'] if
                (s['kind'] in ('source','sink','end') if strategy=='boundaries' else
                 strategy=='all_branches' or s['kind']!='sum_branch' or s['address'] in keep)]
    p['event_order']=[s['id'] for s in p['sites']]
    return p


class Raw(ct.Structure):
    _fields_=[(k,ct.c_uint64) for k in ('timestamp','pid_tid','g')]+[('site',ct.c_uint32),('error',ct.c_uint32)]+[
        ('registers',ct.c_uint64*16)]+[(k,ct.c_uint64) for k in ('flags','a','b','c','d','tag')]


def source(plan,pid,namespace):
    h=re.sub(r'struct event_t \{.*?\};','struct event_t {u64 timestamp,pid_tid,g;u32 site,error;u64 registers[16],flags,a,b,c,d,tag;};',HEADER,count=1,flags=re.S)
    start=h.index('static __always_inline void snapshot(');end=h.index('static __always_inline struct event_t *begin',start)
    h=h[:start]+h[end:]
    h=h.replace('NSDEV',str(namespace.st_dev)+'ULL').replace('NSINO',str(namespace.st_ino)+'ULL').replace('TARGET_PID',str(pid))
    h+='''
BPF_HASH(active,u64,u32,8);
static __always_inline u64 word64(struct event_t *e,u64 p) {u64 v=0;if(!p||bpf_probe_read_user(&v,8,(void *)p)<0)e->error=1;return v;}
static __always_inline u64 word32(struct event_t *e,u64 p) {u32 v=0;if(!p||bpf_probe_read_user(&v,4,(void *)p)<0)e->error=1;return v;}
static __always_inline void regs(struct event_t *e,struct pt_regs *ctx) {
'''
    h+=''.join(f'e->registers[{i}]=ctx->{r.lower()};' for i,r in enumerate(GPRS))+'e->flags=ctx->flags;}\n'
    for s in plan['sites']:
        kind=s['kind'];sid=s['id']
        guard='u64 g=ctx->r14;u32 *state=active.lookup(&g);'
        if kind=='source':
            # begin() validates the target PID before changing active state.
            code=f'''struct event_t *e=begin(ctx,{sid});if(!e)return 0;regs(e,ctx);
 u32 v=ctx->r10?2:1;active.update(&g,&v);e->a=ctx->bx;e->b=ctx->r10;submit(ctx,e);
 if(v==2)return 0;
 e=begin(ctx,{sid});if(!e)return 0;e->tag=1;e->a=ctx->r9;
 e->b=word64(e,e->a+56);e->c=word32(e,e->a+64);if(!e->a||ctx->bx>{LIMIT})e->error=1;submit(ctx,e);
 #pragma unroll
 for(int i=0;i<{LIMIT};i++){{if(i>=ctx->bx)break;
 e=begin(ctx,{sid});if(!e)return 0;e->tag=i+2;
 u64 item=word64(e,ctx->ax+i*8);u64 cart=word64(e,item+40);e->a=word64(e,item+48);
 e->b=word64(e,e->a+56);e->c=word32(e,e->a+64);e->d=word32(e,cart+56);
 if(!item||!cart||!e->a)e->error=1;submit(ctx,e);}}
'''
        else:
            guard+='if(!state'+('' if kind=='end' else '||*state!=1')+')return 0;'
            code=f'struct event_t *e=begin(ctx,{sid});if(!e)return 0;regs(e,ctx);'
            if kind=='sink':code+='e->a=ctx->di;e->b=word64(e,e->a+56);e->c=word32(e,e->a+64);u32 v=2;active.update(&g,&v);'
            elif kind=='end':code+='active.delete(&g);'
            elif kind=='sum_entry':code+=f'e->a=ctx->r10;e->b=(u32)ctx->r11;e->c=word64(e,ctx->sp+{plan["sum_model"]["right_units"]});e->d=word32(e,ctx->sp+{plan["sum_model"]["right_nanos"]});'
            elif kind=='sum_exit':code+='e->a=ctx->r10;e->b=(u32)ctx->r11;e->c=word64(e,ctx->sp+80);'
            code+='submit(ctx,e);'
        h+=f'\nint probe_{sid}(struct pt_regs *ctx){{{guard}{code}return 0;}}\n'
    return h


def decode_record(data,size,sites):
    n=ct.sizeof(Raw);padded=((n+4+7)//8)*8-4
    require(size in (n,padded),f'Event layout mismatch: {size}, expected {n} or {padded}')
    r=Raw.from_buffer_copy(ct.string_at(data,n));require(r.site in sites,'Unknown site')
    return dict(timestamp=r.timestamp,pid_tid=r.pid_tid,g=r.g,site=r.site,error=r.error,
                kind=sites[r.site]['kind'],registers=dict(zip(GPRS,map(int,r.registers))),
                **{k:int(getattr(r,k)) for k in ('flags','a','b','c','d','tag')})


class Replay:
    def __init__(self,plan,events):
        self.plan=plan;self.events=events;self.pos=0;self.heap={};self.calls=[];self.controls=[]
        self.sites={s['id']:s for s in plan['sites']}
        self.addresses={s['address'] for s in plan['sites']}
        self.source_identity=None;self.steps=0

    def take(self,address):
        require(self.pos<len(self.events),'Missing event')
        e=self.events[self.pos];require(self.sites[e['site']]['address']==address,'Unexpected/missing event at '+hex(address))
        require(e['tag']==0,'Misplaced source-field event')
        self.pos+=1;return e

    def sum(self,frame):
        model=self.plan['sum_model'];inputs={'l.'+k:v for k,v in frame.money_registers().items()}
        inputs.update({'r.'+k:v for k,v in frame.money_stack().items()})
        entry=self.take(model['flow']['entry']);require(entry['kind']=='sum_entry','Missing Sum entry')
        observed=[]
        while self.pos<len(self.events) and self.events[self.pos]['kind']=='sum_branch':
            e=self.events[self.pos];s=self.sites[e['site']];self.pos+=1
            observed.append((s['address'],branch_taken(s['op'],e['flags'])))
        require(self.pos<len(self.events),'Missing Sum return');exit=self.events[self.pos]
        require(exit['kind']=='sum_exit' and not exit['c'],'Failed/unfinished Sum');self.pos+=1
        controls={s['address'] for s in self.plan['sites'] if s['kind']=='sum_branch'}
        candidates=[p for p in model['flow']['paths'] if p['return_address']==self.sites[exit['site']]['address'] and
                    [(b['address'],b['taken']) for b in p['branches'] if b['address'] in controls]==observed]
        answers=[]
        for p in candidates:
            result={k:frozenset().union(*(inputs[x] for x in deps)) for k,deps in p['origins'].items()}
            if result not in answers:answers.append(result)
        require(len(answers)==1,'Ambiguous/unmodeled Sum dependency path')
        require(not any(UNKNOWN&v for v in answers[0].values()),'Unknown Sum operand provenance')
        self.calls.append(dict(id=len(self.calls),kind='Sum',entry_event=entry['timestamp'],exit_event=exit['timestamp'],
            inputs={k:sorted(v) for k,v in inputs.items()},origins={k:sorted(v) for k,v in answers[0].items()},
            matched_paths=[p['id'] for p in candidates],output=[sum_adapter.signed(exit['a'],64),sum_adapter.signed(exit['b'],32)]))
        frame.set_money(answers[0])
        # Sum writes the error result into the caller's outgoing argument area.
        for i in range(72,88):frame.stack[i]=EMPTY

    def run_frame(self,name,frame,start_event=None):
        fn=self.plan['functions'][name];rows={r['address']:r for r in fn['rows']};pc=fn['entry']
        first=start_event
        while True:
            self.steps+=1;require(self.steps<=200000,'Replay instruction budget exceeded')
            require(pc in rows,'Execution left modeled interval: '+hex(pc));r=rows[pc]
            e=first;first=None
            if e is None and pc in self.addresses:e=self.take(pc)
            if name==PLACE and pc==fn['exit']:
                require(e is not None and e['kind']=='sink','Missing sink')
                origins={field:union([self.heap.get(e['a']+offset+i,UNKNOWN) for i in range(width)])
                         for field,offset,width in [('Units',56,8),('Nanos',64,4)]}
                require(not any(UNKNOWN&v for v in origins.values()),'Unknown sink storage provenance')
                return dict(status='exact_data_origins',origins={k:sorted(v) for k,v in origins.items()},
                            output=[sum_adapter.signed(e['b'],64),sum_adapter.signed(e['c'],32)],sink_pointer=e['a'],sink_event=e['timestamp'])
            op,args=operands(r['asm']);nextpc=r['next']
            if op in BRANCHES:
                require(e is not None,'Missing branch evidence');taken=branch_taken(op,e['flags'])
                self.controls.append(dict(function=name,address=pc,taken=taken,event=e['timestamp']))
                if taken:nextpc=int(args[0],0)
            elif op=='JMP':nextpc=int(args[0],0)
            elif op=='RET':
                require(name==MULT,'Unexpected PlaceOrder return before sink')
                return frame
            elif op=='CALL':
                callee=args[0]
                if callee==SUM+'(SB)':self.sum(frame)
                elif callee==MULT+'(SB)':
                    child=Frame(MULT,self.plan['functions'][MULT]['frame'],self.heap,{k:frame.reg[k] for k in AGG})
                    for i in range(4):child.stack[child.size+16+i]=frame.stack.get(i,UNKNOWN)
                    before=len(self.calls);self.run_frame(MULT,child)
                    values=child.money_registers();frame.set_money(values)
                    self.calls.append(dict(id=len(self.calls),kind='MultiplySlow',nested_sum_calls=list(range(before,len(self.calls))),
                                           origins={k:sorted(v) for k,v in values.items()}))
                elif callee=='runtime.newobject(SB)' or callee=='runtime.wbMove(SB)':frame.clobber()
                elif re.fullmatch(r'runtime.gcWriteBarrier[1-8]\(SB\)',callee):
                    frame.reg['R11']=[UNKNOWN]*8
                    # Go's slow wbBufFlush path does not preserve SIMD values.
                    # X15 is the ABI zero register; other vector values die.
                    for i in range(15):frame.reg[f'X{i}']=[UNKNOWN]*16
                else:raise ValueError('Unmodeled executed call: '+callee)
            else:frame.apply(r,e)
            pc=nextpc

    def run(self):
        entry=self.events[0];require(entry['kind']=='source' and entry['tag']==0,'Missing source boundary')
        require(self.events[-1]['kind']=='end','Missing PlaceOrder completion')
        require(sum(e['kind']=='source' and e['tag']==0 for e in self.events)==1,'Multiple invocations unsupported')
        require(sum(e['kind']=='end' for e in self.events)==1,'Wrong completion pairing')
        if entry['b']:
            require(len(self.events)==2,'Events after failed preparation')
            return dict(status='no_sink',reason='preparation returned an error',origins={},output=[])
        require(entry['a']<=LIMIT,'Source item bound exceeded')
        count=entry['a'];source_events=self.events[1:count+2]
        require(len(source_events)==count+1 and [e['tag'] for e in source_events]==list(range(1,count+2)), 'Missing/reordered source fields')
        require(all(e['kind']=='source' and e['site']==entry['site'] for e in source_events),'Source event site mismatch')
        require(all(e['a'] for e in source_events) and len({e['a'] for e in source_events})==len(source_events),'Nil/aliased source Money objects unsupported')
        sources=[]
        for i,e in enumerate(source_events):
            name='shipping' if i==0 else f'items[{i-1}].Cost'
            for field,offset,width in [('Units',56,8),('Nanos',64,4)]:
                for j in range(width):self.heap[e['a']+offset+j]=frozenset({name+'.'+field})
            sources.append(dict(field_prefix=name,pointer=e['a'],value=[sum_adapter.signed(e['b'],64),sum_adapter.signed(e['c'],32)],quantity=e['d'] if i else None))
        self.source_identity=dict(pid=entry['pid_tid']>>32,g=entry['g'],return_event=entry['timestamp'])
        if self.plan['strategy']=='boundaries':
            require(len(self.events)==count+4 and self.events[-2]['kind']=='sink','Wrong boundary sequence')
            sink=self.events[-2]
            return dict(status='unknown',reason='No internal copy/call/branch evidence collected; this implementation does not enumerate boundary-only candidates',
                        origins={},output=[sum_adapter.signed(sink['b'],64),sum_adapter.signed(sink['c'],32)],sources=sources,source_identity=self.source_identity)
        self.pos=count+2
        frame=Frame(PLACE,self.plan['functions'][PLACE]['frame'],self.heap)
        result=self.run_frame(PLACE,frame,start_event=entry)
        require(self.pos==len(self.events)-1,'Extra/mispaired events after sink')
        result.update(source_identity=self.source_identity,sources=sources,calls=self.calls,controls=self.controls,
                      instructions_replayed=self.steps,threads=len({e['pid_tid'] for e in self.events}))
        return result


def infer(plan,doc):
    try:
        require(doc['binary_sha256']==plan['binary_sha256'] and not doc['capture_errors'] and doc['returncode']==0,'Capture failed/wrong binary')
        events=sorted(doc['events'],key=lambda e:e['timestamp']);stats=doc['stats']
        require(events and stats['submitted']==len(events) and not any(stats[k] for k in ('lost','read_errors','submit_errors','namespace_errors')),'Incomplete capture')
        require(all(not e['error'] for e in events),'Memory snapshot error')
        require(all(a['timestamp']<b['timestamp'] for a,b in zip(events,events[1:])),'Ambiguous event order')
        require(len({(e['pid_tid']>>32,e['g']) for e in events})==1 and events[0]['g'],'Invocation/G mismatch')
        sites={s['id']:s for s in plan['sites']}
        require(all(e['site'] in sites and e['kind']==sites[e['site']]['kind'] for e in events),'Unknown observation')
        return Replay(plan,events).run()
    except (ValueError,KeyError,IndexError) as exc:
        return dict(status='unknown',reason=str(exc),origins={},output=[])


def evaluate(plan,result,truth):
    expected='no_sink' if not truth['sink_present'] else 'unknown' if plan['strategy']=='boundaries' else 'exact_data_origins'
    passed=result['status']==expected and result['output']==truth['output']
    if expected=='exact_data_origins':passed=passed and result['origins']==truth['origins']
    tp=fp=fn=wrong=0
    if truth['sink_present']:
        for field in ('Units','Nanos'):
            actual=set(truth['origins'][field])
            predicted=set(result['origins'].get(field,[])) if result['status']=='exact_data_origins' else set()
            tp+=len(actual&predicted);fp+=len(predicted-actual);fn+=len(actual-predicted)
            wrong+=int(result['status']=='exact_data_origins' and predicted!=actual)
    return dict(case=truth['case'],strategy=plan['strategy'],passed=passed,status=result['status'],
                reason=result.get('reason'),sink_present=truth['sink_present'],application_error=truth['application_error'],
                exact_fields=2 if expected=='exact_data_origins' and passed else 0,query_fields=2 if truth['sink_present'] else 0,
                definite_fields=2 if truth['sink_present'] and result['status']=='exact_data_origins' else 0,
                wrong_definite_fields=wrong,tp=tp,fp=fp,fn=fn)
