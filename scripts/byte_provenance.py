"""Language-neutral bounded byte instruction replay and dynamic dependency graph.

ABI normalization belongs to go_byte_adapter. Reuse the existing integer core's
symbolic value, condition-code calculation and branch rules, and shared slicing.
"""
import json
from interproc_model import Sym, flags_for
from hybrid_model import branch_taken, BRANCHES, require
from lineage_graph import backward_nodes

MASK64=(1<<64)-1


class MissingObservation(ValueError):
    def __init__(self,address):
        super().__init__('Missing runtime input observation at instruction '+hex(address))
        self.address=address


def snapshot(value):
    data=bytes.fromhex(value['hex']);ptr=value['pointer']
    require(ptr>0 and value['key']==f'{ptr:x}:{len(data)}','Snapshot identity mismatch')
    return ptr,data


class ByteMachine:
    def __init__(self,plan,entry,source,destination,nodes,edges,auxiliary=None):
        self.plan=plan;self.nodes=nodes;self.edges=edges;self.source=source
        self.src,self.input_bytes=source['pointer'],source['bytes']
        self.dst,self.initial_bytes=destination
        self.regs={};self.memory={};self.written=set();self.flags=None;self.steps=[]
        self.write_version=0;self.source_versions=[];self.write_sources=set()
        self.pc=plan['entry'];self.halted=False
        self.instructions={n['address']:n for n in plan['instructions']}
        bindings=[(plan['abi']['dst_register'],self.dst),(plan['abi']['src_register'],self.src)]
        if auxiliary:bindings.append((plan['abi']['aux_register'],auxiliary['pointer']))
        for reg,value in bindings:
            nid='entry:'+reg;nodes[nid]={'id':nid,'kind':'abi-address','value':value}
            self.regs[reg]=Sym(number=value,refs=frozenset({nid}))
        self.runtime_regions=[]
        for region in plan.get('runtime_inputs',[]):
            require(region==dict(register='rdi',length=1),'Unsupported runtime input contract')
            reg=region['register'];ptr=entry['registers'][reg]
            require(ptr>0 and all(not base<=ptr<base+4 for base in
                    [self.src,self.dst]+([auxiliary['pointer']] if auxiliary else [])),'Runtime input overlaps data')
            self.regs[reg]=Sym(number=ptr);self.runtime_regions.append(ptr)
        for definition in [source]+([auxiliary] if auxiliary else []):
            for i,b in enumerate(definition['bytes']):
                nid=definition['id']+'/byte:'+str(i)
                nodes[nid]={'id':nid,'kind':'source-byte','source':definition['id'],'byte':i,'value':b}
                edges.append({'source':definition['id'],'target':nid,'kind':'data'})
                self.memory[definition['pointer']+i]=Sym(number=b,refs=frozenset({nid}),origins=frozenset({(definition['id'],i)}))
        for i,b in enumerate(self.initial_bytes):
            nid='initial-output:'+str(i);nodes[nid]={'id':nid,'kind':'initial-output','byte':i,'value':b}
            self.memory[self.dst+i]=Sym(number=b,refs=frozenset({nid}))
        self.verify(entry)

    def verify(self,event):
        for reg,value in self.regs.items():
            require(event['registers'][reg]==value.number,'Register replay mismatch: '+reg)

    def reg(self,name):
        require(name in self.regs,'Read of unmodeled initial register: '+name)
        return self.regs[name]

    def address(self,arg):
        base=self.reg(arg['base']);index=self.reg(arg['index']) if arg.get('index') else Sym(number=0)
        return Sym(number=(base.number+index.number*arg['scale']+arg['offset'])&MASK64,
                   refs=base.refs|index.refs,origins=base.origins|index.origins)

    def read(self,arg,event=None):
        if arg['kind']=='imm':return Sym(number=arg['value']&((1<<arg['width'])-1))
        if arg['kind']=='reg':
            a=self.reg(arg['reg']);return Sym(number=a.number&((1<<arg['width'])-1),refs=a.refs,origins=a.origins)
        address=self.address(arg).number
        if arg['width']==8 and address in self.runtime_regions:
            require(self.instructions[self.pc]['op']=='cmp','Runtime input is supported only as a comparison operand')
            if event is None:raise MissingObservation(self.pc)
            ptr,data=snapshot(event['values']['load'])
            require(ptr==address and len(data)==1,'Runtime input snapshot mismatch')
            return Sym(number=data[0])
        require(arg['width']==8 and address in self.memory,'Memory read outside declared byte regions')
        value=self.memory[address]
        if event is not None:
            ptr,data=snapshot(event['values']['load'])
            require(ptr==address and data==bytes([value.number]),'Observed byte load contradicts memory replay')
        return value

    def link(self,values,nid,kind='data'):
        for parent in sorted(set().union(*(v.refs for v in values))):
            self.edges.append({'source':parent,'target':nid,'kind':kind})

    def result(self,nid,value,inputs):
        self.link(inputs,nid)
        return Sym(number=value,refs=frozenset({nid}),origins=frozenset().union(*(v.origins for v in inputs)))

    def write_register(self,arg,value):
        width=arg['width'];number=value.number&((1<<width)-1)
        require(width in (32,64),'Partial register writes unsupported')
        self.regs[arg['reg']]=Sym(number=number,refs=value.refs,origins=value.origins)

    def step(self,event=None):
        require(not self.halted and len(self.steps)<self.plan['max_steps'],'Execution exceeds bound or continues after RET')
        n=self.instructions[self.pc]
        if event is not None:
            require(event['site']==n['site'],'Observed instruction order disagrees with CFG replay')
            self.verify(event)
        op=n['op'];args=n['args'];nid='step:'+str(len(self.steps));next_pc=n['next']
        node={'id':nid,'kind':'instruction','address':n['address'],'asm':n['asm'],'step':len(self.steps)}
        if event is None:node['evidence']='modeled-from-boundaries'
        self.nodes[nid]=node;self.steps.append(dict(node,event_sequence=event['sequence'] if event is not None else None))
        if op=='movzx':
            value=self.read(args[0],event);node['read_address']=self.address(args[0]).number
            self.link([self.address(args[0])],nid,'address')
            self.write_register(args[1],self.result(nid,value.number,[value]))
        elif op=='mov':
            value=self.read(args[0]);value=self.result(nid,value.number,[value])
            if args[1]['kind']=='reg':self.write_register(args[1],value)
            else:
                address=self.address(args[1]);self.link([address],nid,'address')
                require(self.dst<=address.number<self.dst+4,'Store outside output region')
                self.memory[address.number]=Sym(number=value.number&255,refs=value.refs,origins=value.origins)
                self.written.add(address.number);node['write_address']=address.number
                self.write_version+=1;self.write_sources.update(s for s,_ in value.origins)
                # Report object-level source changes. Cells retain last-writer
                # definitions internally so partial overwrites do not erase
                # the origin of portions that have not yet been replaced.
                if len(self.written)==4:
                    current=sorted({s for i in range(4) for s,_ in self.memory[self.dst+i].origins})
                    if not self.source_versions or self.source_versions[-1]['sources']!=current:
                        self.source_versions.append({'write_version':self.write_version,'after_step':node['step'],
                            'sources':current,'output_hex':bytes(self.memory[self.dst+i].number for i in range(4)).hex()})
        elif op=='lea':
            value=self.address(args[0]);self.write_register(args[1],self.result(nid,value.number,[value]))
        elif op in ('xor','add','sub'):
            width=n['width'];mask=(1<<width)-1
            if op=='xor' and args[0]==args[1]:
                value=0;inputs=[];left=right=0
            else:
                right=self.read(args[0]);left=self.read(args[1]);inputs=[left,right]
                value=((left.number^right.number) if op=='xor' else (left.number+right.number) if op=='add' else (left.number-right.number))&mask
                left,right=left.number,right.number
            self.flags=flags_for(op,left,right,width)
            self.write_register(args[1],self.result(nid,value,inputs))
        elif op=='inc':
            old=self.read(args[0]);width=n['width'];value=(old.number+1)&((1<<width)-1)
            # INC preserves CF. JL uses SF/OF, but preserve the complete modeled flags.
            old_carry=(self.flags or 0)&1
            self.flags=(flags_for('add',old.number,1,width)&~1)|old_carry
            self.write_register(args[0],self.result(nid,value,[old]))
        elif op in ('cmp','test'):
            a=self.read(args[0],event);b=self.read(args[1],event)
            self.flags=flags_for('cmp' if op=='cmp' else 'test',a.number,b.number,n['width'])
            self.link([a,b],nid,'control')
        elif op in BRANCHES:
            require(self.flags is not None,'Branch uses unmodeled flags')
            if branch_taken(op,self.flags):next_pc=n['target']
        elif op=='jmp':next_pc=n['target']
        elif op=='ret':self.halted=True
        elif op!='nop':raise ValueError('Unimplemented IR instruction: '+op)
        self.pc=next_pc
        self.steps[-1].update(node)


