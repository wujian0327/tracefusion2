#!/usr/bin/env python3
"""Only after B0 first matrix closes, run locked observation addon separately."""
import json,sys,time,subprocess,datetime
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save,sha
HOME=ROOT/'artifacts/external-frozen-transfer-20261029'

def run():
 deadline=time.monotonic()+43200
 while not(HOME/'matrix-progress.json').exists()or not load(HOME/'matrix-progress.json').get('complete'):
  assert time.monotonic()<deadline;time.sleep(10)
 files={}
 for version in ('ae7fe8d','78a9534'):
  for folder in ('tool-runs','original','planning-first'):
   for p in(HOME/version/folder).rglob('*'):
    if p.is_file()and'evaluation-first'not in p.parts:files[str(p.relative_to(HOME))]=sha(p)
 save(HOME/'first-matrix-manifest-before-B1.json',{'files':files,'first_propagation_unchanged':True})
 b=HOME/'MT-B1';b.mkdir()
 for name in ('business-jars','upstream','method-metadata','metadata'):(b/name).symlink_to((HOME/'ae7fe8d'/name).resolve(),target_is_directory=True)
 for name in ('task-seal.json','protocol-start.json','task-original.json'):(b/name).write_bytes((HOME/'ae7fe8d'/name).read_bytes())
 save(b/'protocol-before-business.json',{'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_config_and_original_native_unchanged_from_B0':True,'observation_addon':load(HOME/'native-observation-B1-04/results.json'),'API_order':['apollo-1','mall-swarm-2','mall-swarm-4','mall-swarm-5'],'scope':'Source/sink raw physical facts, actual Gson converter/body/library identities only. No new propagation or certified Gson projection; never overwrite first B0 states.'})
 results=[]
 for api in ['apollo-1','mall-swarm-2','mall-swarm-4','mall-swarm-5']:
  with(HOME/'logs'/('B1-'+api+'.log')).open('w')as f:p=subprocess.run([sys.executable,str(HERE/'external_frozen_entry.py'),'--stage','run','--version','ae7fe8d','--mode','mirrortaint','--api',api,'--observer-addon'],stdout=f,stderr=subprocess.STDOUT)
  results.append({'api':api,'returncode':p.returncode});save(b/'progress.json',{'complete':False,'results':results})
 for p,h in files.items():assert sha(HOME/p)==h,p
 save(b/'progress.json',{'complete':True,'results':results,'first_files_unchanged':len(files)})
if __name__=='__main__':run()
