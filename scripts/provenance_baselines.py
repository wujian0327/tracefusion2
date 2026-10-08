"""Method controls for the fixed four-byte, immutable-control experiment.

These are NOT implementations of HardTaint or SelectiveTaint. The first control
uses nonrelational reaching-origin sets, strong output updates and bounded loop
expansion. The second retains zero/nonzero path correlation. An exhaustive
256-value mode is an additional test oracle, not a deliberately slow baseline.
None calls
the production output-dependence analyzer or consumes fixture names/answers.
Only the existing collector/replayer and its safety checks are shared.
"""
from collections import deque
from time import perf_counter_ns

from hybrid_model import BRANCHES, branch_taken, require
from observation_contract import stable_runtime_input


def _flags(op, left, right, width, previous=None):
    mask=(1 << width)-1; left &= mask; right &= mask
    value=(left-right if op in ('cmp','sub') else left+right if op in ('add','inc') else left^right)&mask
    sign=1 << (width-1)
    carry=left<right if op in ('cmp','sub') else left+right>mask if op in ('add','inc') else False
    overflow=bool(((left^right)&(left^value)&sign) if op in ('cmp','sub') else
                  ((~(left^right)&(left^value))&sign) if op in ('add','inc') else 0)
    bits=int(carry)|(int((value&255).bit_count()%2==0)<<2)|(int(value==0)<<6)|(int(bool(value&sign))<<7)|(int(overflow)<<11)
    if op=='inc':return None if previous is None else (bits&~1)|(previous&1)
    return bits


def _interpret(plan, control):
    """Control=None forgets correlation; an integer fixes the entire run.

    Integer/pointer state and step count partition the worklist; byte-origin
    sets are joined at merges. Unknown branches are explored both ways, while
    each byte store strongly replaces the old definition. This is a bounded
    may-origin analysis, not a general program slicer.
    """
    ir=plan['instructions'];nodes={n['address']:n for n in ir}
    require(0<len(ir)<=64 and len(nodes)==len(ir),'Invalid bounded CFG')
    regs={r:('ptr',region,0) for r,region in [('rax','dst'),('rbx','src'),('rcx','aux'),('rdi','control')]}
    memory={(region,i):frozenset({(region,i)}) for region in ('src','aux','dst') for i in range(4)}
    todo=deque();known={};final=[set() for _ in range(4)];processed=0;returns=0

    def enqueue(pc, depth, registers, mem, flags):
        require(pc in nodes and depth<min(plan.get('max_steps',256),256),'Baseline exceeded execution bound')
        shape=tuple(sorted((r,('origins',) if isinstance(v,frozenset) else v) for r,v in registers.items()))
        key=(pc,depth,shape,flags)
        old=known.get(key)
        if old is None:
            known[key]=(dict(registers),dict(mem));todo.append(key);return
        joined={r:old[0][r]|v if isinstance(v,frozenset) else v for r,v in registers.items()}
        mm={k:old[1][k]|v for k,v in mem.items()}
        if (joined,mm)!=old:known[key]=(joined,mm);todo.append(key)

    enqueue(plan['entry'],0,regs,memory,None)
    while todo:
        key=todo.popleft();pc,depth,_,flags=key
        regs,mem=known[key];regs=dict(regs);mem=dict(mem)
        processed+=1;require(processed<=10000,'Baseline exceeded worklist bound')
        n=nodes[pc];op=n['op'];args=n['args'];next_pc=n['next']

        def address(a):
            base=regs.get(a['base']);index=regs.get(a['index']) if a.get('index') else 0
            require(isinstance(base,tuple) and base[0]=='ptr' and type(index) is int,'Unmodeled baseline address')
            region=base[1];offset=base[2]+index*a['scale']+a['offset']
            require(a['width']==8 and 0<=offset<(1 if region=='control' else 4),'Baseline address outside region')
            return region,offset

        def read(a):
            if a['kind']=='imm':return a['value']
            if a['kind']=='reg':
                require(a['reg'] in regs,'Unmodeled baseline register')
                v=regs[a['reg']]
                require(type(v) is int or isinstance(v,frozenset) or a['width']==64,'Truncated baseline pointer')
                return v&((1<<a['width'])-1) if type(v) is int else v
            loc=address(a);require(loc[0]!='control','Control read outside comparison');return mem[loc]

        if op=='ret':
            for i in range(4):final[i].update(mem['dst',i])
            returns+=1;continue
        if op in ('mov','movzx'):
            value=read(args[0]);target=args[1]
            if target['kind']=='reg':
                require(target['width'] in (32,64),'Unsupported baseline register store')
                require(type(value) is int or isinstance(value,frozenset) or target['width']==64,'Truncated baseline address')
                regs[target['reg']]=value&((1<<target['width'])-1) if type(value) is int else value
            else:
                location=address(target)
                require(op=='mov' and location[0]=='dst' and isinstance(value,frozenset),'Unsupported baseline store')
                mem[location]=value
        elif op=='lea':
            region,index=address(args[0]);regs[args[1]['reg']]=('ptr',region,index)
        elif op in ('xor','add','sub','inc'):
            target=args[-1];require(target['kind']=='reg','Unsupported baseline arithmetic')
            if op=='xor' and args[0]==args[1]:left=right=0
            else:left=read(target);right=1 if op=='inc' else read(args[0])
            require(type(left) is int and type(right) is int,'Symbolic data arithmetic unsupported')
            value=left-right if op=='sub' else left+right if op in ('add','inc') else left^right
            regs[target['reg']]=value&((1<<n['width'])-1)
            require(not isinstance(flags,tuple) or op!='inc','INC after control flags unsupported')
            flags=_flags(op,left,right,n['width'],flags)
        elif op=='cmp':
            if args[0]['kind']=='mem' and address(args[0])[0]=='control':
                require(args[0]['base']=='rdi' and not args[0].get('index') and args[0]['offset']==0 and
                        args[1]['kind']=='imm' and args[1]['value']==0 and n['width']==8,'Unsupported control test')
                flags=('control',None if control is None else _flags('cmp',control,0,8))
            else:
                left,right=read(args[0]),read(args[1])
                require(type(left) is int and type(right) is int,'Data-dependent branch unsupported')
                flags=_flags('cmp',left,right,n['width'])
        elif op=='test':
            require(args[1]['kind']=='mem' and address(args[1])[0]!='control','Unsupported TEST')
            flags=None
        elif op in BRANCHES:
            require(flags is not None,'Unknown branch flags')
            if isinstance(flags,tuple):
                require(op in ('je','jne'),'Unsupported abstract control branch')
                if flags[1] is None:enqueue(n['target'],depth+1,regs,mem,flags)
                elif branch_taken(op,flags[1]):next_pc=n['target']
            elif branch_taken(op,flags):next_pc=n['target']
        elif op=='jmp':next_pc=n['target']
        else:require(op=='nop','Unsupported baseline effect: '+op)
        enqueue(next_pc,depth+1,regs,mem,flags)
    require(returns>0 and all(s and all(r in ('src','aux') for r,_ in s) for s in final),'Incomplete baseline output')
    return final,processed


