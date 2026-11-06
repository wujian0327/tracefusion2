"""Same complete capture, separate decode/reconstruction/query/raw-oracle/export stages."""
import argparse,cProfile,hashlib,json,os,pickle,random,resource,subprocess,sys,time
from pathlib import Path

def worker(protocol,task,mode,repo,out,profile=False):
 sys.path.insert(0,str(repo/'experiments/sockshop-mirrortaint'));sys.path.insert(1,str(repo/'scripts'))
 from run_planned_service import load,save,sha
 from infer_distributed_fields import Reconstruction
 from infer_response_binding import matches
 import external_transfer_oracle as oracle
 from audit_zlt_foundation_revision import tf_pair
 out.mkdir(parents=True,exist_ok=False);spec=load(protocol)['tasks'][task][mode];cap=Path(spec['capture']);planfile=Path(spec['plan']);assert sha(cap)==spec['capture_sha256']and sha(planfile)==spec['plan_sha256'];role=spec['role'];stages={};start=time.perf_counter()
 def execute():
  t=time.perf_counter();rows=oracle.raw(cap);oracle.require_complete_raw_capture(rows);plan=load(planfile);stages['decode']=time.perf_counter()-t
  b=out/'build'/role;b.mkdir(parents=True);(b/'plan.json').write_bytes(planfile.read_bytes());c=out/'capture'/role;c.mkdir(parents=True);(c/'events.jsonl').symlink_to(cap)
  t=time.perf_counter();g=Reconstruction(out/'build',out/'capture',[role],decoded_rows={role:rows});stages['reconstruction']=time.perf_counter()-t
  returns=[r for r in rows if r['kind']=='binding-return'];targets=[(r,f)for r in returns for f in r['fields']if matches(plan['response_binding']['path'],f['path'])];answers=[];t=time.perf_counter()
  for ret,f in targets:answers.append(g.query(ret['message'],f['path'],role,boundary=[{'kind':'binding-source'},{'kind':'argument'}]))
  stages['query']=time.perf_counter()-t;t=time.perf_counter();index=oracle.RawFactIndex(rows);paired=set();scores=[]
  for (ret,f),a in zip(targets,answers):
   sources=[s for s in index.source_family(ret['frame'])if s.get('callee')in plan['response_binding']['source_calls']];want=[]
   for s in sources:
    if s['seq']not in paired:tf_pair(rows,s);paired.add(s['seq'])
    want.extend((s['callee'],s['frame'],s['seq'],v['path'],v['owner'],v['field'],v['version'])for v in s['fields']if all(v.get(k)==f.get(k)for k in('owner','field','version')))
   got=[(s.get('callee'),s.get('root_frame'),s['seq'],s.get('path'),s['owner'],s['field'],s['version'])for s in a['sources']];assert len(want)==1 and a['known']and set(got)==set(want)
   scores.append({'message':ret['message'],'path':f['path'],'expected':want,'predicted':got,'known':a['known']})
  stages['raw_fact_index_and_independent_score']=time.perf_counter()-t;t=time.perf_counter();save(out/'answers.json',answers);save(out/'scores.json',scores)
  with(out/'graph.pkl').open('wb')as f:pickle.dump((g.nodes,g.edges,g.local_queries),f,protocol=4)
  stages['export']=time.perf_counter()-t
  return len(targets)
 if profile:
  profiler=cProfile.Profile();count=profiler.runcall(execute);profiler.dump_stats(str(out/'profile.pstats'))
 else:count=execute()
 save(out/'summary.json',{'task':task,'mode':mode,'targets':count,'correct':count,'phases_seconds':stages,'pipeline_wall_seconds':time.perf_counter()-start,'VmHWM_KiB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'complete_capture_sha256':spec['capture_sha256'],'profile':profile})

def run(home,new_repo):
 out=home/'offline-paired';out.mkdir(exist_ok=False);cpu=min(os.sched_getaffinity(0));rng=random.Random(61106);jobs=[]
 for repeat in range(1,6):
  for task in('zlt-user','ruoyi-dictionary'):
   for mode in('full','selective'):
    versions=['old','new'];rng.shuffle(versions)
    jobs.extend((repeat,task,mode,v)for v in versions)
 (out/'order.json').write_text(json.dumps({'cpu':cpu,'jobs':jobs,'profiler':False},indent=2)+'\n');records=[]
 for repeat,task,mode,version in jobs:
  d=out/('%02d-%s-%s-%s'%(repeat,task,mode,version));repo=home/'old-repository'if version=='old'else new_repo;t=time.perf_counter();before=resource.getrusage(resource.RUSAGE_CHILDREN)
  with(out/(d.name+'.log')).open('w')as log:subprocess.run(['taskset','-c',str(cpu),sys.executable,__file__,'worker','--home',str(home),'--task',task,'--mode',mode,'--repo',str(repo),'--out',str(d)],check=True,stdout=log,stderr=subprocess.STDOUT)
  after=resource.getrusage(resource.RUSAGE_CHILDREN);r=json.loads((d/'summary.json').read_text());r.update(repeat=repeat,version=version,process_wall_seconds=time.perf_counter()-t,process_cpu_seconds=after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime);records.append(r);(out/'progress.json').write_text(json.dumps(records,indent=2)+'\n')
 for repeat in range(1,6):
  for task in('zlt-user','ruoyi-dictionary'):
   for mode in('full','selective'):
    ds=[out/('%02d-%s-%s-%s'%(repeat,task,mode,v))for v in('old','new')]
    assert json.loads((ds[0]/'answers.json').read_text())==json.loads((ds[1]/'answers.json').read_text())
    with(ds[0]/'graph.pkl').open('rb')as f:a=pickle.load(f)
    with(ds[1]/'graph.pkl').open('rb')as f:b=pickle.load(f)
    assert a==b
 (out/'results.json').write_text(json.dumps({'records':records,'answers_full_graph_and_root_audits_equal':True},indent=2)+'\n')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('stage',choices=('worker','run'));p.add_argument('--home',type=Path,required=True);p.add_argument('--task');p.add_argument('--mode');p.add_argument('--repo',type=Path);p.add_argument('--out',type=Path);p.add_argument('--profile',action='store_true');a=p.parse_args()
 if a.stage=='run':run(a.home.resolve(),a.repo.resolve())
 else:worker(a.home.resolve()/'protocol-before-change.json',a.task,a.mode,a.repo.resolve(),a.out.resolve(),a.profile)
