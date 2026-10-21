#!/usr/bin/env python3
"""Rescore fixed availability captures without overwriting original evidence."""
import argparse,copy,csv,json
from collections import Counter
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save,sha
import run_frozen_capability_acceptance as driver


def diagnostic_summary(directory):
    observations=[]
    for file in sorted(directory.glob('round-*/*/capture/orders/events.jsonl')):
        rows=[json.loads(line) for line in file.read_text().splitlines()];starts={r['call_id']:r for r in rows if r['kind']=='collection-call-enter'};waits=[]
        for row in rows:
            start=starts.get(row.get('call_id'))
            if start and row.get('async_future',{}).get('operation')=='get' and start['callee'].startswith('java/util/concurrent/Future.get('):
                waits.append((row['diagnostic_monotonic_ns']-start['diagnostic_monotonic_ns'])/1e9)
        stacks=Counter();samples=0;sidecar=file.with_name(file.name+'.diagnostic.jsonl')
        if sidecar.exists():
            for line in sidecar.read_text().splitlines():
                try:sample=json.loads(line)
                except ValueError:continue
                samples+=1
                for thread in sample['threads']:
                    for label in ('JdkContractProbe.hash','ExecutionKernelHooks.scalarEnd','RequestEntityHooks.hashes'):
                        if any(label in frame for frame in thread['stack']):stacks[label]+=1
        observations.append({'configuration':file.parent.parent.parent.name,'event_sha256':sha(file),'sidecar_sha256':sha(sidecar) if sidecar.exists() else None,'samples':samples,'sampled_stacks':dict(stacks),'future_get_max_seconds_diagnostic':max(waits,default=None),'timeouts':sum(r.get('exception_type')=='java.util.concurrent.TimeoutException'for r in rows),'returned_roots':sum(r['kind']=='binding-return'for r in rows)})
    return observations


