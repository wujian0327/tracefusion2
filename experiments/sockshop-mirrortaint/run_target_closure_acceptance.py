"""One frozen-candidate capability pass, two nonconflicting deployment lanes.

No timed trials; failed jobs remain and independent cohorts continue. Nothing
here plans a sealed external application query.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import datetime
import json
from pathlib import Path
import subprocess
import sys
import threading
from run_planned_service import HERE,load,save,sha


def run(root):
    root=root.resolve();home=root.parent;out=home/'capability-pass-01';out.mkdir(exist_ok=False)
    freeze=load(root/'historical/algorithm-freeze.json')
    for p,h in freeze['sources'].items():assert sha(Path(p))==h
    assert load(root/'target-closure-candidate.json')['commit']==freeze['commit']
    history=root/'historical';base=history/'frozen-base'
    def command(script,*args):return [sys.executable,str(HERE/script),*map(str,args)]
    def old(stage,name):return command('run_account_semantics_revision.py','--root',history,'--stage',stage,'--worker',name)
    lane_a=[('62-orders',old('worker62','orders')),('62-cart',old('worker62','cart')),
            ('62-pair',old('worker62','pair')),('29-orders',old('fields29','orders')),
            ('Mall103',command('run_mall_applicability_matrix.py','--home',root/'mall','--agent-build',base,'--workers',1)),
            ('ZLT15',command('run_zlt_slice_revision.py','zlt','--root',root))]
    lane_b=[('62-reads',old('worker62','reads')),('62-route',old('worker62','route')),
            ('62-travel',old('worker62','travel')),('29-train',old('fields29','train')),
            ('15-route',old('writes','route')),('15-price',old('writes','price')),
            ('Account40',command('run_account_semantics_revision.py','--root',history,'--stage','account'))]
    save(out/'protocol-before-runs.json',{'candidate':freeze['commit'],'core_sources':freeze['sources'],
         'driver_sha256':sha(Path(__file__)),'lanes':{'A':lane_a,'B':lane_b},
         'fresh_captures':True,'cost_trials':False,'failures_preserved':True})
    results={};lock=threading.Lock()
    def record(name,state,**data):
        row={'name':name,'state':state,'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),**data}
        with lock:
            results[name]=row;save(out/'progress.json',{'complete':False,'jobs':results})
            with(out/'journal.jsonl').open('a')as f:f.write(json.dumps(row)+'\n')
        print(row,flush=True)
    def job(name,args):
        record(name,'started')
        with(out/(name+'.log')).open('w')as f:
            process=subprocess.run(args,stdout=f,stderr=subprocess.STDOUT)
        record(name,'completed'if process.returncode==0 else'failed',returncode=process.returncode)
        return process.returncode
    def lane(jobs):
        for name,args in jobs:job(name,args)
    with ThreadPoolExecutor(max_workers=2)as pool:
        futures=[pool.submit(lane,lane_a),pool.submit(lane,lane_b)]
        for future in futures:future.result()
    audits=[('audit-Mall',command('audit_zlt_body_candidate.py','mall','--root',root,'--out',out/'audit-mall')),
            ('audit-ZLT',command('audit_zlt_slice_completion.py','--root',root,'--out',out/'audit-zlt')),
            ('audit-historical',command('audit_zlt_body_candidate.py','historical','--root',root,'--out',out/'audit-historical'))]
    for name,args in audits:job(name,args)
    for p,h in freeze['sources'].items():assert sha(Path(p))==h
    passed=all(r.get('returncode')==0 for r in results.values())
    save(out/'summary.json',{'complete':True,'passed':passed,'jobs':results,
         'algorithm':freeze['commit'],'agent_sha256':sha(base/'distributed-observer.jar'),
         'new_app_first_queries_executed':False,'online_performance_experiment':False})
    print('CAPABILITY PASS COMPLETE',passed,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);run(parser.parse_args().root)
