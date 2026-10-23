#!/usr/bin/env python3
"""Continue capability workers after the separate Orders worker has closed."""
import argparse,json,subprocess,sys,time,os,signal
from pathlib import Path
from run_planned_service import HERE,load,save,sha


def run(root):
    deadline=time.monotonic()+3600
    while time.monotonic()<deadline:
        p=root/'all62-orders-serial/results.json'
        if p.exists()and load(p).get('complete'):break
        time.sleep(3)
    else:raise RuntimeError('Orders worker did not close; no other workers started')
    jobs=[]
    try:
        for name in ('reads','route','travel','cart','pair'):
            log=(root/'logs'/('06-all62-'+name+'-first.log')).open('w');cmd=[sys.executable,str(HERE/'run_transport_observation_revision.py'),'--root',str(root),'--stage','worker','--worker',name];p=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);jobs.append((name,p,log));print({'started':name,'pid':p.pid},flush=True)
        while any(p.poll()is None for _,p,_ in jobs):
            save(root/'worker-status.json',{'workers':{n:p.poll()for n,p,_ in jobs},'orchestrator_sha256':sha(Path(__file__))});time.sleep(3)
        codes={n:p.returncode for n,p,_ in jobs};save(root/'worker-status.json',{'complete':True,'workers':codes,'orchestrator_sha256':sha(Path(__file__))});assert all(c==0 for c in codes.values()),codes
    finally:
        for _,p,f in jobs:
            if p.poll()is None:os.killpg(p.pid,signal.SIGINT);p.wait(timeout=180)
            f.close()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);run(p.parse_args().root.resolve())
