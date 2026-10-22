#!/usr/bin/env python3
"""Development regression only; preserve each build/capture in a fresh directory."""
import argparse,copy,subprocess,os
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save,sha
from build_distributed_plans import build
from plan_capability_policy import choose
import run_frozen_capability_acceptance as driver
from run_quota_capability_acceptance import install

PREVIOUS=ROOT/'artifacts/orders-availability-20261021/quota-all62'

def prepare(root):
    root.mkdir(parents=True,exist_ok=False)
    old=load(PREVIOUS/'frozen-base/build.json')
    build(root/'frozen-base',{r:v['query_config'] for r,v in old['inputs'].items()})
    sources=load(root/'frozen-base/build.json')['sources']
    for source,h in sources.items():
        source=Path(source);assert sha(source)==h
        dest=root/'source-snapshot'/source.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(source.read_bytes())
    plans=root/'frozen-plans';plans.mkdir();results=[]
    for q in driver.QUERIES:  # Exactly the exposed 62; heldout pool never loaded.
        try:
            p,policy=choose(load(root/'frozen-base'/q['role']/'model.json'),q)
            save(plans/(q['id']+'.json'),p);r={'query':q,'status':'accepted','policy':policy,'plan_sha256':sha(plans/(q['id']+'.json'))}
        except ValueError as error:r={'query':q,'status':'rejected','rejection':str(error)}
        results.append(r)
    save(plans/'planning.json',results)
    save(root/'algorithm-freeze.json',{'commit_at_build':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'sources':sources,'base_build':str(root/'frozen-base'),'prior_freeze_sha256':sha(PREVIOUS/'algorithm-freeze.json'),'source_snapshot_is_authoritative':True,'original_jars':{r:v['original_jar_sha256'] for r,v in old['inputs'].items()},'routing':'static common policy; no result-based retry/fallback'})
    for role,record in old['inputs'].items():assert sha(root/'frozen-base'/role/'original.jar')==record['original_jar_sha256']
    print({'prepared':str(root),'accepted':sum(r['status']=='accepted' for r in results)},flush=True)

def run(root,out,group,queries):
    install(root)
    driver.QUERIES=[q for q in driver.QUERIES if not queries or q['id'] in queries]
    save(root/(out.name+'-launch.json'),{'queries':[q['id'] for q in driver.QUERIES],'runtime':'same 1CPU/768MiB heap32/256 GC1 CI2','independent_oracle':'unchanged run_frozen_capability_acceptance.independent','modes':['full','selective'],'driver_sha256':sha(Path(__file__))})
    if group=='carts':driver.carts(out,root/'frozen-base')
    elif group=='orders':driver.orders(out,root/'frozen-base')
    else:
        os.environ['TF2_CAPABILITY_ROLES']=group;os.environ.setdefault('TF2_CAPABILITY_PORT','19420')
        driver.train(out,root/'frozen-base')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',required=True,type=Path);p.add_argument('--prepare',action='store_true');p.add_argument('--out',type=Path);p.add_argument('--group',default='basic');p.add_argument('--query',action='append');a=p.parse_args();root=a.root.resolve()
    if a.prepare:prepare(root)
    if a.out:run(root,a.out.resolve(),a.group,a.query)
