"""Affected two-entry development regression; no new framework contracts."""
import argparse,json,shutil,subprocess
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save,sha
import run_frozen_zlt_reuse as old

H=ROOT/'artifacts/offline-zlt-revision-20261031'

def verify(home):
 f=load(home/'candidate-freeze.json')
 for name,digest in f['sources'].items():assert sha(ROOT/name)==digest,name
 for name,digest in f['binaries'].items():assert sha(Path(name))==digest,name
 return f['sources']

def prepare(home):
 home.mkdir(parents=True,exist_ok=False);baseline=ROOT/'artifacts/frozen-zlt-reuse-20261030'
 for name in ('business-jars','metadata','upstream'):(home/name).symlink_to((baseline/name).resolve(),target_is_directory=True)
 for name in ('task-seal.json','oracle-before-tools.json','environment-images-before-tools.json','candidate-pool-before-planning.json'):shutil.copyfile(baseline/name,home/name)
 # These tasks/inputs were exposed; copying the original seal is a regression protocol.
 save(home/'protocol-start.json',{'TF_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'reference':'c1a4e5c','development_regression':True,'task_seal_sha256':sha(home/'task-seal.json'),'same_two_tasks':True,'no_performance_experiment':True})
 sources={str(p.relative_to(ROOT)):sha(p)for p in HERE.iterdir()if p.suffix in ('.java','.py','.json')}
 binaries=[H/'candidate-build-01/distributed-observer.jar',H/'mt-class-build-02/capability.jar',H/'mt-class-build-02/adapter/integration-adapter.jar',H/'mt-class-build-02/runtime-witness.jar',ROOT/'artifacts/external-tools/mirrortaint/mirrorTaint.jar']
 save(home/'candidate-freeze.json',{'commit':load(home/'protocol-start.json')['TF_commit'],'sources':sources,'binaries':{str(p):sha(p)for p in binaries},'TF_semantics_commit':'1a5ee56','MT_adapter_commit':'caaf62c','shared_index_commits':['278896a','2609d70'],'no_new_runtime_or_library_contract':True})
 old.verify=lambda:verify(home);old.plan(home)
 save(home/'frozen-plans.json',{str(p.relative_to(home)):sha(p)for p in(home/'planning-first').rglob('*.json')})

def run(home,api,mode):
 import portability_tool_config as pc
 verify(home)
 for name,digest in load(home/'frozen-plans.json').items():assert sha(home/name)==digest,name
 old.verify=lambda:verify(home);old.BASE=H/'candidate-build-01';pc.BUNDLE=H/'mt-class-build-02'
 old.run(home,api,mode)
 receipt=home/'runs'/api/mode/'tool-binaries.json'
 if receipt.exists():
  data=load(receipt);data.update(no_core_agent_or_contract_changes=False,candidate_frozen_for_this_run=True,fixed_adapter_limit='Finite Class metadata and explicit source invocation output; no change to native propagation.');save(receipt.with_name('revision-binary-receipt.json'),data)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('stage',choices=['prepare','run']);p.add_argument('--home',type=Path,required=True);p.add_argument('--api');p.add_argument('--mode',choices=['original','full','selective','mirrortaint']);a=p.parse_args()
 if a.stage=='prepare':prepare(a.home.resolve())
 else:run(a.home.resolve(),a.api,a.mode)
