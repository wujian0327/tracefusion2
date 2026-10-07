"""Bounded copy-only output dependency proof, independent of observed values.

Explore zero/nonzero classes of one immutable byte; track symbolic input cells,
then scan writes backwards for last definitions. This proves a final projection,
not an executed path. Unknown effects and exhausted bounds refuse the proof.
"""
from hybrid_model import BRANCHES,branch_taken,require
from interproc_model import flags_for


def analyze_output_dependence(plan):
    require(plan.get('runtime_inputs')==[dict(register='rdi',length=1)] and
            plan.get('runtime_input_ownership')=='request-private' and not plan.get('runtime_state_model'),
            'Output proof requires one immutable private control byte')
    ir=plan['instructions'];nodes={n['address']:n for n in ir}
    require(0<len(ir)<=64 and len(nodes)==len(ir) and plan['entry'] in nodes,'Invalid copy CFG')
    abi=plan['abi'];require(abi==dict(dst_register='rax',src_register='rbx',aux_register='rcx'),'Unsupported copy ABI')
    paths=[]
    for control in (0,1):
        regs={r:('ptr',region,0) for r,region in (('rax','dst'),('rbx','src'),('rcx','aux'),('rdi','control'))}
        memory={(r,i):('byte',r,i) for r in ('src','aux','dst') for i in range(4)}
        pc=plan['entry'];flags=None;control_flags=False;writes=[];steps=0;reads=set()
        def reg(arg):
            require(arg['reg'] in regs,'Unknown initial register');value=regs[arg['reg']]
            if type(value) is int:return value&((1<<arg['width'])-1)
            require(arg['width']==64 or value[0]=='byte','Partial symbolic pointer read')
            return value
        def address(arg):
            base=regs.get(arg['base']);index=regs.get(arg['index']) if arg.get('index') else 0
            require(isinstance(base,tuple) and base[0]=='ptr' and type(index) is int,'Unknown copy address')
            region=base[1];offset=base[2]+index*arg['scale']+arg['offset']
            require(arg['width']==8 and 0<=offset<(1 if region=='control' else 4),'Copy address outside region')
            return region,offset
        def read(arg):
            if arg['kind']=='imm':return arg['value']
            if arg['kind']=='reg':return reg(arg)
            key=address(arg);require(key[0]!='control','Control may only appear in a zero comparison')
            return memory[key]
        while True:
            require(pc in nodes and steps<min(plan.get('max_steps',256),256),'Copy proof exceeds supported execution bound')
            n=nodes[pc];op=n['op'];args=n['args'];steps+=1;following=n['next']
            if op=='ret':break
            if op in ('mov','movzx'):
                value=read(args[0]);target=args[1]
                if target['kind']=='reg':
                    require(target['width'] in (32,64),'Unsupported copy register write')
                    require(type(value) is int or target['width']==64 or value[0]=='byte','Truncated symbolic address')
                    regs[target['reg']]=value&((1<<target['width'])-1) if type(value) is int else value
                else:
                    region,index=address(target);require(op=='mov' and region=='dst','Non-output write')
                    require(isinstance(value,tuple) and value[0]=='byte','Non-copy store')
                    memory[(region,index)]=value;writes.append(dict(instruction=pc,step=steps,byte=index,origin=list(value)))
            elif op=='lea':
                region,index=address(args[0]);regs[args[1]['reg']]=('ptr',region,index)
            elif op in ('xor','add','sub','inc'):
                target=args[-1];require(target['kind']=='reg','Unsupported arithmetic destination')
                width=n['width'];mask=(1<<width)-1
                if op=='xor' and args[0]==args[1]:left=right=0;value=0
                else:
                    left=read(target);right=1 if op=='inc' else read(args[0])
                    require(type(left) is int and type(right) is int,'Data/address arithmetic outside copy proof')
                    value=(left+right if op in ('add','inc') else left-right if op=='sub' else left^right)&mask
                regs[target['reg']]=value
                if op=='inc':
                    # Unknown incoming CF remains unknown; do not invent flags.
                    flags=None if flags is None else (flags_for('add',left,1,width)&~1)|(flags&1)
                else:flags=flags_for(op,left,right,width)
                control_flags=False
            elif op=='cmp':
                if args[0]['kind']=='mem' and address(args[0])[0]=='control':
                    require(args[0]['base']=='rdi' and not args[0].get('index') and args[0]['offset']==0 and
                            args[1]['kind']=='imm' and args[1]['value']==0 and n['width']==8,'Unsupported control comparison')
                    left,right=control,0;reads.add(pc);control_flags=True
                else:
                    left,right=read(args[0]),read(args[1]);require(type(left) is int and type(right) is int,'Data-dependent comparison')
                    control_flags=False
                flags=flags_for('cmp',left,right,n['width'])
            elif op=='test':
                # The supported memory TEST is a successful nil check. Its
                # flags are unknown and must be overwritten before a branch.
                require(args[1]['kind']=='mem' and address(args[1])[0]!='control','Unsupported TEST in copy proof')
                flags=None;control_flags=False
            elif op in BRANCHES:
                require(flags is not None,'Branch on unmodeled data or flags')
                require(not control_flags or op in ('je','jne'),'Only zero/nonzero control branches supported')
                if branch_taken(op,flags):following=n['target']
            elif op=='jmp':following=n['target']
            else:require(op=='nop','Unsupported effect in copy proof: '+op)
            pc=following
        final=[list(memory['dst',i]) for i in range(4)]
        require(all(x[0]=='byte' and x[1] in ('src','aux') for x in final),'Uninitialized output')
        live=set();last=[];killed=[]
        for w in reversed(writes):
            (killed if w['byte'] in live else last).append(w);live.add(w['byte'])
        require(live==set(range(4)),'Incomplete output stores')
        paths.append(dict(control_class='zero' if control==0 else 'nonzero',output=final,
            last_writes=sorted(last,key=lambda w:w['byte']),overwritten_writes=list(reversed(killed)),
            final_registers={r:list(v) if isinstance(v,tuple) else v for r,v in sorted(regs.items())},
            runtime_read_addresses=sorted(reads),steps=steps))
    varying=[i for i in range(4) if paths[0]['output'][i]!=paths[1]['output'][i]]
    return dict(version='bounded-copy-output-v1',varying_output_bytes=varying,paths=paths,
        projection=paths[0]['output'] if not varying else None,
        assumptions=['request-private immutable input regions','disjoint input/output/control regions','successful observed call return'],
        claim='Final byte origins only; not the actual branch, intermediate writes, or minimum observations')


