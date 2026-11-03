"""A first target-related cut: direct-source return plus guarded effect frames.

The callee is NOT proved read-only. Its effects are interpreted conservatively;
only the private returned island can survive them. All effect evidence remains.
"""
from plan_collection_service import analyze
from plan_service_observations import callee


def attach(plan):
    cfg=plan.get('execution_kernel',{})
    if not cfg.get('source_locality'):
        return
    methods=cfg['methods'];sources=set(plan['response_binding']['source_calls'])
    graphs={};forward={};active=set()

    def returned(key):
        if key in forward:return forward[key]
        if key in active or key not in methods:return None
        active.add(key);m=methods[key];graph,_,_,_=analyze(m,allow_loops=True);graphs[key]=graph
        if any('target'in i and i['target']<=i['index'] for i in m['instructions']):
            active.remove(key);forward[key]=None;return None
        def producers(pc,seen=frozenset()):
            if pc<0 or pc in seen:return None
            ins=m['instructions'][pc]
            if ins['op']in (25,176,192):
                found=[]
                for definition in graph[pc]:
                    proof=producers(definition,seen|{pc})
                    if proof is None:return None
                    found.extend(proof)
                return found or None
            if ins['op']in (182,183,184,185):
                target=callee(ins)
                if target in sources:return [(key,pc,target)]
                implementations=cfg['call_targets'].get(key+'@'+str(pc),[])
                if not implementations:return None
                found=[]
                for implementation in implementations:
                    proof=returned(implementation)
                    if proof is None:return None
                    found.extend(proof)
                return found or None
            return None
        proofs=[producers(ins['index']) for ins in m['instructions'] if ins['op']==176]
        active.remove(key)
        result=None if not proofs or any(p is None for p in proofs) else sorted(set(p for group in proofs for p in group))
        if result is not None and len(result)!=1:result=None
        forward[key]=result
        return result

    proof=returned(plan['entry'])
    if not proof:return
    source_method,source_pc,source=proof[0]
    source_type=source.split(')')[1]
    if source_type!='L'+plan['target'].rsplit('.',1)[0]+';':return
    def forwarding_suffix(key,pc):
        """A cut may not destroy state used by a later target computation.

        The first bounded rule permits only reference forwarding after the
        summarized call, including its callers. Everything else collects full
        BEFORE entering that call. Root-object identity alone is insufficient.
        """
        method=methods[key];code=method['instructions'];seen=set();work=[pc+1]
        if method.get('exception_handlers'):return False
        while work:
            at=work.pop()
            if at in seen:continue
            if at>=len(code):return False
            seen.add(at);ins=code[at];op=ins['op']
            if op==176:continue
            if op==167:
                if ins['target']<=at:return False
                work.append(ins['target']);continue
            if op not in (0,25,58,87,89,192):return False
            work.append(at+1)
        return bool(seen)
    def reaches(key,destination,seen=frozenset()):
        if key==destination:return True
        if key in seen:return False
        return any(reaches(target,destination,seen|{key}) for ins in methods[key]['instructions']
                   for target in cfg['call_targets'].get(key+'@'+str(ins['index']),[])
                   if target in forward and forward[target]==proof)
    def continuation_closed(caller,pc):
        if not forwarding_suffix(caller,pc):return False
        for key,value in forward.items():
            if value!=proof or key==caller:continue
            for ins in methods[key]['instructions']:
                if any(reaches(target,caller) for target in cfg['call_targets'].get(key+'@'+str(ins['index']),[])
                       if target in forward and forward[target]==proof):
                    if not forwarding_suffix(key,ins['index']):return False
        return True
    candidates={}
    for caller,result in list(forward.items()):
        if result!=proof:continue
        for ins in methods[caller]['instructions']:
            # A direct invocation has no unknown proxy/advice prelude. The
            # same-owner static form cannot trigger foreign class initialization.
            if ins['op']not in (183,184) or ins.get('name')=='<init>' or not ins['desc'].endswith(')V'):continue
            if ins['op']==184 and ins['owner']!=methods[caller]['owner']:continue
            target=callee(ins)
            if target not in cfg['call_targets'].get(caller+'@'+str(ins['index']),[]):continue
            if not continuation_closed(caller,ins['index']):continue
            from plan_constructor_prefix_guard import eligible
            if not eligible(plan,caller,ins['index'],
                            {key for key,p in forward.items()if p==proof},
                            {'caller':source_method,'pc':source_pc,'callee':source}):continue
            candidates[caller+'@'+str(ins['index'])]={'callee':target,
                'implementation':target,'caller':caller,'pc':ins['index'],
                'reason':'Root returns the same source object; all caller continuations only forward references. Runtime must establish an unexposed source island disjoint from receiver/arguments. Callee keeps arbitrary effects.',
                'continuation':'Reference-only suffix in the candidate caller and every forwarding ancestor; otherwise full collection before invocation.'}
    if candidates:
        cfg['body_observation']={'version':2,'enabled':True,
            'source':{'caller':source_method,'pc':source_pc,'callee':source},
            'forwarding_methods':sorted(key for key,p in forward.items() if p==proof),
            'candidates':candidates,
            'retain':'Frame/call identities, arguments, completion/throw, all writes/versions/aliases/publications, source/transport/contract witnesses',
            'omit':'Internal field-read value events and branch events only inside a certified effect-only frame. Full observation when guard is unavailable/revoked.',
            'effects':'Conservative opaque effects; never a read-only summary or a new source.'}
