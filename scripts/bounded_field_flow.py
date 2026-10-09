"""Acyclic field-copy analysis over a small, explicit Go amd64 instruction model.

Input field ABI and fresh-allocation runtime contract are supplied. Dependency
and distinguishing branches come from the instructions, not fixture case names.
Unsupported operations fail closed. This is not a general binary taint engine.
"""
import copy
import re
from go_object_graph import memory
from hybrid_model import require

REGS=set('AX BX CX DX SI DI R8 R9 R10 R11 R12 R13 R14 R15 SP BP'.split())
LOW={'AL':'AX','BL':'BX','CL':'CX','DL':'DX'}
UNKNOWN=('unknown',)


def analyze(rows,field_offset,max_paths=32,object_size=None):
    object_size=field_offset+8 if object_size is None else object_size
    require(0<=field_offset and field_offset+8<=object_size,'Invalid configured object layout')
    parsed={r['address']:(r['asm'].split(' ',1)[0],re.split(r',\s+',r['asm'].split(' ',1)[1]) if ' ' in r['asm'] else []) for r in rows}
    frames=[i for i,r in enumerate(rows) if parsed[r['address']][0]=='SUBQ' and
            len(parsed[r['address']][1])==2 and parsed[r['address']][1][1]=='SP']
    require(len(frames)==1,'Requires one fixed frame')
    index=frames[0];frame_size=int(parsed[rows[index]['address']][1][0][1:],0)
    require(frame_size>0,'Invalid frame')
    for row in rows[:index+1]:
        op,args=parsed[row['address']]
        require(op in ('LEAQ','CMPQ','JBE','PUSHQ','MOVQ','SUBQ'),'Unsupported prologue')
        if op=='MOVQ':require(args==['SP','BP'],'Prologue changes argument registers')
        if op=='LEAQ':require(args[-1]=='R12','Unexpected prologue scratch register')
    entry=rows[index+1]['address'];by_addr={r['address']:r for r in rows}
    next_addr={r['address']:rows[i+1]['address'] for i,r in enumerate(rows[:-1])}
    paths=[];branches={};visited=set()
    def walk(pc,state,edges,trail):
        require(pc in by_addr and pc>=entry and pc not in trail,'External edge or loop unsupported')
        require(len(paths)<max_paths,'Too many acyclic paths')
        visited.add(pc);trail=trail+[pc]
        op,args=parsed[pc];regs=state['regs'];stack=state['stack']
        require(not state['frame_closed'] or op in ('POPQ','RET') or op.startswith('NOP'),'Instructions after frame teardown unsupported')
        def reg(arg):return regs.get(LOW.get(arg,arg),UNKNOWN)
        def value(arg,width=8):
            if arg in REGS or arg in LOW:return reg(arg) if width==8 and arg in REGS else UNKNOWN
            if arg.startswith('$'):return ('constant',int(arg[1:],0))
            mem=memory(arg);require(mem is not None and not mem['index'],'Unsupported load operand')
            if mem['base']=='SP':
                saved=stack.get(mem['offset'])
                require(saved is not None and saved[0]>=width,'Unmodeled spill load')
                return saved[1] if width==8 and saved[0]==8 else UNKNOWN
            base=reg(mem['base'])
            require(width==8 and base[0]=='input' and mem['offset']==field_offset,'Unmodeled heap read')
            node=dict(address=pc,input_index=base[1],offset=field_offset)
            state['loads'].append(node)
            return ('field',base[1],field_offset,pc)
        def assign(dst,token,width):
            if dst in REGS or dst in LOW:
                require(LOW.get(dst,dst) not in ('SP','BP','R14'),'Unsupported frame/goroutine register write')
                regs[LOW.get(dst,dst)]=token if width==8 and dst in REGS else UNKNOWN
                return
            mem=memory(dst);require(mem is not None and not mem['index'],'Unsupported store operand')
            if mem['base']=='SP':
                offset=mem['offset']
                for other,(size,_) in list(stack.items()):
                    if offset<other+size and other<offset+width:del stack[other]
                stack[offset]=(width,token)
                return
            base=reg(mem['base'])
            require(base[0]=='allocation','Store lacks proved fresh-object/stack separation')
            require(0<=mem['offset'] and mem['offset']+width<=object_size,'Store outside configured fresh object')
            if mem['offset']<=field_offset<mem['offset']+width or field_offset<=mem['offset']<field_offset+8:
                require(width==8 and mem['offset']==field_offset and token[0]=='field','Sink is not an exact field copy')
                state['sinks'].append(dict(address=pc,object=base[1],input_index=token[1],offset=token[2],load_address=token[3]))
        if op in ('MOVQ','MOVB'):
            require(len(args)==2,'Wrong move arity');width=8 if op=='MOVQ' else 1
            assign(args[1],value(args[0],width),width)
        elif op=='MOVZX':
            require(len(args)==2 and args[1] in REGS and bytes.fromhex(by_addr[pc]['code'])[:2]==b'\x0f\xb6','Only byte MOVZX supported')
            value(args[0],1);regs[args[1]]=UNKNOWN
        elif op=='LEAQ':
            mem=memory(args[0]);require(mem and mem['base']=='IP' and not mem['index'] and args[1] in REGS,'Only static-address LEA supported')
            regs[args[1]]=UNKNOWN
        elif op=='CALL':
            require(args==['runtime.newobject(SB)'],'Unmodeled call in field-copy function')
            require(not state['allocations'],'Only one allocation supported')
            state['allocations'].append(pc)
            for r in REGS-{'SP','BP','R14'}:regs[r]=UNKNOWN
            regs['AX']=('allocation',pc)
            # Explicit trusted Go runtime contract: caller spills survive and
            # newobject returns fresh heap storage, disjoint from this frame.
        elif op in ('TESTL','TESTQ','CMPQ','CMPL'):
            require(len(args)==2 and all(a in REGS or a in LOW or a.startswith('$') for a in args),'Unmodeled flag-setting memory read')
        elif op in ('JE','JNE','JMP'):
            require(len(args)==1 and re.fullmatch(r'0x[0-9a-f]+',args[0]),'Unmodeled branch target')
            target=int(args[0],16)
            require(target>pc and target in by_addr,'Backward/external branch unsupported')
            if op=='JMP':walk(target,state,edges,trail);return
            branches[pc]=dict(address=pc,op=op,target=target,fallthrough=next_addr[pc])
            walk(target,copy.deepcopy(state),edges+[dict(address=pc,taken=True)],trail)
            walk(next_addr[pc],state,edges+[dict(address=pc,taken=False)],trail)
            return
        elif op=='ADDQ':
            require(args==['$'+hex(frame_size),'SP'] or args==['$'+str(frame_size),'SP'],'Unmodeled arithmetic')
            state['frame_closed']=True
        elif op=='POPQ':require(args==['BP'] and state['frame_closed'],'Unmodeled POP')
        elif op.startswith('NOP'):pass
        elif op=='RET':
            require(state['frame_closed'],'Return without modeled frame teardown')
            require(state['sinks'] and len(state['allocations'])==1,'Requires completed sink stores to one fresh object')
            # Every accepted store covers the same entire field of the sole
            # fresh allocation. A later exact store kills its previous origin.
            # Partial/unknown/aliased writes are rejected in assign(), not skipped.
            sink=state['sinks'][-1]
            require(reg('AX')==('allocation',sink['object']),'Return is not the sink fresh object')
            paths.append(dict(id=len(paths),branches=edges,loads=state['loads'],writes=state['sinks'],sink=sink,return_address=pc))
            return
        else:raise ValueError('Unsupported instruction: '+by_addr[pc]['asm'])
        require(pc in next_addr,'Fallthrough outside function')
        walk(next_addr[pc],state,edges,trail)
    walk(entry,dict(regs={'AX':('input',0),'BX':('input',1)},stack={},sinks=[],loads=[],allocations=[],frame_closed=False),[],[])
    require(paths,'No modeled return paths')
    def separates(selected):
        groups={}
        for path in paths:
            signature=tuple((e['address'],e['taken']) for e in path['branches'] if e['address'] in selected)
            groups.setdefault(signature,set()).add((path['sink']['input_index'],path['sink']['offset']))
        return all(len(values)==1 for values in groups.values())
    selected=set(branches)
    require(separates(selected),'Control observations cannot distinguish field dependencies')
    # Deterministic deletion yields an inclusion-minimal set in this finite
    # path model, not a globally optimal observation policy.
    for branch in sorted(branches,reverse=True):
        if separates(selected-{branch}):selected.remove(branch)
    return dict(entry=entry,frame_size=frame_size,paths=paths,branches=[branches[a] for a in sorted(branches)],
                selected_branches=sorted(selected),reachable_addresses=sorted(visited),
                assumptions=['Go amd64 ABI input pointers AX/BX; immutable live input objects during one invocation',
                    'Trusted runtime.newobject preserves caller spill origins and returns fresh storage for the configured object layout',
                    'Only modeled acyclic exact field copies to one field of one fresh allocation; last full store determines its returned origin',
                    'No unobserved unsafe/concurrent mutation or asynchronous frame writes'])
