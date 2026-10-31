"""B2 exporter invocation integrity, separate from native propagation/labels."""
from query_observation_planner import require


def validate(rows):
    require(not any(r['kind']=='problem'for r in rows),'Failed native source export')
    headers=[r for r in rows if r['kind']=='export-start']
    require(len(headers)==1 and headers[0].get('protocol')==2,'B2 export protocol missing/ambiguous')
    calls={};ends={};facts={};pending={}
    for r in rows:
        kind=r['kind'];cid=r.get('source_call_id');thread=r.get('thread')
        if kind=='source-call-enter':
            require(type(cid)is int and cid not in calls and r.get('root')is not None,'Native source invocation identity absent/duplicated')
            require(type(r.get('instrumented_instruction_index'))is int and r['instrumented_instruction_index']>=0 and r.get('caller_method')and r.get('callee'),'Native source site absent')
            require(isinstance(r.get('arguments'),list),'Native actual arguments absent');calls[cid]=r;pending.setdefault(thread,[]).append(cid)
        elif kind in ('source-call-exit','source-call-throw'):
            start=calls.get(cid)
            require(start and cid not in ends and pending.get(thread)and pending[thread].pop()==cid,'Native source completion absent/duplicated/misordered')
            require(all(start.get(k)==r.get(k)for k in ('root','thread','caller_method','callee','instrumented_instruction_index')),'Native source completion coordinates differ')
            require((r.get('exception_identity')is None)==(kind=='source-call-exit'),'Native source exception completion differs');ends[cid]=r
        elif kind=='source'and not r.get('call','').startswith('@argument:'):
            start=calls.get(cid)
            require(start and cid not in facts and cid not in ends and r['root']==start['root']and r['call']==start['callee']and thread==start['thread'],'Native source fields outside invocation')
            require(r.get('caller_method')==start['caller_method']and r.get('instrumented_instruction_index')==start['instrumented_instruction_index'],'Native source fields site differs');facts[cid]=r
    require(set(calls)==set(ends)and not any(pending.values()),'Native source invocation incomplete')
    for cid,start in calls.items():
        end=ends[cid]
        if end['kind']=='source-call-exit':
            require(cid in facts and facts[cid].get('result_identity')==end.get('result_identity'),'Native source return fields missing/wrong object')
        else:require(cid not in facts,'Exceptional native source has normal fields')
    return {'calls':len(calls),'normal':sum(e['kind']=='source-call-exit'for e in ends.values()),'exceptional':sum(e['kind']=='source-call-throw'for e in ends.values()),'paired':True}
