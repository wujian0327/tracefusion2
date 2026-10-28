#!/usr/bin/env python3
"""Execute fixed per-target plans with fresh same-fixture services; no performance claims."""
import concurrent.futures,subprocess,sys
from run_portability_first import TASK_ROOT
from run_planned_service import HERE,load

def job(api,mode,index=None):
    dest=TASK_ROOT/'tool-runs'/api/mode/(('query-%03d'%index)if index is not None else'fixed-adapter')
    if(dest/'results.json').exists():return
    cmd=[sys.executable,str(HERE/'run_portability_piggy.py'),'--mode',mode,'--api',api]
    if index is not None:cmd+=['--index',str(index)]
    log=TASK_ROOT/'logs'/('%s-%s-%s.log'%(api,mode,index));p=subprocess.run(cmd,stdout=log.open('w'),stderr=subprocess.STDOUT);print(api,mode,index,p.returncode,flush=True)

def api_run(q):
    job(q['id'],'mirrortaint')
    summary=load(TASK_ROOT/'planning-first'/q['id']/'summary.json')
    for r in summary['rows']:
        if r['status']!='accepted':continue
        for mode in('full','selective'):job(q['id'],mode,r['index'])
if __name__=='__main__':
    qs=[q for q in load(TASK_ROOT/'task-seal.json')['entries']if q['application']=='piggymetrics']
    with concurrent.futures.ThreadPoolExecutor(max_workers=2)as pool:
        for f in [pool.submit(api_run,q)for q in qs]:f.result()
