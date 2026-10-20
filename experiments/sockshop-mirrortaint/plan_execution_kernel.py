"""Opt-in execution-dependency plan; conservative evidence expansion, no business rules."""
from pathlib import Path
import json
from plan_collection_service import analyze, direct_accessors
from plan_distributed_fields import any_target, augment
from plan_service_observations import callee
from query_observation_planner import require, digest, descriptors


def constructor_writes(method):
    """Exact straight-line this.field = argument constructors; no hidden calls."""
    code=method['instructions']; result={}; stack=[]; slot=1
    args={}
    for index,desc in enumerate(descriptors(method['desc'])):
        args[slot]=index;slot+=2 if desc in ('J','D') else 1
    for ins in code:
        op=ins['op']
        if 21<=op<=25:
            stack.append(('self',) if ins['var']==0 else ('arg',args.get(ins['var'])))
        elif op==183 and callee(ins)=='java/lang/Object.<init>()V':
            require(stack.pop()==('self',),'Constructor super receiver differs')
        elif op==181:
            value,receiver=stack.pop(),stack.pop()
            require(receiver==('self',) and value[0]=='arg' and value[1] is not None,'Non-argument constructor write')
            require(ins['owner']+'.'+ins['name'] not in result,'Repeated constructor assignment')
            result[ins['owner']+'.'+ins['name']]=value[1]
        elif op==177:require(not stack,'Constructor stack differs')
        else:raise ValueError('Necessary constructor effects unsupported: '+method['owner']+'.'+method['name']+method['desc']+'@'+str(ins['index'])+' opcode '+str(op))
    return result


def plan_execution(model, entry, target, response_path, source_calls=None, application_calls=False):
    require(entry in model['methods'],'Execution entry absent')
    target=any_target(model,target); method=model['methods'][entry]
    require(application_calls or not method['exception_handlers'],'Execution v1 root exception handlers not yet modeled')
    supported={0,1,2,3,4,5,6,7,8,16,17,18,87,89,96,100,104,132,167,176,178,180,181,182,183,184,185,187,192,198,199}|set(range(21,26))|set(range(54,59))|set(range(153,167))
    if application_calls:supported|={172,173,174,175,177,191,186,189,190,50,83}
    for ins in method['instructions']:require(ins['op'] in supported,'Execution instruction unsupported: '+str(ins['op']))
    graph,operands,states,steps=analyze(method,allow_loops=True)
    require(response_path.startswith('/'),'Explicit response path required')
    getters,setters=direct_accessors(model)
    # Fields are deliberately expanded in v1. No source is registered merely
    # because it is in this set: concrete boundary and instance evidence remain mandatory.
    fields={i['owner']+'.'+i['name'] for m in model['methods'].values() for i in m['instructions'] if i['op'] in (180,181)}
    fields.add(target)
    calls=set(source_calls or [])
    repos={o for o,c in model['classes'].items() if any(x.startswith('org/springframework/data/') and x.endswith('Repository') for x in c.get('interfaces',[]))}
    for m in model['methods'].values():
        for ins in m['instructions']:
            if ins['op'] in (182,185) and ins['owner'] in repos and ins['name'].startswith('find'):calls.add(callee(ins))
    constructors={}
    for ins in method['instructions']:
        if ins['op']==183 and ins['name']=='<init>':
            key=callee(ins)
            if key=='java/util/ArrayList.<init>()V':constructors[key]={}
            else:
                require(key in model['methods'],'Unknown constructor: '+key)
                initializer=model['methods'].get(ins['owner']+'.<clinit>()V')
                require(initializer is None or all(x['op'] in (0,177) for x in initializer['instructions']),'Necessary constructor class initialization unsupported')
                constructors[key]=constructor_writes(model['methods'][key])
    local={'algorithm':'execution-dependency-v1-loop-pilot','profile':'execution-dependency','entry':entry,'target':target,
           'frame_methods':[entry],'producer_method':None,'writer_method':None,'reduction':{},
           'snapshot_fields':sorted(fields),'mapper_fields':[],'full_snapshot_fields':[],
           'selected_read_sites':[entry+'@'+str(i['index']) for i in method['instructions'] if i['op']==180],
           'model_sha256':digest(model),'contracts':[],
           'collection_method':method,'collection_getters':getters,'collection_setters':setters,
           'collection_selected_calls':[i['index'] for i in method['instructions'] if i['op'] in (182,183,184,185) and i['name']!='<init>']}
    plan=augment(model,local)
    owner=target.rsplit('.',1)[0]
    require(any(p['field']==target for p in plan['json_schema'].get(owner,[])),'Target serialization unsupported')
    graph_schema={o:[{k:p[k] for k in ('field','property','descriptor')} for p in ps] for o,ps in plan['json_schema'].items()}
    # Physical boundary snapshots include verified field accessors even when
    # their names are not JavaBean serialization properties. Wire schema stays
    # separate: this does not assert that these fields appear in JSON.
    for prop in getters.values():
        owner,name=prop['field'].rsplit('.',1);item={'field':prop['field'],'property':name,'descriptor':prop['descriptor']}
        if item not in graph_schema.setdefault(owner,[]):graph_schema[owner].append(item)
    ret=method['desc'].split(')')[1];ret_owner=ret[1:-1] if ret.startswith('L') else ''
    wraps=response_path.startswith('/data/') and not any(p['property']=='data' for p in plan['json_schema'].get(ret_owner,[]))
    plan.update(collection_elements=True,response_graph_schema=graph_schema,
        response_binding={'version':1,'path':response_path,'target':target,'source_fields':sorted(fields),
          'root_prefix':'/data' if wraps else '', 'classification':'execution-dependency',
          'source_calls':sorted(calls),'transparent_calls':sorted(set(getters)|set(setters)),
          'source_arguments':[i for i,d in enumerate(descriptors(method['desc'])) if d!='Lorg/springframework/http/HttpHeaders;'],
          'source_boundary':'Unchanged declared entry / repository read-return / actual RPC-read boundary; output snapshots are never sources.'},
        execution_kernel={'version':1,'constructors':constructors,'step_limit':100000,'static_steps':steps,
          'reachable_instructions':len(states),'evidence_policy':'Conservative all root calls, field reads, tracked writes, constructor results and branches in both modes; no reduction claim.',
          'runtime_profiles':json.loads((Path(__file__).parent/'execution-kernel-runtimes-20261020.json').read_text())['profiles']})
    plan['contracts']+=['CFG reaching definitions iterate to a finite fixed point, including backedges; actual replay is step bounded.',
        'Only exact pinned ArrayList/Arrays$ArrayList and ArrayList$Itr operations are modeled.',
        'Field writes use actual object and observed write version; local list add maps the exact inserted value.',
        'Opaque calls poison related heap state and block certainty; matching values alone never preserve origins.',
        'v1 has no arrays, lambda bodies, general application calls, save or asynchronous protocol support.']
    if application_calls:
        from plan_application_calls import augment_calls
        plan=augment_calls(plan,model,calls)
    return plan
