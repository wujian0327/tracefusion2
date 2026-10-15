#!/usr/bin/env python3
"""Derive a bounded returned-field observation plan from original application bytecode.

No business field/method lists. Normal acyclic CFG def-use binds writer operands
back to the root; scalar helpers and LambdaMetafactory/Stream contracts supply
summaries. External calls remain opaque, never guessed from equal values.
"""
import argparse
import copy
import json
from pathlib import Path
from query_observation_planner import descriptors, scalar, require, digest, resolve_target


def callee(n):return n['owner']+'.'+n['name']+n['desc']
def field(n):return n['owner']+'.'+n['name']
def children(e):
    if isinstance(e,dict):
        yield e
        for v in e.values():yield from children(v)
    elif isinstance(e,list):
        for v in e:yield from children(v)


def decode(model,key):
    """Finite normal CFG paths; exceptional exits do not produce a field query.

    Calls are immutable def-use nodes, not interprocedural propagation rules.
    Exception handlers are not entered: runtime incomplete/aborted calls are
    explicitly retained as such, never scored as successful field answers.
    """
    m=model['methods'][key];code=m['instructions'];require(code,'Abstract/native method has no decoded body: '+key);args={};slot=0
    if not m['access']&8:args[0]={'op':'receiver'};slot=1
    for i,d in enumerate(descriptors(m['desc'])):
        args[slot]={'op':'argument','index':i};slot+=2 if d in ('J','D') else 1
    work=[(0,[],args,[],[],set())];done=[];steps=0
    while work:
        pc,stack,locals_,calls,writes,visited=work.pop();steps+=1
        require(steps<10000 and len(work)<256,'CFG/path bound exceeded: '+key)
        require(pc not in visited,'Unmodeled loop: '+key)
        visited=visited|{pc};n=code[pc];op=n['op'];site=key+'@'+str(pc)
        def pop():
            require(stack,'Stack underflow: '+site);return stack.pop()
        if op in range(21,26):stack.append(locals_.get(n['var'],{'op':'unknown','reason':'undefined-local'}))
        elif op in range(54,59):locals_[n['var']]=pop()
        elif op==0:pass
        elif op==1:stack.append({'op':'constant','value':None})
        elif 2<=op<=8:stack.append({'op':'constant','value':op-3})
        elif op in (9,10,11,12,13,14,15):stack.append({'op':'constant','value':op-(9 if op<=10 else 11 if op<=13 else 14)})
        elif op in (16,17):stack.append({'op':'constant','value':n['operand']})
        elif op==18:stack.append({'op':'constant','value':n['constant'],'constant_type':n['constant_type']})
        elif op==89:stack.append(stack[-1])
        elif op==87:pop()
        elif op==187:stack.append({'op':'allocation','site':site,'owner':n['type']})
        elif op==189:
            pop();stack.append({'op':'unknown','reason':'unmodeled-array'})
        elif op==192:pass
        elif op==178:stack.append({'op':'unknown','reason':'static:'+field(n)})
        elif op==180:stack.append({'op':'field','field':field(n),'descriptor':n['desc'],'receiver':pop(),'site':site})
        elif op==181:
            value=pop();owner=pop();writes.append({'site':site,'field':field(n),'receiver':owner,'value':value})
        elif op in (96,97,98,99,100,101,102,103,104,105,106,107,108,109,110,111):
            right,left=pop(),pop();stack.append({'op':'binary','opcode':op,'args':[left,right]})
        elif 133<=op<=147:stack.append({'op':'convert','opcode':op,'arg':pop()})
        elif op in (182,183,184,185):
            params=[pop() for _ in descriptors(n['desc'])][::-1];receiver=None if op==184 else pop()
            e={'op':'call','site':site,'callee':callee(n),'args':params,'receiver':receiver,'opcode':op};calls.append(e)
            if n['desc'].split(')')[1]!='V':stack.append(e)
        elif op==186:
            captures=[pop() for _ in descriptors(n['desc'])][::-1]
            stack.append({'op':'lambda','bootstrap':n['bootstrap'],'bootstrap_args':n['bootstrap_args'],'captures':captures,'site':site})
        elif 153<=op<=166 or op in (198,199):
            pop()
            if 159<=op<=166:pop()
            require(n['target']>pc,'Unmodeled back branch')
            for dest in (pc+1,n['target']):work.append((dest,list(stack),dict(locals_),list(calls),list(writes),set(visited)))
            continue
        elif op==167:
            require(n['target']>pc,'Unmodeled back edge');work.append((n['target'],stack,locals_,calls,writes,visited));continue
        elif 172<=op<=177:
            result=None if op==177 else pop();require(not stack,'Nonempty return stack')
            done.append({'result':result,'calls':calls,'writes':writes});continue
        elif op==191:continue
        else:raise ValueError('Unmodeled opcode '+str(op)+' in '+key)
        work.append((pc+1,stack,locals_,calls,writes,visited))
    return done


