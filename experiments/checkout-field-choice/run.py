#!/usr/bin/env python3
"""Build/run a controlled field-choice variant using the existing BCC lifecycle."""
import argparse
from datetime import datetime,timezone
from functools import partial
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import traceback

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
sys.path.insert(0,str(HERE.parent/'checkout-item-identity'))
import field_choice
from hybrid_model import require
from string_capture import collect

spec=importlib.util.spec_from_file_location('shared_identity_runner',HERE.parent/'checkout-item-identity/run.py')
shared=importlib.util.module_from_spec(spec);spec.loader.exec_module(shared)
CASES=('equal-a','equal-b','different-a','different-b')
OVERWRITE_CASES=tuple(f'{values}-{choices}' for values in ('equal','different') for choices in ('aa','ab','ba','bb'))


def save(path,data):path.write_text(json.dumps(data,indent=2)+'\n')


def execute(args,out):
    overwrite=args.variant=='overwrite'
    function=field_choice.FUNCTION.replace('.chooseUnits','.overwriteUnits') if overwrite else field_choice.FUNCTION
    binary,plan,before,command=shared.build_target(args,out,HERE/'field_choice_test.go',partial(field_choice.plan_binary,function=function))
    strategies=('selected','all_branches','boundaries') if overwrite else ('selected','boundaries')
    if overwrite:
        # Validate the experiment, not just source syntax: optimization must not
        # have removed the early stores/branch we intend to stop observing.
        flow=plan['flow']
        require(len(flow['branches'])==2 and len(flow['paths'])==4 and
                len(flow['selected_branches'])==1 and
                {len(p['writes']) for p in flow['paths']}=={2,3},
                'Optimized binary no longer exercises the intended overwrite/pruning scenario')
    for strategy in strategies:save(out/('plan-'+strategy+'.json'),field_choice.strategy_plan(plan,strategy))
    results=[]
    for case in (OVERWRITE_CASES if overwrite else CASES):
        for strategy in (('native',) if args.mode=='build' else strategies):
            folder=out/case/strategy;folder.mkdir(parents=True)
            extra=dict(TRACEFUSION_IDENTITY_CASE=case,TRACEFUSION_IDENTITY_TRUTH=str(folder/'truth.json'),
                       TRACEFUSION_FIELD_VARIANT=args.variant)
            if strategy=='native':
                command([binary],extra=extra,input='x')
                truth=json.loads((folder/'truth.json').read_text())
                results.append(dict(case=case,native_fixture_passed=True,source_candidates=truth['source_candidates']))
                continue
            print(f'Collecting {case} / {strategy}',flush=True)
            selected=field_choice.strategy_plan(plan,strategy)
            previous={k:os.environ.get(k) for k in extra};os.environ.update(extra)
            try:doc=collect(binary,selected,b'x',folder/'capture',transport=field_choice,timeout_seconds=60)
            finally:
                for k,v in previous.items():
                    if v is None:os.environ.pop(k,None)
                    else:os.environ[k]=v
            inferred=field_choice.infer(selected,doc);save(folder/'inference.json',inferred)
            truth=json.loads((folder/'truth.json').read_text())
            results.append(field_choice.evaluate(selected,inferred,truth))
    summary=dict(all_passed=True,mode=args.mode,bpf_executed=args.mode=='run',cases=results,
                 variant=args.variant,
                 main_go_sha256=before,original_business_source_unchanged=True,
                 controlled_variant=True,scope=plan['scope'],selected_probes=len(plan['sites']),
                 static_path_count=len(plan['flow']['paths']),selected_branch_count=len(plan['flow']['selected_branches']),
                 all_branch_probes=len(plan['all_sites']),
                 omitted_branch_addresses=[b['address'] for b in plan['flow']['branches'] if b['address'] not in plan['flow']['selected_branches']],
                 writes_per_path=[len(p['writes']) for p in plan['flow']['paths']])
    save(out/'summary.json',summary);print(json.dumps(summary),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('build','run'))
    parser.add_argument('--variant',choices=('choice','overwrite'),default='choice')
    parser.add_argument('--checkout',type=Path)
    parser.add_argument('--go',default=os.environ.get('TRACEFUSION_GO') or shutil.which('go'))
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    prefix='checkout-field-overwrite-' if args.variant=='overwrite' else 'checkout-field-choice-'
    out=(args.output or ROOT/'artifacts'/(prefix+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f'))).resolve()
    out.mkdir(parents=True,exist_ok=False)
    try:execute(args,out)
    except Exception:
        (out/'failure.txt').write_text(traceback.format_exc());raise
    finally:print('Return this result archive: '+shutil.make_archive(str(out),'zip',root_dir=out.parent,base_dir=out.name),flush=True)


if __name__=='__main__':main()
