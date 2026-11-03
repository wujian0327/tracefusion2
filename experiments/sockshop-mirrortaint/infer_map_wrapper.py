"""Check return-snapshot wrapper witnesses without creating any source."""
from query_observation_planner import require
from collections import defaultdict


def validate(plan,rows):
    policy=plan.get('map_wrapper_observation')
    classes=defaultdict(list)
    for event in rows:
        if event['kind']=='map-wrapper-class':classes[(event.get('class'),event.get('loader'))].append(event)
    for row in rows:
        if row['kind']!='binding-return':continue
        proofs=row.get('map_wrappers',[])
        if not policy:
            require(not proofs,'Undeclared Map wrapper observation');continue
        require('map_wrappers'in row and isinstance(proofs,list),'Map wrapper witnesses missing')
        owners=set()
        for fact in proofs:
            require(fact['owner']not in owners,'Repeated Map wrapper identity');owners.add(fact['owner'])
            require(fact.get('class')in policy['candidates']and fact.get('chain')==policy['candidates'][fact['class']],'Wrapper hierarchy/hash differs')
            require(all(p['class_sha256']==plan['class_sha256'].get(p['class'])for p in fact['chain']),'Wrapper frozen class differs')
            require(len(fact.get('loaders',[]))==len(fact['chain']),'Wrapper class-loader witnesses absent')
            for item,loader in zip(fact['chain'],fact['loaders']):
                observed=classes.get((item['class'],loader),[])
                require(len(observed)==1 and observed[0]['class_sha256']==item['class_sha256']and observed[0]['seq']<row['seq'],'Wrapper actual class/hash/loader absent or ambiguous')
            require(fact.get('runtime')in policy['contract']['profiles'],'Wrapper JDK implementation not supported')
            require(fact.get('methods')==policy['contract']['read_methods'],'Wrapper read obligations differ')
            require(type(fact.get('size'))is int and 0<=fact['size']<=10000 and fact.get('entries')==fact['size']and type(fact.get('mod_count'))is int,'Wrapper snapshot shape/completion differs')
        desc=policy['declared_return_descriptor'];declared=desc[1:-1]
        if declared in policy['candidates']and row['result'].get('object')is not None:
            require(row['result']['object']in owners,'Root wrapper witness missing/wrong object')
