#!/usr/bin/env python3
"""Original payment-path correctness comparison; not a performance benchmark."""
import argparse
from datetime import datetime,timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import random
import shutil
import sys
import time
import traceback

HERE=Path(__file__).resolve().parent; ROOT=HERE.parents[1]
sys.path[:0]=[str(HERE),str(ROOT/'scripts'),str(HERE.parent/'checkout-item-identity')]
import method_baselines as methods
from string_capture import collect
from independent_machine import check
spec=importlib.util.spec_from_file_location('identity_builder',HERE.parent/'checkout-item-identity/run.py')
builder=importlib.util.module_from_spec(spec); spec.loader.exec_module(builder)

def save(path,doc): path.write_text(json.dumps(doc,indent=2)+'\n')

def faults(plan,doc):
    import copy
    rows=[]
    def attempt(name,p,d): rows.append(dict(name=name,passed=methods.infer(p,d)['status']=='unknown',kind='offline_fault_injection'))
    d=copy.deepcopy(doc); d['stats']['lost']+=1; attempt('lost_event',plan,d)
    d=copy.deepcopy(doc); d['events'][1]['g']+=1; attempt('wrong_g',plan,d)
    d=copy.deepcopy(doc); del d['events'][1]; d['stats']['submitted']-=1; attempt('missing_source_packet',plan,d)
    d=copy.deepcopy(doc); d['events'][-2]['b']+=1; attempt('wrong_sink_witness',plan,d)
    p=copy.deepcopy(plan); p['independent_model']['functions'][methods.PLACE]['rows'][0]['asm']='UNMODELED AX, BX'
    attempt('unsupported_instruction',p,doc)
    return rows