def substitute(e,args,receiver):
    if isinstance(e,list):return [substitute(v,args,receiver) for v in e]
    if not isinstance(e,dict):return e
    if e.get('op')=='argument':return args[e['index']]
    if e.get('op')=='receiver':return receiver
    return {k:substitute(v,args,receiver) for k,v in e.items()}


class Summaries:
    def __init__(self,model):self.model=model;self.methods=set();self.reads={};self.reductions=[]
    def method(self,key,trail=()):
        require(key not in trail and len(trail)<12,'Recursive scalar summary')
        self.methods.add(key);paths=decode(self.model,key)
        require(paths and all(p['result'] is not None for p in paths),'Scalar helper has no result')
        require(not any(p['writes'] for p in paths),'Scalar helper mutates heap')
        # Calls may affect fields even when their return is unused. Only getters,
        # modeled streams and admitted inlined scalar helpers are accepted.
        results=[]
        for p in paths:
            for c in p['calls']:self.expression(c,trail+(key,))
            results.append(self.expression(p['result'],trail+(key,)))
        require(all(e==results[0] for e in results),'Branch-dependent scalar helper needs path-partition planner')
        return results[0]
    def expression(self,e,trail):
        op=e['op']
        if op in ('argument','receiver','constant'):return e
        if op=='field':
            require(scalar(e['descriptor']),'Unmodeled reference field in scalar summary')
            r=self.expression(e['receiver'],trail);require(r['op'] in ('argument','receiver'),'Nested heap source')
            self.reads[e['site']]=e
            return dict(e,receiver=r)
        if op=='convert':return dict(e,arg=self.expression(e['arg'],trail))
        if op=='binary':return dict(e,args=[self.expression(v,trail) for v in e['args']])
        if op=='lambda':
            require(e['bootstrap']=='java/lang/invoke/LambdaMetafactory.metafactory' and not e['captures'],'Only capture-free LambdaMetafactory supported')
            handles=[a for a in e['bootstrap_args'] if isinstance(a,dict)]
            require(len(handles)==1 and handles[0]['tag']==6,'Exact static lambda handle required')
            return {'op':'mapper','method':handles[0]['handle']}
        require(op=='call','Opaque expression in scalar summary: '+str(e))
        key=e['callee']
        if key in ('java/util/List.stream()Ljava/util/stream/Stream;','java/util/Collection.stream()Ljava/util/stream/Stream;'):
            r=e['receiver'];require(r['op']=='argument','Stream must originate at a declared input boundary')
            return {'op':'stream','input_argument':r['index']}
        if key=='java/util/stream/Stream.mapToDouble(Ljava/util/function/ToDoubleFunction;)Ljava/util/stream/DoubleStream;':
            r=self.expression(e['receiver'],trail);mapper=self.expression(e['args'][0],trail)
            require(r['op']=='stream' and mapper['op']=='mapper','Unsupported stream pipeline')
            return {'op':'mapped-stream','input_argument':r['input_argument'],'mapper_method':mapper['method']}
        if key=='java/util/stream/DoubleStream.sum()D':
            r=self.expression(e['receiver'],trail);require(r['op']=='mapped-stream','Unsupported reduction input')
            mapper=self.method(r['mapper_method'],trail)
            item={'op':'sum','site':e['site'],'input_argument':r['input_argument'],'mapper_method':r['mapper_method'],'mapper_expression':mapper}
            if item not in self.reductions:self.reductions.append(item)
            return item
        require(key in self.model['methods'],'Missing external scalar/effect model: '+key)
        m=self.model['methods'][key]
        require(e['opcode'] in (183,184) or self.model['classes'][m['owner']]['access']&16 or m['access']&(2|16)
                or self.is_getter(key),'Unresolved virtual scalar dispatch: '+key)
        result=self.method(key,trail)
        return substitute(result,[self.expression(v,trail) for v in e['args']],
                          self.expression(e['receiver'],trail) if e['receiver'] is not None else None)
    def is_getter(self,key):
        m=self.model['methods'][key];ops=[n['op'] for n in m['instructions']]
        return len(ops)==3 and ops[0]==25 and ops[1]==180 and 172<=ops[2]<=176


