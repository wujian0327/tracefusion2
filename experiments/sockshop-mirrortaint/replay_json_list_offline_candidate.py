"""Isolated offline candidate: do not mutate a running frozen capture source tree."""
import argparse,importlib.util,json,sys
from pathlib import Path
from run_planned_service import load,save,sha
from infer_distributed_fields import Reconstruction

def run(home,out):
 out.mkdir(parents=True,exist_ok=False);candidate=home/'offline-candidate-v2';original={}
 for name in ('infer_json_list_copy','infer_application_execution'):
  original[name]=sys.modules.get(name);path=candidate/(name+'.py');spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m)
 try:
  from infer_execution_kernel import infer_execution
  fixture=home/'scalar-reproduction-02';plan=load(fixture/'plan.json');scalar=[]
  from audit_zlt_foundation_revision import tf_pair
  for mode in('full','selective'):
   p=fixture/mode/'events.jsonl';rows=[json.loads(s)for s in p.read_text().splitlines()];result=infer_execution(plan,rows)
   for ret in(r for r in rows if r['kind']=='binding-return'):
    source=next(r for r in rows if r['kind']=='binding-source'and r['message']==ret['message']);tf_pair(rows,source);slot=next(i for i,f in enumerate(source['fields'])if f['field']=='@list:0');answer=next(a for a in result['answers']if a['root_frame']==ret['frame']and a['path']=='/text');expected=[['field',source['seq'],slot]];assert answer['known']and answer['origins']==expected,(mode,answer,expected);scalar.append({'mode':mode,'root':ret['frame'],'expected':expected,'predicted':answer['origins'],'matched':True})
  save(out/'scalar-checks.json',scalar)
  from run_ruoyi_tolist_revision import audit
  audit(home/'final-C1',out/'C1')
  summary=load(out/'C1/summary.json');assert all(summary['states'][m]=={'known_correct':80,'unknown':9}for m in('full','selective'))
  comparisons=[]
  # Full graph includes source and selection coordinates, not merely values.
  for q in('ruoyi-1','ruoyi-2','ruoyi-3','ruoyi-4','ruoyi-5'):
   for mode in('full','selective'):
    view=out/'C1'/(q+'-'+mode);new=Reconstruction(view/'build',view/'capture',['role']);new_state=(new.nodes,new.edges,new.local_queries)
    for name,old in original.items():
     if old is not None:sys.modules[name]=old
     else:sys.modules.pop(name,None)
    old=Reconstruction(view/'build',view/'capture',['role']);assert new_state==(old.nodes,old.edges,old.local_queries),(q,mode)
    for name in('infer_json_list_copy','infer_application_execution'):
     spec=importlib.util.spec_from_file_location(name,candidate/(name+'.py'));m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m)
    comparisons.append({'query':q,'mode':mode,'whole_graph_sources_and_selectors_equal':True})
  save(out/'compatibility.json',comparisons)
 finally:
  for name,old in original.items():
   if old is None:sys.modules.pop(name,None)
   else:sys.modules[name]=old
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.home.resolve(),a.out.resolve())