def infer(document,plan):
    try:
        require(not document.get('capture_errors') and document.get('returncode')==0,'Capture failed')
        require(document['binary_sha256']==plan['binary_sha256'],'Binary hash mismatch')
        events=sorted(document['events'],key=lambda e:(e['timestamp'],e['sequence']))
        require(events and len({e['sequence'] for e in events})==len(events),'Empty or duplicate events')
        stats=document['stats']
        require(stats['submitted']==len(events) and not any(stats[k] for k in ('lost','read_errors','submit_errors')),'Incomplete transport')
        require(len({(e['pid'],e['g']) for e in events})==1 and all(e['g'] for e in events),'Requires one process/goroutine')
        specs={s['id']:s for s in plan['sites']}
        for e in events:
            s=specs[e['site']];require((e['op'],e['phase'])==(s['op'],s['phase']),'Site contract mismatch')
        root=[e for e in events if e['op']!='instruction']
        require([e['site'] for e in root]==plan['root_order'],'Missing or extra boundary events')
        mode=plan.get('observation_mode','full')
        require(mode in ('full','boundary','selective'),'Unknown observation mode')
        if mode=='boundary':
            contract='runtime-byte-input-v1' if plan.get('runtime_inputs') else 'closed-four-byte-leaf-v1'
            require(plan.get('replay_contract')==contract,'Missing boundary replay contract')
            require(events==root and len(root)==10,'Boundary mode accepts no internal events')
            require(not any(s['op']=='instruction' for s in plan['sites']),'Boundary plan still attaches internal probes')
            execution=[]
        elif mode=='selective':
            contract='runtime-byte-input-v1' if plan.get('runtime_inputs') else 'closed-four-byte-leaf-v1'
            require(plan.get('replay_contract')==contract,'Missing selective replay contract')
            require(events[:7]==root[:7] and events[-3:]==root[-3:],'Instruction evidence outside transform interval')
            execution=events[7:-3]
            selected=set(plan.get('selected_instruction_sites',[]))
            require(selected=={s['id'] for s in plan['sites'] if s['op']=='instruction'},'Selective attachment contract mismatch')
            require(all(e['op']=='instruction' and e['site'] in selected for e in execution),'Unexpected selective evidence')
        else:
            require(events[:7]==root[:7] and events[-3:]==root[-3:],'Instruction evidence outside transform interval')
            execution=events[7:-3]
            require(execution and all(e['op']=='instruction' for e in execution),'Missing leaf execution')
        nodes={};edges=[];reads=[]
        for i in range(3):
            before,after=root[2*i:2*i+2];sid='source:'+str(i+1)
            pointer,data=snapshot(after['values']['value']);_,path=snapshot(before['values']['path'])
            require(len(data)==4,'Source must return four bytes')
            require(all(pointer+4<=s['pointer'] or s['pointer']+4<=pointer for s in reads),'Source regions overlap')
            reads.append({'id':sid,'pointer':pointer,'bytes':data})
            nodes[sid]={'id':sid,'kind':'source','path':path.decode(),'length':4}
        work=root[6];src,src_bytes=snapshot(work['values']['src']);dst,dst_bytes=snapshot(work['values']['dst'])
        require(len(src_bytes)==len(dst_bytes)==4,'Work ABI region length mismatch')
        candidates=[s for s in reads if s['pointer']==src and s['bytes']==src_bytes]
        require(len(candidates)==1,'Work input has no consistent observed read definition')
        require(all(dst+4<=s['pointer'] or s['pointer']+4<=dst for s in reads),'Output overlaps source')
        require(work['registers'][plan['abi']['dst_register']]==dst and work['registers'][plan['abi']['src_register']]==src,'Work ABI registers disagree')
        auxiliary=None
        if 'aux_register' in plan['abi']:
            aux_pointer=work['registers'][plan['abi']['aux_register']]
            matches=[s for s in reads if s['pointer']==aux_pointer]
            require(len(matches)==1 and aux_pointer!=src,'Auxiliary input has no distinct observed read definition')
            auxiliary=matches[0]
        for region in plan.get('runtime_inputs',[]):
            register=region['register'];pointer=work['registers'][register]
            require(all(not s['pointer']<=pointer<s['pointer']+4 for s in reads),'Runtime input aliases an observed source')
            if mode=='full':require(execution[0]['registers'][register]==pointer,'Runtime input argument changed before leaf entry')
        machine=ByteMachine(plan,execution[0] if mode=='full' else work,candidates[0],(dst,dst_bytes),nodes,edges,auxiliary)
        if mode=='boundary':
            while not machine.halted:machine.step()
        elif mode=='selective':
            position=0
            while not machine.halted:
                n=machine.instructions[machine.pc];event=None
                if n.get('site') in selected:
                    require(position<len(execution),'Missing selected instruction event')
                    event=execution[position];position+=1
                machine.step(event)
            require(position==len(execution),'Extra selected instruction events')
        else:
            for e in execution:machine.step(e)
        require(machine.halted and machine.written==set(range(dst,dst+4)),'Missing return or incompletely defined output')
        machine.verify(root[7])
        pointer,data=snapshot(root[8]['values']['value'])
        actual=bytes(machine.memory[dst+i].number for i in range(4))
        require(pointer==dst and data==actual,'JSON input disagrees with replayed stores')
        _,encoded=snapshot(root[9]['values']['json']);output=json.loads(encoded)
        model=plan.get('json_model','string-result-v1')
        if model=='gin-byte-array-v1':
            require(isinstance(output,dict) and set(output)=={'result'} and
                    isinstance(output['result'],list) and all(type(b) is int for b in output['result']) and
                    output['result']==list(actual),'JSON array contradicts observed byte output')
        else:
            require(model=='string-result-v1','Unsupported JSON model')
            require(isinstance(output,dict) and set(output)=={'result'} and isinstance(output['result'],str)
                    and output['result'].encode()==actual,'JSON value contradicts observed byte output')
        byte_sources=[]
        for i in range(4):
            value=machine.memory[dst+i];nid='output-byte:'+str(i)
            nodes[nid]={'id':nid,'kind':'output-byte','byte':i,'value':value.number}
            machine.link([value],nid)
            byte_sources.append({'output_byte':i,'origins':[{'source':s,'byte':j} for s,j in sorted(value.origins)]})
            edges.append({'source':nid,'target':'json:1','kind':'data'})
        nodes['json:1']={'id':'json:1','kind':'json-summary'}
        nodes['output:result']={'id':'output:result','kind':'output-field','value':output['result']}
        edges.append({'source':'json:1','target':'output:result','kind':'data'})
        keep=backward_nodes(edges,['output:result'],{'data'})
        origins=sorted(n for n in keep if nodes[n]['kind']=='source')
        return {'status':'resolved_under_instruction_model','sources':origins,
                'source_versions':machine.source_versions,
                'overwritten_sources':sorted(machine.write_sources-set(origins)),
                'total_writes':machine.write_version,
                'noncontributing_reads':[s['id'] for s in reads if s['id'] not in keep],
                'output':output,'byte_sources':byte_sources,'instruction_steps':machine.steps,'observation_mode':mode,
                'graph':{'nodes':[nodes[n] for n in sorted(keep)],'edges':[e for e in edges if e['kind']=='data' and e['source'] in keep and e['target'] in keep]},
                'scope':('Instruction replay between retained observations; assumes complete declared data inputs, observed runtime control reads, no other external writes/calls; explicit data dependencies only' if mode!='full' else 'Leaf instructions derive byte dependencies; configured read/JSON boundaries; explicit data only; four-byte separate buffers; no transform summary')}
    except MissingObservation as exc:
        return {'status':'unknown','reason':str(exc),'needed_instruction_addresses':[exc.address]}
    except (ValueError,KeyError,TypeError,UnicodeError) as exc:
        return {'status':'unknown','reason':str(exc)}
