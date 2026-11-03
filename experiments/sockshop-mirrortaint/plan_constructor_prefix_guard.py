"""Conservative pre-cut constructor transfer check.

A constructor is a call even when it has no ordinary collection-call event.
Following reaching definitions catches direct and derived source references;
unknown constructor effects cannot be excused by a later argument-disjoint call.
This check can overapproximate immutable derived values and collect full.
"""
from plan_collection_service import analyze


def eligible(plan,caller,pc,forwarding,source):
    methods=plan['execution_kernel']['methods']
    targets=plan['execution_kernel']['call_targets']
    graph,_,_,_=analyze(methods[caller],allow_loops=True)
    code=methods[caller]['instructions'];memo={}
    def may_transfer(definition,visiting=frozenset()):
        if definition<0:return False
        if definition in memo:return memo[definition]
        if definition in visiting:return True
        ins=code[definition]
        declared=caller==source['caller'] and definition==source['pc']
        forwarded=any(key in forwarding for key in targets.get(caller+'@'+str(definition),[]))
        result=declared or forwarded or any(may_transfer(d,visiting|{definition})for d in graph[definition])
        memo[definition]=result;return result
    for ins in code[:pc]:
        if ins['op']==183 and ins.get('name')=='<init>' and any(may_transfer(d)for d in graph[ins['index']]):
            return False
    return True
