#!/usr/bin/env python3
"""Fresh-process planning with exactly the deployed structural routing policy."""
import argparse
import os
from pathlib import Path
import random
import subprocess
import sys
import time
from run_planned_service import load, save, sha
from plan_capability_policy import choose
from plan_date_projection import attach_date_projection
import measure_static_planning as previous


def worker(out, base, kind):
    original = previous.augment
    def augment(model, plan):
        p = attach_date_projection(original(model, plan), model)
        p['source_evidence'] = True
        return p
    previous.augment = augment
    q = previous.query(kind) if kind != 'price' else None
    if q:
        previous.plan_response = lambda model, *a, **kw: choose(model, q)[0]
    previous.worker(out, base, kind)


def run(root):
    out=root/'static-planning';out.mkdir();cpu=min(os.sched_getaffinity(0));jobs=[(r,k) for r in range(1,6) for k in ('cart','train','price')];random.Random(221023).shuffle(jobs);results=[]
    save(out/'protocol.json',{'order':jobs,'cpu':cpu,'fresh_process':True,'RSS':'15ms samples, summed process tree; shared pages may be repeated','OS_cache_flushed':False,'source_sha256':sha(Path(__file__))})
    for repeat,kind in jobs:
        d=out/(f'round-{repeat:02d}-'+kind);d.mkdir()
        cmd=['taskset','-c',str(cpu),sys.executable,str(Path(__file__).resolve()),'worker','--root',str(root),'--out',str(d),'--kind',kind]
        start=time.monotonic_ns();peak=0;samples=0
        with (d/'worker.log').open('w') as log:
            p=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,env={**os.environ,'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1'})
            while p.poll() is None:
                peak=max(peak,previous.tree_rss(p.pid));samples+=1;time.sleep(.015)
        if p.returncode:raise ValueError('Planning failed: '+str(d))
        r=load(d/'worker.json');r.update(repeat=repeat,subprocess_wall_seconds=(time.monotonic_ns()-start)/1e9,process_tree_sampled_peak_rss_bytes=peak,rss_samples=samples)
        save(d/'measurement.json',r);results.append(r)
    save(out/'results.json',{'all_passed':True,'measurements':results})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=('run','worker'));p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path);p.add_argument('--kind',choices=('cart','train','price'));a=p.parse_args();root=a.root.resolve()
    if a.stage=='worker':worker(a.out.resolve(),root/(a.kind+'-build'),a.kind)
    else:run(root)
