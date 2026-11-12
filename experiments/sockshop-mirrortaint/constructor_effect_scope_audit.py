"""Executable review, not an authorization consumed by the reconstruction core.

A static local candidate is deliberately distinct from a runtime certificate.
There is no active native-effect contract in this revision.
"""
from call_write_effects import WriteEffects
from query_observation_planner import descriptors
from plan_service_observations import callee
from plan_collection_service import analyze


def summarize(model,key):
    methods=model['methods'];classes=model['classes'];seen=set();todo=[key]
    calls=[];writes=[];references=[];globals_=[];open_=[];initializers=[]
    effects=WriteEffects(methods,lambda m,p:(),())
    while todo:
        name=todo.pop()
        if name in seen:continue
        seen.add(name)
        method=methods.get(name)
        if method is None:open_.append({'method':name,'reason':'bytecode absent'});continue
        cls=classes.get(method['owner'])
        if cls is None:open_.append({'method':name,'reason':'declaring class metadata absent'})
        else:
            initializer=methods.get(method['owner']+'.<clinit>()V')
            if initializer and any(i['op']not in(0,177)for i in initializer['instructions']):initializers.append(method['owner'])
        if not method['instructions']:
            open_.append({'method':name,'reason':'native/abstract/no bytecode'});continue
        try:
            operands=analyze(method,allow_loops=True)[1]
        except ValueError as e:
            open_.append({'method':name,'reason':'static input analysis: '+str(e)});operands={}
        for i,ins in enumerate(method['instructions']):
            if ins['op']==181:
                writes.append({'method':name,'pc':i,'field':ins['owner']+'.'+ins['name'],'descriptor':ins['desc']})
                if ins['desc'].startswith(('L','[')):
                    references.append({'method':name,'pc':i,'field':ins['owner']+'.'+ins['name'],'value_definitions':sorted(operands.get(i,[[],[]])[0]),'receiver_definitions':sorted(operands.get(i,[[],[]])[1]),'external_alias_must_remain_reachable':True})
            elif ins['op']==179:globals_.append({'method':name,'pc':i,'field':ins['owner']+'.'+ins['name']})
            elif ins['op']in(79,80,81,82,83,84,85,86,186):open_.append({'method':name,'pc':i,'reason':'array/global/bootstrap effect needs its own contract'})
            elif ins['op']in(182,183,184,185):
                called=callee(ins);calls.append({'caller':name,'pc':i,'callee':called,'opcode':ins['op']})
                if ins['op']==183 and ins['name']=='<init>':todo.append(called)
                else:open_.append({'method':name,'pc':i,'reason':'dispatch/callback/native effect not certified','callee':called})
    paths=[]
    try:
        field_paths,opaque=effects.summary(key)
        paths=[{'root':'this'if p.root==-1 else'argument:'+str(p.root),'fields':[list(x)for x in p.fields]}for p in sorted(field_paths,key=lambda p:(p.root,p.fields))]
        open_.extend({'method':x,'reason':'unclosed transitive effect'}for x in sorted(opaque))
    except (ValueError,KeyError)as e:open_.append({'method':key,'reason':'write addresses: '+str(e)})
    external=[p for p in paths if p['root']!='this'or len(p['fields'])!=1]
    return {'kind':'constructor-effect-review-v1','constructor':key,'class_sha256':{o:classes[o]['sha256']for o in sorted({methods[k]['owner']for k in seen if k in methods})if o in classes},'write_addresses':paths,'write_sites':writes,'parameter_or_nested_writes':external,'reference_stores':references,'global_stores':globals_,'calls':calls,'unclosed':open_,'initialization_obligations':sorted(set(initializers)),'static_local_candidate':not(open_ or external or globals_ or initializers),'runtime_license':False,'runtime_blockers':['No new constructor-effect witness protocol is active','Actual allocation/dispatch/class-init/native effect/write-version/completion facts must be verified before certification'],'core_consumes_this_review':False}
