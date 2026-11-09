"""Fresh normal provenance process; never imports or executes the oracle."""
import argparse,resource,time
from pathlib import Path
from run_unrelated_work_scaling import H,load,save

def run(trial,task,tier,mode):
 out=trial/'normal-offline';out.mkdir(exist_ok=False);started=time.perf_counter();cpu=time.process_time();phases={};cpu_phases={}
 def timed(name,fn):
  t=time.perf_counter();c=time.process_time();r=fn();phases[name]=time.perf_counter()-t;cpu_phases[name]=time.process_time()-c;return r
 cases=load(trial/'warmup.json')['requests']+load(trial/'measure.json')['requests'];path='/target'if task=='controlled'else'/data/expiresIn'
 if mode in('full','selective'):
  import json
  from infer_distributed_fields import Reconstruction
  # Use exactly the normal capture guard also used by Reconstruction; no
  # hand-created partial event set or independent oracle in this worker.
  def decode():
   return [json.loads(l)for l in(trial/'capture/events.jsonl').read_text().splitlines()]
  rows=timed('decode',decode)
  plan=H/'controlled-build-04'/tier/'plan.json'if task=='controlled'else H/'mall-plan.json'
  (out/'build/role').mkdir(parents=True);(out/'capture/role').mkdir(parents=True);(out/'build/role/plan.json').write_bytes(plan.read_bytes());(out/'capture/role/events.jsonl').symlink_to((trial/'capture/events.jsonl').resolve())
  g=timed('reconstruct_including_required_integrity_and_certificates',lambda:Reconstruction(out/'build',out/'capture',['role'],decoded_rows={'role':rows}))
  answers=timed('query',lambda:[g.query(c['message'],path,'role',boundary=[{'kind':'binding-source'},{'kind':'argument'}])for c in cases])
 else:
  from run_mirror_capability_probe import read_events,native_answer
  view=out/'native-view';view.mkdir();(view/'role').symlink_to((trial/'capture').resolve(),target_is_directory=True)
  rows=timed('decode_validate_bind',lambda:read_events(view,'role'))
  answers=timed('native_tag_decode_query',lambda:[native_answer(rows,c['message'],path)for c in cases])
 timed('export',lambda:save(out/'answers.json',answers))
 summary={'targets':len(answers),'wall_seconds':time.perf_counter()-started,'cpu_seconds':time.process_time()-cpu,'phases_seconds':phases,'phase_cpu_seconds':cpu_phases,'VmHWM_KiB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'independent_oracle_executed':False,'profiler':False,'fresh_exec':True}
 save(out/'summary.json',summary)
 # Outside measured time: exact prediction consistency with separate audit.
 assert answers==load(trial/'audit/answers.json'),'Normal prediction differs from independent audit prediction'
 save(out/'prediction-equivalence.json',{'exact_all_answers':True,'checks_not_in_normal_cost':True})
 print(summary)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--trial',type=Path,required=True);p.add_argument('--task',required=True);p.add_argument('--tier',required=True);p.add_argument('--mode',required=True);a=p.parse_args();run(a.trial.resolve(),a.task,a.tier,a.mode)
