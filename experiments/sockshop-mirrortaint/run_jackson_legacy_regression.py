#!/usr/bin/env python3
"""Fresh historical distributed paths, original inputs, private JSON observer."""
import argparse,json,subprocess
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save,sha
from build_distributed_plans import build
import run_distributed_paths as paths
from run_quota_capability_acceptance import qualified_options
from evaluate_distributed_paths import evaluate


def run(out):
    out.mkdir(parents=True,exist_ok=False);old=ROOT/'artifacts/call-lifecycle-revision-20261020/legacy-build';manifest=load(old/'build.json');b=out/'build'
    build(b,{r:v['query_config']for r,v in manifest['inputs'].items()})
    for role,record in manifest['inputs'].items():assert sha(b/role/'original.jar')==record['original_jar_sha256']
    capture=out/'capture';paths.freeze(capture,b,151028,ROOT/'artifacts/call-lifecycle-revision-20261020/historical-business')
    observed=paths.observed
    def configured(spec,name,role,dest,build):
        observed(spec,name,role,dest,build);cfg=spec['services'][name];cfg['environment']['JAVA_OPTS']=qualified_options(cfg['environment']['JAVA_OPTS'])
    paths.observed=configured
    save(out/'protocol-before-business.json',{'core_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'driver_sha256':sha(Path(__file__)),'original_input_sha256':sha(capture/'cases.json'),'original_JARs_unchanged':True,'observed_JVM':'1CPU/768MiB heap32/256 GC1 CI2','no_performance':True})
    paths.capture_sockshop(capture,b);paths.capture_train(capture,b);evaluate(capture,b)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.out.resolve())
