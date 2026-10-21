#!/usr/bin/env python3
"""Recompute original Orders instance truth, admission guards and version identity.

Writes only a new derived directory; never changes captured evidence. The oracle
is the separately reviewed original-code/raw-message oracle used by the driver.
"""
import argparse,collections,copy,json
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save,sha
from audit_application_call_revision import class_hashes
from plan_response_binding import plan_response
from plan_async_dependencies import attach_async_dependencies
from infer_async_protocol import validate_async_protocol
from infer_execution_kernel import infer_execution
from run_orders_source_chain import evaluate
from normalize_orders_origins import source_coordinate
from run_execution_kernel_pilot import independent
import run_ticketinfo_wrapper_revision as ticket
import run_response_binding_revision as old


def audit(root,out):
    out.mkdir(parents=True,exist_ok=False)
    frozen=load(root/'algorithm-freeze.json');base=Path(frozen['base_build'])
    for category in ('sources','drivers'):
        assert all(sha(Path(p))==s for p,s in frozen[category].items()),category
    for name,key in [('orders-end-to-end-protocol-20261021.json','protocol_sha256'),('execution-kernel-protocol-20261020.json','reserved_protocol_sha256'),('capability-comparison-62-20261020.json','baseline_protocol_sha256')]:
        assert sha(HERE/name)==frozen[key]
    assert len(load(HERE/'execution-kernel-protocol-20261020.json')['unexamined_candidates'])==29
    agent=class_hashes(base/'distributed-observer.jar');raw={};checked_builds={}
    assert all(sha(base/r/'original.jar')==v for r,v in frozen['original_jars'].items())
    def record(path):raw[str(path.relative_to(ROOT))]=sha(path)
    def build_check(build,role):
        assert class_hashes(build/'distributed-observer.jar')==agent,build
        assert sha(build/role/'original.jar')==frozen['original_jars'][role]
        p=load(build/role/'plan.json');fresh=plan_response(load(build/role/'model.json'),p['entry'],p['target'],p['response_binding']['path'],execution_kernel=True,application_calls=True)
        if p.get('source_evidence'):fresh['source_evidence']=True
        if p.get('async_dependencies'):fresh=attach_async_dependencies(fresh)
        assert p==fresh,build
        checked_builds[str(build.relative_to(ROOT))]={'plan_equal':True,'all_agent_classes_equal':True,'actual_plan_sha256':sha(build/role/'plan.json')}
    protocol=load(HERE/'orders-end-to-end-protocol-20261021.json');queries={q['id']:q for q in protocol['queries']}
    baseline_path=ROOT/'artifacts/baseline-capability-20261020/audit-final-v3/instances.json'
    baseline={(r['query'],r['case']):r for r in load(baseline_path) if r['query'] in queries}
    assert len(baseline)==72 and all(r['baseline_state']=='known_correct' and r['tf_state']!='known_correct' for r in baseline.values())
    record(baseline_path)
    reference=None;orders=[];instances=[];tasks=[];sample=None
    ds=sorted((root/'business-frozen-final').glob('*-sockshop-*'))
    assert len(ds)==24 and load(root/'business-frozen-final/results.json')['complete']
    assert load(root/'business-frozen-final/cleanup.json')['status']=='completed'
    for d in ds:
        cfg=load(d/'configuration.json');q=cfg['query'];assert q==queries[q['id']]
        build_check(d/'build','orders');p=load(d/'build/orders/plan.json')
        assert p==load(root/'frozen-plans-v3'/(q['id']+'.json'))
        cap=d/'capture';path=cap/'orders/events.jsonl';record(path)
        rows=[json.loads(s) for s in path.read_text().splitlines()]
        assert not any(r['kind']=='problem' for r in rows)
        cases=load(cap/'run.json')['cases'];assert len(cases)==6
        frozen_input=[(c['fixture'],c['request_body'],c['message']) for c in cases]
        if reference is None:reference=frozen_input
        else:assert frozen_input==reference
        dest=out/'orders-rescored'/d.name;dest.mkdir(parents=True)
        (dest/'build').symlink_to(d/'build',target_is_directory=True);(dest/'capture').symlink_to(cap,target_is_directory=True)
        ev=evaluate(dest,q);scores=load(dest/'evaluation.json')['predictions'];tp=fp=fn=empty=0
        for t in scores:
            want={tuple(v) for v in t['expected']};answer=t['answer'];actual={source_coordinate('orders',s,rows) for s in answer['sources']} if answer['known'] else set()
            previous=baseline[(q['id'],t['case'])];assert len(want)==previous['source_set_size']
            tp+=len(want&actual);fp+=len(actual-want);fn+=len(want-actual);empty+=answer['known'] and not want
            instances.append({'configuration':d.name,**t})
        ev.update(query=q['id'],path=q['path'],mode=cfg['mode'],tp=tp,fp=fp,fn_including_unknown_positive=fn,known_empty=empty,answerability=ev['known_exact']/ev['targets'])
        assert ev['targets']==6 and not ev['wrong'] and not ev['evidence_invalid']
        if q['path']=='/date':assert ev['unknown']==6 and ev['known_exact']==0
        else:assert ev['known_exact']==6 and ev['unknown']==0
        receipt=validate_async_protocol(p,rows);tasks.append({'configuration':d.name,'tasks':len(receipt['tasks']),'gets':sum(len(t['gets']) for t in receipt['tasks'])})
        if q['path']=='/customer/username' and cfg['mode']=='full':sample=(p,rows,scores)
        orders.append(ev)
    assert len({(r['query'],r['mode']) for r in orders})==24
    totals={}
    for mode in ('full','selective'):
        rs=[r for r in orders if r['mode']==mode];totals[mode]={key:sum(r[key] for r in rs) for key in ('targets','known_exact','unknown','wrong','evidence_invalid','oracle_unavailable','N/A_requests','tp','fp','fn_including_unknown_positive','known_empty')}
        assert totals[mode]['targets']==72 and totals[mode]['known_exact']==66 and totals[mode]['unknown']==6
    # Actual business evidence perturbations, additional to fixture controls.
    p,rows,scores=sample;mutations={}
    for label in ('missing-worker-end','wrong-future','missing-save-proof','executed-save-handler','wrong-callback-call','wrong-RPC-parent'):
        altered=copy.deepcopy(rows)
        if label=='missing-worker-end':altered.remove(next(r for r in altered if r['kind']=='async-worker-end'))
        elif label=='wrong-future':next(r for r in altered if r['kind']=='async-submit-end')['future']['object']='wrong'
        elif label=='missing-save-proof':altered.remove(next(r for r in altered if r['kind']=='mongo-save-effect'))
        elif label=='executed-save-handler':next(r for r in altered if r['kind']=='mongo-save-effect')['callback_invocations']=1
        elif label=='wrong-callback-call':next(r for r in altered if r['kind']=='enter' and '/Customer.toString' in r['method'])['callback_call_id']=-1
        else:next(r for r in altered if r['seq']==scores[0]['answer']['sources'][0]['seq'])['parent_message']='wrong-parent'
        try:infer_execution(p,altered)
        except ValueError:mutations[label]='refused'
        else:raise AssertionError('Accepted corrupted business evidence: '+label)
    controls={}
    for name,expected in {'request-frozen-final':(24,14,10,11),'mongo-frozen-final':(14,6,8,9),'async-controls-final':(30,18,12,6),'list-callback-development-02':(10,8,2,5),'application-controls-final':(34,26,8,6),'foundation-controls-final':(30,18,12,9)}.items():
        d=root/name;report=load(d/'results.json');assert report['all_passed'];assert class_hashes(d/'build/distributed-observer.jar')==agent
        controls[name]={}
        for mode,r in report['modes'].items():
            known=r.get('known_exact',r.get('known'));assert (r['targets'],known,r['expected_unknown'],len(r['faults']))==expected
            assert all(r['faults'].values());g=old.Reconstruction(d/'build',d/mode,['fixture']);rows=g.rows['fixture']
            for c in r['checks']:
                message=c.get('case',{}).get('message',c['answer']['target']['message'])
                a=g.query(message,'/text','fixture',boundary=old.BOUNDARY);assert a==c['answer']
                if name in ('request-frozen-final','list-callback-development-02','foundation-controls-final') and a['known']:
                    truth=c.get('truth',c.get('expected'));assert {old.predicted_coord(s) for s in a['sources']}=={tuple(v) for v in truth}
                if name in ('mongo-frozen-final','async-controls-final') and a['known']:
                    root_frame=next(x['frame'] for x in rows if x['kind']=='binding-return' and x.get('message')==message);assert {int(s['field'].split(':')[1]) for s in a['sources']}==set(c['expected_root_arguments']) and all(s['root_frame']==root_frame for s in a['sources'])
                if name=='application-controls-final' and a['known']:
                    truth=set();want=c['expected_argument']
                    if isinstance(want,int):
                        source=next(x for x in rows if x['kind']=='binding-input' and x.get('message')==message and x['argument']==want);f=next(f for f in source['fields'] if f['field']=='ApplicationCallFixture$Item.text');truth={old.source_coord('fixture',source,f)}
                    assert {old.predicted_coord(s) for s in a['sources']}==truth
            record(d/mode/'fixture/events.jsonl');controls[name][mode]={'targets':r['targets'],'known_exact':known,'expected_unknown':r['expected_unknown'],'faults':len(r['faults'])}
    loops=load(root/'loop-frozen-final/results.json');assert loops['complete']
    for d in (root/'loop-frozen-final').glob('*-trainticket-*'):
        q=load(d/'query.json');role=q['role'];build_check(d/'build',role);cap=d/'capture';g=old.Reconstruction(d/'build',cap,[role])
        for c in load(cap/'run.json')['cases']:
            for path,value in old.leaves(c['response'],q['path']):
                a=g.query(c['message'],path,role,boundary=old.BOUNDARY);assert a['known'] and {old.predicted_coord(s) for s in a['sources']}==independent(q,c,path,g.rows[role])
        record(cap/role/'events.jsonl')
    for mode in totals:assert sum(r['exact'] for r in loops['results'] if r['mode']==mode)==60
    ti=load(root/'ticketinfo-frozen-final/results.json');assert ti['complete']
    for d in (root/'ticketinfo-frozen-final').glob('*-trainticket-*'):
        q=load(d/'configuration.json')['query'];build_check(d/'build','ticketinfo');dest=out/'ticketinfo-rescored'/d.name;dest.mkdir(parents=True);(dest/'build').symlink_to(d/'build',target_is_directory=True);(dest/'capture').symlink_to(d/'capture',target_is_directory=True);ev=ticket.evaluate(dest,q);assert ev['correct']==ev['targets']==7 and ev['wrong']==ev['unknown']==0;record(d/'capture/ticketinfo/events.jsonl')
    for mode in totals:assert sum(r['correct'] for r in ti['results'] if r['mode']==mode)==21
    cart=load(root/'cart-pair-frozen-final/results.json');assert cart['all_passed'] and all(r['known_exact']==2 and r['unknown']==0 for r in cart['results'])
    for mode in totals:
        d=root/'cart-pair-frozen-final'/mode;build_check(d/'build','carts');g=old.Reconstruction(d/'build',d/'capture',['carts']);rows=g.rows['carts']
        for c in load(d/'capture/run.json')['cases']:
            ret=next(r for r in rows if r['kind']=='binding-return' and r.get('message')==c['message']);family={ret['frame']}
            for _ in range(30):family.update(r['frame'] for r in rows if r['kind']=='enter' and r.get('parent') in family)
            sources=[r for r in rows if r['kind']=='binding-source' and r.get('frame') in family and '.findByCustomerId(' in r['callee']];assert len(sources)==1
            f=next(f for f in sources[0]['fields'] if f['path']=='/0/customerId');a=g.query(c['message'],'/customerId','carts',boundary=old.BOUNDARY);assert a['known'] and {old.predicted_coord(s) for s in a['sources']}=={old.source_coord('carts',sources[0],f)}
        record(d/'capture/carts/events.jsonl')
    carts={mode:0 for mode in totals};restore=dict(carts)
    for name in ('cart-gaps-frozen-final','cart-restore-frozen-final'):
        report=load(root/name/'results.json');assert report['complete']
        dirs=(root/name).glob('*-sockshop-*') if name=='cart-gaps-frozen-final' else [root/name/m for m in totals]
        for d in dirs:
            q=load(d/'configuration-freeze.json')['query'];build_check(d/'build','carts');cap=d/'capture';g=old.Reconstruction(d/'build',cap,['carts']);rows=g.rows['carts'];mode=load(d/'evaluation.json')['mode']
            for c in load(cap/'run.json')['cases']:
                if c['http_status']!=200:continue
                ret=next(x for x in rows if x['kind']=='binding-return' and x.get('message')==c['message']);family={ret['frame']}
                for _ in range(40):family.update(x['frame'] for x in rows if x['kind']=='enter' and x.get('parent') in family)
                sources=[x for x in rows if x['kind']=='binding-source' and x.get('frame') in family and '.findByCustomerId(' in x['callee']];assert len(sources)==1
                prefix='/0/items'
                if name=='cart-gaps-frozen-final':prefix+='/'+str(next(i for i,x in enumerate(c['fixture']['fixture_read_items']) if x['itemId']==c['request_path'].rsplit('/',1)[-1]))
                for path,value in old.leaves(c['response'],q['path']):
                    f=next(f for f in sources[0]['fields'] if f['path']==prefix+path);a=g.query(c['message'],path,'carts',boundary=old.BOUNDARY);assert a['known'] and {old.predicted_coord(s) for s in a['sources']}=={old.source_coord('carts',sources[0],f)}
                    (carts if name=='cart-gaps-frozen-final' else restore)[mode]+=1
            record(cap/'carts/events.jsonl')
    assert carts=={'full':15,'selective':15} and restore=={'full':6,'selective':6}
    legacy=load(root/'legacy-offline-final/results.json');assert legacy['states']=={'known_correct':213,'unknown':88}
    assert load(root/'constructor-write-refusal.json')['still_refused']
    assert load(root/'recorder-controls-final/results.json')['all_passed']
    redaction=load(root/'diagnostic-redaction-first/results.json');assert redaction['answers_equal'] and redaction['targets']==6
    for name in ('binding-controls-final','lifecycle-controls-final','collection-controls-final'):assert load(root/name/'results.json')['all_passed']
    summary={'all_passed':True,'algorithm_commit':frozen['commit'],'orders_per_mode':totals,'queries':orders,'controls':controls,'business_faults':mutations,'loop_exact_per_mode':60,'ticketinfo_exact_per_mode':21,'cart_pair_exact_per_mode':2,'cart_single_get_exact_per_mode':15,'cart_read_restored_per_mode':6,'legacy_offline':legacy,'diagnostic_redaction':{k:v for k,v in redaction.items() if k!='answers'},'new_development_gap_repairs':66,'cumulative_development_repairs':163,'remaining_development_gaps':6,'heldout_unexamined':29,'whole_62_full_selective_acceptance':False,'goal_382_of_431_confirmed':False,'new_performance':False,'retained_first_failures':{'missing_default_candidate':'24e321e','callback_candidate':'bdbe111','callback_batch_targets_invalid':6}}
    save(out/'audit.json',summary);save(out/'orders-instances.json',instances);save(out/'async-counts.json',tasks);save(out/'build-identity.json',checked_builds);save(out/'raw-sha256.json',raw)
    print(json.dumps({k:v for k,v in summary.items() if k not in ('queries','controls','legacy_offline')},ensure_ascii=False,indent=2))
    return summary

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--snapshot',type=Path);a=p.parse_args();result=audit(a.root.resolve(),a.out.resolve())
    if a.snapshot:save(a.snapshot,result)
