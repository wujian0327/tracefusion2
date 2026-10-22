#!/usr/bin/env python3
"""Frozen all-62 source acceptance, using existing inputs and independent oracle."""
import argparse,subprocess,sys,os,time,signal,shutil
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save,sha
from run_remaining_semantics_revision import prepare as build_candidate
import run_quota_capability_acceptance as quota
import run_frozen_capability_acceptance as driver

PARENT=ROOT/'artifacts/library-gap-revision-20261022'

def prepare(root):
    build_candidate(root);f=load(root/'algorithm-freeze.json');prior=load(quota.PARENT/'quota-all62/algorithm-freeze.json');commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    for key in ('acceptance_protocol_sha256','protocol_sha256'):f[key]=prior[key]
    f.update(commit=commit,algorithm_commit=commit,experiment_commit=commit,builder_sha256=sha(HERE/'build_distributed_plans.py'),planning_sha256=sha(root/'frozen-plans/planning.json'),runtime_policy=prior['runtime_policy'],source_coordinate_revision='HTTP field graph retains actual raw frame; TicketInfo oracle no longer deliberately drops it',original_runtime_library_caveat='Actual parent-loaded Agent Jackson definitions differ from original application bundled classes; both hashes disclosed; not a native-runtime or new cost comparison')
    f['oracle_sources']={str(HERE/n):sha(HERE/n)for n in ['run_frozen_capability_acceptance.py','run_response_binding_revision.py','run_execution_kernel_pilot.py','run_sockshop_model_revision.py','normalize_orders_origins.py']};save(root/'algorithm-freeze.json',f)
    (root/'drivers').mkdir();(root/'logs').mkdir()
    for n in ['run_library_gap_acceptance.py','run_quota_capability_acceptance.py','run_frozen_capability_acceptance.py','run_cart_reread_baseline_pair.py']:(root/'drivers'/('cart-pair-library-driver-at-launch.py'if n=='run_cart_reread_baseline_pair.py'else n)).write_bytes((HERE/n).read_bytes())
    save(root/'protocol-before-business.json',{'commit':commit,'queries':len(driver.QUERIES),'input_reference':'original 62/431 development comparison','modes':['full','selective'],'orders':'serial, first; preserve every failure','other_workers':'independent ports and volumes; no cost estimation','heldout29':'not opened','oracle_sources':f['oracle_sources'],'runtime_policy':f['runtime_policy'],'no_result_replacement':True})

def worker(root,name):quota.worker(root,name)

def run(root):
    worker(root,'orders');jobs=[]
    try:
        for name in ('reads','route','travel','cart','pair'):
            log=(root/'logs'/(name+'.log')).open('w');cmd=[sys.executable,str(Path(__file__).resolve()),'--root',str(root),'--worker',name];proc=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);jobs.append((name,proc,log));print({'started':name,'pid':proc.pid},flush=True)
        while any(p.poll()is None for _,p,_ in jobs):save(root/'worker-status.json',{'workers':{n:p.poll()for n,p,_ in jobs}});time.sleep(3)
        codes={n:p.returncode for n,p,_ in jobs};save(root/'worker-status.json',{'complete':True,'workers':codes});assert all(v==0 for v in codes.values()),codes
    finally:
        for _,p,log in jobs:
            if p.poll()is None:os.killpg(p.pid,signal.SIGINT);p.wait(timeout=180)
            log.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',required=True,type=Path);p.add_argument('--prepare',action='store_true');p.add_argument('--worker',choices=['orders','reads','route','travel','cart','pair']);a=p.parse_args();root=a.root.resolve()
    if a.prepare:prepare(root)
    elif a.worker:worker(root,a.worker)
    else:run(root)
