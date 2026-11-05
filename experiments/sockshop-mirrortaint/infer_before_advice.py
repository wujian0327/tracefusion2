"""Original match/adapter completion precede target; effects are not erased."""
from query_observation_planner import require

def validate(plan, index, dispatch, call):
    contract=plan['execution_kernel']['direct_dispatch_contract'].get('before_only')
    require(contract and dispatch['before_class_sha256']==contract['class_sha256'],'Before dispatch contract differs')
    require(dispatch['empty_chain']is False and dispatch['transparent_interceptors']==[],'Before effects cannot be claimed empty/transparent')
    for name,digest in contract['class_sha256'].items():
        if name.endswith('InterceptorAndDynamicMethodMatcher'): continue  # read-only field layout pin at runtime
        found=index[('before-dispatch-framework',name)]
        require(len(found)==1 and found[0]['class_sha256']==digest and found[0]['seq']<dispatch['seq'],'Before framework observation absent/ambiguous')
    steps=index[('before-dispatch-step',call['call_id'])]
    require([s['seq']for s in steps]==dispatch['before_steps'],'Missing/duplicate before dispatch steps')
    require(all(call['seq']<s['seq']<dispatch['seq'] and s['frame']==call['frame'] and
                s['thread']==call['thread'] and s['invocation']==dispatch['invocation'] for s in steps),'Before effect scope/timing differs')
    require(dispatch['chain'] and [s['index']for s in dispatch['chain']]==list(range(len(dispatch['chain']))),'Before chain index differs')
    require([s['index']for s in steps]==sorted(s['index']for s in steps),'Before interceptor execution order differs')
    for slot in dispatch['chain']:
        events=[s for s in steps if s['index']==slot['index']]
        enters=[s for s in events if s['stage']=='interceptor-enter']
        done=[s for s in events if s['stage']=='before-complete']
        matches=[s for s in events if s['stage']=='dynamic-match']
        if slot['kind']=='expose':
            require(slot['type']=='org.springframework.aop.interceptor.ExposeInvocationInterceptor' and len(enters)==1 and len(events)==1,'Expose invocation evidence differs')
        else:
            require(slot['kind']in ('before','dynamic-before'),'Unmodeled advice kind')
            dynamic=slot['kind']=='dynamic-before';matched=slot['matched']
            require(slot['type']==('org.springframework.aop.framework.InterceptorAndDynamicMethodMatcher'if dynamic else'org.springframework.aop.framework.adapter.MethodBeforeAdviceInterceptor'),'Before slot implementation differs')
            require(type(matched)is bool and len(matches)==int(dynamic),'Before match count differs')
            if dynamic:require(matches[0]['matched']==matched,'Dynamic match result differs')
            require(len(done)==len(enters)==int(matched) and len(events)==int(dynamic)+2*int(matched),'Before adapter completion differs')
            if matched:
                require(enters[0]['seq']<done[0]['seq'] and (not dynamic or matches[0]['seq']<enters[0]['seq']),'Before adapter order differs')
                require(enters[0]['adapter_type']==done[0]['adapter_type']=='org.springframework.aop.framework.adapter.MethodBeforeAdviceInterceptor','Unknown executed interceptor')
        require(all(s['adapter']==slot['adapter'] for s in enters+done),'Before adapter identity differs')
    require(all(0<=s['index']<len(dispatch['chain']) for s in steps),'Extra interceptor index')
