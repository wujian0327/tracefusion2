"""Explicit JSON target binding and profile dispatch, independent of business names.

Runtime return/serialization witnesses never serve as source boundaries. Opaque
objects may be observed but their fields cannot become certain by equal values.
"""
from plan_collection_service import analyze, direct_accessors, plan_collection
from plan_distributed_fields import any_target, augment
from plan_service_observations import callee, plan_service
from plan_distributed_fields import copy_plan
from query_observation_planner import digest, require, scalar, descriptors


def pure_constructor(method):
    if method['name']!='<init>': return False
    for ins in method['instructions']:
        if ins['op'] in (182,183,184,185):
            if not (ins['op']==183 and ins['owner']=='java/lang/Object' and ins['name']=='<init>'):return False
        elif ins['op'] not in set(range(21,26))|{0,1,177,181}:return False
    return True


def plan_response(model, entry, target, response_path, source_calls=None, read_forward_contracts=False, execution_kernel=False):
    if execution_kernel:
        from plan_execution_kernel import plan_execution
        return plan_execution(model, entry, target, response_path, source_calls)
    require(entry in model['methods'],'Entry method absent: '+entry)
    target=any_target(model,target);owner,name=target.rsplit('.',1)
    row=next(f for f in model['classes'][owner]['fields'] if f['name']==name)
    require(row['desc'] not in ('Ljava/util/Date;','Ljava/util/UUID;'),
            'Target type unsupported by response binding: '+row['desc'])
    require(response_path.startswith('/') and '//' not in response_path,'Explicit nonempty response JSON path required')
    root=model['methods'][entry]
    # Validate every root instruction, including effects/exception edges. Nothing
    # outside the apparent value slice is silently ignored in this revision.
    graph,operands,states,steps=analyze(root)
    require(any(i['op']==176 for i in root['instructions']),'Response entry must return an object')
    getters,setters=direct_accessors(model)
    direct_writers=[i for i in root['instructions'] if i['op'] in (182,183,185) and
                    callee(i) in setters and setters[callee(i)]['field']==target]
    ctor_writers=[i for i in root['instructions'] if i['op']==183 and callee(i) in model['methods'] and
                  any(x['op']==181 and x['owner']+'.'+x['name']==target for x in model['methods'][callee(i)]['instructions'])]
    if direct_writers:
        kind='local-container' if row['desc']=='Ljava/util/Map;' else 'local-scalar'
        require(kind=='local-container' or scalar(row['desc']),'Local target type unsupported: '+row['desc'])
        local=plan_collection(model,entry,target,scalar_target=kind=='local-scalar')
    elif ctor_writers:
        # This route is a statically identified constructor assignment. Do not
        # use a sequence of failed planners to discover the output category.
        paths=__import__('plan_service_observations').decode(model,entry)
        candidates=[c for p in paths for c in p['calls'] if c['callee'] in {callee(i) for i in ctor_writers}]
        # Existing mapped reduction owns numeric computed constructor targets;
        # reference/constant forwarding uses the explicit copy analyzer.
        if row['desc'] in ('F','D'):
            kind='mapped-reduction';local=plan_service(model,entry,target)
        else:
            kind='constructor-copy';local=copy_plan(model,entry,target)
    else:
        kind='returned-object-forward'
        local={'algorithm':'response-identity-evidence-v1','profile':'response-forward','entry':entry,'target':target,
               'frame_methods':[entry],'producer_method':None,'writer_method':None,'reduction':{},
               'snapshot_fields':[target],'mapper_fields':[],'full_snapshot_fields':[],
               'selected_read_sites':[],'model_sha256':digest(model),'contracts':[]}
    plan=augment(model,local)
    require(any(p['field']==target for p in plan['json_schema'].get(owner,[])),
            'Target serialization schema unsupported or custom: '+target)
    graph_schema={}
    for key,prop in getters.items():
        own,field=prop['field'].rsplit('.',1)
        value={'field':prop['field'],'property':field,'descriptor':prop['descriptor']}
        if value not in graph_schema.setdefault(own,[]):graph_schema[own].append(value)
    for own,props in plan['json_schema'].items():
        for prop in props:
            value={k:prop[k] for k in ('field','property','descriptor')}
            if value not in graph_schema.setdefault(own,[]):graph_schema[own].append(value)
    repository_owners={o for o,c in model['classes'].items() if any(
        i.startswith('org/springframework/data/') and i.endswith('Repository') for i in c.get('interfaces',[]))}
    calls=set(source_calls or [])
    for m in model['methods'].values():
        for ins in m['instructions']:
            if ins['op'] in (182,185) and ins['owner'] in repository_owners and ins['name'].startswith('find'):
                calls.add(callee(ins))
    transparent=set(getters)|set(setters)
    transparent.update(k for k,m in model['methods'].items() if pure_constructor(m))
    library={
        'org/springframework/http/HttpEntity.getBody()Ljava/lang/Object;',
        'org/springframework/http/ResponseEntity.getBody()Ljava/lang/Object;',
        'org/springframework/hateoas/Resource.getContent()Ljava/lang/Object;',
        'java/util/Collections.singletonList(Ljava/lang/Object;)Ljava/util/List;',
        'java/util/Collections.emptyList()Ljava/util/List;',
        'org/springframework/amqp/rabbit/core/RabbitTemplate.convertAndSend(Ljava/lang/String;Ljava/lang/Object;)V'}
    for own in ('java/util/List','java/util/Collection','java/util/ArrayList'):
        for suffix in ('isEmpty()Z','size()I','get(I)Ljava/lang/Object;','indexOf(Ljava/lang/Object;)I'):
            library.add(own+'.'+suffix)
    transparent.update(library)
    for ins in root['instructions']:
        if ins['op']==183 and ins['name']=='<init>' and ins['owner']==owner:
            require(callee(ins) in transparent,'Unmodeled target constructor effects')
    needed={target}
    for rule in plan.get('copy_rules',[]):
        if rule['source']['kind']=='field-read':needed.add(rule['source']['field'])
    for pc in plan.get('collection_selected_calls',[]):
        ins=root['instructions'][pc]
        if callee(ins) in getters:needed.add(getters[callee(ins)]['field'])
    ret=root['desc'].split(')')[1]
    ret_owner=ret[1:-1] if ret.startswith('L') else ''
    wraps_data=response_path.startswith('/data/') and not any(p['property']=='data' for p in plan['json_schema'].get(ret_owner,[]))
    plan.update(response_binding={'version':1,'path':response_path,'target':target,'source_fields':sorted(needed),
                    'root_prefix':'/data' if wraps_data else '',
                    'classification':kind,'root_return_descriptor':root['desc'].split(')')[1],
                    'source_calls':sorted(calls),'transparent_calls':sorted(transparent),
                    'source_arguments':[i for i,d in enumerate(descriptors(root['desc'])) if d!='Lorg/springframework/http/HttpHeaders;'],
                    'source_boundary':'Original declared entry inputs, Spring Data read-return fields and actual RPC read fields; never root-return/output snapshots',
                    'root_instruction_validation_steps':steps},
                response_graph_schema=graph_schema,collection_elements=True)
    plan['snapshot_fields']=sorted(set(plan['snapshot_fields'])|{p['field'] for ps in graph_schema.values() for p in ps})
    plan['contracts']+=['Actual root return and serialized target must share owner/field/version and request context.',
        'Read-return source calls are an explicit Spring Data boundary contract, not database history reconstruction.',
        'Opaque call results/effects touching the target remain unknown; no equal-value origin selection.',
        'No general loops, invokedynamic, reference array creation, reflective/native or shared mutable source support.']
    if read_forward_contracts and plan['profile']=='response-forward':
        from plan_read_effects import read_effects
        plan['read_forward_contracts']=read_effects(model)
        plan['planning_caveats']={'unresolved_necessary_calls':sorted({callee(i) for i in root['instructions']
            if i['op'] in (182,183,184,185) and i['name']!='<init>' and callee(i) not in calls|transparent
            and callee(i) not in plan['read_forward_contracts']['composed_methods']}),
            'runtime_conditions':plan['read_forward_contracts']['contracts'],
            'root_effects_including_constructors_proved':entry in plan['read_forward_contracts']['composed_methods'],
            'meaning':'Accepted target binding; end-to-end answer remains conditional on required sources and call effects.'}
    return plan
