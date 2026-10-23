"""Conservative target/effect/path closure, with a source-boundary first cut.

Calls, exceptional completion, alias-bearing references and container effects
remain expanded. The first executable reduction removes *value observations*
of irrelevant scalar assignments in exact unplanned constructors, only while
inside a declared read-return boundary. Write versions and mutation guards
remain mandatory. This is not general call/instruction slicing.
"""
from collections import defaultdict
from plan_collection_service import analyze
from plan_service_observations import callee
from query_observation_planner import digest


SCALARS={'Z','B','C','S','I','J','F','D','Ljava/lang/String;'}


def application_value_fields(plan):
    cfg=plan['execution_kernel'];required={plan['target']}
    for m in cfg['methods'].values():
        for ins in m['instructions']:
            if ins['op']==180:required.add(ins['owner']+'.'+ins['name'])
            if ins['op']in (182,183,184,185):
                getter=plan.get('collection_getters',{}).get(callee(ins))
                if getter:required.add(getter['field'])
    for effect in cfg.get('constructors',{}).values():
        fields=effect.get('fields',{})if isinstance(effect,dict)and effect.get('kind')=='assignments'else effect if isinstance(effect,dict)and 'kind'not in effect else {}
        for value in fields.values():
            if isinstance(value,dict)and 'field'in value:required.add(value['field'])
    return required


def application_write_sites(plan,model):
    required=application_value_fields(plan);methods=plan['execution_kernel']['methods'];sites={}
    invoked={callee(i)for m in methods.values()for i in m['instructions']if i['op']in (182,183,184,185)}
    for key,m in model['methods'].items():
        frame=key in methods and m['name']!='<init>'
        setter=key in invoked and key in plan.get('collection_setters',{})and not m['exception_handlers']
        if not(frame or setter):continue
        for ins in m['instructions']:
            if ins['op']!=181 or ins['desc']not in SCALARS:continue
            field=ins['owner']+'.'+ins['name'];owner=model['classes'].get(ins['owner'],{})
            if field in required or owner.get('super')!='java/lang/Object':continue
            declared=[f for f in owner.get('fields',[])if f['name']==ins['name']and f['desc']==ins['desc']and not f['access']&8]
            if len(declared)!=1:continue
            sites[key+'@'+str(ins['index'])]={'field':field,'descriptor':ins['desc'],'method':key,'pc':ins['index'],'kind':'frame'if frame else'setter','field_owner':ins['owner'],'method_owner':m['owner'],'method_sha256':model['classes'][m['owner']]['sha256'],'field_class_sha256':owner['sha256'],'proof':'Scalar value never read by planned bytecode/getter/constructor projection and is not the target. Actual exact receiver class and rooted Frame/call required; retain object, field, version and site, all calls and paths.'}
    return required,sites


