#!/usr/bin/env python3
"""First bounded closure capture on the original six Cart regression inputs."""
import argparse,copy
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save,sha
from plan_capability_policy import choose
import build_distributed_plans as builder
import run_frozen_capability_acceptance as driver
from run_quota_capability_acceptance import qualified_options


def run(root):
    base=root/'prototype-build-01';old=load(ROOT/'artifacts/transport-observation-shared-20261023/frozen-base/build.json');builder.build(base,{k:v['query_config']for k,v in old['inputs'].items()})
    q=next(q for q in driver.QUERIES if q['id']=='sockshop-carts-getItems-each-itemId');p,policy=choose(load(base/'carts/model.json'),q);save(root/'prototype-cart-plan.json',p);save(root/'prototype-sources.json',load(base/'build.json')['sources'])
    assert len(p['execution_observation_closure']['candidate_write_sites'])==3
    driver.QUERIES=[q];driver.plan=lambda query:copy.deepcopy(p)
    def check():
        for f,h in load(root/'prototype-sources.json').items():assert sha(Path(f))==h
    driver.check=check;original=driver.mode_config
    def mode(spec,name,role,cap,build,which):
        original(spec,name,role,cap,build,which);cfg=spec['services'][name];cfg['environment']['JAVA_OPTS']=qualified_options(cfg['environment']['JAVA_OPTS'])
    driver.mode_config=mode;driver.carts(root/'prototype-cart-first',base)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);run(p.parse_args().root.resolve())
