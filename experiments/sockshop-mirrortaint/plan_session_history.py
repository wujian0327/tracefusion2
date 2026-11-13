"""Opt-in sequential capture roots, using the existing application bytecode planner."""
from copy import deepcopy
from query_observation_planner import require
from plan_application_calls import augment_calls


def attach(plan, model, roots, data_fields, control_fields=()):
    require(plan['profile']=='execution-dependency','Session history needs application execution')
    require(plan['execution_kernel']['version']>=2,'Session history needs method invocation evidence')
    require(plan['entry'] in roots and len(set(roots))==len(roots),'Session roots must include query entry once')
    require(not set(data_fields)&set(control_fields),'Data/control field declarations overlap')
    result=deepcopy(plan)
    result=augment_calls(result,model,result['response_binding']['source_calls'],roots=roots)
    result['response_binding']['source_fields']=sorted(set(data_fields)|set(control_fields))
    result['session_history']={'version':1,'scope':'sequential-http-external-input-and-application-roots',
        'roots':sorted(roots),'query_entry':plan['entry'],'data_fields':sorted(data_fields),
        'control_fields':sorted(control_fields),'source_direction':'request','source_phase':'read',
        'evidence':'real framed writes, existing constructor/call/exception protocols; exact physical versions only'}
    return result
