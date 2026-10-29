#!/usr/bin/env python3
"""Check that the configuration adapter reproduces each frozen postprocessor."""
import argparse,json,subprocess,sys
from pathlib import Path
import external_frozen_entry as entry

def run(version,api,index):
 entry.setup(version)
 from plan_capability_policy import choose
 home=entry.OUT/version;q=entry.load(home/'planning-first'/api/('%03d.json'%index))['query'];model=entry.load(home/'metadata'/q['role']/'model.json')
 expected,_=choose(model,q);actual,_=entry.source_calibrated_plan(model,q,[])
 changed=[k for k in expected.keys()|actual.keys() if expected.get(k)!=actual.get(k)]
 assert not changed,(version,api,changed)
 output=entry.OUT/'source-config-C1'/('equivalence-'+version+'-'+api+'.json')
 entry.save(output,{'all_passed':True,'version':version,'api':api,'profile':actual['profile'],'no_new_sources_adapter_equals_original_choose':True,'changed_keys':changed,'meaning':'Checks adapter composition with empty extra declarations; source-calibrated plans intentionally differ when sealed boundaries are supplied. Not a source correctness test.'})
 print(version,api,actual['profile'],'equal',flush=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--version',choices=['ae7fe8d','78a9534']);p.add_argument('--api');a=p.parse_args()
 if a.version:run(a.version,a.api,0)
 else:
  for version in('ae7fe8d','78a9534'):
   for api in('apollo-1','mall-swarm-2','mall-swarm-5'):
    subprocess.run([sys.executable,__file__,'--version',version,'--api',api],check=True)
