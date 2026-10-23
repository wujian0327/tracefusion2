#!/usr/bin/env python3
"""Reuse only exact captures across the final routing-only correction."""
import argparse,copy,shutil,subprocess,hashlib
from pathlib import Path
from run_planned_service import ROOT,load,save,sha
from audit_application_call_revision import class_hashes
import run_frozen_capability_acceptance as driver
import run_quota_capability_acceptance as quota

CHANGED={'sockshop-carts-addToCart-unitPrice','sockshop-carts-addToCart-quantity','sockshop-carts-addToCart-itemId'}


def reuse(root):
    prior=root.parent/'final';driver.HOME=root;driver.check();agent=class_hashes(root/'frozen-base/distributed-observer.jar');assert agent==class_hashes(prior/'frozen-base/distributed-observer.jar')
    before=load(prior/'algorithm-freeze.json')['sources'];after=load(root/'algorithm-freeze.json')['sources'];allowed={'build_distributed_plans.py','plan_capability_policy.py','plan_async_dependencies.py','contract_obligations.py'}
    assert all(Path(k).name in allowed for k in before.keys()|after.keys()if before.get(k)!=after.get(k))
    changed={q['id']for q in driver.QUERIES if sha(root/'frozen-plans'/(q['id']+'.json'))!=sha(prior/'frozen-plans'/(q['id']+'.json'))};assert changed==CHANGED
    receipts=[];byid={q['id']:q for q in driver.QUERIES}
    for folder in ('all62-orders-serial','all62-reads','all62-route','all62-travel','all62-cart'):
        previous=load(prior/folder/'results.json');assert previous['complete'];out=root/folder;out.mkdir(exist_ok=True);records=[]
        for rec in previous['results']:
            q=byid[rec['query']]
            if q['id']in changed:continue
            name=rec['mode']+'-'+q['id'];source=prior/folder/name;d=out/name;d.mkdir(exist_ok=True)
            assert sha(source/'build'/q['role']/'plan.json')==sha(root/'frozen-plans'/(q['id']+'.json'))and class_hashes(source/'build/distributed-observer.jar')==agent
            for part in ('build','capture','input-audit.json'):
                if not(d/part).exists():(d/part).symlink_to(source/part,target_is_directory=(source/part).is_dir())
                assert (d/part).resolve()==(source/part).resolve()
            for name in ('evaluation.json','independent-truth.json','execution-audit.json'):
                if(source/name).exists():
                    if not(d/name).exists():shutil.copyfile(source/name,d/name)
                    assert sha(d/name)==sha(source/name)
            receipt={'source':str(source),'new_deployment':False,'all_compiled_Agent_classes_and_plan_bytes_identical':True,'all_reconstruction_sources_unchanged':True,'raw_sha256':sha(source/'capture'/q['role']/'events.jsonl'),'original_manifest_sha256':sha(source/'build/build.json'),'original_evaluation_sha256':sha(source/'evaluation.json')};save(d/'reuse.json',receipt);receipts.append(receipt);records.append({k:v for k,v in load(d/'evaluation.json').items()if k!='predictions'})
        save(out/'results.json',{'complete':folder!='all62-cart','results':records,'reuse':'Exact plan and compiled Agent, unchanged offline semantics. Changed Cart plans await new capture.'})
    # Existing pair and semantic suites use identical plans and Agent classes.
    for folder in ('cart-create-pair','closure-controls','controls','guard-controls','date-controls','received-controls','legacy-collection-controls'):
        if not(root/folder).exists():(root/folder).symlink_to(prior/folder,target_is_directory=True)
    assert sha(prior/'cart-create-pair/full/build/carts/plan.json')==sha(root/'frozen-plans/sockshop-carts-get-customerId.json')
    import run_execution_closure_revision as old29
    qs=load(old29.FIRST29/'protocol-before-first.json')['queries'];records=[];out=root/'regression29-train';out.mkdir(exist_ok=True);oldresult=load(prior/'regression29-train/results.json');assert oldresult['complete']
    original_queries=driver.QUERIES;driver.QUERIES=qs
    # This stage reuses scores only after proving both the data and all
    # reconstruction/oracle sources identical. The independent full audit
    # rechecks their state and origin signatures at the final version.
    for rec in oldresult['results']:
        q=next(q for q in qs if q['id']==rec['query']);source=prior/'regression29-train'/(rec['mode']+'-'+q['id']);d=out/source.name
        assert sha(source/'build'/q['role']/'plan.json')==sha(root/'regression29-plans'/(q['id']+'.json'))and class_hashes(source/'build/distributed-observer.jar')==agent
        if not d.exists():d.symlink_to(source,target_is_directory=True)
        records.append(rec)
    driver.QUERIES=original_queries
    save(out/'results.json',{'complete':True,'results':records,'reuse':'Raw, plans, compiled Agent and independent scoring sources unchanged; original scores retained.'})
    for folder in ('development-route-frozen','development-price-frozen','application-off'):
        if not(root/folder).exists():(root/folder).symlink_to(prior/folder,target_is_directory=True)
    for q in load(root/'protocol.json')['queries']:assert sha(root/'write-plans'/(q['id']+'.json'))==sha(prior/'write-plans'/(q['id']+'.json'))
    save(root/'capture-reuse-audit.json',{'all_passed':True,'changed_queries':sorted(changed),'reused62_configurations':len(receipts),'receipts':receipts,'same_compiled_Agent_classes':True,'reconstruction_oracle_sources_unchanged':True,'old_failed_Cart_predictions_retained':str(prior/'all62-cart'),'not_new_independent_deployments':True})


