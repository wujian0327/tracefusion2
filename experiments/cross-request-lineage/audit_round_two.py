#!/usr/bin/env python3
"""Independent delivery evidence checks; never supplies origins to inference."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from run import ROOT,HERE,CORE,load,save,sha
from analyze import rows


def audit(home,predictions,scores,negatives,out):
    out.mkdir(parents=True,exist_ok=False);initial=load(HERE/'round-two-initial-state.json');frozen=load(home/'freeze.json')
    assert all(sha(HERE/n)==h for n,h in initial['round_one_files'].items())
    assert sha(home/'expected-round-two.json')==frozen['expected_sha256']==sha(HERE/'expected-round-two.json')
    assert sha(home/'workload.json')==frozen['workload_sha256']==sha(HERE/'workload.json')
    assert all(sha(ROOT/n)==h for n,h in initial['runtime_hashes'].items())
    assert all(sha(ROOT/n)==h for n,h in initial['dependency_locks'].items())
    manifest=load(home/'build/manifest.json');tfmanifest=load(home/'build/tf/build.json')
    assert sha(home/'build/tf/distributed-observer.jar')==manifest['tf_agent_sha256']==tfmanifest['agent_sha256']
    assert sha(home/'build/tf/B/plan.json')==manifest['plans']['B']==tfmanifest['inputs']['B']['plan_sha256']
    assert sha(Path(manifest['native']))==manifest['native_sha256']
    assert all(sha(Path(p))==h for p,h in manifest['dependencies'].items())
    # Collector Java and offline Python are distinct immutable receipts; a
    # current-core replay may legitimately follow an earlier collector build.
    assert all(sha(Path(p))==h for p,h in tfmanifest['sources'].items()if p.endswith('.java'))
    replay=load(predictions/'replay-receipt.json');assert replay['oracle_consumed']is False
    assert all(sha(Path(p))==h for p,h in replay['current_core_sources'].items())
    score=load(scores/'score.json');negative=load(negatives/'results.json')
    assert all(r['source_status']=='correct'and r['version_status']in ('correct','N/A')and r['business_equal']for r in score['rows'])
    assert negative['known_positive_required']and negative['original_positive_still_correct']
    assert len(negative['negative_checks'])==90 and len(negative['wrong_wrapper_rejected'])==2
    assert all(r['positive_before']=='known_correct'and r['state']in ('unknown','rejected')and 'control-write-address'not in r['reason']for r in negative['negative_checks'])
    namespaces=set();facts=[]
    for cap in sorted((home/'captures/tracefusion').glob('*/*')):
        rs=rows(cap/'B/events.jsonl');header=rs[0];namespace=(header['capture_session'],header['process_instance'])
        assert namespace not in namespaces;namespaces.add(namespace)
        assert [r['seq']for r in rs]==list(range(1,len(rs)+1))
        assert rs[-1]['kind']=='metrics'and rs[-1]['session_history_event_count']==len(rs)and not rs[-1]['capture_invalid']
        assert all((r['capture_session'],r['process_instance'])==namespace for r in rs)
        assert header['plan_sha256']==manifest['plans']['B']
        run=load(cap/'run.json');assert len([r for r in rs if r['kind']=='session-request-cleanup'])==len(run['requests'])
        calls=[r for r in rows(cap/'B/http.jsonl')if r['path']=='/call'];assert len(calls)==len(run['requests'])and len({r['pid']for r in calls})==1
        assert all('rpc_traceparent'not in r for r in calls),'This round must use direct B'
        history=load(predictions/'tracefusion'/cap.parent.name/cap.name/'prediction.json')['result']['session_history']
        assert history['namespace']==list(namespace)
        for v in history['versions']:
            assert v['namespace']==list(namespace)and v['completion']=='normal'
            assert v['dependency_complete_at_publish']and v['effects_complete_at_publish']
            assert rs[v['write_seq']-1]['kind']=='write'
        facts.append({'case':cap.name,'repeat':cap.parent.name,'namespace':list(namespace),'requests':len(calls),'historical_versions':len(history['versions']),'canonical_binding_aliases':len(history['bindings']),'actual_history_reads':len(history['reads'])})
    for case in {r['case']for r in facts}:assert len([r for r in facts if r['case']==case])>=2
    checks=Counter((r['mutation'],r['regenerated'],r['state'],r['reason'])for r in negative['negative_checks'])
    finals=score['final_queries'];normal=[r for r in finals['tracefusion']if not r['sixth_full_evidence']]
    raw_sixth=[r for r in finals['tracefusion']if r['sixth_full_evidence']]
    result={'verified':True,'normal_final_queries':len(normal),'normal_source_correct':sum(r['source_status']=='correct'for r in normal),'normal_version_correct':sum(r['version_status']=='correct'for r in normal),
            'sixth_full_evidence_final_queries':len(raw_sixth),'checkpoint_summary':score['summary'],'captures':facts,
            'negative_states':dict(Counter(r['state']for r in negative['negative_checks'])),'negative_details':[{'mutation':k[0],'regenerated':k[1],'state':k[2],'reason':k[3],'count':n}for k,n in checks.items()],
            'wrong_wrapper_detected':len(negative['wrong_wrapper_rejected']),'round_one_inputs_unchanged':True,'runtime_and_dependency_locks_unchanged':True,
            'offline_current_core_receipt':str(predictions/'replay-receipt.json'),'collector_build_receipt':str(home/'build/tf/build.json')}
    save(out/'verification.json',result)
    print(json.dumps({k:v for k,v in result.items()if k not in ('captures','negative_details')}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--predictions',type=Path,required=True);p.add_argument('--scores',type=Path,required=True);p.add_argument('--negatives',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();audit(a.run.resolve(),a.predictions.resolve(),a.scores.resolve(),a.negatives.resolve(),a.out.resolve())