def plan_service(model,entry,target):
    require(entry in model['methods'],'Entry is absent')
    target=resolve_target(model,target);root_paths=decode(model,entry);root_calls={c['site']:c for p in root_paths for c in p['calls']}
    bindings=[]
    for c in root_calls.values():
        if c['callee'] not in model['methods']:continue
        try:paths=decode(model,c['callee'])
        except ValueError:continue
        ws=[w for p in paths for w in p['writes'] if w['field']==target]
        if not ws:continue
        require(len({digest(w) for w in ws})==1,'Path-dependent target write needs stronger planner')
        w=ws[0];require(w['receiver']=={'op':'receiver'} and w['value']['op']=='argument','Target write must copy a declared writer parameter')
        bindings.append((c,w,c['args'][w['value']['index']]))
    if not bindings:return plan_identity_return(model,entry,target,root_paths)
    require(len(bindings)==1,'Need one statically bound target writer in entry; found '+str(len(bindings)))
    writer,write,operand=bindings[0]
    require(operand['op']=='call' and operand['callee'] in model['methods'],'Target operand needs modeled application scalar producer')
    # Reject path-dependent reaching definitions even if one path overwrote the
    # dictionary above: each occurrence must bind the same target operand.
    for p in root_paths:
        for c in p['calls']:
            if c['site']==writer['site']:require(c['args'][write['value']['index']]==operand,'Path-dependent writer operand')
    summaries=Summaries(model);expression=summaries.method(operand['callee'])
    require(model['methods'][operand['callee']]['desc'].endswith(')F'),'Service profile currently requires a float producer')
    require(len(summaries.reductions)==1,'This service profile requires exactly one sequential mapped reduction')
    reduction=summaries.reductions[0]
    def validate_outer(e):
        if e['op']=='sum':return
        require(e['op'] in ('constant','binary','convert'),'Extra producer input/effect requires an explicit model')
        for arg in e.get('args',[]):validate_outer(arg)
        if 'arg' in e:validate_outer(e['arg'])
    validate_outer(expression)
    mapper_fields=sorted({n['field'] for n in children(reduction['mapper_expression']) if n.get('op')=='field'})
    require(mapper_fields,'Reduction mapper has no field sources')
    # Exact mapper DTO runtime type and read-only epoch are checked in recorder.
    mapper=model['methods'][reduction['mapper_method']]
    require(mapper['access']&8 and len(descriptors(mapper['desc']))==1 and mapper['desc'].endswith(')D'),'Only one-argument static double mapper supported')
    require(all(n['receiver']=={'op':'argument','index':0} for n in children(reduction['mapper_expression']) if n.get('op')=='field'),
            'Mapper fields must belong to the concrete member argument')
    frames=sorted({entry,operand['callee'],reduction['mapper_method'],writer['callee']})
    all_fields=sorted({owner+'.'+f['name'] for owner,c in model['classes'].items() for f in c['fields'] if not f['access']&8})
    return {'algorithm':'returned-field-service-plan-v1','profile':'mapped-reduction','entry':entry,'target':target,'target_descriptor':
        next(f['desc'] for f in model['classes'][target.rsplit('.',1)[0]]['fields'] if f['name']==target.rsplit('.',1)[1]),
        'model_sha256':digest(model),'class_sha256':{o:c['sha256'] for o,c in model['classes'].items()},
        'writer_method':writer['callee'],'writer_site':writer['site'],'write_site':write['site'],'writer_parameter':write['value']['index'],
        'producer_method':operand['callee'],'producer_callsite':operand['site'],'expression':expression,'reduction':reduction,
        'mapper_fields':mapper_fields,'mapper_owner':descriptors(mapper['desc'])[0][1:-1],
        'frame_methods':frames,'summary_methods':sorted(summaries.methods),
        'field_read_sites':list(summaries.reads),'snapshot_fields':mapper_fields+[target],
        'full_snapshot_fields':all_fields,
        'contracts':['Query boundary: actual collection/DTO object field versions at scalar producer entry, not HTTP/DB origin.',
                     'Normal acyclic entry def-use, one writer and one scalar producer per completed root; rejected/exceptional roots produce no target.',
                     'Exact unmodified class hashes; one sequential List/Collection.stream-mapToDouble-sum, capture-free static lambda.',
                     'Collection members thread-owned; source fields read-only between producer entry and return; application writes version-counted.',
                     'Runtime callbacks must exactly match ordered collection membership; empty and duplicate members retained.',
                     'Writer invocation is tied to producer call site by decoded def-use, never by equality of scalar values.',
                     'Returned object must be the written target with the same final field version; repository replacement/reflective mutation unsupported.',
                     'Opaque framework calls outside the selected scalar slice are boundaries, not analyzed propagation.']}


