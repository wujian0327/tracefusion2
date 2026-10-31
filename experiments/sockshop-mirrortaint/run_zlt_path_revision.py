"""Bounded two-entry development/final driver; original tasks remain sealed."""
import argparse,hashlib,json,shutil,subprocess
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save,sha

def prepare(home,base,models,plans):
 home.mkdir(parents=True,exist_ok=False);prior=ROOT/'artifacts/frozen-zlt-reuse-20261030'
 for name in('business-jars','upstream'):(home/name).symlink_to((prior/name).resolve(),target_is_directory=True)
 for name in('task-seal.json','oracle-before-tools.json','environment-images-before-tools.json'):shutil.copyfile(prior/name,home/name)
 for q in load(home/'task-seal.json')['entries']:
  role=q['role'];p=home/'metadata'/role;p.mkdir(parents=True);shutil.copyfile(models/role/'model.json',p/'model.json');shutil.copyfile(prior/'metadata'/role/'receipt.json',p/'receipt.json');d=home/'planning-first'/q['id'];d.mkdir(parents=True);shutil.copyfile(plans/q['id']/'plan.json',d/'000-plan.json');save(d/'000.json',{'status':'conditional','scope':'Developed original task; actual contracts still required'})
 commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip();save(home/'protocol-start.json',{'TF_commit':commit,'base':str(base),'development_exposed_queries':True,'no_performance':True,'same_inputs_and_boundaries':True})
 sources={str(p):sha(p)for p in HERE.iterdir()if p.suffix in('.java','.py','.json')};save(home/'run-source-lock.json',{'sources':sources,'agent':str(base/'distributed-observer.jar'),'agent_sha256':sha(base/'distributed-observer.jar'),'plans':{str(p):sha(p)for p in(home/'planning-first').rglob('*-plan.json')}})

def run(home,api,mode):
 import run_frozen_zlt_reuse as runner
 import portability_tool_config as pc
 import run_external_zlt_environment as env
 from sockshop import Deployment
 lock=load(home/'run-source-lock.json')
 def verify():
  # Semantic development can proceed between independent deployments, but each
  # deployment has its own exact source receipt. Agent and actual plan immutable.
  assert sha(Path(lock['agent']))==lock['agent_sha256']
  for name,value in lock['plans'].items():assert sha(Path(name))==value
  return {'agent_sha256':lock['agent_sha256']}
 runner.verify=verify;runner.BASE=Path(lock['agent']).parent;oldsave,oldcompose=env.save,Deployment.compose
 try:runner.run(home,api,mode)
 finally:env.save=oldsave;Deployment.compose=oldcompose
 save(home/'runs'/api/mode/'revision-receipt.json',{'same_original_JAR':True,'same_sealed_task':True,'candidate_lock':sha(home/'run-source-lock.json'),'not_a_frozen_unseen_test':True,'source_at_run':{str(p):sha(p)for p in HERE.iterdir()if p.suffix in('.java','.py','.json')},**verify()})

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('stage',choices=['prepare','run']);p.add_argument('--home',type=Path,required=True);p.add_argument('--base',type=Path);p.add_argument('--models',type=Path);p.add_argument('--plans',type=Path);p.add_argument('--api');p.add_argument('--mode',choices=['original','full','selective']);a=p.parse_args()
 if a.stage=='prepare':prepare(a.home.resolve(),a.base.resolve(),a.models.resolve(),a.plans.resolve())
 else:run(a.home.resolve(),a.api,a.mode)
