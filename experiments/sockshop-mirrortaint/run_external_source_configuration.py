#!/usr/bin/env python3
"""Separate C1: wire the already sealed sources through the frozen public API.

 Preserve the first policy-generated plans/captures. Reuse only unchanged
 original/MT evidence; every C1 TF run uses a new isolated deployment.
 """
import argparse,datetime,subprocess,sys,time,shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save,sha
HOME=ROOT/'artifacts/external-frozen-transfer-20261029';C1=HOME/'source-config-C1';ENTRY=HERE/'external_frozen_entry.py'

def plan_one(item):
 version,api,index=item;dest=C1/version/'planning-first'/api;dest.mkdir(parents=True,exist_ok=True)
 log=dest/('%03d-planning.log'%index)
 with log.open('w')as f:
  try:r=subprocess.run([sys.executable,str(ENTRY),'--version',version,'--stage','source-calibrated-plan','--api',api,'--index',str(index)],stdout=f,stderr=subprocess.STDOUT,timeout=180);code=r.returncode
  except subprocess.TimeoutExpired:code='analysis_limited'
 path=dest/('%03d.json'%index)
 if not path.exists():
  old=load(HOME/version/'planning-first'/api/('%03d.json'%index));save(path,{**old,'status':'analysis_limited'if code=='analysis_limited'else'planning_environment_failure','reason':'C1 planning process failed; no partial plan accepted','returncode':code})
 return load(path)

def launch(version,api,mode,index):
 log=C1/'logs'/('-'.join([api,version,mode,'%03d'%index])+'.log')
 with log.open('w')as f:
  try:r=subprocess.run([sys.executable,str(ENTRY),'--version',version,'--stage','run','--api',api,'--mode',mode,'--index',str(index),'--source-calibrated'],stdout=f,stderr=subprocess.STDOUT,timeout=900);code=r.returncode
  except subprocess.TimeoutExpired:code='driver_timeout'
 return {'version':version,'api':api,'mode':mode,'index':index,'returncode':code,'log':str(log)}

def prepare(entries):
 C1.mkdir();(C1/'logs').mkdir()
 save(C1/'protocol-before-planning.json',{'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'configuration_revision':'C1','why':'High-level frozen choose did not forward the already sealed read_source_candidates. First plans/captures retained as integration failure; use existing low-level plan_response(source_calls=...) without new semantics.','source_declaration_audit_sha256':sha(HOME/'source-declaration-configuration-audit.json'),'frozen_source_declaration_sha256':sha(HOME/'task-seal.json'),'frozen_oracle_sha256':sha(HOME/'oracle-before-tools.json'),'all_ten_APIs_and_all59_queries_retained':True,'route':'Frozen choose selects profile before runtime; same snapshot plan_response receives explicit source declarations; same frozen postprocessing functions. No per-field propagation, new model or hash relaxation.','run_order':[q['id']for q in entries],'parallelism':6,'reason_for_parallelism':'Independent containers/data volumes, capability only; no costs inferred. First matrix remains its original three workers.','TF_capture_reuse':False,'original_MT_reuse':'Unchanged original inputs, JARs, native/B0 binaries and exact source configuration; previous source/target export limits retained.','performance':False})
 for name in('task-seal.json','oracle-before-tools.json','protocol-before-tools.json'):shutil.copyfile(HOME/name,C1/name)
 for version in('ae7fe8d','78a9534'):
  home=C1/version;home.mkdir()
  for name in('business-jars','upstream','method-metadata','metadata','original'):
   p=HOME/version/name
   if not p.exists()and name=='original':p=HOME/'ae7fe8d/original'
   (home/name).symlink_to(p.resolve(),target_is_directory=True)
  for name in('task-seal.json','protocol-start.json','task-original.json'):shutil.copyfile(HOME/version/name,home/name)
  for q in entries:
   dest=home/'tool-runs'/q['id'];dest.mkdir(parents=True)
   # Target may not exist yet; it is opened only after the first matrix closes.
   (dest/'mirrortaint').symlink_to((HOME/'ae7fe8d/tool-runs'/q['id']/'mirrortaint').absolute(),target_is_directory=True)
 tasks=[(v,q['id'],i)for v in('ae7fe8d','78a9534')for q in entries for i in range(len(q['return_targets']))]
 with ThreadPoolExecutor(max_workers=6)as pool:plans=list(pool.map(plan_one,tasks))
 save(C1/'planning-summary.json',plans)

def first_API_closed(q):
 state=load(HOME/'matrix-progress.json');records=[r for r in state['results']if r.get('api')==q['id'] and r.get('mode')in('full','selective')]
 return len(records)==4*len(q['return_targets']) and (HOME/'ae7fe8d/tool-runs'/q['id']/'mirrortaint/fixed-adapter/results.json').exists()

def run(resume_planning=False):
 entries=load(HOME/'task-seal.json')['entries']
 if not resume_planning:prepare(entries)
 else:
  plans=load(C1/'planning-summary.json');assert len(plans)==118
  for version in('ae7fe8d','78a9534'):
   for q in entries:
    for i in range(len(q['return_targets'])):
     p=C1/version/'planning-first'/q['id']/('%03d.json'%i);metadata=load(p)
     if metadata['status']=='accepted':assert sha(p.with_name('%03d-plan.json'%i))==metadata['plan_sha256']
  save(C1/'scheduling-amendment-before-C1-business.json',{'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'first_plans_or_captures_overwritten':False,'source_configuration_changed':False,'scope':'C1 may begin each API only after BOTH versions/modes of that API close in the first matrix. First API order is unchanged in both cohorts. No semantic fix follows future API answers.','parallelism':'At most 3 C1 deployments while first matrix has its 3; at most 6 C1 after first matrix closes. Independent data/network/project for every deployment.','no_performance':True})
 results=[]
 for q in entries:
  while not first_API_closed(q):time.sleep(10)
  api=q['id'];print('API',api,flush=True)
  for version in('ae7fe8d','78a9534'):
   planned=[load(C1/version/'planning-first'/api/('%03d.json'%i))for i in range(len(q['return_targets']))]
   for mode in('full','selective'):
    accepted=[p for p in planned if p['status']=='accepted']
    workers=6 if load(HOME/'matrix-progress.json').get('complete')else 3
    with ThreadPoolExecutor(max_workers=workers)as pool:
     for result in pool.map(lambda p:launch(version,api,mode,p['index']),accepted):
      results.append(result);save(C1/'progress.json',{'complete':False,'latest_api':api,'results':results});print(result,flush=True)
    for p in planned:
     if p['status']!='accepted':results.append({'api':api,'version':version,'mode':mode,'index':p['index'],'state':p['status'],'no_deployment':True})
  save(C1/'progress.json',{'complete':False,'completed_through':api,'results':results})
 save(C1/'progress.json',{'complete':True,'results':results,'no_core_agent_or_contract_changes':True})

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--resume-planning',action='store_true');a=p.parse_args();run(a.resume_planning)
