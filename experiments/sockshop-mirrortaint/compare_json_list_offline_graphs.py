"""Compare complete captured graphs before accepting an offline-only slot repair."""
import argparse,importlib,json,sys,types
from pathlib import Path
from run_planned_service import load,save,sha
from infer_distributed_fields import Reconstruction

def run(home,out,groups):
 out.mkdir(parents=True,exist_ok=False);names=('infer_json_list_copy','infer_application_execution');old={};new={}
 parent=load(home/'final-candidate/historical/algorithm-freeze.json')
 for n in names:
  p=home/'final-candidate/historical/source-snapshot/experiments/sockshop-mirrortaint'/(n+'.py')
  canonical=str(Path(__file__).resolve().parent/(n+'.py'));assert sha(p)==parent['sources'][canonical]
  m=types.ModuleType(n);m.__file__=str(p);exec(compile(p.read_bytes(),str(p),'exec'),m.__dict__);old[n]=m
 for n in names:
  p=home/'offline-candidate-v2'/(n+'.py');m=types.ModuleType(n);m.__file__=str(p);exec(compile(p.read_bytes(),str(p),'exec'),m.__dict__);new[n]=m
 records=[]
 for group in groups:
  for capture in sorted((home/'final-candidate'/group).rglob('capture')):
   if not capture.is_dir():continue
   build=capture.parent/'build';roles=sorted(p.name for p in capture.iterdir()if p.is_dir()and(p/'events.jsonl').exists()and(build/p.name/'plan.json').exists())
   if not roles:continue
   digests={str(capture/r/'events.jsonl'):sha(capture/r/'events.jsonl')for r in roles};results=[]
   for modules in(old,new):
    sys.modules.update(modules)
    try:
     graph=Reconstruction(build,capture,roles);results.append(('graph',graph.nodes,graph.edges,graph.local_queries))
    except ValueError as e:results.append(('rejected',type(e).__name__,str(e)))
   assert results[0]==results[1],str(capture)
   assert all(sha(Path(p))==digest for p,digest in digests.items())
   records.append({'group':group,'capture':str(capture),'roles':roles,'complete_graph_equal':True,'node_count':len(results[0][1])if results[0][0]=='graph'else None,'rejection':results[0][1:]if results[0][0]=='rejected'else None,'raw_hashes':digests,'plan_hashes':{r:sha(build/r/'plan.json')for r in roles}})
   save(out/'progress.json',{'complete':False,'records':records})
 sys.modules.update(old);save(out/'checks.json',{'complete':True,'records':records,'groups':groups,'effective_changed_modules':{n:sha(home/'offline-candidate-v2'/(n+'.py'))for n in names},'capture_reuse_not_new_deployment':True});print('Complete graph pairs',len(records))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--groups',nargs='+',required=True);a=p.parse_args();run(a.home.resolve(),a.out.resolve(),a.groups)