def audit(root,out,validation='frozen-validation'):
    limited=validation=='quota-jvm-validation';protocol_file='quota-jvm-validation-protocol-before-run.json'if limited else 'validation-protocol-before-freeze.json'
    out.mkdir(parents=True,exist_ok=False);base=root/'buffered-core';freeze=load(base/'algorithm-freeze.json');protocol=load(root/protocol_file);before=load(root/validation/'protocol-before-deployments.json')
    assert protocol['repetitions']==before['repetitions']==3 and not before['diagnostic'];assert freeze['validation_protocol_sha256']==sha(HERE/'orders-availability-validation-20261021.json')
    assert bool(before.get('quota_aware_jvm',False))==limited
    if limited:assert sha(root/protocol_file)==sha(HERE/'orders-quota-jvm-validation-20261021.json') and before['gc_logging']
    assert all(sha(Path(p))==digest==sha(base/'source-snapshot'/Path(p).relative_to(ROOT)) for p,digest in freeze['sources'].items())
    assert sha(HERE/'execution-kernel-protocol-20261020.json')=='87c40107282aaccb8e049fc5ffe37bb1e66deacfeabd0f015a08544bc1972fae'
    configurations=[];requests=[];targets=[];refusals=[]
    query_map={q['id']:q for q in driver.QUERIES};expected={(mode,q)for mode in protocol['modes']for q in protocol['queries']}
    for index in range(1,4):
        round_root=root/validation/('round-'+str(index));manifest=load(round_root/'results.json');assert manifest['complete'];assert {(r['mode'],r['query'])for r in manifest['results']}==expected
        for result in manifest['results']:
            q=query_map[result['query']];mode=result['mode'];name=mode+'-'+q['id'];directory=round_root/name;cap=directory/'capture';plan=load(directory/'build/orders/plan.json');spec=load(cap/'compose.json')['services']['orders'];driver.old.verify_build(directory/'build')
            assert sha(directory/'build/distributed-observer.jar')==sha(base/'frozen-base/distributed-observer.jar');assert sha(directory/'build/orders/plan.json')==sha(base/'frozen-plans'/(q['id']+'.json'))
            assert spec['cpus']==1 and spec['mem_limit']=='768m';opts=spec['environment']['JAVA_OPTS'];assert '-Xms32m -Xmx256m' in opts and 'service.diagnostic'not in opts;assert plan['source_evidence']
            if limited:
                assert '-XX:ParallelGCThreads=1' in opts and '-XX:CICompilerCount=2' in opts
                header=(cap/'orders/gc.log').read_text().splitlines()[2];assert '-XX:ParallelGCThreads=1' in header and '-XX:CICompilerCount=2' in header
            else:assert '-XX:ParallelGCThreads='not in opts and '-XX:CICompilerCount='not in opts
            raw=cap/'orders/events.jsonl';rows=[json.loads(s)for s in raw.read_text().splitlines()];assert not any('diagnostic_monotonic_ns'in r for r in rows);assert not raw.with_name(raw.name+'.diagnostic.jsonl').exists()
            timed=[r for r in rows if r['kind']=='collection-call-enter' and r.get('callee','').startswith('java/util/concurrent/Future.get(J')];assert timed and all(r['args'][0]['value']==5 for r in timed)
            successful=0
            for case in load(round_root/'input-protocol-before-queries.json')['cases']:
                file=cap/case['case']/'business-result.json';r=load(file) if file.exists() else {};ok=r.get('business_passed',False) and r.get('http_status')==201;successful+=ok
                requests.append({'round':index,'mode':mode,'query':q['id'],'case':case['case'],'state':'completed'if ok else 'business_error'if file.exists() else 'unexecuted','elapsed_seconds':(r['end_monotonic_ns']-r['start_monotonic_ns'])/1e9 if 'end_monotonic_ns'in r else None})
            scored=None
            successful_cases=[load(file) for file in sorted(cap.glob('group-*/contract-result.json'))]
            if successful_cases:
                dest=out/'rescore'/('round-'+str(index))/name;dest.mkdir(parents=True);(dest/'build').symlink_to((directory/'build').resolve(),target_is_directory=True)
                if (cap/'run.json').exists():(dest/'capture').symlink_to(cap.resolve(),target_is_directory=True)
                else:
                    # The driver stops on a business error. Independently score
                    # preceding completed requests without rewriting that run.
                    shadow=dest/'capture';shadow.mkdir()
                    for file in cap.iterdir():
                        if file.name!='run.json':(shadow/file.name).symlink_to(file.resolve(),target_is_directory=file.is_dir())
                    save(shadow/'run.json',{'status':'business-failed-partial','roles':['orders'],'mode':mode,'cases':successful_cases})
                scored=driver.evaluate(dest,q);detail=load(dest/'evaluation.json')
                targets.extend({'round':index,'mode':mode,**t}for t in detail['predictions'])
                # Corrupt copies only: neither an incomplete buffered tail nor
                # a lost interior event may become an accepted closed capture.
                for label,bad in [('missing-footer',[r for r in rows if r['kind']!='metrics']),('truncated-tail',rows[:-100]),('missing-interior',rows[:100]+rows[101:])]:
                    try:driver.old.Reconstruction(directory/'build',cap,['orders'],decoded_rows={'orders':bad})
                    except ValueError as e:refusals.append({'round':index,'mode':mode,'query':q['id'],'fault':label,'rejected':True,'reason':str(e)})
                    else:raise AssertionError('Accepted incomplete stream: '+label)
            for request in requests[-6:]:
                if request['state']!='completed':targets.append({'round':index,'mode':mode,'query':q['id'],'case':request['case'],'path':q['path'],'state':request['state'],'not_provenance_NA':True})
            configurations.append({'round':index,'mode':mode,'query':q['id'],'intended_requests':6,'business_completed':successful,'timeout_count':sum(r.get('exception_type')=='java.util.concurrent.TimeoutException'for r in rows),'event_sha256':sha(raw),'agent_sha256':sha(directory/'build/distributed-observer.jar'),'plan_sha256':sha(directory/'build/orders/plan.json'),'score':scored,'original_failure':result.get('failure')})
    counts=Counter(t['state']for t in targets);business=Counter(r['state']for r in requests);passed=business=={'completed':72} and counts=={'known_correct':72} and all(c['score']['fp']==c['score']['fn']==c['score']['oracle_unavailable']==0 for c in configurations)
    controls={name:load(root/'semantic-controls'/name/'results.json')for name in ('application','request-async','async-dependencies','received-mutations','date')}
    assert all(result['all_passed']for result in controls.values())
    summary={'algorithm_commit':freeze['algorithm_commit'],'scope':'Two previously affected Orders query families; targeted availability only','all_targeted_checks_passed':passed,'intended_requests':72,'business_states':dict(business),'target_states':dict(counts),'modes':{m:{'requests':dict(Counter(r['state']for r in requests if r['mode']==m)),'targets':dict(Counter(t['state']for t in targets if t['mode']==m)),'tp':sum(t.get('tp',0)for t in targets if t['mode']==m),'fp':sum(t.get('fp',0)for t in targets if t['mode']==m),'fn':sum(t.get('fn',0)for t in targets if t['mode']==m)}for m in ('full','selective')},'configurations':configurations,'stream_fault_rejections':len(refusals),'metadata_and_buffer_controls':load(root/'metadata-buffer-controls/stdout.json'),'unit_tests':76,'unit_result':load(root/'semantic-controls/unit-result.json'),'semantic_suite_paths':{name:str(root/'semantic-controls'/name/'results.json')for name in controls},'diagnostic_before_cache':diagnostic_summary(root/'diagnostic-first'),'diagnostic_cache_prototype':diagnostic_summary(root/'diagnostic-cached'),'original_timeout_artifacts_preserved':True,'sole_timeout_root_cause_proven':False,'new_62_query_acceptance':False,'new_cost_result':False,'heldout_29_untouched':True}
    summary.update(validation_configuration=validation,limited_gc_jit_threads=limited,validation_protocol_sha256=sha(root/protocol_file),original_parameter_failure_replaced=False)
    save(out/'audit.json',summary);save(out/'targets.json',targets);save(out/'stream-faults.json',refusals)
    for name,records in [('requests',requests),('configurations',[{k:v for k,v in c.items()if k!='score'}for c in configurations])]:
        with (out/(name+'.csv')).open('w')as stream:
            writer=csv.DictWriter(stream,fieldnames=list(records[0]));writer.writeheader();writer.writerows(records)
    return summary

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--validation',choices=('frozen-validation','quota-jvm-validation'),default='frozen-validation');a=p.parse_args();r=audit(a.root.resolve(),a.out.resolve(),a.validation);print(json.dumps({k:v for k,v in r.items()if k in ('algorithm_commit','all_targeted_checks_passed','business_states','target_states','modes','stream_fault_rejections')},indent=2))
