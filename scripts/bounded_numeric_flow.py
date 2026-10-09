"""Bounded acyclic integer data-dependency interpretation, not numeric replay.

Language adapters supply ABI seeds, read-only call contracts and query outputs.
Byte slots distinguish partial writes; arithmetic conservatively joins operand
field origins. Conditions do not implicitly taint data. Unknown output origins,
unknown calls/stores, loops and unsupported instructions fail closed.
"""
import copy
import re
from go_object_graph import memory
from hybrid_model import require
from path_observation import select_branches

UNKNOWN = frozenset({'<unknown>'})
EMPTY = frozenset()
REGS = set('AX BX CX DX SI DI R8 R9 R10 R11 R12 R13 R14 R15'.split())
LOW = dict(AL='AX', BL='BX', CL='CX', DL='DX')
BRANCHES = {'JE','JNE','JG','JGE','JL','JLE','JBE','JA'}


def branch_taken(op, flags):
    zf,sf,of,cf = (bool(flags & (1 << b)) for b in (6,7,11,0))
    return {'JE':zf,'JNE':not zf,'JG':not zf and sf==of,'JGE':sf==of,
            'JL':sf!=of,'JLE':zf or sf!=of,'JBE':cf or zf,'JA':not cf and not zf}[op]


def analyze(rows, frame_size, initial_registers, initial_stack, outputs, calls, globals_read, max_paths=256):
    by = {r['address']:r for r in rows}
    require(len(by)==len(rows) and rows, 'Duplicate/empty instruction rows')
    parsed = {r['address']:(r['asm'].split(' ',1)[0],re.split(r',\s+',r['asm'].split(' ',1)[1]) if ' ' in r['asm'] else []) for r in rows}
    following = {r['address']:rows[i+1]['address'] for i,r in enumerate(rows[:-1])}
    state = dict(regs={}, stack={}, closed=False)
    for reg, width, name in initial_registers:
        require(reg in REGS and width in (4,8), 'Invalid seed register')
        state['regs'][reg] = [frozenset({name})]*width + [EMPTY]*(8-width)
    for offset,width,name in initial_stack:
        for i in range(width):state['stack'][offset+i] = frozenset({name})
    paths=[];branches={};visited=set()

    def walk(pc, st, edges, trail):
        require(pc in by and pc not in trail, 'External edge/loop unsupported')
        require(len(paths)<max_paths, 'Too many numeric paths')
        trail=trail+[pc];visited.add(pc)
        op,args=parsed[pc]
        require(not st['closed'] or op in ('POPQ','RET') or op.startswith('NOP'), 'Unmodeled frame teardown')
        def read(arg,width):
            if arg.startswith('$'):
                int(arg[1:],0);return [EMPTY]*width
            reg=LOW.get(arg,arg)
            if reg in REGS:
                require(width<=8, 'Wide integer register read')
                return st['regs'].get(reg,[UNKNOWN]*8)[:width]
            if arg=='X15':return [EMPTY]*width  # explicit Go ABI permanent-zero SIMD register contract
            mem=memory(arg)
            if mem and mem['base']=='SP' and not mem['index']:
                return [st['stack'].get(mem['offset']+i,UNKNOWN) for i in range(width)]
            require(arg in globals_read, 'Unmodeled memory read: '+arg)
            return [UNKNOWN]*width  # error-interface metadata; never a numeric output origin
        def write(arg,value):
            reg=LOW.get(arg,arg);width=len(value)
            if reg in REGS:
                require(reg!='R14' and width in (4,8), 'Unmodeled partial/goroutine register write')
                st['regs'][reg]=value+[EMPTY]*(8-width);return
            mem=memory(arg)
            require(mem and mem['base']=='SP' and not mem['index'], 'Unmodeled/aliased memory write: '+arg)
            for i,origin in enumerate(value):st['stack'][mem['offset']+i]=origin
        def union(*values):return frozenset().union(*(x for value in values for x in value))
        if op in ('MOVQ','MOVL','MOVUPS'):
            require(len(args)==2, 'Wrong move arity')
            width={'MOVQ':8,'MOVL':4,'MOVUPS':16}[op]
            write(args[1],read(args[0],width))
        elif op=='MOVSXD':
            require(len(args)==2, 'Wrong extension arity')
            value=read(args[0],4);write(args[1],value+[value[-1]]*4)
        elif op in ('ADDQ','ADDL','SUBQ','SUBL','IMULQ','IMULL','SARQ','INCQ','DECQ','XORL'):
            if args==['$'+hex(frame_size),'SP'] and op=='ADDQ':
                st['closed']=True
            else:
                width=8 if op.endswith('Q') else 4
                require(len(args) in (1,2,3), 'Wrong arithmetic arity')
                if op=='XORL':
                    require(len(args)==2 and args[0]==args[1] and args[0] in REGS, 'Only zeroing XOR supported')
                    origin=EMPTY
                elif len(args)==1:
                    require(op in ('INCQ','DECQ'), 'Unknown unary arithmetic')
                    origin=union(read(args[0],width))
                elif len(args)==3:
                    require(op in ('IMULL','IMULQ'), 'Unknown three-operand arithmetic')
                    origin=union(read(args[0],width),read(args[1],width))
                else:origin=union(read(args[0],width),read(args[1],width))
                write(args[-1],[origin]*width)
        elif op in ('TESTL','TESTQ','CMPL','CMPQ'):
            require(len(args)==2,'Wrong comparison arity')
            width=8 if op.endswith('Q') else 4
            for arg in args:read(arg,1 if arg in LOW else width)
        elif op=='CALL':
            require(len(args)==1 and args[0] in calls,'Unmodeled call: '+str(args))
            # Supplied read-only contract preserves this frame/argument storage.
            # Caller-saved register results are unknown, not fabricated clean data.
            for reg in REGS-{'R14'}:st['regs'][reg]=[UNKNOWN]*8
        elif op in BRANCHES or op=='JMP':
            require(len(args)==1 and re.fullmatch(r'0x[0-9a-f]+',args[0]), 'Unmodeled branch target')
            target=int(args[0],16)
            require(target>pc and target in by,'Backward/external branch')
            if op=='JMP':walk(target,st,edges,trail);return
            branches[pc]=dict(address=pc,op=op,target=target,fallthrough=following[pc])
            walk(target,copy.deepcopy(st),edges+[dict(address=pc,taken=True)],trail)
            walk(following[pc],st,edges+[dict(address=pc,taken=False)],trail);return
        elif op.startswith('NOP'):pass
        elif op=='POPQ':require(args==['BP'] and st['closed'],'Unmodeled POP')
        elif op=='RET':
            require(st['closed'],'Return before modeled frame teardown')
            origins={name:sorted(union(read(reg,width))) for name,(reg,width) in outputs.items()}
            require(all('<unknown>' not in v for v in origins.values()),'Unknown reaches numeric output')
            paths.append(dict(id=len(paths),branches=edges,origins=origins,return_address=pc));return
        else:raise ValueError('Unsupported numeric instruction: '+by[pc]['asm'])
        require(pc in following,'Fallthrough outside function')
        walk(following[pc],st,edges,trail)
    walk(rows[0]['address'],state,[],[])
    outcome=lambda p:tuple((k,tuple(v)) for k,v in sorted(p['origins'].items()))
    selected=select_branches(paths,branches,outcome,observe_return=True)
    return dict(entry=rows[0]['address'],paths=paths,branches=[branches[a] for a in sorted(branches)],
                selected_branches=selected,reachable_addresses=sorted(visited),
                semantics='executed operand field dependencies; no implicit control taint or value-based source filtering')
