"""Validate pre-observation MVC exclusion. Never creates source dependencies."""
from collections import defaultdict
from query_observation_planner import require
from transport_context import validate_context


def validate(plan,rows):
    cfg=plan.get('query_request_scope');events=[r for r in rows if r['kind'].startswith('query-scope-')]
    if cfg is None:require(not events,'Undeclared request ownership evidence');return
    require(cfg['version']==1 and cfg['entry']==plan['entry'],'Request scope policy differs')
    cov=[r for r in events if r['kind']=='query-scope-coverage']
    require(len(cov)==1 and cov[0]['entry']==plan['entry']and cov[0]['class']==cfg['entry_class']and cov[0]['class_sha256']==cfg['entry_class_sha256']==plan['class_sha256'][cfg['entry_class']],'Root instrumentation coverage missing/ambiguous')
    framework=defaultdict(list);dispatch={};ends={};roots={};excluded={};completed={};server={}
    for r in rows:
        if r['kind']=='http-server-context':
            validate_context(r);require(r['message']not in server,'Duplicate server context');server[r['message']]=r
        if r['kind']=='query-scope-framework':framework[(r['class'],r['loader'])].append(r)
        if r['kind']=='query-scope-dispatch-enter':
            key=r['dispatch_id'];require(key not in dispatch,'Duplicate dispatch identity');dispatch[key]=r
        if r['kind']=='query-scope-dispatch-exit':
            key=r['dispatch_id'];require(key not in ends,'Duplicate dispatch completion');ends[key]=r
        if r['kind']=='query-scope-root':
            require(r['entry']==plan['entry']and r['root_frame']not in roots,'Duplicate/wrong query root association');roots[r['root_frame']]=r
        if r['kind']=='query-scope-output-excluded':
            key=(r['dispatch_id'],r['carrier_object']);require(key not in excluded,'Duplicate excluded output');excluded[key]=r
        if r['kind']in('query-scope-output-excluded-end','query-scope-output-excluded-abort'):
            key=(r['dispatch_id'],r['carrier_object']);require(key not in completed,'Duplicate excluded output completion');completed[key]=r
    def context(r):
        validate_context(r);base=server.get(r['message']);require(base is not None and base['seq']<r['seq'],'Ownership lacks actual server context')
        keys=('trace_id','request_span_id','span_id','parent_span_id')
        if r['kind']!='query-scope-root':keys+=('uri',)
        require(all(r.get(k)==base.get(k)for k in keys),'Ownership server context differs')
    fields=('message','handler_method','handler_class_sha256','request_object','response_object','framework_loader','web_type','thread')
    for key,r in dispatch.items():
        context(r);require(key in ends,'Dispatch completion missing');end=ends[key]
        require(r['seq']<end['seq']and all(r.get(k)==end.get(k)for k in fields),'Dispatch completion mispaired')
        require(r.get('request_object')and r.get('response_object')and cfg['handlers'].get(r['handler_method'])==r['handler_class_sha256'],'Unverified actual MVC handler')
        for name,pin in cfg['framework']['profiles'][0]['class_sha256'].items():
            if '/async/'in name and r['web_type']!='org/springframework/web/context/request/async/StandardServletAsyncWebRequest':continue
            facts=framework.get((name,r['framework_loader']),[])
            # The response carrier class may be loaded at serialization time.
            limit=end['seq']if name.endswith('/ServletServerHttpResponse')else r['seq']
            require(len(facts)==1 and facts[0]['class_sha256']==pin and facts[0]['seq']<limit,'MVC framework evidence missing/ambiguous')
    require(set(ends)==set(dispatch),'Foreign dispatch completion')
    entries={r['frame']:r for r in rows if r['kind']=='enter'and r['method']==plan['entry']}
    require(set(entries)==set(roots),'Query root entry/association missing or foreign')
    messages=set()
    for frame,r in roots.items():
        context(r);entry=entries[frame];require(r['seq']<entry['seq']and r['thread']==entry['thread'],'Query root association ordering differs');messages.add(r['message'])
        d=dispatch.get(r.get('dispatch_id'))
        if r.get('dispatch_id')is None:
            # No licensed MVC scope: full observation remains mandatory. The
            # actual root/message still prevents omission for this message.
            require(not any(x['message']==r['message']for x in excluded.values()),'Unscoped query output was excluded')
        else:require(d is not None and d['seq']<r['seq']<ends[d['dispatch_id']]['seq']and d['message']==r['message'],'Query root lacks its actual dispatch')
    for r in rows:
        if r['kind']=='binding-return':require(r['frame']in roots and r.get('message')==roots[r['frame']]['message'],'Return message differs from query root')
    require(set(excluded)==set(completed),'Excluded output completion missing/foreign')
    for key,r in excluded.items():
        d=dispatch.get(r['dispatch_id']);end=completed[key]
        require(d is not None and all(r.get(k)==d.get(k)for k in fields),'Excluded output belongs to another dispatch')
        require(all(end.get(k)==r.get(k)for k in fields+('carrier_object','query_output_scope'))and d['seq']<r['seq']<end['seq']<ends[d['dispatch_id']]['seq'],'Excluded output interval/completion differs')
        require(cov[0]['seq']<r['seq']and r.get('parent_span_id')is None and r.get('query_output_scope')=='independent-unparented-handler','Unproved independent response')
        require(r.get('web_type')=='org/springframework/web/context/request/async/StandardServletAsyncWebRequest'and r.get('synchronous')is True and ends[d['dispatch_id']].get('synchronous')is True,'Excluded response lacks verified synchronous lifecycle state')
        require(r['message']not in messages and not any(x['message']==r['message']and x['handler_method']==plan['entry']for x in dispatch.values()),'Query-owned output was excluded')
        require(not any(x.get('message')==r['message']and x['kind']in('binding-return','http-rpc-enter')for x in rows),'Required query/RPC output excluded')
