#!/usr/bin/env python3
"""Exact old/new full captures; independent raw-fact scoring and phase timings."""
import argparse,json,os,random,resource,subprocess,sys,time
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];sys.path.append(str(ROOT/'scripts'))
from run_frozen_zlt_reuse import load,save,sha
OLD=ROOT/'artifacts/frozen-locality-cost-20261030'
MALL=ROOT/'artifacts/source-locality-effects-20261030/final-mall-03'

def worker(trial,out,mode):
 if mode=='mirrortaint':
  from measure_frozen_common_offline import mt_worker
  return mt_worker(trial,out)
 from infer_distributed_fields import Reconstruction
 import external_transfer_oracle as oracle
 out.mkdir(parents=True,exist_ok=False);times={};start=time.perf_counter();t=time.perf_counter()
 rows=oracle.raw(trial/'capture/events.jsonl');oracle.require_complete_raw_capture(rows);times['decode']=time.perf_counter()-t
 b=out/'build/mall-admin';b.mkdir(parents=True);(b/'plan.json').write_bytes((MALL/'planning-first/mall-swarm-3/002-plan.json').read_bytes());c=out/'capture/mall-admin';c.mkdir(parents=True);(c/'events.jsonl').symlink_to((trial/'capture/events.jsonl').resolve())
 t=time.perf_counter();g=Reconstruction(out/'build',out/'capture',['mall-admin'],decoded_rows={'mall-admin':rows});times['reconstruction']=time.perf_counter()-t
 cases=load(trial/'warmup.json')['requests']+load(trial/'measure.json')['requests'];answers=[];t=time.perf_counter()
 for c in cases:answers.append((c,g.query(c['message'],'/data/expiresIn','mall-admin',boundary=[{'kind':'binding-source'},{'kind':'argument'},{'kind':'http-json','direction':'response','phase':'read'}])))
 times['query']=time.perf_counter()-t;t=time.perf_counter();save(out/'answers.json',[{'case':c['case'],'answer':a}for c,a in answers]);times['export']=time.perf_counter()-t
 t=time.perf_counter();index=oracle.RawFactIndex(rows);scored=[];prior={r['case']:r for r in load(trial/'offline-fresh/scores.json')}
 for c,a in answers:
  ret=index.returns.get(c['message'],[]);assert len(ret)==1
  want={tuple(v)for v in oracle.tf_expected(rows,ret[0],{'kind':'rpc-field','api':'mall-swarm-3','rpc_owner':'AuthService'},'/data/expiresIn',raw_index=index)}
  got={(s.get('callee'),s.get('root_frame'),s['seq'],s.get('path'),s['owner'],s['field'],s['version'])for s in a['sources']}
  assert want and a['known']and got==want and {tuple(v)for v in prior[c['case']]['actual']}==got
  assert a['target']['observed']['value']==c['response']['data']['expiresIn']and c['business_passed']
  scored.append({'case':c['case'],'known':a['known'],'expected':sorted(want,key=str),'actual':sorted(got,key=str)})
 times['independent_score']=time.perf_counter()-t;save(out/'scores.json',scored)
 save(out/'summary.json',{'correct':len(scored),'targets':len(scored),'normalized_signatures_equal':True,'phases_seconds':times,'core_seconds':times['reconstruction']+times['query'],'wall_seconds':time.perf_counter()-start,'VmHWM_KiB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'oracle_uses_raw_facts_only':True})

def run(home):
 out=home/'paired-cost';out.mkdir(exist_ok=False);cpu=min(os.sched_getaffinity(0));jobs=[]
 rng=random.Random(311026)
 for r in range(1,6):
  for mode in('full','selective','mirrortaint'):
   versions=['old','indexed'];rng.shuffle(versions)
   for v in versions:jobs.append((r,mode,v))
 save(out/'protocol-before-runs.json',{'jobs':jobs,'logical_cpu':cpu,'fresh_exec':True,'profiler':False,'driver_sha256':sha(Path(__file__)),'old_snapshot':'old-repository','indexed_snapshot':'indexed-repository','offline_only':True,'no_online_metric_changed':True})
 results=[]
 for repeat,mode,version in jobs:
  trial=OLD/('round-%02d-%s'%(repeat,mode));d=out/('round-%02d-%s-%s'%(repeat,mode,version));repo=home/('old-repository'if version=='old'else'indexed-repository');script=repo/'experiments/sockshop-mirrortaint'/('measure_frozen_common_offline.py'if version=='old'else'run_offline_index_revision.py')
  before=resource.getrusage(resource.RUSAGE_CHILDREN);started=time.perf_counter()
  with(out/(d.name+'.log')).open('w')as f:subprocess.run(['taskset','-c',str(cpu),sys.executable,str(script),'worker','--home',str(trial),'--out',str(d),'--mode',mode],stdout=f,stderr=subprocess.STDOUT,check=True)
  after=resource.getrusage(resource.RUSAGE_CHILDREN);result=load(d/'summary.json');assert result['correct']==result['targets']==180
  result.update(repeat=repeat,mode=mode,version=version,process_wall_seconds=time.perf_counter()-started,process_cpu_seconds=after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime);save(d/'process.json',result);results.append(result);save(out/'progress.json',{'results':results});print(repeat,mode,version,round(result['process_wall_seconds'],4),flush=True)
 save(out/'results.json',{'complete':True,'measurements':results})
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('stage',choices=['worker','run']);p.add_argument('--home',required=True,type=Path);p.add_argument('--out',type=Path);p.add_argument('--mode');a=p.parse_args()
 if a.stage=='run':run(a.home.resolve())
 else:worker(a.home.resolve(),a.out.resolve(),a.mode)
