#!/usr/bin/env python3
"""Capability audit gates all subsequent live cost measurements."""
import argparse,subprocess,sys,time
from pathlib import Path
from run_planned_service import HERE,load,save,sha


def run(capability,cost):
    deadline=time.monotonic()+7200
    while time.monotonic()<deadline:
        p=capability/'worker-status.json'
        if p.exists()and load(p).get('complete'):
            assert all(v==0 for v in load(p)['workers'].values());break
        time.sleep(3)
    else:raise RuntimeError('Capability workers did not close; no cost samples allowed')
    commands=[[sys.executable,str(HERE/'audit_transport_observation_revision.py'),'--root',str(capability),'--out',str(capability/'capability-audit')]]
    commands.extend([sys.executable,str(HERE/'run_transport_cart_cost.py'),'--root',str(cost),'--stage',s]for s in ('calibrate','run','memory','planning'))
    commands.append([sys.executable,str(HERE/'audit_transport_cart_cost.py'),'--root',str(cost)])
    for i,cmd in enumerate(commands):
        home=capability if i==0 else cost;log=home/'logs'/f'pipeline-{i:02d}.log';save(home/'pipeline-last-command.json',{'index':i,'command':cmd,'driver_sha256':sha(Path(__file__))})
        print({'starting':i,'command':cmd,'log':str(log)},flush=True)
        with log.open('w')as f:subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,check=True)
    save(cost/'pipeline-complete.json',{'all_passed':True,'no_cost_before_capability_pass':True,'driver_sha256':sha(Path(__file__))})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--capability',type=Path,required=True);p.add_argument('--cost',type=Path,required=True);a=p.parse_args();run(a.capability.resolve(),a.cost.resolve())
