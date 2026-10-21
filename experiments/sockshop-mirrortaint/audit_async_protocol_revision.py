#!/usr/bin/env python3
"""Recheck closed task identities and independently rescore original Orders captures."""
import argparse, collections, copy, json
from pathlib import Path
from run_planned_service import ROOT, HERE, load, save, sha
from infer_async_protocol import validate_async_protocol
from audit_application_call_revision import class_hashes
from run_async_orders_revision import evaluate
from plan_response_binding import plan_response
from run_execution_kernel_pilot import independent
import run_response_binding_revision as old
import run_ticketinfo_wrapper_revision as ticketinfo_driver


def audit(root, out):
    out.mkdir(parents=True, exist_ok=False)
    freeze=load(root/'algorithm-freeze.json'); raw={}; orders={}; protocols={}; mutations={}
    assert all(sha(Path(p))==s for p,s in freeze['sources'].items())
    assert all(sha(Path(p))==s for p,s in freeze['driver_hashes'].items())
    assert sha(HERE/'async-task-protocol-20261021.json')==freeze['protocol_sha256']
    assert sha(HERE/'execution-kernel-protocol-20261020.json')==freeze['reserved_protocol_sha256']
    assert len(load(HERE/'execution-kernel-protocol-20261020.json')['unexamined_candidates'])==29
    base=root/'base-build'; agent=class_hashes(base/'distributed-observer.jar')
    assert sha(HERE/'build_distributed_plans.py')==load(base/'build.json')['builder_sha256']
    assert all(sha(base/r/'original.jar')==s for r,s in freeze['original_jars'].items())
    def record(path): raw[str(path.relative_to(ROOT))]=sha(path)
    semantics=load(root/'semantics-final-02/results.json')
    for mode in ('full','selective'):
        p=load(root/'semantics-final-02/build/fixture/plan.json')
        rows=[json.loads(s) for s in (root/'semantics-final-02'/mode/'events.jsonl').read_text().splitlines()]
        current=validate_async_protocol(p,rows)
        assert current==semantics['modes'][mode]['audit'] and len(current['tasks'])==15
        assert len(semantics['modes'][mode]['faults'])==14 and all(semantics['modes'][mode]['faults'].values())
        assert class_hashes(root/'semantics-final-02/build/distributed-observer.jar')==agent
        record(root/'semantics-final-02'/mode/'events.jsonl')
    fixtures=None; snapshots=[]
    for d in sorted((root/'business-frozen-first').glob('*-sockshop-*')):
        config=load(d/'configuration.json'); query=config['query']; mode=config['mode']
        p=load(d/'build/orders/plan.json'); path=d/'capture/orders/events.jsonl'
        fresh=plan_response(load(d/'build/orders/model.json'),query['entry'],query['target'],query['path'],
                            execution_kernel=True,application_calls=True)
        fresh['source_evidence']=True;fresh['async_protocol']=load(HERE/'async-task-contracts-20261021.json')
        assert fresh==p
        rows=[json.loads(s) for s in path.read_text().splitlines()];record(path)
        assert not any(r['kind']=='problem' for r in rows)
        assert class_hashes(d/'build/distributed-observer.jar')==agent
        scoring=out/'rescored'/d.name;scoring.mkdir(parents=True)
        (scoring/'build').symlink_to(d/'build',target_is_directory=True)
        (scoring/'capture').symlink_to(d/'capture',target_is_directory=True)
        result=evaluate(scoring,query); orders[d.name]=result
        scored=load(scoring/'evaluation.json')['predictions'];tp=fp=fn=0
        for target in scored:
            expected={tuple(v) for v in target['expected']}
            actual={old.predicted_coord(s) for s in target['answer']['sources']} if target['answer']['known'] else set()
            tp+=len(actual&expected);fp+=len(actual-expected);fn+=len(expected-actual)
        result.update(tp=tp,fp=fp,fn_including_unknown_positive=fn,
                      answerability=result['known_exact']/result['targets'],known_exact_rate=None)
        assert result['targets']==result['unknown']==6 and result['known_exact']==result['wrong']==0
        current=validate_async_protocol(p,rows); protocols[d.name]=current
        assert len(current['tasks'])==36 and all(t['status']=='worker_completed' for t in current['tasks'])
        assert sum(len(t['gets']) for t in current['tasks'])==66
        assert all(len(t['rpc_messages'])==1 for t in current['tasks'])
        run=load(d/'capture/run.json'); observed=[(c['fixture'],c['request_body'],c['message']) for c in run['cases']]
        if fixtures is None: fixtures=observed
        else: assert fixtures==observed
        snapshots.extend({'configuration':d.name,**t} for t in load(scoring/'evaluation.json')['predictions'])
        tests={}
        for label in ('missing-worker-completion','wrong-worker-object','wrong-future','wrong-inner',
                      'missing-get-proof','wrong-get-task','missing-worker-frame','wrong-framework-hash'):
            changed=copy.deepcopy(rows)
            if label=='missing-worker-completion': changed.remove(next(r for r in changed if r['kind']=='async-worker-end'))
            elif label=='wrong-worker-object': next(r for r in changed if r['kind']=='enter' and r.get('async_task_id'))['receiver']='wrong-object'
            elif label=='wrong-future': next(r for r in changed if r['kind']=='async-submit-end')['future']['object']='wrong-future'
            elif label=='wrong-inner': next(r for r in changed if r['kind']=='async-worker-inner')['inner']['object']='wrong-inner'
            elif label=='missing-get-proof': del next(r for r in changed if r.get('async_future'))['async_future']
            elif label=='wrong-get-task': next(r for r in changed if r.get('async_future'))['async_future']['task_id']=-1
            elif label=='missing-worker-frame': changed.remove(next(r for r in changed if r['kind']=='enter' and r.get('async_task_id')))
            else: next(r for r in changed if r['kind']=='async-framework')['sha256']='wrong'
            try: validate_async_protocol(p,changed)
            except ValueError: tests[label]=True
            else: raise AssertionError('Original business accepted '+label)
        mutations[d.name]=tests
    assert len(orders)==4 and load(root/'business-frozen-first/cleanup.json')['status']=='completed'
    loops=load(root/'loop-frozen/results.json');assert loops['complete']
    for d in sorted((root/'loop-frozen').glob('*-trainticket-*')):
        q=load(d/'query.json');role=q['role'];cap=d/'capture'
        assert class_hashes(d/'build/distributed-observer.jar')==agent
        graph=old.Reconstruction(d/'build',cap,[role]);rows=graph.rows[role]
        for case in load(cap/'run.json')['cases']:
            for path,value in old.leaves(case['response'],q['path']):
                want=independent(q,case,path,rows)
                answer=graph.query(case['message'],path,role,boundary=old.BOUNDARY)
                assert answer['known'] and {old.predicted_coord(s) for s in answer['sources']}==want
    for mode in ('full','selective'):
        assert sum(r['exact'] for r in loops['results'] if r['mode']==mode)==60
    cart=load(root/'cart-pair-frozen/results.json');assert cart['all_passed']
    assert all(v['known_exact']==2 and v['unknown']==0 for v in cart['results'])
    for mode in ('full','selective'):
        d=root/'cart-pair-frozen'/mode;cap=d/'capture'
        assert class_hashes(d/'build/distributed-observer.jar')==agent
        graph=old.Reconstruction(d/'build',cap,['carts']);rows=graph.rows['carts']
        for case in load(cap/'run.json')['cases']:
            ret=next(r for r in rows if r['kind']=='binding-return' and r.get('message')==case['message'])
            family={ret['frame']}
            for _ in range(30): family.update(r['frame'] for r in rows if r['kind']=='enter' and r.get('parent') in family)
            sources=[r for r in rows if r['kind']=='binding-source' and r.get('frame') in family and '.findByCustomerId(' in r['callee']]
            assert len(sources)==1
            calls=[r for r in rows if r['kind']=='collection-call-enter' and r.get('frame') in family and r['callee']==sources[0]['callee']]
            assert len(calls)==(2 if case['created'] else 1)
            f=next(f for f in sources[0]['fields'] if f['path']=='/0/customerId')
            assert f['observed']['value']==case['customerId']
            a=graph.query(case['message'],'/customerId','carts',boundary=old.BOUNDARY)
            assert a['known'] and {old.predicted_coord(s) for s in a['sources']}=={old.source_coord('carts',sources[0],f)}
    ticketinfo=load(root/'ticketinfo-frozen/results.json');assert ticketinfo['complete']
    for d in sorted((root/'ticketinfo-frozen').glob('*-trainticket-*')):
        q=load(d/'configuration.json')['query']
        assert class_hashes(d/'build/distributed-observer.jar')==agent
        scoring=out/'rescored-ticketinfo'/d.name;scoring.mkdir(parents=True)
        (scoring/'build').symlink_to(d/'build',target_is_directory=True)
        (scoring/'capture').symlink_to(d/'capture',target_is_directory=True)
        result=ticketinfo_driver.evaluate(scoring,q)
        assert result['correct']==result['targets']==7 and result['unknown']==result['wrong']==0
    for mode in ('full','selective'):
        assert sum(v['correct'] for v in ticketinfo['results'] if v['mode']==mode)==21
    assert load(root/'legacy-offline/results.json')['states']=={'known_correct':213,'unknown':88}
    for suite in ('foundation-controls','application-controls'):
        control=load(root/suite/'results.json');assert control['all_passed']
    for path in root.rglob('events.jsonl'):
        record(path)
    summary={'all_passed':True,'algorithm_commit':freeze['commit'],'orders':orders,
             'async_tasks_total':sum(len(v['tasks']) for v in protocols.values()),
             'async_gets_total':sum(len(t['gets']) for v in protocols.values() for t in v['tasks']),
             'orders_targets':24,'orders_known':0,'orders_unknown':24,'orders_wrong':0,
             'new_gap_repairs':0,'cumulative_gap_repairs':97,'remaining_gap_instances':72,
             'semantics_tasks_per_mode':15,'semantics_faults_per_mode':14,
             'business_faults_per_configuration':8,'loop_exact_per_mode':60,'cart_pair_exact_per_mode':2,
             'ticketinfo_exact_per_mode':21,
             'legacy_offline_correct':213,'legacy_offline_unknown':88,'heldout_unexamined':29,
             'observation_only':True,'no_performance':True,'full_62_acceptance_complete':False}
    save(out/'raw-sha256.json',raw);save(out/'task-receipts.json',protocols)
    save(out/'orders-instances.json',snapshots);save(out/'business-mutations.json',mutations)
    save(out/'audit.json',summary);save(HERE/'async-protocol-results-20261021.json',summary)
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();audit(a.root.resolve(),a.out.resolve())