def attach_execution_closure(plan,model):
    if plan.get('profile')!='execution-dependency':return plan
    cfg=plan['execution_kernel'];methods=cfg['methods'];needed=defaultdict(set);reasons={};work=[];graphs={}
    needed[plan['target']].add('query target field/version')
    for key,m in methods.items():
        dependencies,_,_,_=analyze(m,allow_loops=True);graphs[key]=dependencies;seeds={}
        for ins in m['instructions']:
            pc=ins['index'];why=[]
            if ins['op']in(180,181):needed[ins['owner']+'.'+ins['name']].add('conservative complete application field obligation')
            if 172<=ins['op']<=177:why.append('return/parameter transfer')
            if ins['op']in(181,83):why.append('possible field/container effect; retain aliases conservatively')
            if ins['op']in(182,183,184,185,186):why.append('call implementation/arguments/effects/exception closure')
            if 153<=ins['op']<=167 or ins['op']in(198,199,191):why.append('actual branch/loop/exception path')
            if why:seeds[pc]=why;work.append((key,pc))
        for h in m['exception_handlers']:seeds.setdefault(h['handler'],[]).append('original exception handler');work.append((key,h['handler']))
        reasons[key]={str(pc):why for pc,why in seeds.items()}
    marked=set()
    while work:
        key,pc=work.pop()
        if(key,pc)in marked:continue
        marked.add((key,pc))
        if pc<0:
            reasons[key].setdefault('formal:'+str(pc),[]).append('receiver/formal parameter definition transferred at actual call')
            continue
        ins=methods[key]['instructions'][pc]
        reasons[key].setdefault(str(pc),[]).append('backward operand/effect/path dependency')
        if ins['op']in(180,181):needed[ins['owner']+'.'+ins['name']].add('required application field read/write')
        if ins['op']in(182,183,184,185):
            call=callee(ins)
            for kind in ('collection_getters','collection_setters'):
                fact=plan.get(kind,{}).get(call)
                if fact:needed[fact['field']].add('accessor identity/version contract')
            # Candidate implementations were expanded by the common call
            # planner. Every callee keeps its return/effect/path obligations.
        work.extend((key,p)for p in graphs[key][pc])
    # Values from constructor summaries can be used without an interpreted
    # frame. Do not prune any field those shared summaries must reconstruct.
    for effect in cfg.get('constructors',{}).values():
        fields=effect.get('fields',{})if isinstance(effect,dict)and effect.get('kind')=='assignments'else effect if isinstance(effect,dict)and 'kind'not in effect else {}
        for f,expression in fields.items():
            needed[f].add('constructor-state summary')
            if isinstance(expression,dict)and 'field'in expression:needed[expression['field']].add('constructor input projection')
    for site in cfg.get('decoder_birth_sites',{}).values():
        for f in site.get('written_fields',[]):needed[f].add('decoder default/source role proof')
    # Native-save ID writes have a separate @mongo-save site, and decoder
    # constructor fields above are retained. Candidate sites below are exact
    # ordinary constructors, never those native proof writes.
    disabled=[]
    sources=plan.get('response_binding',{}).get('source_calls',[])
    candidates={};rejected={}
    if sources and not disabled:
        from plan_execution_kernel import constructor_writes
        for key,m in model['methods'].items():
            if m['name']!='<init>'or key in methods:continue
            try:
                if m['exception_handlers']:continue
                assignments=constructor_writes(m)
            except(ValueError,IndexError,KeyError):continue
            for ins in m['instructions']:
                if ins['op']!=181:continue
                field=ins['owner']+'.'+ins['name'];site=key+'@'+str(ins['index'])
                if field in needed or ins['desc']not in SCALARS:continue
                candidates[site]={'field':field,'descriptor':ins['desc'],'constructor':key,'class_sha256':model['classes'][m['owner']]['sha256'],'proof':'exact argument-assignment constructor outside interpreted methods; scalar field outside target/effect/path closure; only elide within declared source-call extent; versions/guards retained'}
    plan['execution_observation_closure']={'version':1,'enabled':True,'strategy':'source-boundary scalar write-value cut','needed_fields':{k:sorted(v)for k,v in sorted(needed.items())},'retained_instruction_reasons':reasons,'retained_methods':sorted(methods),'marked_instruction_count':sum(pc>=0 for _,pc in marked),'source_calls':sources,'candidate_write_sites':candidates,'disabled_reasons':disabled,'model_sha256':digest(model),'full':'All original value observations; identical version and required semantic checks','selective':'Only certified irrelevant scalar write values inside source boundaries may be omitted; keep all application frames/calls, branches, handlers, container effects, sources and actual write counters','general_execution_slicing_complete':False}
    values,sites=application_write_sites(plan,model)
    plan['execution_observation_closure']['application_write_values']={'version':1,'enabled':True,'required_value_fields':sorted(values),'sites':sites,'record':'write-version retains concrete owner/field/version/site; no value boxing/persistence at certified sites. No event-count, call-deletion or global format-compression claim.'}
    return plan
