"""Validate observation-only invocation facts; never infer dependencies here."""
from collections import defaultdict
from query_observation_planner import require


def validate(plan, rows):
    cfg=plan.get('source_observation'); relevant=[r for r in rows if r['kind'].startswith(('source-context-','source-call-'))]
    if not cfg:
        require(not relevant,'Unplanned source observation protocol');return {'calls':0,'facts':0}
    require(cfg.get('version')==1,'Source observation version differs')
    contexts={}; calls={}; closed_contexts=set(); closed_calls=set(); completions={}; source_fields=[]; stacks=defaultdict(list); facts=0
    frames={r['frame']:r for r in rows if r['kind']=='enter'}
    for r in rows:
        kind=r['kind']; oid=r.get('observation_frame'); thread=r.get('thread')
        if kind=='source-context-enter':
            require(isinstance(oid,str) and oid.startswith('sf') and oid not in contexts,'Source context identity absent/duplicated')
            require(r.get('caller_method')in cfg['methods'] and r.get('observation_only')is True,'Unplanned source context')
            require(r.get('frame')in frames and frames[r['frame']]['seq']<r['seq'],'Source context has no actual parent Frame')
            require(r.get('caller_class_sha256')==plan['class_sha256'].get(r['caller_method'].split('.')[0]),'Source caller class differs')
            require(r.get('parent_observation_frame')==(stacks[thread][-1]if stacks[thread]else None),'Source context parent differs')
            contexts[oid]=r;stacks[thread].append(oid)
        elif kind=='source-context-exit':
            require(oid in contexts and oid not in closed_contexts and stacks[thread] and stacks[thread][-1]==oid,'Source context completion differs')
            require(all(cid in closed_calls for cid,c in calls.items()if c['observation_frame']==oid),'Source context has incomplete call')
            require(r.get('frame')==contexts[oid]['frame'] and r.get('caller_method')==contexts[oid]['caller_method'],'Source context owner differs')
            closed_contexts.add(oid);stacks[thread].pop()
        elif kind=='source-call-enter':
            cid=r.get('source_call_id');proof=cfg['sites'].get(r.get('site'))
            require(isinstance(cid,str) and cid.startswith('sc') and cid not in calls,'Source invocation ID absent/duplicated')
            require(oid in contexts and oid not in closed_contexts and stacks[thread][-1]==oid,'Source invocation context differs')
            require(proof and all(r.get(k)==proof[v]for k,v in [('callee','callee'),('caller_method','caller'),('pc','pc')]),'Source invocation site/caller differs')
            require(r.get('frame')==contexts[oid]['frame'] and isinstance(r.get('args'),list),'Source invocation actual arguments/parent absent')
            calls[cid]=r
        elif kind in ('source-call-exit','source-call-throw'):
            cid=r.get('source_call_id');c=calls.get(cid)
            require(c and cid not in closed_calls and all(c.get(k)==r.get(k)for k in ('frame','thread','observation_frame','callee','site','caller_method')),'Source invocation completion differs')
            require(oid not in closed_contexts and r['seq']>c['seq'],'Source completion outside caller')
            require((r.get('exception')is None)==(kind=='source-call-exit'),'Source completion exception differs')
            closed_calls.add(cid);completions[cid]=r
        elif kind=='binding-source' and r.get('source_scope')=='observation-only-call':
            cid=r.get('source_call_id');c=calls.get(cid)
            require(c and cid not in closed_calls,'Source fields outside invocation interval')
            require(all(r.get(k)==c.get(v)for k,v in [('source_observation_frame','observation_frame'),('source_caller_method','caller_method'),('source_pc','pc'),('source_callsite','site'),('callee','callee'),('frame','frame'),('thread','thread')]),'Source fields invocation coordinates differ')
            require(bool(r.get('fields')),'Source observation fields absent');source_fields.append(r);facts+=1
    require(set(contexts)==closed_contexts and set(calls)==closed_calls and not any(stacks.values()),'Source observation capture incomplete')
    for r in source_fields:
        end=completions[r['source_call_id']]
        require(end['kind']=='source-call-exit' and r.get('source_result')==end.get('result'),'Source return object differs from actual completion')
    return {'calls':len(calls),'facts':facts,'interpreted_callers':False}
