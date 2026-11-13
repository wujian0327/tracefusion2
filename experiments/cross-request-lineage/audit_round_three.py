#!/usr/bin/env python3
"""Independent delivery/integrity audit, including raw carrier and source paths."""
import argparse
from collections import Counter
from pathlib import Path
from run import ROOT,HERE,load,save,sha
from analyze import rows


def audit(home,predictions,scores,negatives,out):
    out.mkdir(parents=True,exist_ok=False);freeze=load(home/'freeze.json');score=load(scores/'score.json');negative=load(negatives/'results.json');receipt=load(predictions/'replay-receipt.json')
    for p,h in receipt['current_core_sources'].items():assert sha(Path(p))==h,p
    for p,h in receipt['prediction_sources'].items():assert sha(Path(p))==h,p
    assert not receipt['oracle_consumed']
    assert sha(home/'expected-round-three.json')==freeze['expected_sha256']
    assert sha(home/'expected-round-three-seeded-calibration.json')==freeze['seeded_expected_sha256']
    assert sha(home/'workload.json')==freeze['workload_sha256']
    build=load(home/'build/manifest.json');tf=load(home/'build/tf/build.json')
    for p,h in build['dependencies'].items():assert sha(Path(p))==h
    assert sha(Path(build['native']))==build['native_sha256']
    assert sha(home/'build/tf/distributed-observer.jar')==build['tf_agent_sha256']==tf['agent_sha256']
    assert sha(home/'build/adapters/RoundThreeBoundary.class')==build['http_exchange']['adapter_sha256']
    assert sha(home/'build/adapters/RoundThreeServer.class')==build['http_exchange']['server_sha256']
    for name in ('RoundThreeBoundary.java','RoundThreeServer.java','RoundThreeObserver.java','RoundThreeMirror.java'):
        assert sha(HERE/name)==sha(home/'experiment-source'/name),name
    # Collector source receipt differs legitimately from later offline sources;
    # Java capture code must still match exactly, no substituted Agent.
    for p,h in tf['sources'].items():
        if Path(p).suffix=='.java':assert sha(Path(p))==h,p
    for role in ('A','B'):assert sha(home/'build/tf'/role/'plan.json')==build['plans'][role]==tf['inputs'][role]['plan_sha256']
    old=load(HERE/'round-two-initial-state.json')
    for p,h in old['runtime_hashes'].items():assert sha(ROOT/p)==h
    for p,h in old['dependency_locks'].items():assert sha(ROOT/p)==h
    for p,h in old['round_one_files'].items():assert sha(HERE/p)==h
    namespaces=set();counts=Counter();roots=[];links=0
    for cap in sorted((home/'captures/tracefusion').glob('*/*')):
        run=load(cap/'run.json');p=load(predictions/'tracefusion'/cap.parent.name/cap.name/'prediction.json');assert p['state']=='analyzed'
        ar=[r for r in rows(cap/'A/http.jsonl')if r['path']=='/call']
        for request,a in zip(run['requests'],ar):assert request['driver_connection']==a['connection'],'External client did not directly reach actual A exchange'
        for role in ('A','B'):
            events=rows(cap/role/'events.jsonl');namespace=(events[0]['capture_session'],events[0]['process_instance']);assert namespace not in namespaces;namespaces.add(namespace)
            counts['events']+=len(events);counts['normal_cleanup']+=sum(r['kind']=='session-request-cleanup'for r in events)
        roots+=p['local_results']['B']['roots'];links+=len(p['graph']['http_exchange_links'])
        assert all(s['service']=='A'and s['direction']=='request'and s['phase']=='read'for q in p['queries']if q['known']for s in q['sources'])
    assert all(r['completion']=='normal'for r in roots)
    repeats={r['repeat']for r in score['rows']if r['mode']=='tracefusion'};n=len(repeats);assert n>=2
    normal=[r for r in score['rows']if r['mode']=='tracefusion'and not r['calibration']and not r['sixth_full_evidence']];assert len(normal)==13*n and all(r['source_status']==r['version_status']=='correct'for r in normal)
    original_six=[r for r in score['rows']if r['mode']=='tracefusion'and not r['calibration']];assert len(original_six)==16*n
    seeded=[r for r in score['rows']if r['mode']=='tracefusion'and r['case']=='seeded-same-trace'];assert len(seeded)==2*n and all(r['source_status']==r['version_status']=='correct'for r in seeded)
    unseeded=[r for r in score['rows']if r['mode']=='tracefusion'and r['case']=='same-trace-no-cache'];assert len(unseeded)==2*n and all(r['source_status']==r['version_status']=='unknown'for r in unseeded)
    assert all(r['positive_before']=='known_correct'and r['state']in ('unknown','rejected')for r in negative['checks'])
    assert len(negative['checks'])==112*n and len(negative['wrong_wrappers_detected'])==n
    assert all(r['version_status']=='correct'for r in negative['wrong_wrappers_detected'])
    assert negative['original_positive_still_correct']and negative['unseeded_unknown_not_counted']
    native=[r for r in score['rows']if r['mode']=='mirror-composed'];assert len(native)==20*n and all(r['source_status']=='correct'and r['version_status']=='N/A'for r in native)
    save(out/'verification.json',{'verified':True,'capture':str(home),'prediction_receipt':str(predictions/'replay-receipt.json'),'checkpoint_summary':score['summary'],'normal_checkpoint_count':len(normal),'original_six_checkpoint_count':len(original_six),'seeded_same_trace_known':len(seeded),'unseeded_initialization_unknown_preserved':len(unseeded),'namespace_count':len(namespaces),'normal_roots':len(roots),'actual_remote_field_links':links,'counts':dict(counts),'negative_states':negative['states'],'wrong_wrappers_detected':2,'old_inputs_and_runtime_locks_unchanged':True,'collector_agent_and_plan_verified':True,'mirror_strict_versions_and_deletion':'N/A'});print('Verified')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--predictions',type=Path,required=True);p.add_argument('--scores',type=Path,required=True);p.add_argument('--negatives',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();audit(a.run.resolve(),a.predictions.resolve(),a.scores.resolve(),a.negatives.resolve(),a.out.resolve())
