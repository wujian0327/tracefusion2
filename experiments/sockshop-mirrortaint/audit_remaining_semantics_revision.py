#!/usr/bin/env python3
"""Separate fresh development regressions from historical offline compatibility."""
import argparse,collections,gc
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save,sha
from audit_application_call_revision import class_hashes
import run_frozen_capability_acceptance as driver
import run_response_binding_revision as old

PREVIOUS=ROOT/'artifacts/orders-availability-20261021/quota-all62/audit-qualified/source-union'

def historical(root,out):
    out.mkdir(parents=True,exist_ok=False);rows=load(PREVIOUS/'instances.json');groups=collections.defaultdict(list)
    for row in rows:
        if row.get('capture') and row['state']=='known_correct':groups[row['capture']].append(row)
    by_id={q['id']:q for q in driver.QUERIES};results=[];hashes={};counts=collections.defaultdict(collections.Counter)
    for capture,items in groups.items():
        cap=Path(capture);q=by_id[items[0]['query']];role=q['role'];graph=old.Reconstruction(cap.parent/'build',cap,[role]);run=load(cap/'run.json')
        for row in items:
            if row.get('message'):message=row['message']
            else:message=run['cases'][0 if row['case']=='first-create'else 1]['message']
            a=graph.query(message,row['path'],role,boundary=old.BOUNDARY)
            if role=='orders':
                from normalize_orders_origins import source_coordinate
                actual={source_coordinate(role,s,graph.rows[role]) for s in a['sources']}
            else:actual={old.predicted_coord(s) for s in a['sources']}
            expected={tuple(x)for x in row['expected']}
            state=('known_correct'if actual==expected else'known_wrong')if a['known']else'unknown'
            assert state==row['state'],(row['query'],row['case'],state,row['state'])
            results.append({'mode':row['mode'],'query':row['query'],'case':row['case'],'path':row['path'],'old_state':row['state'],'new_state':state,'capture':capture});counts[row['mode']][state]+=1
        for f in [cap/role/'events.jsonl',cap/'run.json',cap.parent/'build'/role/'plan.json']:hashes[str(f)]=sha(f)
        del graph;gc.collect()
        print({'replayed':len(results),'capture':cap.parent.name},flush=True)
    for mode in ('full','selective'):assert counts[mode]=={'known_correct':382},counts[mode]
    save(out/'results.json',{'all_passed':True,'basis':'Previously known answers only; old Agent/plans/captures, current offline code. Not new deployments or new overall-version answerability. Old unknown captures may lack newly required library witnesses.','modes':dict(counts),'previous_unknown_not_claimed_as_replayed':39,'planning_rejections_not_executed':10,'records':results,'raw_sha256':hashes})

def audit(root,out):
    out.mkdir(parents=True,exist_ok=False);freeze=load(root/'frozen-candidate/algorithm-freeze.json');agent=class_hashes(root/'frozen-candidate/frozen-base/distributed-observer.jar')
    for p,h in freeze['sources'].items():assert sha(Path(p))==h,p
    planning=load(root/'frozen-candidate/frozen-plans/planning.json');rejected=[r for r in planning if r['status']=='rejected']
    assert len(planning)==62 and len(rejected)==1 and rejected[0]['query']['id']=='trainticket-price-findAllPriceConfig-data-each-id'
    assert 'Ljava/util/UUID;'in rejected[0]['rejection']
    reports={};receipts={};by_id={q['id']:q for q in driver.QUERIES}
    expected={'cart':{'known_correct':15,'unknown':3},'basic':{'unknown':21},'station':{'known_correct':20},'route':{'known_correct':40}}
    for group,want in expected.items():
        result=load(root/('final-'+group)/'results.json');assert result['complete'];counts=collections.defaultdict(collections.Counter);evaluations=[]
        for record in result['results']:
            assert 'failure'not in record and not record.get('oracle_unavailable'),record
            mode=record['mode'];q=by_id[record['query']];d=root/('final-'+group)/(mode+'-'+q['id']);ev=load(d/'evaluation.json');counts[mode].update(ev['states'])
            assert class_hashes(d/'build/distributed-observer.jar')==agent
            assert sha(d/'build'/q['role']/'plan.json')==sha(root/'frozen-candidate/frozen-plans'/(q['id']+'.json'))
            assert load(d/'capture/run.json')['status']=='business-completed' and load(d/'input-audit.json')['checks']
            for role,h in freeze['original_jars'].items():assert sha(d/'build'/role/'original.jar')==h
            services=load(d/'capture/compose.json')['services'];observed=[v for v in services.values()if '-javaagent:'in v.get('environment',{}).get('JAVA_OPTS','')];assert len(observed)==1
            for config in observed:
                flags=config['environment']['JAVA_OPTS'].split();assert all(x in flags for x in ('-Xms32m','-Xmx256m','-XX:ParallelGCThreads=1','-XX:CICompilerCount=2'))
                assert config['cpus']==1 and config['mem_limit']=='768m'
            for f in [d/'capture'/q['role']/'events.jsonl',d/'capture/run.json',d/'independent-truth.json',d/'evaluation.json']:receipts[str(f.relative_to(ROOT))]=sha(f)
            evaluations.extend({**r,'mode':mode}for r in ev['predictions'])
        for mode in ('full','selective'):assert counts[mode]==want,(group,mode,counts[mode],want)
        mapping={(r['mode'],r['query'],r['case'],r['path']):r for r in evaluations}
        for r in evaluations:
            other=mapping[('selective'if r['mode']=='full'else'full',r['query'],r['case'],r['path'])];assert r['state']==other['state']
        reports[group]={'modes':dict(counts),'deployments':len(result['results']),'queries':len(result['results'])//2}
    semantics=load(root/'semantics-04/results.json');numeric=load(root/'numeric-final/results.json');application=load(root/'application-regression/results.json');history=load(root/'historical-known-offline/results.json')
    assert all(x['all_passed']for x in [semantics,numeric,application,history])
    for name,result in [('semantics-04',semantics),('numeric-final',numeric),('application-regression',application)]:assert class_hashes(root/name/'build/distributed-observer.jar')==agent
    save(out/'audit.json',{'all_passed':True,'algorithm_commit':freeze['algorithm_commit'],'fresh_groups':reports,'newly_correct_development_instances_per_mode':15,'remaining_original_counterexamples':{'Cart_create_unknown':3,'Basic_unknown':21,'UUID_planning_rejected':10},'new_full431_deployment_completed':False,'historical_offline_only':history['modes'],'heldout_29':'not planned/executed','costs':'not measured','raw_sha256':receipts})
    print(reports,flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',required=True,type=Path);p.add_argument('--out',required=True,type=Path);p.add_argument('--historical',action='store_true');a=p.parse_args();(historical if a.historical else audit)(a.root.resolve(),a.out.resolve())
