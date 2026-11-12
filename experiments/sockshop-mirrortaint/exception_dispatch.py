"""Versioned, capture-local Throwable class identities; no name-only matching."""
from query_observation_planner import require
from analysis_status import AnalysisLimit


def first_handler(fact, table, pc, error, typename, method, hashes, registry, parents):
    require(isinstance(fact,dict) and fact.get('version')==1,'Exception dispatch witness/version absent')
    require(fact.get('method')==method and fact.get('exception',{}).get('object')==error.get('object') and error.get('object') is not None,'Exception dispatch method/object differs')
    require(fact.get('actual_type','').replace('/','.')==typename,'Exception dispatch actual type differs')
    caller=fact['caller'];require(caller['name']==method.split('.')[0],'Exception dispatch caller differs')
    def check(node):
        require(isinstance(node.get('id'),str) and isinstance(node.get('class_sha256'),str) and len(node['class_sha256'])==64,'Exception class identity/hash absent')
        if node['loader'] is not None:
            if node['loader']!=caller['loader']:raise AnalysisLimit('exception-loader','Exception dispatch across unverified application loaders')
            if node['name'] not in hashes:raise AnalysisLimit('exception-dispatch','Exception class metadata absent: '+node['name'])
            require(node['class_sha256']==hashes[node['name']],'Exception class hash differs')
        else:require(node['name'].startswith('java/'),'Unverified bootstrap exception class')
        by_id=registry.setdefault(('class-id',node['id']),node)
        require(by_id==node,'Exception Class identity reused for different type/loader')
        key=(node['name'],node['loader']);old=registry.setdefault(key,node)
        require(old==node,'Exception class identity/hierarchy changed')
    check(caller)
    nodes=fact['hierarchy'];require(nodes and nodes[0]['name']==fact['actual_type'],'Exception actual hierarchy differs')
    actual=registry.setdefault(('exception-object',error['object']),nodes[0]['id'])
    require(actual==nodes[0]['id'],'Exception object changed runtime class')
    ids=[n['id']for n in nodes];require(len(set(ids))==len(ids),'Exception hierarchy duplicate/cycle')
    for i,node in enumerate(nodes):
        check(node);require(node['super']==(ids[i+1]if i+1<len(ids)else None),'Exception superclass chain incomplete')
        if node['loader'] is not None:
            if node['name']not in parents:raise AnalysisLimit('exception-dispatch','Exception superclass metadata absent: '+node['name'])
            require(parents[node['name']]['super']==(nodes[i+1]['name']if i+1<len(nodes)else None),'Exception superclass differs from frozen class metadata')
    require(nodes[-1]['name']=='java/lang/Object' and nodes[-1]['loader']is None and any(n['name']=='java/lang/Throwable'and n['loader']is None for n in nodes),'Exception is not a witnessed Throwable')
    targets=fact['targets'];require(len(targets)==len(table),'Exception table witness length differs')
    result=None
    for h,target in zip(table,targets):
        require((target is None)==(h['type']is None),'Exception catch-all differs')
        if target is not None:
            check(target);require(target['name']==h['type'],'Exception original table order/type differs')
        if result is None and h['start']<=pc<h['end'] and (target is None or target['id']in ids):result=h['handler']
    return result
