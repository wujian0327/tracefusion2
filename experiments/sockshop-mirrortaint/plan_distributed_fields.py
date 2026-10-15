#!/usr/bin/env python3
"""Default-property schemas and generic field-copy bindings; no business answers."""
from plan_service_observations import decode,callee,field
from query_observation_planner import require,digest


def json_schema(model):
    schema={};rejected=[]
    for owner,c in model['classes'].items():
        props=[]
        for f in c['fields']:
            if f['access']&8:continue
            key=owner+'.'+f['name'];getter=None
            for k,m in model['methods'].items():
                if m['owner']!=owner or m['access']&8 or m['desc']!='()'+f['desc']:continue
                code=m['instructions']
                if len(code)==3 and [v['op'] for v in code[:2]]==[25,180] and code[0]['var']==0 and field(code[1])==key and 172<=code[2]['op']<=176:
                    prefix='is' if m['name'].startswith('is') and f['desc']=='Z' else 'get'
                    if not m['name'].startswith(prefix):continue
                    suffix=m['name'][len(prefix):]
                    prop=suffix if len(suffix)>1 and suffix[:2].isupper() else suffix[:1].lower()+suffix[1:]
                    if prop==f['name']:getter=k;break
            if getter is None and not f['access']&1:continue
            annotations=c.get('annotations',[])+f.get('annotations',[])+(model['methods'][getter].get('annotations',[]) if getter else [])
            custom=[a for a in annotations if a.startswith('Lcom/fasterxml/jackson/') and a!='Lcom/fasterxml/jackson/annotation/JsonIgnoreProperties;']
            if custom:rejected.append({'field':key,'annotations':custom});continue
            props.append({'property':f['name'],'field':key,'descriptor':f['desc'],'getter':getter})
        if props:schema[owner]=props
    return schema,rejected


def any_target(model,target):
    owner,name=target.rsplit('.',1);found=[]
    for o,c in model['classes'].items():
        canonical=o.replace('/','.').replace('$','.')
        if o!=owner and canonical!=owner and not canonical.endswith('.'+owner):continue
        for f in c['fields']:
            if f['name']==name and not f['access']&8:found.append(o+'.'+name)
    require(len(found)==1,'Absent/ambiguous field: '+target);return found[0]


def copy_plan(model,entry,target):
    target=any_target(model,target);rules=[];frames={entry};schema,_=json_schema(model)
    getters={p['getter']:p for ps in schema.values() for p in ps if p['getter']}
    for path in decode(model,entry):
        for c in path['calls']:
            if c['callee'] not in model['methods']:continue
            try:paths=decode(model,c['callee'])
            except ValueError:continue
            for p in paths:
                for w in p['writes']:
                    if w['field']!=target:continue
                    require(w['receiver']=={'op':'receiver'} and w['value']['op']=='argument','Non-parameter field write needs stronger model')
                    operand=c['args'][w['value']['index']]
                    if operand['op']=='call' and operand['callee'] in getters:
                        g=getters[operand['callee']]
                        require(not operand['args'],'Parameterized getter is unsupported')
                        source={'kind':'field-read','site':operand['callee']+'@1','field':g['field']}
                    elif operand['op']=='argument':source={'kind':'argument','index':operand['index']}
                    elif operand['op']=='constant':source={'kind':'constant','value':operand['value']}
                    else:raise ValueError('Unmodeled field-copy operand')
                    rule={'callsite':c['site'],'writer':c['callee'],'write_site':w['site'],'field':target,'parameter':w['value']['index'],'source':source}
                    if rule not in rules:rules.append(rule)
                    frames.add(c['callee'])
    require(rules,'No automatic field-copy binding')
    return {'algorithm':'bytecode-copy-to-field-v1','profile':'field-copy','entry':entry,'target':target,'frame_methods':sorted(frames),
            'binding_callsites':sorted({r['callsite'] for r in rules}),'copy_rules':rules,'writer_method':None,'producer_method':None,'reduction':{},
            'selected_read_sites':sorted({r['source']['site'] for r in rules if r['source']['kind']=='field-read'}),
            'model_sha256':digest(model),'class_sha256':{o:c['sha256'] for o,c in model['classes'].items()},
            'snapshot_fields':[target],'mapper_fields':[], 'full_snapshot_fields':[],
            'contracts':['Acyclic decoded root; field write copies constructor/method argument directly.',
                         'Caller argument is a direct pure-getter return or root argument; no value-based matching.',
                         'Actual read and target-write instances, parameter identity and static caller site must agree.',
                         'Additional origins in repository/JSON internals are outside the local copy summary.']}


def augment(model,plan=None):
    schema,rejected=json_schema(model)
    if plan is None:plan={'profile':'transport-boundary','entry':None,'frame_methods':[],'producer_method':None,'writer_method':None,'reduction':{},'snapshot_fields':[],'full_snapshot_fields':[],'contracts':[]}
    plan=dict(plan);fields=sorted({p['field'] for ps in schema.values() for p in ps})
    plan.update(class_sha256={o:c['sha256'] for o,c in model['classes'].items()},json_schema=schema,json_rejected_properties=rejected)
    plan['snapshot_fields']=sorted(set(plan['snapshot_fields'])|set(fields));plan['full_snapshot_fields']=fields
    plan['transport_contracts']=['Default Jackson properties backed by verified direct getters/public fields; custom property serializers/mixins/naming strategies excluded.',
        'Nested known DTOs and ordered collections; unknown object shapes are not assigned fabricated origins.',
        'W3C trace-id plus concrete request span-id from traceparent, direction and JSON pointer identify a cross-process field edge; no custom response echo; values only validate it.',
        'Within a process, only the same observed object/declared field/version may be forwarded without a bytecode dependency edge.',
        'All relevant bytecode writes must be in supplied classes; arbitrary reflective/native writes and concurrent mutable DTO sharing excluded.',
        'Transport observation is a common framework model, currently observing admitted DTO properties rather than minimal per-target transport points.']
    return plan
