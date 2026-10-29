#!/usr/bin/env python3
"""All fixed Mall tasks, full first, then selective; independent deployments."""
import argparse,concurrent.futures,json,subprocess,sys,time
from pathlib import Path
from run_plan_applicability_revision import HERE,ROOT,load,save,sha

def run(home,agent,workers):
    tasks=load(home/'planning-summary.json');assert len(tasks)==21
    candidate=load(home/'candidate-code.json');assert sha(agent/'distributed-observer.jar')==candidate['agent_sha256']
    for p,h in candidate['sources'].items():assert sha(ROOT/p)==h,p
    for p,h in candidate['planning_inputs'].items():assert sha(home/p)==h,p
    seal={'order':[r['query']['id']for r in tasks],'modes':['full','selective'],'workers':workers,'capability_only':True,'same_candidate_and_agent':True,'all_21_query_obligations_retained':True,'reuse_pilot_captures':False}
    save(home/'matrix-protocol-before-business.json',seal);logs=home/'logs';logs.mkdir(exist_ok=True);results=[]
    def launch(task,mode):
        api=task['query']['id'].rsplit('-',1)[0];index=task['index'];label=api+'-'+mode+'-%03d'%index
        record={'api':api,'mode':mode,'index':index,'planning_status':task['status']}
        if task['status']!='accepted_conditional':return {**record,'state':'planning_rejected','reason':task.get('reason')}
        args=[sys.executable,str(HERE/'run_plan_applicability_revision.py'),'run','--home',str(home),'--agent-build',str(agent),'--api',api,'--mode',mode,'--index',str(index)]
        with(logs/(label+'.log')).open('w')as f:
            try:code=subprocess.run(args,stdout=f,stderr=subprocess.STDOUT,timeout=900).returncode
            except subprocess.TimeoutExpired:code='driver_timeout'
        record['returncode']=code
        capture=home/'tool-runs'/api/mode/('query-%03d'%index)
        receipt=capture/'results.json'
        if receipt.exists()and load(receipt).get('cleanup_returncode')==0:
            with(logs/(label+'-audit.log')).open('w')as f:
                record['audit_returncode']=subprocess.run([sys.executable,str(HERE/'audit_plan_applicability_revision.py'),'--home',str(home),'--api',api,'--mode',mode,'--index',str(index),'--out',str(home/'evaluation'/api/mode/('%03d'%index))],stdout=f,stderr=subprocess.STDOUT).returncode
            summary=home/'evaluation'/api/mode/('%03d'%index)/'summary.json'
            if summary.exists():record.update(load(summary))
        else:record.update(state='environment_or_driver_failure',receipt_present=receipt.exists())
        return record
    for mode in seal['modes']:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers)as pool:
            futures=[pool.submit(launch,t,mode)for t in tasks]
            for future in concurrent.futures.as_completed(futures):
                try:r=future.result()
                except Exception as e:r={'state':'driver_exception','error':str(e)}
                results.append(r);save(home/'matrix-progress.json',{'complete':False,'mode':mode,'results':results});print(r,flush=True)
    save(home/'matrix-progress.json',{'complete':True,'results':results,'no_performance':True})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);p.add_argument('--agent-build',type=Path,required=True);p.add_argument('--workers',type=int,default=6);a=p.parse_args();run(a.home.resolve(),a.agent_build.resolve(),a.workers)
