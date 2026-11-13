#!/usr/bin/env python3
"""Offline predictions only; independent expectations are forbidden inputs."""
import argparse
import json
from pathlib import Path
import sys
import traceback
from run import CORE,load,save,sha
sys.path.insert(0,str(CORE))
from infer_execution_kernel import infer_execution
from analyze import rows


def predict(plan,events):
    try:return {'state':'analyzed','result':infer_execution(plan,events)}
    except Exception as e:return {'state':'rejected','error':str(e),'type':type(e).__name__,'traceback':traceback.format_exc()}


def oracle_guard():
    def guard(event,args):
        if event=='open'and isinstance(args[0],str)and (Path(args[0]).name.startswith('expected')or Path(args[0]).name=='workload.json'):
            raise RuntimeError('Independent oracle is forbidden to the analyzer')
    sys.addaudithook(guard)


def run(home,out):
    oracle_guard();out.mkdir(parents=True,exist_ok=False)
    plan=load(home/'build/tf/B/plan.json')
    for cap in sorted((home/'captures/tracefusion').glob('*/*')):
        dest=out/'tracefusion'/cap.parent.name/cap.name;dest.mkdir(parents=True)
        save(dest/'prediction.json',predict(plan,rows(cap/'B/events.jsonl')))
    for cap in sorted((home/'captures/mirrortaint').glob('*/*')):
        dest=out/'mirrortaint'/cap.parent.name/cap.name;dest.mkdir(parents=True)
        save(dest/'prediction.json',{'state':'native_export','events':rows(cap/'B/native.jsonl'),'strict_version_query':'N/A','offline_missing_write_query':'N/A'})
    save(out/'replay-receipt.json',{'current_core_sources':{str(p):sha(p)for p in CORE.iterdir()if p.suffix in ('.py','.java','.json')},'oracle_consumed':False})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path);p.add_argument('--out',type=Path,required=True);p.add_argument('--plan',type=Path);p.add_argument('--events',type=Path);a=p.parse_args()
    if a.events:
        if not a.plan:p.error('--events requires --plan')
        oracle_guard();a.out.mkdir(parents=True,exist_ok=False);save(a.out/'prediction.json',predict(load(a.plan),rows(a.events)))
    elif a.run:run(a.run.resolve(),a.out.resolve())
    else:p.error('--run or --events is required')
