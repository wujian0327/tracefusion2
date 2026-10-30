#!/usr/bin/env python3
"""One normal reconstruction pass; separate independent audits from pipeline cost.

The first timing driver repeats locality validation outside Reconstruction.
Keep that audit, but do not charge it a second time as algorithm execution.
No validation inside the frozen reconstruction is removed or changed.
"""
import argparse,copy,json,random,resource,subprocess,sys,time
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];sys.path.append(str(ROOT/'scripts'))
from run_frozen_locality_cost import MALL,PATH,verify
from run_frozen_zlt_reuse import load,save,sha

def tf_worker(trial,out):
 from infer_distributed_fields import Reconstruction
 import external_transfer_oracle as oracle
 out.mkdir(parents=True,exist_ok=False);times={};start=time.perf_counter();cpu=time.process_time();t=time.perf_counter()
 rows=oracle.raw(trial/'capture/events.jsonl');oracle.require_complete_raw_capture(rows);times['decode_complete_capture']=time.perf_counter()-t
 b=out/'build/mall-admin';b.mkdir(parents=True);(b/'plan.json').write_bytes((MALL/'planning-first/mall-swarm-3/002-plan.json').read_bytes())
 c=out/'capture/mall-admin';c.mkdir(parents=True);(c/'events.jsonl').symlink_to((trial/'capture/events.jsonl').resolve())
 t=time.perf_counter();g=Reconstruction(out/'build',out/'capture',['mall-admin'],decoded_rows={'mall-admin':rows});times['graph_reconstruction_including_required_locality_validation']=time.perf_counter()-t
 cases=load(trial/'warmup.json')['requests']+load(trial/'measure.json')['requests'];answers=[];t=time.perf_counter()
 for c in cases:answers.append((c,g.query(c['message'],PATH,'mall-admin',boundary=[{'kind':'binding-source'},{'kind':'argument'},{'kind':'http-json','direction':'response','phase':'read'}])))
 times['query_restore']=time.perf_counter()-t;t=time.perf_counter();save(out/'answers.json',[{'case':c['case'],'answer':a}for c,a in answers]);times['export']=time.perf_counter()-t
 t=time.perf_counter();scored=[]
 prior={s['case']:s for s in load(trial/'offline-fresh/scores.json')}
 for c,a in answers:
  ret=[r for r in rows if r['kind']=='binding-return'and r.get('message')==c['message']];assert len(ret)==1
  want={tuple(v)for v in oracle.tf_expected(rows,ret[0],{'kind':'rpc-field','api':'mall-swarm-3','rpc_owner':'AuthService'},PATH)}
  got={(s.get('callee'),s.get('root_frame'),s['seq'],s.get('path'),s['owner'],s['field'],s['version'])for s in a['sources']}
  assert want and a['known']and want==got and c['business_passed']and a['target']['observed']['value']==c['response']['data']['expiresIn']
  assert {tuple(v)for v in prior[c['case']]['expected']}==want and {tuple(v)for v in prior[c['case']]['actual']}==got
  scored.append({'case':c['case'],'known':True,'exact':True,'expected':sorted(want,key=str),'actual':sorted(got,key=str)})
 times['independent_score_and_signature_check']=time.perf_counter()-t;save(out/'scores.json',scored)
 save(out/'summary.json',{'targets':len(scored),'correct':len(scored),'positive':len(scored),'phases_seconds':times,'core_seconds':times['graph_reconstruction_including_required_locality_validation']+times['query_restore'],'pipeline_wall_seconds_including_export_and_score':time.perf_counter()-start,'pipeline_cpu_seconds_including_export_and_score':time.process_time()-cpu,'VmHWM_KiB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'answers_and_instance_signatures_unchanged':True,'redundant_external_certificate_pass':False,'frozen_internal_certificate_consumer_retained':True})

def mt_worker(trial,out):
 from audit_frozen_transfer_cost import mt_offline
 out.mkdir(parents=True,exist_ok=False)
 for name in('capture','warmup.json','measure.json'):(out/name).symlink_to((trial/name).resolve(),target_is_directory=(trial/name).is_dir())
 mt_offline(out);summary=load(out/'offline-native/summary.json');save(out/'summary.json',summary)

def run(home):
 verify();out=home/'common-offline-single-pass';out.mkdir(exist_ok=False);jobs=[p for p in sorted(home.glob('round-*'))if p.is_dir()and not p.name.endswith('original')];assert len(jobs)==15
 random.Random(30102027).shuffle(jobs);save(out/'protocol-before-runs.json',{'order':[p.name for p in jobs],'driver_sha256':sha(Path(__file__)),'reason':'Keep the separate strict audit, remove only its duplicate invocation outside the frozen normal reconstruction. Source/target/answers/Agent/core and every internal certificate/completeness check unchanged. Fresh-exec for both TF and MT; scoring/export separate. Original timings retained.','source_manifest_sha256':sha(home/'common-files-before-formal.json')})
 results=[]
 for trial in jobs:
  mode=load(trial/'result.json')['mode'];d=out/trial.name;start=time.perf_counter();before=resource.getrusage(resource.RUSAGE_CHILDREN)
  with(out/(trial.name+'.log')).open('w')as log:subprocess.run([sys.executable,__file__,'worker','--home',str(trial),'--out',str(d),'--mode',mode],check=True,stdout=log,stderr=subprocess.STDOUT)
  after=resource.getrusage(resource.RUSAGE_CHILDREN);s=load(d/'summary.json');assert s['correct']==s['targets']==180
  s.update(trial=trial.name,mode=mode,round=int(trial.name.split('-')[1]),process_wall_seconds=time.perf_counter()-start,process_cpu_seconds=after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime);save(d/'process.json',s);results.append(s);save(out/'progress.json',{'complete':False,'results':results});print(trial.name,round(s['process_wall_seconds'],3),flush=True)
 save(out/'results.json',{'complete':True,'results':results});verify()
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('stage',choices=['run','worker']);p.add_argument('--home',type=Path,required=True);p.add_argument('--out',type=Path);p.add_argument('--mode');a=p.parse_args()
 if a.stage=='run':run(a.home.resolve())
 elif a.mode=='mirrortaint':mt_worker(a.home.resolve(),a.out.resolve())
 else:tf_worker(a.home.resolve(),a.out.resolve())
