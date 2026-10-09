#!/usr/bin/env python3
"""Observe the original money.Sum; no replacement implementation or disabled optimization."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import traceback

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(HERE.parent/'checkout-item-identity')]
import sum_adapter as adapter
from string_capture import collect
from hybrid_model import require
spec=importlib.util.spec_from_file_location('identity_builder',HERE.parent/'checkout-item-identity/run.py')
shared=importlib.util.module_from_spec(spec);spec.loader.exec_module(shared)
CASES=('equal-positive','carry','negative-carry','adjust-positive','adjust-negative','cancel','zero',
       'invalid-nanos','invalid-sign','currency-mismatch')
STRATEGIES=('selected','all_branches','boundaries')


def save(path,data):path.write_text(json.dumps(data,indent=2)+'\n')


def execute(args,out):
    binary,plan,before,command=shared.build_target(args,out,HERE/'sum_test.go',adapter.plan_binary)
    checkout=(args.checkout or ROOT/'artifacts/online-boutique-v0.10.4').resolve()
    source=checkout/'src/checkoutservice/money/money.go'
    money_hash=hashlib.sha256(source.read_bytes()).hexdigest()
    require(money_hash=='c7e81c0e8e24cafce6ccf35b9846d76cea114969998355db34d01169687e67f3','Original money source differs')
    for strategy in STRATEGIES:save(out/('plan-'+strategy+'.json'),adapter.strategy_plan(plan,strategy))
    results=[]
    for case in CASES:
        for strategy in (('native',) if args.mode=='build' else STRATEGIES):
            folder=out/case/strategy;folder.mkdir(parents=True)
            extra=dict(TRACEFUSION_IDENTITY_CASE=case,TRACEFUSION_IDENTITY_TRUTH=str(folder/'truth.json'))
            if strategy=='native':
                command([binary],extra=extra,input='x')
                results.append(dict(case=case,native_fixture_passed=True));continue
            print(f'Collecting {case} / {strategy}',flush=True)
            selected=adapter.strategy_plan(plan,strategy)
            previous={k:os.environ.get(k) for k in extra};os.environ.update(extra)
            try:doc=collect(binary,selected,b'x',folder/'capture',transport=adapter,timeout_seconds=60)
            finally:
                for k,v in previous.items():
                    if v is None:os.environ.pop(k,None)
                    else:os.environ[k]=v
            inferred=adapter.infer(selected,doc);save(folder/'inference.json',inferred)
            # Oracle is unavailable to inference; open only after result is saved.
            results.append(adapter.evaluate(selected,inferred,json.loads((folder/'truth.json').read_text())))
    require(hashlib.sha256(source.read_bytes()).hexdigest()==money_hash,'Original source changed')
    summary=dict(all_passed=True,mode=args.mode,bpf_executed=args.mode=='run',cases=results,
                 upstream_commit=shared.COMMIT,main_go_sha256=before,money_go_sha256=money_hash,
                 original_business_source_unchanged=True,scope=plan['scope'],assumptions=plan['assumptions'],
                 selected_probes=len(plan['sites']),all_branch_probes=len(plan['all_sites']),
                 static_path_count=len(plan['flow']['paths']),selected_branch_count=len(plan['flow']['selected_branches']))
    save(out/'summary.json',summary);print(json.dumps(summary),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('build','run'))
    parser.add_argument('--checkout',type=Path)
    parser.add_argument('--go',default=os.environ.get('TRACEFUSION_GO') or shutil.which('go'))
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    out=(args.output or ROOT/'artifacts'/('checkout-money-sum-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f'))).resolve()
    out.mkdir(parents=True,exist_ok=False)
    try:execute(args,out)
    except Exception:
        (out/'failure.txt').write_text(traceback.format_exc());raise
    finally:print('Return this result archive: '+shutil.make_archive(str(out),'zip',root_dir=out.parent,base_dir=out.name),flush=True)


if __name__=='__main__':main()
