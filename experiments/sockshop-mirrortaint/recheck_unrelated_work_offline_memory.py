"""Uniform same-capture meter correction, after online measurements only.
Keep ru_maxrss (which may inherit a pre-exec high water mark) and read actual
/proc/self/status VmHWM in a new fresh-exec for every instrumented capture.
No provenance code, necessary check, prediction, or online metric is changed.
"""
import json,os,random,resource,subprocess,sys,time
from pathlib import Path
from run_unrelated_work_scaling import H,HERE,ROOT,load,save,sha,verify

def run():
 verify();assert load(H/'formal-complete.json')['passed'];out=H/'offline-proc-memory-recheck';out.mkdir(exist_ok=False)
 old=HERE/'measure_unrelated_work_offline.py';assert sha(old)==load(H/'formal-code-seal-before-timing.json')['files'][str(old)]
 text=old.read_text().replace("trial/'normal-offline'","trial/'normal-offline-proc'")
 needle="'VmHWM_KiB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss"
 assert needle in text
 text=text.replace(needle,"'inherited_or_current_ru_maxrss_KiB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'VmHWM_KiB':int(next(line.split()[1]for line in Path('/proc/self/status').read_text().splitlines()if line.startswith('VmHWM:')))")
 first=text.index(' # Outside measured time:');last=text.index(' print(summary)',first)
 text=text[:first]+text[last:] # Comparison belongs to independent experiment validation, not production cost.
 worker=out/'worker.py';worker.write_text(text)
 jobs=[j for j in load(H/'formal-order-before-timing.json')['jobs']if j['mode']!='original'];random.Random(2026110918).shuffle(jobs)
 save(out/'protocol-before-recheck.json',{'worker_sha256':sha(worker),'source_meter_sha256':sha(old),'only_changes':['new output directory','explicit /proc/self/status VmHWM plus unchanged ru_maxrss diagnostic','experimental answer comparison outside measured child process'],'all_required_checks_retained':True,'entire_same_captures':True,'jobs':jobs,'logical_cpu':min(os.sched_getaffinity(0)),'new_Agent_deployment':False,'old_online_and_offline_files_unchanged':True,'no_profiler':True})
 for j in jobs:
  trial=H/'formal'/('%02d-%s-%s-%s'%(j['round'],j['task'],j['tier'],j['mode']));env={**os.environ,'PYTHONPATH':str(HERE)}
  cmd=['taskset','-c',str(min(os.sched_getaffinity(0))),sys.executable,str(worker),'--trial',str(trial),'--task',j['task'],'--tier',j['tier'],'--mode',j['mode']]
  before=resource.getrusage(resource.RUSAGE_CHILDREN);start=time.perf_counter()
  with(trial/'normal-offline-proc-process.log').open('w')as f:subprocess.run(cmd,env=env,stdout=f,stderr=subprocess.STDOUT,check=True)
  after=resource.getrusage(resource.RUSAGE_CHILDREN);save(trial/'normal-offline-proc-process.json',{'wall_seconds':time.perf_counter()-start,'cpu_seconds':after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime,'fresh_exec':True,'includes_process_start_and_imports':True,'logical_cpu':min(os.sched_getaffinity(0))})
  answers=load(trial/'normal-offline-proc/answers.json');assert answers==load(trial/'normal-offline/answers.json')==load(trial/'audit/answers.json')
  save(trial/'normal-offline-proc/prediction-equivalence.json',{'exact_all_answers':True,'checked_after_timed_child_process':True})
 save(out/'complete.json',{'captures':len(jobs),'all_predictions_equal':True,'uniform_proc_meter_for_all_arms_and_rounds':True});print('RECHECK COMPLETE',len(jobs))

if __name__=='__main__':run()
