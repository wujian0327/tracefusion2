"""Separate independent-scoring optimization from old/new reconstruction costs."""
import argparse,json,os,random,resource,subprocess,sys,time
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save

def run(home):
 assert load(home/'measurement-complete.json')['complete']and(home/'strict-online-overrides.json').exists()
 protocol=home/'offline-standard-volume/protocol-before-change.json';out=home/'indexed-oracle-paired';out.mkdir(exist_ok=False);rng=random.Random(61107);cpu=min(os.sched_getaffinity(0));jobs=[]
 for group in('score-only','combined-core'):
  for repeat in range(1,6):
   for task in('zlt-user','ruoyi-dictionary'):
    for mode in('full','selective'):
     versions=['old','new'];rng.shuffle(versions);jobs.extend((group,repeat,task,mode,v)for v in versions)
 save(out/'protocol-before-runs.json',{'jobs':jobs,'cpu':cpu,'source_protocol':str(protocol),'profiler':False,'score_only':'Same reconstruction version; compare original raw validator on whole rows versus indexed candidate rows.','combined_core':'Same indexed independent scorer for both old/new reconstruction versions.','no_online_deployment':True})
 records=[]
 for group,repeat,task,mode,version in jobs:
  name='%s-%02d-%s-%s-%s'%(group,repeat,task,mode,version);d=out/name;indexed=group=='combined-core'or version=='new';repo=home/'old-repository'if group=='combined-core'and version=='old'else ROOT
  cmd=['taskset','-c',str(cpu),sys.executable,str(HERE/('measure_indexed_raw_oracle.py'if indexed else'measure_shared_work_revision.py'))]
  if not indexed:cmd.append('worker')
  cmd+=['--home',str(home),'--protocol',str(protocol),'--task',task,'--mode',mode,'--repo',str(repo),'--out',str(d)]
  start=time.perf_counter();before=resource.getrusage(resource.RUSAGE_CHILDREN)
  with(out/(name+'.log')).open('w')as f:subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,check=True)
  after=resource.getrusage(resource.RUSAGE_CHILDREN);r=load(d/'summary.json');r.update(group=group,repeat=repeat,version=version,indexed_independent_score=indexed,process_wall_seconds=time.perf_counter()-start,process_cpu_seconds=after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime);records.append(r);save(out/'progress.json',records)
 for group in('score-only','combined-core'):
  for repeat in range(1,6):
   for task in('zlt-user','ruoyi-dictionary'):
    for mode in('full','selective'):
     ds=[out/('%s-%02d-%s-%s-%s'%(group,repeat,task,mode,v))for v in('old','new')]
     assert load(ds[0]/'answers.json')==load(ds[1]/'answers.json')and load(ds[0]/'scores.json')==load(ds[1]/'scores.json')
 save(out/'results.json',{'records':records,'all_answers_and_independent_coordinates_equal':True,'core_optimization_separate_from_score_optimization':True})

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);run(p.parse_args().home.resolve())
