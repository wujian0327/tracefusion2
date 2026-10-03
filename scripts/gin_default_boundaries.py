"""Natural concurrency: correctness and observed coverage are separate gates."""
import gin_migration_boundaries as migration
from hybrid_model import require


def bind(events,plans,config,runtime):
    # Scope checks and the shared reconstruction engine remain unchanged.
    result=migration.bind(events,plans,config,runtime)
    if result['issues']:return result
    try:
        require(config['gin_api'].get('scheduling')=='runtime-default' and
                config['gin_api'].get('phase_barriers') is False,'Default scheduler fixture not configured')
        rows=sorted(events,key=lambda e:e['observation_sequence'])
        active={};overlap_pairs=set();cross_thread_pairs=set();last_tid={}
        for e in rows:
            rid=e['request_id'];tid=e['pid_tid']
            last_tid[rid]=tid
            if e['kind']==3:active[rid]=e['timestamp']
            # Scope overlap is observed evidence, not proof of simultaneous
            # CPU execution. Per-event TIDs identify multiple OS threads.
            for other in active:
                if other!=rid:
                    pair=tuple(sorted((rid,other)));overlap_pairs.add(pair)
                    if last_tid[other]!=tid:cross_thread_pairs.add(pair)
            if e['kind']==4:del active[rid]
        result['natural_scheduling']=dict(
            max_active_scopes=result['concurrency']['max_active_scopes'],
            overlapping_request_pairs=len(overlap_pairs),
            overlapping_pairs_with_distinct_observed_threads=len(cross_thread_pairs),
            observed_thread_count=len({e['pid_tid'] for e in rows}),
            migrated_requests=result['migration']['migrated_requests'],
            observed_thread_transitions=result['migration']['observed_thread_transitions'])
        result['scope']='Natural default-scheduler Gin requests; observed process/G generations, private reads, shared computation provenance and fixed JSON summary'
        return result
    except (ValueError,KeyError,IndexError,TypeError) as exc:
        return dict(results=[],compute_results=[],read_operations=[],issues=[dict(error=str(exc))],
                    boundary_issues=[dict(error=str(exc))],oracle_used_for_inference=False)


def default_scheduler(metadata):
    return (isinstance(metadata,dict) and type(metadata.get('gomaxprocs')) is int and metadata['gomaxprocs']>0
            and type(metadata.get('num_cpu')) is int and metadata['num_cpu']>0
            and metadata.get('gomaxprocs_env_set') is False and metadata.get('scheduler_override_flags')==[])


def evaluate(inferred,oracle,stats,plans):
    report=migration.concurrent.evaluate(inferred,oracle['requests'],stats,plans,require_phase_barriers=False)
    provenance_ok=report['passed']
    initial=oracle['scheduler_initial'];final=oracle['scheduler_final']
    defaults=default_scheduler(initial) and default_scheduler(final)
    observed=inferred.get('natural_scheduling',{})
    overlap=observed.get('max_active_scopes',0)>=2 and observed.get('overlapping_request_pairs',0)>0
    report.pop('batches') # Natural execution has no server-side phase gates.
    report.update(provenance_checks_passed=provenance_ok,default_scheduler_verified=defaults,
        natural_concurrency_coverage_passed=overlap,
        passed=provenance_ok and defaults and overlap,
        scheduler=dict(initial=initial,final=final,
                       multi_p_configured=initial.get('gomaxprocs',0)>1 and final.get('gomaxprocs',0)>1),
        natural_scheduling=observed,migration=inferred.get('migration',{}),
        migration_required=False,
        scope='28 requests with unchanged field/source checks; default scheduler metadata and at least two observed overlapping scopes required; natural migration reported but not forced; no CPU-parallelism or performance claim')
    return report
