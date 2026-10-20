#!/usr/bin/env python3
"""Frozen constructor and predicate audit; writes only a new audit directory and small summary."""
import argparse,json
from pathlib import Path
from zipfile import ZipFile
from run_planned_service import ROOT,HERE,load,save,sha
from plan_response_binding import plan_response
from infer_distributed_fields import Reconstruction
from infer_execution_kernel import infer_execution
import run_response_binding_revision as old
from run_execution_kernel_pilot import independent
from audit_application_call_revision import class_hashes


def audit(root,out):
    out.mkdir(parents=True,exist_ok=False);freeze=load(root/'algorithm-freeze.json');base=root/'business-frozen-base-build'
    assert all(sha(Path(p))==v for p,v in freeze['sources'].items()),'Frozen code changed'
    assert sha(HERE/'execution-kernel-protocol-20261020.json')==freeze['reserved_protocol_sha256']
    assert len(load(HERE/'execution-kernel-protocol-20261020.json')['unexamined_candidates'])==29
    assert sha(HERE/'constructor-effect-protocol-20261020.json')==freeze['protocol_sha256']
    assert all(sha(base/role/'original.jar')==v for role,v in freeze['original_jars'].items())
    agent=class_hashes(base/'distributed-observer.jar');raw_hashes={};business=[]
    def record(cap,role):
        path=cap/role/'events.jsonl';raw_hashes[str(path.relative_to(ROOT))]=sha(path)
    def plan_equal(build,role):
        p=load(build/role/'plan.json');new=plan_response(load(base/role/'model.json'),p['entry'],p['target'],p['response_binding']['path'],execution_kernel=True,application_calls=True)
        assert p==new;assert class_hashes(build/'distributed-observer.jar')==agent
    for dest in sorted((root/'business-frozen').glob('*-trainticket-*')):
        q=load(dest/'query.json');cap=dest/'capture';plan_equal(dest/'build',q['role']);record(cap,q['role']);run=load(cap/'run.json');assert run['status']=='business-completed' and run['cleanup_returncode']==0
        rows=[json.loads(x) for x in (cap/q['role']/'events.jsonl').read_text().splitlines()];graph=Reconstruction(dest/'build',cap,[q['role']]);checks=[]
        for case in run['cases']:
            for path,value in old.leaves(case['response'],q['path']):
                expected=independent(q,case,path,rows);answer=graph.query(case['message'],path,q['role'],boundary=old.BOUNDARY);actual={old.predicted_coord(s) for s in answer['sources']}
                assert answer['known'] and expected==actual and answer['target']['observed']['value']==value
                checks.append({'case':case['case'],'path':path,'expected':sorted(expected,key=str),'answer':answer})
        business.append({'id':q['id'],'mode':run['mode'],'targets':len(checks),'exact':len(checks),'tp':sum(len(c['expected']) for c in checks),'fp':0,'fn':0,'unknown':0});save(out/(dest.name+'.json'),checks)
    assert len(business)==8
    totals={mode:{key:sum(r[key] for r in business if r['mode']==mode) for key in ('targets','exact','tp','fp','fn','unknown')} for mode in ('full','selective')}
    assert all(v['targets']==60 and v['exact']==60 for v in totals.values())
    # Verify same inputs and actual responses across modes, independent of source inference.
    qs={load(d/'query.json')['id'] for d in (root/'business-frozen').glob('full-*')}
    for qid in qs:
        a=load(root/'business-frozen'/('full-'+qid)/'capture/run.json')['cases'];b=load(root/'business-frozen'/('selective-'+qid)/'capture/run.json')['cases']
        assert len(a)==len(b)
        assert all(all(x[k]==y[k] for k in ('request_path','request_body','database_documents','response','http_status')) for x,y in zip(a,b))
    carts={};creation={}
    for mode in ('full','selective'):
        d=root/'cart-restore-frozen'/mode;cap=d/'capture';plan_equal(d/'build','carts');record(cap,'carts');graph=Reconstruction(d/'build',cap,['carts']);rows=graph.rows['carts'];checks=[]
        for case in load(cap/'run.json')['cases']:
            ret=next(r for r in rows if r['kind']=='binding-return' and r.get('message')==case['message']);family={ret['frame']}
            for _ in range(30):family.update(r['frame'] for r in rows if r['kind']=='enter' and r.get('parent') in family)
            sources=[r for r in rows if r['kind']=='binding-source' and r.get('frame') in family and '.findByCustomerId(' in r['callee']];assert len(sources)==1
            for path,value in old.leaves(case['response'],'/*/itemId'):
                f=next(f for f in sources[0]['fields'] if f['path']=='/0/items'+path);assert f['observed']['value']==value
                answer=graph.query(case['message'],path,'carts',boundary=old.BOUNDARY);assert answer['known'] and {old.predicted_coord(s) for s in answer['sources']}=={old.source_coord('carts',sources[0],f)};checks.append(answer)
        assert len(checks)==6;carts[mode]={'targets':6,'exact':6,'tp':6,'fp':0,'fn':0,'unknown':0};save(out/('cart-'+mode+'.json'),checks)
        d=root/'create-frozen'/mode;cap=d/'capture';plan_equal(d/'build','carts');record(cap,'carts');graph=Reconstruction(d/'build',cap,['carts']);rows=graph.rows['carts'];checks=[]
        for case in load(cap/'run.json')['cases']:
            ret=next(r for r in rows if r['kind']=='binding-return' and r.get('message')==case['message']);family={ret['frame']}
            for _ in range(30):family.update(r['frame'] for r in rows if r['kind']=='enter' and r.get('parent') in family)
            sources=[r for r in rows if r['kind']=='binding-source' and r.get('frame') in family and '.findByCustomerId(' in r['callee']];assert len(sources)==1
            f=next(f for f in sources[0]['fields'] if f['path']=='/0/customerId');answer=graph.query(case['message'],'/customerId','carts',boundary=old.BOUNDARY);assert answer['known']==(case['index']==1)
            calls=[r for r in rows if r['kind']=='collection-call-enter' and r.get('frame') in family and r['callee']==sources[0]['callee']];assert len(calls)==(2 if case['index']==0 else 1)
            if answer['known']:assert {old.predicted_coord(s) for s in answer['sources']}=={old.source_coord('carts',sources[0],f)}
            checks.append({'request':case['index'],'source_read_ordinal':len(calls),'answer':answer})
        creation[mode]={'known_exact':1,'unknown':1,'independent_source_reads':[2,1]};save(out/('creation-'+mode+'.json'),checks)
    # Controls have literal independent argument/constant expectations in the frozen driver.
    controls={}
    for name in ('semantics-frozen','contracts-frozen','application-semantics-frozen'):
        result=load(root/name/'results.json');assert result['all_passed'];assert class_hashes(root/name/'build/distributed-observer.jar')==agent
        for mode in ('full','selective'):
            record(root/name/mode,'fixture');graph=Reconstruction(root/name/'build',root/name/mode,['fixture']);report=result['modes'][mode]
            assert all(report['faults'].values());controls[name+'-'+mode]={k:v for k,v in report.items() if k!='checks'}
    for name in ('binding-frozen','lifecycle-frozen','collection-frozen','loop-semantics-frozen'):
        assert load(root/name/'results.json')['all_passed']
    legacy=load(root/'legacy-offline-frozen/results.json');assert legacy['states']=={'known_correct':213,'unknown':88}
    witness=root/'constructor-write-control';badrows=[json.loads(x) for x in (witness/'events.jsonl').read_text().splitlines()]
    try:infer_execution(load(witness/'plan.json'),badrows)
    except ValueError as e:assert 'constructor write' in str(e)
    else:raise AssertionError('Historical missing constructor write accepted')
    # Re-evaluate each original exposed Cart target against raw repository facts.
    original_file=ROOT/'artifacts/baseline-capability-20261020/audit-final-v3/instances.json';original=load(original_file);protocol=load(HERE/'constructor-effect-protocol-20261020.json');gap_instances=[];gap_queries=[];cart_gaps={};extra_guards={};faults={}
    for mode in ('full','selective'):
        cart_gaps[mode]={'targets':0,'exact':0,'tp':0,'fp':0,'fn':0,'unknown':0};extra_guards[mode]=0
        for q in [q for q in protocol['queries'] if q['role']=='carts']:
            d=root/'cart-gaps-frozen'/(mode+'-'+q['id']);cap=d/'capture';plan_equal(d/'build','carts');record(cap,'carts');graph=Reconstruction(d/'build',cap,['carts']);rows=graph.rows['carts'];checks=[]
            cases=load(cap/'run.json')['cases'];prior=[r for r in original if r['query']==q['id']];baseline_cases=load(Path(prior[0]['baseline_capture'])/'run.json')['cases']
            for case in cases:
                if case.get('supplementary_guard'):
                    assert case['fixture']['fixture_read_items'][0]['quantity']==case['fixture']['fixture_read_items'][1]['quantity'] and case['fixture']['fixture_read_items'][0]['unitPrice']==case['fixture']['fixture_read_items'][1]['unitPrice']
                else:
                    before=next(c for c in baseline_cases if c['case']==case['case']);assert all(case[k]==before[k] for k in ('request_path','request_body','http_status'));assert case['fixture']['expected_items']==before['fixture']['expected_items']
                if case['http_status']!=200:continue
                ret=next(r for r in rows if r['kind']=='binding-return' and r.get('message')==case['message']);family={ret['frame']}
                for _ in range(30):family.update(r['frame'] for r in rows if r['kind']=='enter' and r.get('parent') in family)
                sources=[r for r in rows if r['kind']=='binding-source' and r.get('frame') in family and '.findByCustomerId(' in r['callee']];assert len(sources)==1
                selected=case['request_path'].rsplit('/',1)[-1];index=next(i for i,item in enumerate(case['fixture']['fixture_read_items']) if item['itemId']==selected)
                if case.get('supplementary_guard'):assert index==1
                for path,value in old.leaves(case['response'],q['path']):
                    f=next(f for f in sources[0]['fields'] if f['path']=='/0/items/'+str(index)+path);assert f['observed']['value']==value;answer=graph.query(case['message'],path,'carts',boundary=old.BOUNDARY);expected=old.source_coord('carts',sources[0],f)
                    assert answer['known'] and {old.predicted_coord(s) for s in answer['sources']}=={expected}
                    check={'query':q['id'],'mode':mode,'case':case['case'],'path':path,'status':'known_correct','source_index':index,'expected':expected,'answer':answer};checks.append(check)
                    if case.get('supplementary_guard'):extra_guards[mode]+=1
                    else:
                        prior_instance=next(r for r in prior if r['case']==case['case'] and r['path']==path);assert prior_instance['baseline_state']=='known_correct' and prior_instance['client_value']==value;gap_instances.append(check)
                        for metric in ('targets','exact','tp'):cart_gaps[mode][metric]+=1
            save(out/(mode+'-'+q['id']+'.json'),checks)
            if q['id']=='sockshop-carts-get-quantity':
                import copy
                for label in ('logger-version','missing-logger-contract','filter-capture-identity','missing-required-constructor-field'):
                    altered=copy.deepcopy(rows)
                    if label=='logger-version':next(r for r in altered if r.get('contract',{}).get('kind')=='logger-factory')['contract']['class_sha256']['org/slf4j/LoggerFactory']='wrong-version'
                    elif label=='missing-logger-contract':next(r for r in altered if r.get('contract',{}).get('kind')=='logger-factory').pop('contract')
                    elif label=='filter-capture-identity':next(r for r in altered if r['kind']=='enter' and r.get('callback_call_id'))['receiver']='wrong-predicate-receiver'
                    else:altered.remove(next(r for r in altered if r['kind']=='write' and '.<init>' in r['site'] and r['field'].endswith('.items')))
                    try:infer_execution(load(d/'build/carts/plan.json'),altered)
                    except ValueError as e:faults[mode+'-'+label]=str(e)
                    else:raise AssertionError('Required Cart witness not checked: '+label)
    assert all(t['exact']==15 for t in cart_gaps.values()) and all(v==3 for v in extra_guards.values())
    for q in protocol['queries']:
        old_instances=[r for r in original if r['query']==q['id']]
        if q['role']=='ticketinfo':
            try:plan_response(load(base/q['role']/'model.json'),q['entry'],q['target'],q['path'],execution_kernel=True,application_calls=True)
            except ValueError as e:reason=str(e)
            else:raise AssertionError('Unexpectedly accepted pending TicketInfo query')
            gap_queries.append({'id':q['id'],'targets':len(old_instances),'status':'planning_rejected','reason':reason})
            for mode in ('full','selective'):
                for row in old_instances:gap_instances.append({'query':q['id'],'case':row['case'],'path':row['path'],'mode':mode,'status':'planning_rejected','reason':reason})
        else:gap_queries.append({'id':q['id'],'targets':len(old_instances),'status':'known_correct_both_modes'})
    assert len(gap_instances)==72
    summary={'all_passed':True,'algorithm_commit':freeze['commit'],'cart_new_gap_repairs':cart_gaps,'same_value_second_member_guards':extra_guards,'real_cart_required_evidence_faults':faults,'cart_restoration':carts,'creation_guard':creation,'business_loop_totals':totals,'semantic_controls':controls,'gap_queries':gap_queries,'newly_fixed_baseline_gaps':15,'previously_fixed':60,'remaining_baseline_gaps':94,'reserved_candidates':29,'original_jars':len(freeze['original_jars']),'legacy_offline':legacy,'constructor_write_refusal':True,'whole_62_full_selective_acceptance':False,'goal_382_of_431_met':False,'new_performance':False,'scope':'Original Cart15 newly correct, TicketInfo21 still planning-rejected. Original213 successes retained by old-capture offline replay, not new full deployment.'}
    save(out/'gap-instances.json',gap_instances)
    save(out/'audit.json',summary);save(out/'raw-sha256.json',raw_hashes);save(HERE/'constructor-effect-results-20261020.json',summary);print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',required=True,type=Path);p.add_argument('--out',required=True,type=Path);a=p.parse_args();audit(a.root.resolve(),a.out.resolve())
