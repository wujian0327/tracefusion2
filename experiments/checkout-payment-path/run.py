#!/usr/bin/env python3
"""One fixed original-business integration, with native and three observation policies."""
import argparse
from datetime import datetime,timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import traceback

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(HERE),str(HERE.parent/'checkout-item-identity')]
import payment_adapter as adapter
from string_capture import collect
from hybrid_model import require
spec=importlib.util.spec_from_file_location('identity_builder',HERE.parent/'checkout-item-identity/run.py')
shared=importlib.util.module_from_spec(spec);spec.loader.exec_module(shared)


def save(path,data):path.write_text(json.dumps(data,indent=2)+'\n')


def negative_checks(plan,doc):
    import copy
    checks=[]
    candidates=[i for i,e in enumerate(doc['events']) if e['kind']=='sum_entry']
    # Fault injection only; these are not additional kernel runs. Adjusting the
    # submitted count prevents merely testing the trivial count mismatch gate.
    if candidates:
        bad=copy.deepcopy(doc);del bad['events'][candidates[0]];bad['stats']['submitted']-=1
        checks.append(('missing_call',adapter.infer(plan,bad)['status']=='unknown'))
    bad=copy.deepcopy(doc);bad['events'][1]['g']+=1
    checks.append(('wrong_g',adapter.infer(plan,bad)['status']=='unknown'))
    bad=copy.deepcopy(doc);bad['stats']['lost']+=1
    checks.append(('lost_event',adapter.infer(plan,bad)['status']=='unknown'))
    bad=copy.deepcopy(plan)
    bad['functions'][adapter.PLACE]['rows'][0]['asm']='UNMODELED AX, BX'
    checks.append(('unknown_instruction',adapter.infer(bad,doc)['status']=='unknown'))
    return [dict(name=name,passed=passed,kind='offline_fault_injection') for name,passed in checks]


def execute(args,out):
    binary,plan,before,command=shared.build_target(args,out,HERE/'payment_test.go',adapter.plan_binary)
    checkout=(args.checkout or ROOT/'artifacts/online-boutique-v0.10.4').resolve()
    money=checkout/'src/checkoutservice/money/money.go'
    money_hash=hashlib.sha256(money.read_bytes()).hexdigest()
    require(money_hash=='c7e81c0e8e24cafce6ccf35b9846d76cea114969998355db34d01169687e67f3','Original money source differs')
    manifest=json.loads((HERE/'cases.json').read_text());save(out/'cases.json',manifest)
    for strategy in ('selected','all_branches','boundaries'):save(out/('plan-'+strategy+'.json'),adapter.strategy_plan(plan,strategy))
    results=[];negatives=[]
    for case in manifest:
        for strategy in (('native',) if args.mode=='build' else ('native','selected','all_branches','boundaries')):
            folder=out/case['Name']/strategy;folder.mkdir(parents=True)
            extra=dict(TRACEFUSION_IDENTITY_CASE=case['Name'],TRACEFUSION_PAYMENT_CASE=json.dumps(case),TRACEFUSION_IDENTITY_TRUTH=str(folder/'truth.json'))
            if strategy=='native':
                command([binary],extra=extra,input='x')
                results.append(dict(case=case['Name'],strategy=strategy,passed=True,native_fixture_passed=True));continue
            print(f'Collecting {case["Name"]} / {strategy}',flush=True)
            selected=adapter.strategy_plan(plan,strategy);previous={k:os.environ.get(k) for k in extra};os.environ.update(extra)
            try:doc=collect(binary,selected,b'x',folder/'capture',transport=adapter,timeout_seconds=120)
            finally:
                for k,v in previous.items():
                    if v is None:os.environ.pop(k,None)
                    else:os.environ[k]=v
            inferred=adapter.infer(selected,doc);save(folder/'inference.json',inferred)
            truth_path=folder/'truth.json'
            if truth_path.exists():result=adapter.evaluate(selected,inferred,json.loads(truth_path.read_text()))
            else:result=dict(case=case['Name'],strategy=strategy,passed=False,status='capture_failure',reason=inferred.get('reason'))
            result['events']=len(doc['events']);result['perf_bytes']=sum(int(n)*v for n,v in doc['diagnostics'].get('sample_sizes',{}).items())
            results.append(result)
            if case['Name']=='one-repeated' and strategy=='selected' and result['passed']:negatives=negative_checks(selected,doc)
            # A broken collector is a common-mode failure: preserve diagnostics
            # and stop instead of compiling/attaching another 29 times.
            require(not doc['capture_errors'],'Capture failed: '+str(doc['capture_errors']))
    require(hashlib.sha256(money.read_bytes()).hexdigest()==money_hash,'Business source changed')
    metrics={}
    if args.mode=='run':
        for strategy in ('selected','all_branches','boundaries'):
            rows=[r for r in results if r['strategy']==strategy]
            m={k:sum(r.get(k,0) for r in rows) for k in ('query_fields','exact_fields','definite_fields','wrong_definite_fields','tp','fp','fn','events','perf_bytes')}
            # A missing truth file is a failed run, never an excluded success.
            m['failed_runs']=sum(not r['passed'] for r in rows)
            m['expected_query_fields']=2*sum(not c.get('PreparationFailure',False) for c in manifest)
            m['exact_set_rate']=m['exact_fields']/m['expected_query_fields']
            m['definite_coverage']=m['definite_fields']/m['expected_query_fields']
            m['relation_precision']=m['tp']/(m['tp']+m['fp']) if m['tp']+m['fp'] else None
            m['relation_recall']=m['tp']/(m['tp']+m['fn']) if m['tp']+m['fn'] else None
            metrics[strategy]=m
    summary=dict(all_passed=all(r['passed'] for r in results+negatives),mode=args.mode,bpf_executed=args.mode=='run',
                 cases=results,negative_checks=negatives,metrics=metrics,upstream_commit=shared.COMMIT,main_go_sha256=before,money_go_sha256=money_hash,
                 scope=plan['scope'],assumptions=plan['assumptions'],selected_probes=len(plan['sites']),all_probes=len(plan['all_sites']),
                 performance_protocol_executed=False,
                 note='Native wall time is only a fixture diagnostic; the frozen paired steady-state performance protocol is not implemented by this correctness runner')
    save(out/'summary.json',summary)
    print(json.dumps(dict(all_passed=summary['all_passed'],runs=len(results),negative_checks=len(negatives))),flush=True)
    require(summary['all_passed'],'Integration mismatches; inspect summary and inference files')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=('build','run'));p.add_argument('--checkout',type=Path)
    p.add_argument('--go',default=os.environ.get('TRACEFUSION_GO') or shutil.which('go'));p.add_argument('--output',type=Path)
    args=p.parse_args();out=(args.output or ROOT/'artifacts'/('checkout-payment-path-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f'))).resolve()
    out.mkdir(parents=True,exist_ok=False)
    try:execute(args,out)
    except Exception:
        (out/'failure.txt').write_text(traceback.format_exc());raise
    finally:print('Return this result archive: '+shutil.make_archive(str(out),'zip',root_dir=out.parent,base_dir=out.name),flush=True)


if __name__=='__main__':main()
