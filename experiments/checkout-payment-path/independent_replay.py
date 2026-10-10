"""Two bounded method controls on raw ELF instructions and snapshot-v2 events.

This module deliberately imports no production inference/planning or test oracle.
Observed slicing uses caller control/address witnesses and Sum entry/return,
but executes Sum independently. Boundary replay has no internal witnesses.
SSA edges represent direct data operations; control dependence is separate.
"""
from independent_machine import (Graph,State,Byte,word,number,signed,check,split,
    memory,taken,live_registers,GPRS,REGS,AGG,COND)

BASE='github.com/GoogleCloudPlatform/microservices-demo/src/checkoutservice'
PLACE=BASE+'.(*checkoutService).PlaceOrder'
MULT=BASE+'/money.MultiplySlow'
SUM=BASE+'/money.Sum'
VALID=BASE+'/money.IsValid'

class Replay:
    def __init__(self,model,sites,events,observed):
        self.model=model; self.sites={s['id']:s for s in sites}; self.events=events
        self.observed=observed; self.pos=0; self.graph=Graph(); self.steps=0
        self.next_heap=1<<62; self.next_stack=1<<61; self.calls=[]; self.controls=[]; self.barriers=[]
        self.by={k:{r['address']:r for r in v['rows']} for k,v in model['functions'].items()}
        self.addresses={s['address'] for s in sites} if observed else set()
        self.live={k:live_registers(v,self.call_effect) for k,v in model['functions'].items()}

    def call_effect(self,callee):
        killed=set(REGS)-{'SP','BP','R14','X15'}
        if callee==BASE+'.(*checkoutService).chargeCard(SB)': return {'DI'},set()
        if 'gcWriteBarrier' in callee: return set(),{'R11'}|{'X'+str(i) for i in range(15)}
        if callee=='runtime.wbMove(SB)': return {'AX','BX','CX'},killed
        if callee=='runtime.newobject(SB)': return {'AX'},killed
        if callee=='runtime.memequal(SB)': return {'AX','BX','CX'},killed
        return set(AGG),killed

    def take(self,address):
        check(self.pos<len(self.events),'Missing event at '+hex(address))
        e=self.events[self.pos]; self.pos+=1
        check(e['site'] in self.sites and self.sites[e['site']]['address']==address and e['tag']==0,
              'Missing/reordered event at '+hex(address))
        return e

    def allocate(self):
        self.next_heap+=256; return self.next_heap

    def frame(self,name,parent=None,event=None):
        f=State(self.graph,parent.heap if parent else None); f.frame=self.model['functions'][name]['frame']
        self.next_stack+=4096; f.base=self.next_stack
        if event is not None: f.base=event['registers']['SP']
        f.reg['SP']=word(f.base,8)
        if parent:
            f.regions=list(parent.regions); f.private=list(parent.private)
            for r in AGG+('R14',): f.reg[r]=list(parent.reg[r])
            for i in range(88): f.stack[f.frame+16+i]=parent.stack.get(i,Byte(None,1))
        return f

    def seed(self,entry,packets,request):
        f=self.frame(PLACE,event=entry if self.observed else None)
        for r in GPRS:
            if r!='SP': f.reg[r]=word(entry['registers'][r],8)
        def put(addr,data):
            for i,b in enumerate(data): f.heap[addr+i]=b
        def currency(e,ptr,offset):
            r=e['registers']; p,n,v=r['AX'],r['BX'],r['CX']
            check(p and 0<n<=8,'Unsupported/missing snapshot-v2 currency')
            f.region(p,n,clean=True); put(p,word(v,n))
            put(ptr+offset,word(p,8)+word(n,8))
        array=entry['registers']['AX']; n=entry['a']
        check(n==entry['registers']['BX'] and n<=32,'Source slice ABI/count differs')
        if n: f.region(array,n*8,clean=True)
        check(entry['registers']['R9']==packets[0]['a'],'Shipping ABI pointer differs')
        for i,e in enumerate(packets):
            p=e['a']; f.region(p,72,clean=True); currency(e,p,40)
            prefix='shipping' if i==0 else 'items['+str(i-1)+'].Cost'
            for field,offset,size,value in [('Units',56,8,e['b']),('Nanos',64,4,e['c'])]:
                node=self.graph.make(None,label=prefix+'.'+field); put(p+offset,word(value,size,node))
            if i:
                item,cart=e['registers']['DX'],e['registers']['DI']
                check(item and cart and 1<=signed(e['d'],32)<=32,'Unsupported item graph/quantity')
                f.region(item,56,clean=True); f.region(cart,64,clean=True)
                put(array+(i-1)*8,word(item,8)); put(item+40,word(cart,8)); put(item+48,word(p,8))
                put(cart+56,word(e['d'],4))
        check(request['a'],'Missing request boundary metadata')
        f.region(request['a'],self.model['request_size'],clean=True)
        currency(request,request['a'],self.model['request_currency'])
        for i,b in enumerate(word(request['a'],8)): f.stack[f.frame+40+i]=b
        return f

    def barrier_call(self,state,callee):
        if callee=='runtime.wbMove(SB)': state.clobber(); return
        check('gcWriteBarrier' in callee,'Unexpected barrier call')
        state.clobber(barrier=True)
        if self.observed:
            check(self.pos<len(self.events),'Missing barrier continuation')
            p=self.events[self.pos]['registers']['R11']
        else: p=self.allocate()
        state.region(p,128,clean=True,private=True); state.reg['R11']=word(p,8)

    def merge_barrier(self,name,state,row):
        # Runtime WB state is not an input snapshot. Prove both alternatives
        # equivalent at their compiler join, including all application storage
        # and registers live after the join. Only private WB buffer differs.
        op,args=split(row['asm']); check(op=='JE','Unsupported WB conditional')
        join=int(args[0],16); pc=row['next']; slow=state.clone(); limit=0
        old=self.observed; self.observed=False
        try:
            while pc!=join:
                check(pc in self.by[name] and limit<32,'Unbounded WB slow alternative'); limit+=1
                r=self.by[name][pc]; operation,a=split(r['asm'])
                if operation=='CALL':
                    check(a[0]=='runtime.wbMove(SB)' or 'gcWriteBarrier' in a[0],'Unmodeled WB alternative call')
                    self.barrier_call(slow,a[0])
                elif operation=='JMP':
                    check(int(a[0],16)==join,'WB alternative jumps outside join'); pc=join; continue
                else:
                    check(operation not in COND|{'JMP','RET'},'Unexpected WB alternative control')
                    slow.apply(r)
                pc=r['next']
        finally: self.observed=old
        live=self.live[name].get(join,set())
        different=[r for r in sorted(live) if r in state.reg and state.reg[r]!=slow.reg[r]]
        check(not different,'WB alternatives differ in live register at '+hex(row['address'])+': '+','.join(different))
        check('FLAGS' not in live or state.flags==slow.flags,'WB alternatives differ in live flags')
        check(state.stack==slow.stack,'WB alternatives mutate application stack')
        check(all(state.heap.get(a)==slow.heap.get(a) for base,n in state.regions for a in range(base,base+n)),
              'WB alternatives mutate application heap')
        self.barriers.append(dict(function=name,address=row['address'],join=join,live_registers=sorted(live),equivalent=True))
        state.flags=None; return join

    def invoke(self,state,callee):
        name=callee.removesuffix('(SB)')
        if name in (MULT,SUM,VALID):
            event=None
            if self.observed and name in (MULT,SUM):
                event=self.take(self.model['functions'][name]['entry'])
                if name==SUM:
                    expected=[state.rnum('R10'),state.rnum('R11',4),number([state.stack.get(56+i,Byte(None,1)) for i in range(8)]),
                              number([state.stack.get(64+i,Byte(None,1)) for i in range(4)])]
                    check(expected==[event[k] for k in ('a','b','c','d')],'Sum entry value witness differs')
            child=self.frame(name,state,event); self.execute(name,child,first=event)
            returned={r:list(child.reg[r]) for r in (('AX',) if name==VALID else AGG)}
            if name==SUM:
                for i in range(16): state.stack[72+i]=child.stack.get(child.frame+88+i,Byte(None,1))
            state.clobber()
            for r,d in returned.items(): state.reg[r]=d
            self.calls.append(dict(function=name,units=state.rnum('R10'),nanos=state.rnum('R11',4)))
        elif callee=='runtime.newobject(SB)':
            p=self.events[self.pos]['registers']['AX'] if self.observed and self.pos<len(self.events) else self.allocate()
            check(p and not any(a<=p<a+n for a,n in state.regions),'Allocation not fresh')
            state.clobber(); state.region(p,72,clean=True)
            for i in range(72): state.heap[p+i]=Byte(0,0)
            state.reg['AX']=word(p,8)
        elif callee=='runtime.memequal(SB)':
            a,b,n=(state.rnum(r) for r in ('AX','BX','CX')); check(None not in (a,b,n) and n<=8,'Unknown currency comparison')
            left=state.read('0(AX)',n); right=state.read('0(BX)',n)
            check(all(x.value is not None for x in left+right),'Missing currency bytes')
            result=int([x.value for x in left]==[x.value for x in right]); state.clobber(); state.reg['AX']=word(result,8)
        elif callee=='runtime.wbMove(SB)' or 'gcWriteBarrier' in callee: self.barrier_call(state,callee)
        else: raise ValueError('Unsupported executed call '+callee)

    def execute(self,name,state,first=None):
        fn=self.model['functions'][name]; pc=fn['entry']
        while True:
            self.steps+=1; check(self.steps<=200000,'Independent replay budget exceeded')
            check(pc in self.by[name],'Execution left verified function interval at '+hex(pc))
            row=self.by[name][pc]; op,args=split(row['asm']); e=first; first=None
            if self.observed and e is None and name!=VALID and pc in self.addresses: e=self.take(pc)
            if e is not None:
                state.base=e['registers']['SP']; state.reg['SP']=word(state.base,8)
            if name==PLACE and pc==fn['exit']:
                pointer=e['a'] if e is not None else state.rnum('DI'); check(pointer is not None,'Unknown sink pointer')
                outputs={}; queries={}
                for field,off,size in [('Units',56,8),('Nanos',64,4)]:
                    d=state.read(hex(off)+'(DI)',size,e)
                    check(number(d) is not None,'Unknown replayed output')
                    outputs[field]=signed(number(d),size*8)
                    queries[field]=self.graph.backward(x.definition for x in d)
                    check('<unknown>' not in queries[field]['origins'],'Unknown sink data definition')
                return dict(status='exact_data_origins',origins={k:q['origins'] for k,q in queries.items()},
                            output=[outputs['Units'],outputs['Nanos']],backward_queries=queries)
            nxt=row['next']
            if op in COND:
                if e is not None: direction=taken(op,e['flags'])
                elif state.flags=='barrier': pc=self.merge_barrier(name,state,row); continue
                else:
                    check(isinstance(state.flags,int),'Unknown branch predicate at '+hex(pc))
                    direction=taken(op,state.flags)
                self.controls.append(dict(function=name,address=pc,taken=direction,observed=e is not None))
                if direction: nxt=int(args[0],16)
            elif op=='JMP': nxt=int(args[0],16)
            elif op=='CALL': self.invoke(state,args[0])
            elif op=='RET':
                if name==SUM and e is not None:
                    check([state.rnum('R10'),state.rnum('R11',4),number([state.stack.get(state.frame+88+i,Byte(None,1)) for i in range(8)])]==
                          [e['a'],e['b'],e['c']],'Sum return witness differs')
                check(name!=PLACE,'Unexpected PlaceOrder return before sink'); return
            else: state.apply(row,e)
            pc=nxt

    def run(self):
        e=self.events[0]; check(e['kind']=='source' and e['tag']==0,'Missing source boundary')
        check(self.events[-1]['kind']=='end' and sum(x['kind']=='end' for x in self.events)==1,'Missing invocation completion')
        check(sum(x['kind']=='source' and not x['tag'] for x in self.events)==1,'Multiple invocations unsupported')
        if e['b']:
            check(len(self.events)==2,'Events after failed preparation'); return dict(status='no_sink',origins={},output=[])
        n=e['a']; check(n<=32,'Item bound exceeded'); packets=self.events[1:n+2]; request=self.events[n+2]
        check([p['tag'] for p in packets]==list(range(1,n+2)) and request['tag']==n+2,'Missing snapshot-v2 packets')
        check(all(p['kind']=='source' and p['site']==e['site'] for p in packets+[request]),'Snapshot-v2 site mismatch')
        check(all(p['a'] for p in packets) and len({p['a'] for p in packets})==len(packets),'Aliased/nil Money unsupported')
        sinks=[x for x in self.events if x['kind']=='sink']; check(len(sinks)==1,'Missing/ambiguous sink')
        self.pos=n+3; f=self.seed(e,packets,request)
        if not self.observed: check(len(self.events)==n+5 and self.events[-2]['kind']=='sink','Unexpected boundary observations')
        answer=self.execute(PLACE,f,first=e if self.observed else None)
        if self.observed: check(self.pos==len(self.events)-1,'Extra/mispaired internal events')
        sink=sinks[0]; check(answer['output']==[signed(sink['b'],64),signed(sink['c'],32)],'Boundary sink value witness differs')
        answer.update(instructions_executed=self.steps,ssa_nodes=len(self.graph.nodes),calls=self.calls,
                      controls=self.controls,barrier_equivalence_checks=self.barriers)
        return answer

def validate_capture(plan,doc):
    check(doc['binary_sha256']==plan['binary_sha256'] and not doc['capture_errors'] and doc['returncode']==0,'Wrong binary/capture failure')
    events=sorted(doc['events'],key=lambda e:e['timestamp']); stats=doc['stats']
    check(events and stats['submitted']==len(events) and not any(stats[k] for k in ('lost','read_errors','submit_errors','namespace_errors')),'Incomplete capture')
    check(all(not e['error'] for e in events),'Snapshot read error')
    check(all(a['timestamp']<b['timestamp'] for a,b in zip(events,events[1:])),'Ambiguous event order')
    check(len({(e['pid_tid']>>32,e['g']) for e in events})==1 and events[0]['g'],'Invocation/G mismatch')
    sites={s['id']:s for s in plan['sites']}
    check(all(e['site'] in sites and e['kind']==sites[e['site']]['kind'] for e in events),'Unknown observation')
    return events

def infer(plan,doc):
    try:
        events=validate_capture(plan,doc)
        return Replay(plan['independent_model'],plan['sites'],events,plan['strategy']=='path_sensitive_slice').run()
    except (ValueError,KeyError,IndexError,TypeError) as exc:
        return dict(status='unknown',reason=str(exc),origins={},output=[])