def execute(args,out):
    binary,common,before,command=builder.build_target(args,out,HERE/'payment_test.go',methods.plan_binary)
    manifest=json.loads((HERE/'cases.json').read_text()); save(out/'cases.json',manifest)
    plans={s:methods.strategy_plan(common,s) for s in methods.STRATEGIES}
    for s,p in plans.items(): save(out/('plan-'+s+'.json'),p)
    source_files=['compare_methods.py','check_methods_local.py','method_baselines.py','independent_machine.py','independent_replay.py','payment_adapter.py','payment_test.go','cases.json']
    hashes={n:hashlib.sha256((HERE/n).read_bytes()).hexdigest() for n in source_files}
    source_dir=out/'method-sources'; source_dir.mkdir()
    for n in source_files: shutil.copy2(HERE/n,source_dir/n)
    env=dict(platform=platform.platform(),python=sys.version,go=command([args.go,'version']).strip(),
             source_sha256=hashes,upstream_commit=builder.COMMIT,binary_sha256=common['binary_sha256'],
             snapshot_version=2,seed=args.seed,performance_protocol_executed=False)
    save(out/'environment.json',env)
    results=[]; negatives=[]; orders=[]; rng=random.Random(args.seed)
    denominator=2*sum(not c.get('PreparationFailure',False) for c in manifest)
    def report(error=None):
        metrics={}
        if args.mode=='run':
            for strategy in methods.STRATEGIES:
                rows=[r for r in results if r['strategy']==strategy]
                m={k:sum(r.get(k,0) for r in rows) for k in ('query_fields','exact_fields','definite_fields','wrong_definite_fields','tp','fp','fn','events','perf_bytes')}
                m.update(expected_query_fields=denominator,expected_runs=len(manifest),attempted_runs=len(rows),
                         unattempted_runs=len(manifest)-len(rows),failed_runs=sum(not r['passed'] for r in rows)+len(manifest)-len(rows),
                         exact_set_rate=m['exact_fields']/denominator)
                metrics[strategy]=m
        completed=len(results)==len(manifest)*(5 if args.mode=='run' else 1)
        d=dict(all_passed=completed and all(r['passed'] for r in results+negatives),mode=args.mode,
               bpf_attempted=args.mode=='run',bpf_executed=any(r.get('stats',{}).get('probe_hits',0)>0 for r in results),
               cases=results,metrics=metrics,negative_checks=negatives,environment=env,main_go_sha256=before,
               performance_protocol_executed=False,scope=common['scope'],contracts=common['independent_model']['contracts'],
               interpretation='Method controls implemented here; not a reproduction of a published taint/slicing system. Boundary sufficiency/ties/advantages must all be reported.')
        if error is not None: d['failure']=error
        save(out/'summary.json',d); save(out/'run-order.json',orders)
        return d
    for case in manifest:
        order=list(methods.STRATEGIES); rng.shuffle(order); orders.append(dict(case=case['Name'],order=order))
        for strategy in ['native']+(order if args.mode=='run' else []):
            folder=out/case['Name']/strategy; folder.mkdir(parents=True)
            extra=dict(TRACEFUSION_IDENTITY_CASE=case['Name'],TRACEFUSION_PAYMENT_CASE=json.dumps(case),
                       TRACEFUSION_IDENTITY_TRUTH=str(folder/'truth.json'))
            if strategy=='native':
                command([binary],extra=extra,input='x'); results.append(dict(case=case['Name'],strategy=strategy,passed=True)); continue
            print(f'Collecting {case["Name"]} / {strategy}',flush=True)
            previous={k:os.environ.get(k) for k in extra}; os.environ.update(extra)
            try: doc=collect(binary,plans[strategy],b'x',folder/'capture',transport=methods,timeout_seconds=120)
            finally:
                for k,v in previous.items():
                    if v is None: os.environ.pop(k,None)
                    else: os.environ[k]=v
            started=time.perf_counter_ns(); cpu=time.process_time_ns()
            inferred=methods.infer(plans[strategy],doc)
            analysis=dict(wall_ns=time.perf_counter_ns()-started,cpu_ns=time.process_time_ns()-cpu,
                          scope='offline single inference diagnostic; no formal performance claim')
            save(folder/'inference.json',inferred); save(folder/'analysis-timing.json',analysis)
            truth=folder/'truth.json'
            r=methods.evaluate(plans[strategy],inferred,json.loads(truth.read_text())) if truth.exists() else dict(
                case=case['Name'],strategy=strategy,passed=False,status='missing_truth')
            r.update(events=len(doc['events']),perf_bytes=sum(int(n)*v for n,v in doc['diagnostics'].get('sample_sizes',{}).items()),stats=doc['stats'])
            results.append(r)
            if case['Name']=='one-repeated' and strategy in ('boundary_replay','path_sensitive_slice') and r['passed']:
                negatives.extend(dict(strategy=strategy,**row) for row in faults(plans[strategy],doc))
            if doc['capture_errors']:
                report(error=doc['capture_errors'])
                raise ValueError('Capture failure: '+str(doc['capture_errors']))
    summary=report(); print(json.dumps(dict(all_passed=summary['all_passed'],runs=len(results),metrics=summary['metrics'])),flush=True)
    check(summary['all_passed'],'Method mismatch/unknown; see summary and per-case inference (failed queries stay in denominator)')

def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('mode',choices=('build','run'))
    p.add_argument('--checkout',type=Path); p.add_argument('--go',default=os.environ.get('TRACEFUSION_GO') or shutil.which('go'))
    p.add_argument('--output',type=Path); p.add_argument('--seed',type=int,default=20261009)
    args=p.parse_args(); out=(args.output or ROOT/'artifacts'/('checkout-method-comparison-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f'))).resolve()
    out.mkdir(parents=True,exist_ok=False)
    try: execute(args,out)
    except Exception:
        (out/'failure.txt').write_text(traceback.format_exc()); raise
    finally: print('Return this result archive: '+shutil.make_archive(str(out),'zip',root_dir=out.parent,base_dir=out.name),flush=True)

if __name__=='__main__': main()
