"""Pre-execution structural routing; never reads runtime answers or baseline labels."""
from plan_response_binding import plan_response
from plan_async_dependencies import attach_async_dependencies
from query_observation_planner import require
CONVERSION='edu/fudan/common/util/JsonUtils.conveterObject(Ljava/lang/Object;Ljava/lang/Class;)Ljava/lang/Object;'

def specialize_transport(plan, *, scope=True, fields=True):
    """Project evidence only after a query's return is bound.

    Application execution/effect closure is unchanged. Request-serialization
    proofs are consumed only on outbound requests; target serialization has
    its own mapper/path and before/after object checks, in both policies.
    The two options permit separate observation ablations, not answer routing.
    """
    if plan.get('response_binding'):
        plan['transport_evidence_policy']={'version':2,
            'request_proofs_outbound_only':bool(scope),
            'project_bound_response_fields':bool(fields),
            'response_path':plan['response_binding']['path'],
            'conditions':'Both modes share optional outbound-only request-proof cleanup on actual bound server responses. Field persistence projection is selective-only. Retain target serializer and complete pre/post snapshot checks, outbound request proofs and all application evidence.'}
    return plan

def choose(model,query):
    args=(model,query['entry'],query['target'],query['path']);failures={};legacy=kernel=None
    try:legacy=plan_response(*args,read_forward_contracts=True)
    except ValueError as error:failures['legacy']=str(error)
    try:kernel=plan_response(*args,execution_kernel=True,application_calls=True)
    except ValueError as error:failures['execution']=str(error)
    shape=[]
    if kernel:
        for m in kernel['execution_kernel']['methods'].values():
            for i in m['instructions']:
                if i['op'] in (50,83,132,186,189):shape.append('array-loop-or-lambda')
                if i['op'] in (182,183,184,185) and i.get('owner','').startswith('org/springframework/http/RequestEntity'):shape.append('request-entity-effects')
                if i['op'] in (182,183,184,185) and (i.get('desc','').endswith('Ljava/util/concurrent/Future;') or i.get('name')=='save' and i.get('desc')=='(Ljava/lang/Object;)Ljava/lang/Object;'):shape.append('task-or-save-effects')
                if 'target' in i and i['target']<=i['index']:shape.append('control-flow-backedge')
    if legacy and legacy['profile']!='response-forward':plan=legacy;reason='Existing specialized scalar/copy proof has priority'
    elif kernel and (not legacy or shape or query['entry'] not in legacy.get('read_forward_contracts',{}).get('composed_methods',{})):plan=kernel;reason='Execution semantics for structural effects or unavailable root composition'
    elif legacy:plan=legacy;reason='Existing finite return-forward contract'
    elif kernel:plan=kernel;reason='Execution fallback with supported semantics'
    else:raise ValueError('No supported static plan: '+str(failures))
    features=set()
    if plan['profile']=='execution-dependency':
        from contract_obligations import features as api_obligations
        features=api_obligations(plan,model)
        if features:plan=attach_async_dependencies(plan,features,model.get('library_inventory'))
        plan['contract_applicability']={'version':1,'features':sorted(features),'selection':'Actual planned APIs; library implementation/hash and runtime preconditions remain mandatory. Save is not a task or decoder contract.'}
    if CONVERSION in model['methods'] and any(i['op']in (182,183,184,185)and i.get('owner','')+'.'+i.get('name','')+i.get('desc','')==CONVERSION for m in plan.get('execution_kernel',{}).get('methods',{}).values()for i in m['instructions']):
        plan['json_conversion_methods']=[CONVERSION];plan['json_conversion_contract']='Existing pinned default Jackson relative-path conversion contract; not a business formula.'
    plan['source_evidence']=True
    if plan['profile']=='execution-dependency':
        specialize_transport(plan)
        from plan_execution_closure import attach_execution_closure
        attach_execution_closure(plan,model)
    return plan,{'version':2,'reason':reason,'contract_features':sorted(features),'structural_triggers':sorted(set(shape)),'failed_candidates':failures,'answer_independent':True}
