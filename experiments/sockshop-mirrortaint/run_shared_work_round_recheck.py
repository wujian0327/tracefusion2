"""Clean replacement of the entire explicitly affected task/round; retain originals."""
import argparse,subprocess,sys
from pathlib import Path
from run_planned_service import HERE,load,save,sha

def run(home):
 assert load(home/'measurement-complete.json')['complete']
 out=home/'online-round1-recheck';out.mkdir(exist_ok=False)
 jobs=[j for j in load(home/'online-paired/order-before-runs.json')['jobs']if j[0]==1 and j[1]=='zlt-user'];assert len(jobs)==4
 save(out/'protocol-before-runs.json',{'jobs':jobs,'interference':load(home/'measurement-interference.json'),'same_original_random_order':True,'warmup_seconds':30,'measure_seconds':60,'rps':2,'concurrency':2,'no_probe_or_profiler':True})
 overrides={}
 for repeat,task,version,mode in jobs:
  name='%02d-%s-%s-%s'%(repeat,task,version,mode);d=out/name
  cmd=[sys.executable,str(HERE/'run_shared_work_business.py'),'trial','--home',str(home),'--out',str(d),'--task',task,'--version',version,'--mode',mode]
  with(out/(name+'.log')).open('w')as f:subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,check=True)
  overrides[name]=str(d);save(out/'progress.json',overrides)
 save(home/'strict-online-overrides.json',{'overrides':overrides,'reason':load(home/'measurement-interference.json'),'initial_round_not_deleted':True,'replacement_full_task_round':True})
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);run(p.parse_args().home.resolve())