def plan_identity_return(model,entry,target,paths):
    """A separate reusable contract: return an unmodified input DTO instance.

    Inspect all return/load and store instructions, including exception handlers,
    rather than assuming that a library failure follows the normal path.
    """
    m=model['methods'][entry];code=m['instructions'];require(paths,'No completed root path')
    result=paths[0]['result'];require(result and result['op']=='argument' and all(p['result']==result for p in paths),'Target has neither a modeled write nor an identity return')
    index=result['index'];args=descriptors(m['desc']);owner=target.rsplit('.',1)[0]
    require(args[index]=='L'+owner+';','Identity-return argument type differs from target')
    slot=(0 if m['access']&8 else 1)+sum(2 if d in ('J','D') else 1 for d in args[:index])
    require(not any(n['op'] in range(54,59) and n['var']==slot for n in code),'Returned argument slot is overwritten')
    for i,n in enumerate(code):
        if 172<=n['op']<=177:require(n['op']==176 and i>0 and code[i-1]=={'index':i-1,'op':25,'var':slot},'All normal/handled returns must directly load the same argument')
        require(n['op'] not in (181,179,186),'Identity-return body has writes or dynamic effects')
        if n['op'] in (182,183,184,185):
            require(callee(n) in {'java/io/PrintStream.println(Ljava/lang/String;)V',
                'org/springframework/amqp/rabbit/core/RabbitTemplate.convertAndSend(Ljava/lang/String;Ljava/lang/Object;)V'},
                'Missing read-only argument-effect contract: '+callee(n))
    all_fields=sorted({o+'.'+f['name'] for o,c in model['classes'].items() for f in c['fields'] if not f['access']&8})
    return {'algorithm':'returned-field-service-plan-v1','profile':'identity-return','entry':entry,'target':target,
        'input_argument':index,'input_owner':owner,'model_sha256':digest(model),
        'class_sha256':{o:c['sha256'] for o,c in model['classes'].items()},'frame_methods':[entry],
        'snapshot_fields':[target],'mapper_fields':[target],'full_snapshot_fields':all_fields,
        'producer_method':None,'writer_method':None,'reduction':{},'summary_methods':[],
        'contracts':['Query boundary is the concrete root input object field version, not the HTTP sender field or AMQP consumer.',
                     'Every return, including handled failures, directly returns the unchanged input argument slot.',
                     'PrintStream.println and RabbitTemplate.convertAndSend have declared read-only DTO-argument effects; no general external effect inference.',
                     'Exact concrete runtime DTO class; application bytecode writes version-counted and forbidden during active input epoch.',
                     'Input/output object identity, field version and observed String identity/value must remain equal; reflective/native writes outside this model are unsupported.']}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--model',type=Path,required=True);p.add_argument('--entry',required=True)
    p.add_argument('--target',required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    a.out.write_text(json.dumps(plan_service(json.loads(a.model.read_text()),a.entry,a.target),indent=2)+'\n')
