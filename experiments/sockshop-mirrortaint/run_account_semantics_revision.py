#!/usr/bin/env python3
"""Freeze finite Account semantics, then fresh Account40 and historical cohorts.
No performance, baseline first-pass overwrite, or automatic push.
"""
import argparse,json,shutil,subprocess,datetime
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save,sha
PARENT=ROOT/'artifacts/contract-routing-revision-20261023/final-v2'
DEVELOPMENT=ROOT/'artifacts/account-semantics-20261028'
FIRST=ROOT/'artifacts/portability-first-20261028'

def prepare(root):
 from build_distributed_plans import build
 from plan_capability_policy import choose
 import run_frozen_capability_acceptance as tf
 root.mkdir(parents=True);(root/'logs').mkdir();inputs={k:v['query_config']for k,v in load(PARENT/'frozen-base/build.json')['inputs'].items()};inputs['piggy-account']={'jar':str(FIRST/'business-jars/piggy-account.jar'),'entry':'com/piggymetrics/account/controller/AccountController.createNewAccount(Lcom/piggymetrics/account/domain/User;)Lcom/piggymetrics/account/domain/Account;','targets':['com/piggymetrics/account/domain/Account.name'],'response_path':'/name','execution_kernel':True,'application_calls':True};base=root/'frozen-base';build(base,inputs);manifest=load(base/'build.json');prior=load(PARENT/'algorithm-freeze.json');assert all(manifest['inputs'][r]['original_jar_sha256']==h for r,h in prior['original_jars'].items());commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip();shutil.copyfile(PARENT/'protocol.json',root/'protocol.json')
 cohorts=[('frozen-plans',tf.QUERIES),('regression29-plans',load(ROOT/'artifacts/heldout29-first-20261023/protocol-before-first.json')['queries']),('write-plans',load(root/'protocol.json')['queries'])]
 for folder,queries in cohorts:
  d=root/folder;d.mkdir();records=[]
  for q in queries:
   try:p,policy=choose(load(base/q['role']/'model.json'),q);save(d/(q['id']+'.json'),p);records.append({'query':q,'status':'accepted','policy':policy,'plan_sha256':sha(d/(q['id']+'.json'))})
   except ValueError as e:records.append({'query':q,'status':'rejected','rejection':str(e)})
  save(d/'planning.json',records);assert len(records)==len(queries)
 account=root/'account-final/planning-first/piggymetrics-2';account.mkdir(parents=True)
 for i in range(10,20):
  q=load(DEVELOPMENT/'piggy-account-development-01/planning-first/piggymetrics-2'/('%03d.json'%i));p,policy=choose(load(base/'piggy-account/model.json'),q['query']);save(account/('%03d.json'%i),q);save(account/('%03d-plan.json'%i),p);save(account/('%03d-policy.json'%i),policy)
 for f,h in manifest['sources'].items():
  assert sha(Path(f))==h;dest=root/'source-snapshot'/Path(f).relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(f,dest)
 prior.update(commit=commit,algorithm_commit=commit,commit_at_build=commit,base_build=str(base),sources=manifest['sources'],builder_sha256=sha(HERE/'build_distributed_plans.py'),planning_sha256=sha(root/'frozen-plans/planning.json'),original_jars={r:v['original_jar_sha256']for r,v in manifest['inputs'].items()},pair_driver_sha256=sha(HERE/'run_cart_reread_baseline_pair.py'),parent_algorithm='ae7fe8d',scope='Finite foundation/default, Feign input preservation, provided-ID Mongo2 and checked scalar projections. Exposed development tasks; no cost or unseen-query claim.');save(root/'algorithm-freeze.json',prior);save(root/'development-current.json',{'base':str(base),'plans':str(root/'write-plans'),'iteration':'frozen'});(root/'drivers').mkdir()
 for name in ('run_quota_capability_acceptance.py','run_frozen_capability_acceptance.py','run_cart_reread_baseline_pair.py','run_account_semantics_revision.py','audit_account_candidate.py','account_candidate_oracle.py'):
  shutil.copyfile(HERE/name,root/'drivers'/('cart-pair-library-driver-at-launch.py'if name=='run_cart_reread_baseline_pair.py'else name))
 save(root/'protocol-before-business.json',{'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'algorithm':commit,'Account':{'targets':40,'known_positive_required':4,'known_empty_required':36,'historic_MT_correct_required':36,'inputs_and_truth':'Existing original cases and independent code/DB/raw-coordinate oracle, development regression only'},'historical':{'queries62':431,'fields29':244,'write15':96},'fresh_Agent_deployments_required':True,'Station':'Preserve403; no auth retry','no_performance':True,'first_capture_protection_sha256':sha(ROOT/'artifacts/monitor-reliability-account-20261028/protected-first-evidence.json'),'driver_sha256':{p.name:sha(p)for p in(root/'drivers').iterdir()}})
 print({'candidate_frozen':commit,'core_files':len(manifest['sources']),'cohorts':[(f,len(q))for f,q in cohorts]},flush=True)

def account(root):
 from run_monitor_revision_recipient import run
 from audit_account_candidate import run as score
 failures=[]
 for mode in ('full','selective'):
  for i in range(10,20):
   d=root/'account-final/diagnostics/collector-preservation'/mode/('query-%03d'%i)
   if(d/'results.json').exists():raise ValueError('Refuse to overwrite candidate attempt '+str(d))
   try:run(root/'account-final',root/'frozen-base',mode,i,'piggymetrics-2')
   except Exception as e:failures.append({'mode':mode,'index':i,'error':str(e)})
   save(root/'account-runtime-status.json',{'complete':False,'failures':failures,'latest':{'mode':mode,'index':i}})
 save(root/'account-runtime-status.json',{'complete':True,'failures':failures});score(root/'account-final',root/'account-score-first',True)

def worker(root,stage,name):
 import run_quota_capability_acceptance as quota
 if stage=='worker62':quota.worker(root,name)
 elif stage=='fields29':
  import run_execution_closure_revision as revision
  revision.regression29(root,name)
 else:
  import run_contract_routing_revision as revision
  import run_frozen_capability_acceptance as tf
  quota.install(root);tf.HOME=root;revision.development(root,name)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',required=True,type=Path);p.add_argument('--stage',required=True,choices=('prepare','account','worker62','fields29','writes'));p.add_argument('--worker');a=p.parse_args();root=a.root.resolve()
 if a.stage=='prepare':prepare(root)
 elif a.stage=='account':account(root)
 else:worker(root,a.stage,a.worker)
