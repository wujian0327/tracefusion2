#!/usr/bin/env python3
"""Real Recipient control with candidate collector; first source/semantic plans unchanged."""
import argparse,json
from pathlib import Path
from run_planned_service import ROOT,load,save,sha
import run_portability_piggy as old
import portability_tool_config as config
FIRST=ROOT/'artifacts/portability-first-20261028'

def run(root,build,mode,index,api="piggymetrics-5"):
 manifest=load(build/'build.json')
 def verify(_):
  assert sha(build/'distributed-observer.jar')==manifest['agent_sha256']
  for p,h in manifest['sources'].items():assert sha(Path(p))==h,p
  for p,h in load(FIRST/'piggy-independent-first-03/first-captures-manifest.json')['files'].items():assert sha(FIRST/p)==h,p
 root.mkdir(exist_ok=True)
 for item in ('business-jars','upstream','metadata','planning-first'):
  p=root/item
  try:p.symlink_to(FIRST/item,target_is_directory=True)
  except FileExistsError:assert p.resolve()==(FIRST/item).resolve() or item=='planning-first' and not p.is_symlink()
 for item in ('task-seal.json','protocol-start.json'):
  p=root/item
  try:p.symlink_to(FIRST/item)
  except FileExistsError:assert p.resolve()==(FIRST/item).resolve()
 old.verify=verify;config.verify=verify;config.BASE=build
 old.run(root,'unused',mode,api,index,True)
 home=root/'diagnostics/collector-preservation'/mode/('query-%03d'%index)
 # The reused environment driver labels its own old first-pass captures. These
 # are new candidate deployments: retain that input provenance, correct labels.
 for name in ('diagnostic-protocol.json','tool-binaries.json','cases-before-business.json'):
  path=home/name
  if not path.exists():continue
  receipt=load(path)
  for key in ('frozen_core','fixed_core','no_core_agent_or_contract_changes','no_algorithms_modified','algorithm_or_contract_changes'):receipt.pop(key,None)
  receipt.update(candidate_build=str(build),candidate_agent_sha256=sha(build/'distributed-observer.jar'),first_input_reference='ae7fe8d; new candidate capture, not a rerun/replacement of FIRST',candidate_build_manifest_sha256=sha(build/'build.json'))
  save(path,receipt)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--build',type=Path,required=True);p.add_argument('--mode',choices=['original','full','selective'],required=True);p.add_argument('--index',type=int,default=4);p.add_argument('--api',default='piggymetrics-5');a=p.parse_args();run(a.root.resolve(),a.build.resolve(),a.mode,a.index,a.api)
