#!/usr/bin/env python3
"""Continue after already launched correctness jobs; gate all timed trials."""
import argparse,datetime,json,subprocess,sys,time
from pathlib import Path
from run_planned_service import HERE,load,save,sha


def run(root,cost):
    out=root/'logs';status=root/'pipeline-status.json'
    def node(name,**values):
        record={'node':name,'time_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),**values};save(out/(name+'.json'),record);save(status,record);print(record,flush=True)
    def wait(path,predicate):
        deadline=time.monotonic()+7200
        while time.monotonic()<deadline:
            if path.exists()and predicate(load(path)):return load(path)
            time.sleep(5)
        raise TimeoutError(str(path))
    def command(name,script,*args):
        node(name+'-start',script=script)
        with(out/(name+'.log')).open('w')as log:subprocess.run([sys.executable,str(HERE/script),*map(str,args)],stdout=log,stderr=subprocess.STDOUT,check=True)
        node(name+'-complete')
    try:
        node('20-awaiting-launched-regressions',algorithm=load(root/'algorithm-freeze.json')['commit'])
        s=wait(root/'worker-status.json',lambda v:v.get('complete'));assert all(v==0 for v in s['workers'].values()),s
        wait(root/'regression29-train/results.json',lambda v:v.get('complete'))
        command('21-regression29-orders','run_execution_closure_revision.py','--root',root,'--stage','regression29','--worker','orders')
        command('22-development62-audit','audit_execution_closure_revision.py','--root',root,'--stage','development')
        command('23-regression29-audit','audit_execution_closure_revision.py','--root',root,'--stage','fields29')
        for role in('station','route','price'):wait(root/'heldout21-first'/('runtime-'+role)/'results.json',lambda v:v.get('complete'))
        command('24-heldout21-first-audit','audit_execution_closure_revision.py','--root',root,'--stage','heldout')
        # Correctness deployments are now closed; timed trials run serially.
        command('25-cost-calibration','run_execution_closure_cost.py','--root',cost,'--stage','calibrate')
        command('26-formal-cost','run_execution_closure_cost.py','--root',cost,'--stage','run')
        command('27-offline-memory','run_execution_closure_cost.py','--root',cost,'--stage','memory')
        command('28-static-planning','run_execution_closure_cost.py','--root',cost,'--stage','planning')
        command('29-input-scale','run_execution_closure_cost.py','--root',cost,'--stage','scale')
        command('30-cost-audit','audit_execution_closure_cost.py','--root',cost)
        node('31-pipeline-complete',all_passed=True,core_unchanged=True,first_heldout_failures_retained=True)
    except BaseException as error:node('pipeline-failed',error=str(error));raise


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',required=True,type=Path);p.add_argument('--cost',required=True,type=Path);a=p.parse_args();run(a.root.resolve(),a.cost.resolve())
