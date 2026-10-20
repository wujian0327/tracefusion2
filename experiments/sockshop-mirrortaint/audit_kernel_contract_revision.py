#!/usr/bin/env python3
"""Frozen shared-contract audit; writes only a new audit directory and small summary."""
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
    assert sha(HERE/'kernel-contract-protocol-20261020.json')==freeze['stage_protocol_sha256']
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
        d=root/'cart-frozen'/mode;cap=d/'capture';plan_equal(d/'build','carts');record(cap,'carts');graph=Reconstruction(d/'build',cap,['carts']);rows=graph.rows['carts'];checks=[]
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
    for name in ('semantics-frozen','application-semantics-frozen'):
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
    gaps=load(root/'gaps-frozen/results.json');assert gaps['target_instances']==36 and gaps['newly_correct']==0 and all(r['new_status']=='planning_rejected' for r in gaps['instances'])
    summary={'all_passed':True,'algorithm_commit':freeze['commit'],'cart_restoration':carts,'creation_guard':creation,'business_loop_totals':totals,'semantic_controls':controls,'gap_queries':gaps['queries'],'gap_targets':36,'newly_fixed_baseline_gaps':0,'remaining_baseline_gaps':109,'reserved_candidates':29,'original_jars':len(freeze['original_jars']),'legacy_offline':legacy,'constructor_write_refusal':True,'whole_62_full_selective_acceptance':False,'goal_382_of_431_met':False,'new_performance':False,'scope':'Cart restored through shared kernel; 36 exposed gap instances still planning-rejected, not runtime unknown. 213 old successes are offline replay only.'}
    save(out/'audit.json',summary);save(out/'raw-sha256.json',raw_hashes);save(HERE/'kernel-contract-results-20261020.json',summary);print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',required=True,type=Path);p.add_argument('--out',required=True,type=Path);a=p.parse_args();audit(a.root.resolve(),a.out.resolve())