def certify_output_projection(plan):
    result=analyze_output_dependence(plan)
    require(result['projection'] is not None,'Final byte origins still depend on control at positions '+str(result['varying_output_bytes']))
    return result


def apply_output_projection(machine,certificate,returned):
    """Bind the checked static projection to this request's actual objects."""
    from interproc_model import Sym
    bases={'src':machine.src,'dst':machine.dst,'aux':machine.regs[machine.plan['abi']['aux_register']].number,
           'control':machine.runtime_regions[0]}
    def evaluate(value):
        if type(value) is int:return value
        kind,region,index=value
        return bases[region]+index if kind=='ptr' else machine.memory[bases[region]+index].number
    # Only constrain registers whose expression is invariant across both paths.
    a,b=[p['final_registers'] for p in certificate['paths']]
    for r,value in a.items():
        if b.get(r)==value:require(returned['registers'][r]==evaluate(value),'Output proof exit register mismatch: '+r)
    for index,value in enumerate(certificate['projection']):
        _,region,offset=value;origin=machine.memory[bases[region]+offset]
        nid='projection-byte:'+str(index)
        machine.nodes[nid]=dict(id=nid,kind='certified-output-dependency',byte=index,
                               evidence='all-supported-control-classes-agree')
        machine.link([origin],nid)
        machine.memory[machine.dst+index]=Sym(number=origin.number,refs=frozenset({nid}),origins=origin.origins)
    machine.written=set(range(machine.dst,machine.dst+4));machine.halted=True
