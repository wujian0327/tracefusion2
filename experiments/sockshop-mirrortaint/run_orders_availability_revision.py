#!/usr/bin/env python3
"""Orders availability diagnosis with original six inputs, limits and deadline.

Diagnostic receipts are separate from frozen, diagnostics-off validation. Failures
are never replaced by a successful retry. Source answers use the existing
independent raw-fact oracle, not the diagnostic timings or stack samples.
"""
import argparse,subprocess
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save,sha
import run_frozen_capability_acceptance as driver
from build_distributed_plans import build

PREVIOUS=ROOT/'artifacts/date-effects-capability-20261021/final-capability'
QUERIES=('sockshop-orders-newOrder-address-postcode','sockshop-orders-newOrder-customer-lastName')

def prepare(root):
    root.mkdir(parents=True,exist_ok=False)
    old=load(PREVIOUS/'frozen-base/build.json');inputs={role:row['query_config'] for role,row in old['inputs'].items()}
    build(root/'frozen-base',inputs)
    sources=load(root/'frozen-base/build.json')['sources'];save(root/'algorithm-freeze.json',{'commit_at_build':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'sources':sources,'uncommitted_sources_recorded_by_hash':True,'base_build':str(root/'frozen-base'),'previous_freeze_sha256':sha(PREVIOUS/'algorithm-freeze.json')})
    for name,digest in sources.items():
        source=Path(name);dest=root/'source-snapshot'/source.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);assert sha(source)==digest;dest.write_bytes(source.read_bytes())
    save(root/'source-snapshot.json',{'all_sources_verified':True,'files':sources})
    plans=root/'frozen-plans';plans.mkdir()
    # This investigation changes only collector implementation. Static routing
    # and the predeclared query/source semantics remain byte-for-byte identical.
    for file in (PREVIOUS/'frozen-plans').glob('*.json'):(plans/file.name).write_bytes(file.read_bytes())
    for role,row in old['inputs'].items():assert sha(root/'frozen-base'/role/'original.jar')==row['original_jar_sha256']

def run(root,out,diagnostic=False,repetitions=1,gc_diagnostic=False,quota_aware_jvm=False):
    driver.HOME=root;driver.check();driver.QUERIES=[q for q in driver.QUERIES if q['id'] in QUERIES]
    original=driver.mode_config
    if diagnostic or gc_diagnostic or quota_aware_jvm:
        def configured(spec,name,role,cap,build,mode):
            original(spec,name,role,cap,build,mode)
            if diagnostic:spec['services'][name]['environment']['JAVA_OPTS']+=' -Dservice.diagnostic.timing=true'
            if gc_diagnostic:spec['services'][name]['environment']['JAVA_OPTS']+=' -XX:+PrintGCDetails -XX:+PrintGCTimeStamps -XX:+PrintGCApplicationStoppedTime -Xloggc:/tf2/capture/gc.log'
            if quota_aware_jvm:spec['services'][name]['environment']['JAVA_OPTS']+=' -XX:ParallelGCThreads=1 -XX:CICompilerCount=2'
        driver.mode_config=configured
    out.mkdir(parents=True,exist_ok=False)
    save(out/'protocol-before-deployments.json',{'queries':list(QUERIES),'repetitions':repetitions,'modes':['full','selective'],'diagnostic':diagnostic,'gc_logging':gc_diagnostic,'quota_aware_jvm':quota_aware_jvm,'warmup':False,'deadline_seconds':5,'preserve_every_first_attempt':True,'sources':load(root/'algorithm-freeze.json')['sources'],'driver_sha256':sha(Path(__file__))})
    (out/'driver-at-launch.py').write_bytes(Path(__file__).read_bytes())
    results=[]
    for index in range(1,repetitions+1):
        dest=out/('round-'+str(index));driver.orders(dest,root/'frozen-base');results.append({'round':index,'results':load(dest/'results.json')['results']});save(out/'results.json',{'complete':index==repetitions,'rounds':results})
    return results

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--prepare',action='store_true');p.add_argument('--out',type=Path);p.add_argument('--diagnostic',action='store_true');p.add_argument('--gc-diagnostic',action='store_true');p.add_argument('--quota-aware-jvm',action='store_true');p.add_argument('--repetitions',type=int,default=1);a=p.parse_args();root=a.root.resolve()
    if a.prepare:prepare(root)
    if a.out:run(root,a.out.resolve(),a.diagnostic,a.repetitions,a.gc_diagnostic,a.quota_aware_jvm)
