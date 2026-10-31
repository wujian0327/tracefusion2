"""B2.2 exporter-only rerun. Invoke once per API in a fresh Python process."""
import argparse,shutil
from pathlib import Path
from run_planned_service import ROOT,load,save,sha
import run_frozen_zlt_reuse as runner

H=ROOT/'artifacts/offline-zlt-revision-20261031'

def verify(home):
 # TF frozen core and all original query plans are unchanged. The sole allowed
 # source delta is the separately frozen MT export header startup correction.
 old=load(H/'final-zlt-03/candidate-freeze.json');metadata='experiments/sockshop-mirrortaint/MirrorCapabilityAgent.java'
 for name,digest in old['sources'].items():
  if name not in {metadata,'experiments/sockshop-mirrortaint/build_native_mirror_bundle.py','experiments/sockshop-mirrortaint/audit_zlt_foundation_revision.py'}:assert sha(ROOT/name)==digest,name
 fix=H/'mt-class-build-03/source-snapshot/MirrorCapabilityAgent.java'
 assert sha(fix)==load(H/'mt-class-build-03/build.json')['sources_sha256'][str(fix)]
 assert sha(ROOT/metadata)in (old['sources'][metadata],sha(fix))
 native=ROOT/'artifacts/external-tools/mirrortaint/mirrorTaint.jar';assert sha(native)=='e4c679206993b45c6727a4ace1d4dcff6df0ded2b80b56b27b8c86741be63fe7'
 assert sha(H/'mt-class-build-04/capability.jar')==load(H/'mt-class-build-04/build.json')['probe_sha256']
 assert sha(H/'candidate-build-01/distributed-observer.jar')==old['binaries'][str(H/'candidate-build-01/distributed-observer.jar')]
 return {'TF_candidate':old['commit'],'MT_source_sha256':sha(fix),'MT_jar_sha256':sha(H/'mt-class-build-04/capability.jar'),'native_sha256':sha(native)}

def prepare(home):
 home.mkdir(parents=True,exist_ok=False);reference=H/'final-zlt-03'
 for name in('metadata','business-jars','upstream','planning-first'):(home/name).symlink_to((reference/name).resolve(),target_is_directory=True)
 for name in('task-seal.json','oracle-before-tools.json','environment-images-before-tools.json'):shutil.copyfile(reference/name,home/name)
 save(home/'protocol-start.json',{'TF_commit':load(reference/'protocol-start.json')['TF_commit'],'MT_adapter':'B2.2 startup context correction and existing private JSON packaging','TF_and_original_captures_reused':str(reference)})
 for api in('ZLT-MP-1','ZLT-MP-4'):
  p=home/'runs'/api;p.mkdir(parents=True)
  for mode in('original','full','selective'):(p/mode).symlink_to(reference/'runs'/api/mode,target_is_directory=True)
 save(home/'adapter-freeze-before-tools.json',verify(home))

def run(home,api):
 import portability_tool_config as pc
 import run_external_zlt_environment as env
 from sockshop import Deployment
 check=lambda:verify(home);check();runner.verify=check;runner.BASE=H/'candidate-build-01';pc.BUNDLE=H/'mt-class-build-04'
 original_save,original_compose=env.save,Deployment.compose
 try:runner.run(home,api,'mirrortaint')
 finally:env.save=original_save;Deployment.compose=original_compose
 save(home/'runs'/api/'mirrortaint/revision-binary-receipt.json',{'mode':'mirrortaint','adapter':'B2.2','native_propagation_unchanged':True,'no_TF_agent_change':True,**check()})

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('stage',choices=['prepare','run']);p.add_argument('--home',type=Path,required=True);p.add_argument('--api',choices=['ZLT-MP-1','ZLT-MP-4']);a=p.parse_args()
 if a.stage=='prepare':prepare(a.home.resolve())
 else:run(a.home.resolve(),a.api)
