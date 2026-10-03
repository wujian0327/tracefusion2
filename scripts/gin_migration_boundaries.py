"""Request lifetime + observed process/G identity, independent of OS scheduling."""
import gin_concurrent_boundaries as concurrent
from hybrid_model import require
from language_adapters import ExecutionPolicy


class GoroutineRequestPolicy(ExecutionPolicy):
    def identity(self, event, registers):
        rid=event['request_id'];g=event['regs'][registers.index('r14')];tgid=event['pid_tid']>>32
        require(rid>0 and g>0 and tgid>0,'Missing process/G/request identity')
        return tgid,g,rid

    def key(self, event):
        return event['request_id']

    def group(self, events):
        result={}
        for e in events:result.setdefault((self.key(e),e['call_id']),[]).append(e)
        return result

    def result_key(self, result):
        return result['execution_id']

    def result_identity(self, key, events):
        return dict(execution_id=key,observed_pid_tids=sorted({e['pid_tid'] for e in events}))


POLICY=GoroutineRequestPolicy('observed-process-g-request', 'r14')


def groups(rows):
    active={};gs={};closed={};processes=set()
    for event in rows:
        tgid,g,rid=POLICY.identity(event,concurrent.shared.reads.core.model.REGS)
        processes.add(tgid);require(len(processes)==1,'Multiple target processes')
        if event['kind']==3:
            require(rid not in active and rid not in closed,'Repeated request generation')
            require((tgid,g) not in gs,'Overlapping goroutine request lifetimes')
            active[rid]=[];gs[tgid,g]=rid
        require(rid in active and gs.get((tgid,g))==rid,'Event outside observed G/request lifetime')
        request=active[rid]
        require(event['request_sequence']==len(request),'Missing or repeated request-local observation')
        if request:require(event['timestamp']>=request[-1]['timestamp'],'Non-monotonic request observations')
        request.append(event)
        if event['kind']==4:
            closed[rid]=active.pop(rid);del gs[tgid,g]
    require(not active and closed,'Unclosed or empty request set')
    require(set(closed)==set(range(1,len(closed)+1)),'Missing request generation')
    return [closed[k] for k in sorted(closed)]


def bind(events,plans,config,runtime):
    try:
        require(config['gin_api'].get('pinned_request_thread') is False and
                config['gin_api'].get('execution_identity')=='process-g-request-v1','Migration adapter not configured')
        result=concurrent.bind(events,plans,config,runtime,group_requests=groups,context_policy=POLICY)
        if result['issues']:return result
        requests=groups(sorted(events,key=lambda e:e['observation_sequence']))
        by_id={r[0]['request_id']:r for r in requests};details=[]
        for out in result['results']:
            request=by_id[out['request_id']];tids=sorted({e['pid_tid'] for e in request})
            hops=[dict(previous_sequence=a['request_sequence'],sequence=b['request_sequence'],
                       from_pid_tid=a['pid_tid'],to_pid_tid=b['pid_tid'],from_kind=a['kind'],to_kind=b['kind'])
                  for a,b in zip(request,request[1:]) if a['pid_tid']!=b['pid_tid']]
            reads=[e for e in request if e['kind']==1]
            compute=[e for e in request if e['kind']==0]
            render=next(e for e in request if e['kind']==6)
            detail=dict(request_id=out['request_id'],g=request[0]['regs'][14],observed_pid_tids=tids,
                        observed_thread_transitions=len(hops),transitions=hops,
                        different_read_threads=len(reads)==2 and reads[0]['pid_tid']!=reads[1]['pid_tid'],
                        compute_to_render_changed_thread=compute[-1]['pid_tid']!=render['pid_tid'])
            details.append(detail)
            out.update(execution_id=out['request_id'],observed_pid_tids=tids,
                       execution_identity=dict(tgid=request[0]['pid_tid']>>32,g=request[0]['regs'][14],generation=out['request_id']),
                       request_identity='observed process/G plus scope generation; raw TIDs retained',migration=detail)
        result.update(migration=dict(migrated_requests=sum(len(d['observed_pid_tids'])>1 for d in details),
            observed_thread_transitions=sum(d['observed_thread_transitions'] for d in details),
            requests=details),scope='Observed G follows an unpinned request across OS threads; fixed JSON summary, private objects; no child-G propagation or stack-relocation support')
        return result
    except (ValueError,KeyError,IndexError,TypeError,StopIteration) as exc:
        return dict(results=[],compute_results=[],read_operations=[],issues=[dict(error=str(exc))],
                    boundary_issues=[dict(error=str(exc))],oracle_used_for_inference=False)


def evaluate(inferred,oracle,stats,plans):
    report=concurrent.evaluate(inferred,oracle,stats,plans)
    migration=inferred.get('migration',{});details=migration.get('requests',[])
    covered=(len(details)==28 and migration.get('migrated_requests')==28 and
             all(d['different_read_threads'] and d['compute_to_render_changed_thread'] for d in details))
    report.update(provenance_checks_passed=report['passed'],migration_coverage_passed=covered,
                  migration=migration,passed=report['passed'] and covered,
                  scope='Four concurrent unpinned requests; require observed migration between reads and between computation and JSON in all 28 requests; controlled scheduling, not throughput or arbitrary goroutine propagation')
    return report
