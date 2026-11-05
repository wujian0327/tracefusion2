"""Use the isolated consumer to test missing/ambiguous scalar slot evidence."""
import argparse,copy,json,sys,types
from pathlib import Path
from run_planned_service import load,save,sha
from infer_execution_kernel import infer_execution

def run(home,out):
 out.mkdir(parents=True,exist_ok=False);candidate=home/'offline-candidate-v2';checks=[]
 for name in('infer_json_list_copy','infer_application_execution'):
  path=candidate/(name+'.py');module=types.ModuleType(name);module.__file__=str(path);exec(compile(path.read_bytes(),str(path),'exec'),module.__dict__);sys.modules[name]=module
 fixture=home/'scalar-reproduction-02';plan=load(fixture/'plan.json');hashes={}
 for mode in('full','selective'):
  path=fixture/mode/'events.jsonl';hashes[str(path)]=sha(path);rows=[json.loads(s)for s in path.read_text().splitlines()];source=next(r for r in rows if r['kind']=='binding-source');root=source['frame']
  for fault in('missing-slot','ambiguous-slot','wrong-slot-version','wrong-source-call','missing-call-completion'):
   changed=copy.deepcopy(rows);s=next(r for r in changed if r['seq']==source['seq'])
   if fault=='missing-slot':s['fields']=[]
   elif fault=='ambiguous-slot':s['fields'].append(copy.deepcopy(s['fields'][0]))
   elif fault=='wrong-slot-version':s['fields'][0]['version']+=1
   elif fault=='wrong-source-call':s['source_call_id']=-1
   else:next(r for r in changed if r['kind']=='collection-call-exit'and r['call_id']==s['source_call_id'])['kind']='diagnostic-missing-source-finish'
   try:
    result=infer_execution(plan,changed);assert all(not a['known']for a in result['answers']if a['root_frame']==root);status='unknown';reason=None
   except ValueError as e:status='rejected';reason=str(e)
   checks.append({'mode':mode,'fault':fault,'state':status,'reason':reason})
 assert all(sha(Path(p))==v for p,v in hashes.items());save(out/'checks.json',{'checks':checks,'original_hashes_unchanged':hashes})
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.home.resolve(),a.out.resolve())
