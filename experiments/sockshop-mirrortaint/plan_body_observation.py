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
            candidates[caller+'@'+str(ins['index'])]={'callee':target,
                'implementation':target,'caller':caller,'pc':ins['index'],
                'reason':'Root returns the same source object. Runtime must establish an unexposed source island disjoint from receiver/arguments. Callee keeps arbitrary effects.'}
    if candidates:
        cfg['body_observation']={'version':1,'enabled':True,
            'source':{'caller':source_method,'pc':source_pc,'callee':source},
            'forwarding_methods':sorted(key for key,p in forward.items() if p==proof),
            'candidates':candidates,
            'retain':'Frame/call identities, arguments, completion/throw, all writes/versions/aliases/publications, source/transport/contract witnesses',
            'omit':'Internal field-read value events and branch events only inside a certified effect-only frame. Full observation when guard is unavailable/revoked.',
            'effects':'Conservative opaque effects; never a read-only summary or a new source.'}
