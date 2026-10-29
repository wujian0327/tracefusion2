#!/usr/bin/env python3
"""Execute sealed APIs in order; parallelize only independent query deployments."""
import json,subprocess,sys,time,datetime
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save,sha
HOME=ROOT/'artifacts/external-frozen-transfer-20261029'
ENTRY=HERE/'external_frozen_entry.py'

def launch(version,api,mode,index=None,attempt=None):
 suffix='original'if mode=='original'else'B0'if mode=='mirrortaint'else'%03d'%index
 log=HOME/'logs'/('-'.join([api,version,mode,suffix])+'.log')
 args=[sys.executable,str(ENTRY),'--version',version,'--stage','run','--api',api,'--mode',mode]
 if index is not None:args+=['--index',str(index)]
 if attempt:args+=['--attempt',attempt]
 started=time.monotonic()
 with log.open('w')as f:
  try:p=subprocess.run(args,stdout=f,stderr=subprocess.STDOUT,timeout=900);code=p.returncode
  except subprocess.TimeoutExpired:code='driver_timeout'
 return {'version':version,'api':api,'mode':mode,'index':index,'returncode':code,'log':str(log),'wall_seconds':time.monotonic()-started}

def run():
 results=[];queries=load(HOME/'task-seal.json')['entries']
 for q in queries:
  api=q['id'];print('API',api,flush=True)
  original=HOME/'ae7fe8d/original'/q['application']/('sealed-'+api)
  if not(original/'results.json').exists():results.append(launch('ae7fe8d',api,'original',attempt='sealed-'+api))
  else:results.append({'api':api,'mode':'original','receipt':str(original/'results.json'),'reuse':'Original environment already executed in this sealed batch; no tool/algorithm capture reuse'})
  results.append(launch('ae7fe8d',api,'mirrortaint'))
  for version in ('ae7fe8d','78a9534'):
   deadline=time.monotonic()+7200
   while not all((HOME/version/'planning-first'/api/('%03d.json'%i)).exists()for i in range(len(q['return_targets']))):
    assert time.monotonic()<deadline,'Planning not finished; do not replace API'
    time.sleep(2)
   planned=[load(HOME/version/'planning-first'/api/('%03d.json'%i))for i in range(len(q['return_targets']))]
   for mode in ('full','selective'):
    accepted=[p for p in planned if p['status']=='accepted']
    with ThreadPoolExecutor(max_workers=3)as pool:
     for r in pool.map(lambda p:launch(version,api,mode,p['index']),accepted):
      results.append(r);save(HOME/'matrix-progress.json',{'complete':False,'latest_api':api,'results':results});print({k:v for k,v in r.items()if k!='log'},flush=True)
    for p in planned:
     if p['status']!='accepted':results.append({'api':api,'version':version,'mode':mode,'index':p['index'],'state':p['status'],'no_tool_deployment':True})
  save(HOME/'matrix-progress.json',{'complete':False,'completed_through':api,'results':results})
 save(HOME/'matrix-progress.json',{'complete':True,'results':results,'core_or_contract_changes':False,'no_performance':True})
if __name__=='__main__':run()
