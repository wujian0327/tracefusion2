"""API obligations from planned bytecode; independent of query results."""


def features(plan,model):
    needed=set()
    repos={o for o,c in model['classes'].items()if any(i.startswith('org/springframework/data/')and i.endswith('Repository')for i in c.get('interfaces',[]))}
    for method in plan['execution_kernel']['methods'].values():
        for i in method['instructions']:
            if i['op']not in (182,183,184,185):continue
            if i['owner']in repos and i['name']=='save'and i['desc']=='(Ljava/lang/Object;)Ljava/lang/Object;':needed.add('save')
            if i['desc'].endswith('Ljava/util/concurrent/Future;'):needed.add('async')
            if i['owner'].startswith('org/springframework/http/RequestEntity'):needed.add('request')
            # The existing hash-pinned Object/List renderer lives in the
            # request-wrapper contract pack. It is an independent obligation:
            # a save must not enable it, nor may splitting save disable it.
            if i['owner']=='java/lang/StringBuilder'and i['name']=='append'and i['desc']=='(Ljava/lang/Object;)Ljava/lang/StringBuilder;':needed.add('render')
    # A verified conversion summary can already supply this same renderer;
    # a planned RequestEntity obligation also selects the shared pack. Do not
    # replace either contract or change an otherwise identical plan merely to
    # duplicate the label. The missing independent render obligation remains.
    if 'request'in needed or plan['execution_kernel'].get('request_entity_contracts'):needed.discard('render')
    return needed
