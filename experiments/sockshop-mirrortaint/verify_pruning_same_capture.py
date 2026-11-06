"""Full graph/answer/choice/root compatibility on identical unfiltered captures."""
import argparse,pickle,subprocess,sys
from pathlib import Path
from run_planned_service import HERE,ROOT,load,save

def run(home,out):
 out.mkdir(parents=True,exist_ok=False);records=[]
 for task in load(home/'protocol-before-change.json')['order']:
  trial=home/'short'/(task+'-none');protocol=trial/'offline-protocol.json';folders=[]
  for name,repo in [('reference',home/'reference-core-4cb5943'),('current',ROOT)]:
   d=out/(task+'-'+name);cmd=[sys.executable,str(HERE/'measure_shared_work_revision.py'),'worker','--home',str(home),'--protocol',str(protocol),'--task',task,'--mode','selective','--repo',str(repo),'--out',str(d),'--graph']
   with(out/(task+'-'+name+'.log')).open('w')as f:subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,check=True)
   folders.append(d)
  with(folders[0]/'graph.pkl').open('rb')as f:a=pickle.load(f)
  with(folders[1]/'graph.pkl').open('rb')as f:b=pickle.load(f)
  assert a==b,task
  assert load(folders[0]/'answers.json')==load(folders[1]/'answers.json')and load(folders[0]/'scores.json')==load(folders[1]/'scores.json')
  records.append({'task':task,'full_nodes_edges_local_states_versions_origins_selectors_root_audits_equal':True,'same_unfiltered_capture_sha256':load(folders[0]/'summary.json')['complete_capture_sha256']})
 save(out/'checks.json',{'passed':True,'records':records,'diagnostic_only_not_formal_timing':True});print('Full identical-capture evidence compatibility passed')

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.home.resolve(),a.out.resolve())
