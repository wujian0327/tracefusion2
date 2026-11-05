"""Read-only capture reuse view with an independently frozen offline consumer."""
import argparse,copy,shutil
from pathlib import Path
from run_planned_service import ROOT,load,save,sha

def run(home):
 parent=home/'final-candidate';final=load(home/'final-offline-freeze.json');initial=load(home/'final-freeze.json')
 assert load(home/'capability-pass-01/summary.json')['passed']
 for p,h in final['sources'].items():assert sha(Path(p))==h,p
 changed=[p for p,h in initial['sources'].items()if final['sources'][p]!=h]
 assert {Path(p).name for p in changed}=={'infer_application_execution.py','infer_json_list_copy.py'}
 view=home/'offline-final-view';view.mkdir(exist_ok=False)
 for p in parent.iterdir():
  if p.name not in('historical','mall'):(view/p.name).symlink_to(p.resolve(),target_is_directory=p.is_dir())
 for name,override in(('historical','algorithm-freeze.json'),('mall','candidate-code.json')):
  d=view/name;d.mkdir();source=parent/name
  for p in source.iterdir():
   if p.name not in(override,'source-snapshot'):(d/p.name).symlink_to(p.resolve(),target_is_directory=p.is_dir())
  receipt=copy.deepcopy(load(source/override));receipt['original_capture_algorithm']=initial['commit'];receipt['offline_reconstruction_algorithm']=final['commit']
  if name=='historical':
   receipt['commit']=final['commit'];receipt['algorithm_commit']=final['commit'];receipt['commit_at_build']=initial['commit'];receipt['sources']=final['sources']
   for p in final['sources']:
    dest=d/'source-snapshot'/Path(p).relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest)
  else:receipt['sources']={str(Path(p).relative_to(ROOT)):h for p,h in final['sources'].items()}
  save(d/override,receipt)
 reuse={'first_candidate':initial['commit'],'offline_candidate':final['commit'],'original_capture_root':str(parent),'Agent_unchanged':True,'agent_sha256':initial['agent_sha256'],'plans_unchanged':True,'changed_query_ids':{},'changed_offline_files':changed,'no_new_deployments_in_this_view':True,'same_batch_complete_graph_equivalence_required':True}
 save(view/'capture-reuse-receipt.json',reuse)
 print(view)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);run(p.parse_args().home.resolve())
