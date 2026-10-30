#!/usr/bin/env python3
"""Fresh processes for the exact frozen Mall plan; no Agent compilation."""
import argparse,json,os,resource,subprocess,sys,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
from run_frozen_locality_cost import MALL,verify
from run_planned_service import load,save,sha

def worker(out):
 from plan_capability_policy import choose
 start=time.perf_counter();cpu=time.process_time();q=load(MALL/'planning-first/mall-swarm-3/002.json')['query'];m=load(MALL/'metadata/mall-admin/model.json');d=load(MALL/'deployment-environment.json');plan,route=choose(m,q,deployment=d)
 expected=load(MALL/'planning-first/mall-swarm-3/002-plan.json');assert plan==expected,'Planning differs from deployed plan'
 save(out,{'plan_identical':True,'wall_seconds':time.perf_counter()-start,'cpu_seconds':time.process_time()-cpu,'VmHWM_KiB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'plan_sha256':sha(MALL/'planning-first/mall-swarm-3/002-plan.json')})

def run(home):
 verify();out=home/'static-planning';out.mkdir(exist_ok=False);cpu=min(os.sched_getaffinity(0));results=[]
 for i in range(5):
  p=out/('repeat-%02d.json'%i);start=time.perf_counter();before=resource.getrusage(resource.RUSAGE_CHILDREN)
  subprocess.run(['taskset','-c',str(cpu),sys.executable,__file__,'worker','--home',str(p)],check=True)
  after=resource.getrusage(resource.RUSAGE_CHILDREN);r=load(p);r.update(process_wall_seconds=time.perf_counter()-start,process_cpu_seconds=after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime);results.append(r)
 save(out/'summary.json',{'repeats':results,'logical_cpu':cpu,'fresh_process':True,'OS_page_cache_flushed':False,'compile_and_deploy_excluded':True,'driver_sha256':sha(Path(__file__))});print(results)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('stage',choices=['worker','run']);p.add_argument('--home',type=Path,required=True);a=p.parse_args();(worker if a.stage=='worker'else run)(a.home.resolve())