def baseline_decision(plan, method):
    require(method in ('origin_sets','path_sensitive','enumerate256'),'Unknown baseline')
    started=perf_counter_ns()
    result=dict(method=method,status='unsupported',mode=None,
                claim='Method control on bounded copy IR; not a reproduction of a published system')
    try:
        require(plan.get('observation_mode','full')=='full','Start from a full plan')
        require(plan.get('observation_target')=='final-byte-origins-v1','Explicit final-origin query required')
        require(plan.get('abi')==dict(dst_register='rax',src_register='rbx',aux_register='rcx'),'Unsupported ABI')
        stable_runtime_input(plan)
        outputs=[set() for _ in range(4)];steps=0
        controls=[None] if method=='origin_sets' else (0,1) if method=='path_sensitive' else range(256)
        # The interpreter rejects every control use except an 8-bit compare
        # with zero. Thus 0 and 1 represent all 256 values for path_sensitive.
        for control in controls:
            result_sets,count=_interpret(plan,control);steps+=count
            for dest,origins in zip(outputs,result_sets):dest.update(origins)
        varying=[i for i,s in enumerate(outputs) if len(s)!=1]
        result.update(status='selected',mode='entry' if varying else 'output',
            output_origin_sets=[[[r,i] for r,i in sorted(s)] for s in outputs],
            varying_output_bytes=varying,processed_states=steps,
            control_assignments=len(controls),
            reason='Observe one immutable control byte' if varying else 'Final origins invariant under baseline analysis')
    except (ValueError,KeyError,TypeError,IndexError) as exc:
        result['reason']=str(exc)
    result['analysis_ns']=perf_counter_ns()-started
    return result