def cart(root):
    quota.install(root);driver.QUERIES=[q for q in driver.QUERIES if q['id']in CHANGED]
    out=root/'cart-render-recapture';driver.carts(out,root/'frozen-base');new=load(out/'results.json');assert new['complete']
    merge(root)


def merge(root):
    out=root/'cart-render-recapture';new=load(out/'results.json');assert new['complete']
    existing=load(root/'all62-cart/results.json')
    for rec in new['results']:
        name=rec['mode']+'-'+rec['query']
        if not(root/'all62-cart'/name).exists():(root/'all62-cart'/name).symlink_to(out/name,target_is_directory=True)
    unchanged=[r for r in existing['results']if r['query']not in CHANGED]
    save(root/'all62-cart/results.json',{'complete':True,'results':unchanged+new['results'],'changed_plan_captures_fresh':6,'unchanged_plan_captures_reused':14})


def cache(root):
    import audit_frozen_capability_acceptance as audit
    destination=root/'compatible-score-cache';destination.mkdir();hashes={};derived={};count=0
    for folder in ('all62-orders-serial','all62-reads','all62-route','all62-travel','all62-cart'):
        r=load(root/folder/'results.json');assert r['complete']
        for rec in r['results']:
            q=next(q for q in driver.QUERIES if q['id']==rec['query']);d=root/folder/(rec['mode']+'-'+q['id']);c=destination/('rescore-'+d.name);c.mkdir();manifest=load(d/'build/build.json')
            expected=load(root/'algorithm-freeze.json')['sources'];allowed={'build_distributed_plans.py','plan_capability_policy.py','plan_async_dependencies.py','contract_obligations.py'}
            assert all(Path(k).name in allowed for k in manifest['sources'].keys()|expected.keys()if manifest['sources'].get(k)!=expected.get(k))
            assert manifest['sources']==expected or load(d/'reuse.json')['all_reconstruction_sources_unchanged']
            for name in ('evaluation.json','independent-truth.json','execution-audit.json'):
                if(d/name).exists():shutil.copyfile(d/name,c/name);derived[str((c/name).relative_to(destination))]=sha(c/name)
            for path in (d/'capture'/q['role']/'events.jsonl',d/'capture/run.json',d/'input-audit.json',d/'build'/q['role']/'plan.json'):hashes[str(path.relative_to(ROOT))]=sha(path)
            count+=1
    assert count==124
    names=('run_frozen_capability_acceptance.py','run_response_binding_revision.py','run_execution_kernel_pilot.py','run_sockshop_model_revision.py','normalize_orders_origins.py','audit_baseline_capabilities.py')
    from run_planned_service import HERE
    for name in names:
        original=root.parent/'final/drivers'/name
        if original.exists():assert sha(original)==sha(HERE/name)
        old_commit=load(root.parent/'final/algorithm-freeze.json')['commit']
        contents=subprocess.check_output(['git','show',old_commit+':'+str((HERE/name).relative_to(ROOT))],cwd=ROOT)
        assert hashlib.sha256(contents).hexdigest()==sha(HERE/name)
    save(destination/'raw-hashes.json',hashes);save(destination/'audit.json',{'all_passed':True,'scope':'Compatibility and hashes of124 precomputed independent scores; not an end-to-end capability verdict. The final auditor computes that verdict separately.','scoring_source_sha256':{str(HERE/name):sha(HERE/name)for name in names},'derived_sha256':derived,'reconstruction_source_differences_confined_to_routing_and_builder':True})


def capability(root):
    import audit_execution_closure_revision as current
    from audit_frozen_capability_acceptance import audit
    current.audit62=lambda home,out,partial:audit(home,out,partial=partial,reuse=root/'compatible-score-cache')
    current.development(root)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',required=True,type=Path);p.add_argument('--stage',required=True,choices=('reuse','cart','merge','cache','capability'));a=p.parse_args();{'reuse':reuse,'cart':cart,'merge':merge,'cache':cache,'capability':capability}[a.stage](a.root.resolve())
