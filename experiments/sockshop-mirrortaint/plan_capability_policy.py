"""Pre-execution structural routing; never reads runtime answers or baseline labels."""
from plan_response_binding import plan_response
from plan_async_dependencies import attach_async_dependencies
from query_observation_planner import require
CONVERSION='edu/fudan/common/util/JsonUtils.conveterObject(Ljava/lang/Object;Ljava/lang/Class;)Ljava/lang/Object;'

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
                if i['op'] in (182,183,184,185) and (i.get('desc','').endswith('Ljava/util/concurrent/Future;') or i.get('name')=='save' and i.get('desc')=='(Ljava/lang/Object;)Ljava/lang/Object;'):shape.append('task-or-save-effects')
                if 'target' in i and i['target']<=i['index']:shape.append('control-flow-backedge')
    if legacy and legacy['profile']!='response-forward':plan=legacy;reason='Existing specialized scalar/copy proof has priority'
    elif kernel and (not legacy or shape or query['entry'] not in legacy.get('read_forward_contracts',{}).get('composed_methods',{})):plan=kernel;reason='Execution semantics for structural effects or unavailable root composition'
    elif legacy:plan=legacy;reason='Existing finite return-forward contract'
    elif kernel:plan=kernel;reason='Execution fallback with supported semantics'
    else:raise ValueError('No supported static plan: '+str(failures))
    if plan['profile']=='execution-dependency':plan=attach_async_dependencies(plan)
    if CONVERSION in model['methods']:
        plan['json_conversion_methods']=[CONVERSION];plan['json_conversion_contract']='Existing pinned default Jackson relative-path conversion contract; not a business formula.'
    plan['source_evidence']=True
    return plan,{'version':1,'reason':reason,'structural_triggers':sorted(set(shape)),'failed_candidates':failures,'answer_independent':True}
