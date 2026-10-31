"""Declared source sites can be observed without interpreting their callers."""
from plan_service_observations import callee


def attach(plan, model):
    declared=set(plan.get('response_binding',{}).get('source_calls',[]))
    interpreted=set(plan.get('execution_kernel',{}).get('methods',{}))|set(plan.get('frame_methods',[]))
    sites={}; unsupported=[]
    for key, method in model['methods'].items():
        if key in interpreted:continue
        for ins in method['instructions']:
            if ins['op'] not in (182,183,184,185) or callee(ins) not in declared:continue
            site=key+'@'+str(ins['index'])
            if method.get('name','').startswith('<') or '.<' in key:
                unsupported.append({'site':site,'reason':'Uninitialized/initializer observation context unsupported'});continue
            sites[site]={'caller':key,'pc':ins['index'],'callee':callee(ins),
                         'caller_class_sha256':model['classes'][key.split('.')[0]]['sha256']}
    if sites:
        plan['response_binding']['source_occurrence_protocol']=2
        plan['source_observation']={'version':1,'methods':sorted({s['caller']for s in sites.values()}),
            'sites':sites,'unsupported':unsupported,'scope':'Invocation facts only. Opaque callers/effects remain uninterpreted.'}
    return plan
