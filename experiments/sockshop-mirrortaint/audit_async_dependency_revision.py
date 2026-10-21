#!/usr/bin/env python3
"""Recheck worker dependency sources, private imports and original Orders captures."""
import argparse, collections, copy, json
from pathlib import Path
from run_planned_service import ROOT, HERE, load, save, sha
from infer_async_protocol import validate_async_protocol
from audit_application_call_revision import class_hashes
from run_async_dependency_orders import evaluate
from plan_async_dependencies import attach_async_dependencies
from infer_application_execution import infer_application
from execution_dependency_state import Value
from plan_response_binding import plan_response
from run_execution_kernel_pilot import independent
import run_response_binding_revision as old
import run_ticketinfo_wrapper_revision as ticketinfo_driver


def audit(root, out):
    out.mkdir(parents=True, exist_ok=False)
    freeze=load(root/'algorithm-freeze.json'); raw={}; orders={}; protocols={}; mutations={}
    assert all(sha(Path(p))==s for p,s in freeze['sources'].items())
    assert all(sha(Path(p))==s for p,s in freeze['drivers'].items())
    assert sha(HERE/'async-dependency-protocol-20261021.json')==freeze['protocol_sha256']
    assert sha(HERE/'execution-kernel-protocol-20261020.json')==freeze['reserved_protocol_sha256']
    assert len(load(HERE/'execution-kernel-protocol-20261020.json')['unexamined_candidates'])==29
    base=root/'final-validation-build'; agent=class_hashes(base/'distributed-observer.jar')
    assert sha(HERE/'build_distributed_plans.py')==load(base/'build.json')['builder_sha256']
    assert all(sha(base/r/'original.jar')==s for r,s in freeze['original_jars'].items())
    def record(path): raw[str(path.relative_to(ROOT))]=sha(path)
    reuse={}
    def verify_capture(build,role):
        p=load(build/role/'plan.json')
        fresh=plan_response(load(build/role/'model.json'),p['entry'],p['target'],p['response_binding']['path'],execution_kernel=True,application_calls=True)
        if p.get('source_evidence'):fresh['source_evidence']=True
        if p.get('async_dependencies'):fresh=attach_async_dependencies(fresh)
        elif p.get('async_protocol'):fresh['async_protocol']=load(HERE/'async-task-contracts-20261021.json')
        assert fresh==p and class_hashes(build/'distributed-observer.jar')==agent
        assert sha(build/role/'original.jar')==freeze['original_jars'][role]
        reuse[str(build.relative_to(ROOT))]={'plan_equal':True,'all_agent_class_hashes_equal':True,
            'actual_capture_build_sha256':sha(build/'build.json'),'capture_algorithm':freeze.get('capture_commit'),
            'final_offline_algorithm':freeze['commit'],'scope':'Original capture retained; offline-only guard revision, not another deployment.'}

    semantics=load(root/'semantics-final-safe/results.json')
    expected={0:[1],1:[1],2:[],3:[2],4:None,5:None,6:None,7:None,8:[],9:None,10:[1],11:[],12:[1],13:[2],14:None}
    for mode in ('full','selective'):
        build=root/'semantics-final-safe/build';cap=root/'semantics-final-safe'/mode
        graph=old.Reconstruction(build,cap,['fixture']);rows=graph.rows['fixture']
        checks=semantics['modes'][mode]['checks'];assert len(checks)==30
        for check in checks:
            case=check['case'];want=expected[case['mode']]
            answer=graph.query(case['message'],'/text','fixture',boundary=old.BOUNDARY)
            assert answer['known']==(want is not None)
            if want is not None:
                ret=next(r for r in rows if r['kind']=='binding-return' and r.get('message')==case['message'])
                assert len(answer['sources'])==len(want)
                assert {s['field'] for s in answer['sources']}=={'@argument:'+str(i) for i in want}
                assert all(s['kind']=='argument' and s['root_frame']==ret['frame'] for s in answer['sources'])
            if case['mode']==12:assert case['response']['text']=='pre:SAME'
        assert semantics['modes'][mode]['known_exact']==18 and semantics['modes'][mode]['expected_unknown']==12
        assert len(semantics['modes'][mode]['faults'])==6 and all(semantics['modes'][mode]['faults'].values())
        assert semantics['modes'][mode]['budget_status']=='analysis_limited'
        assert class_hashes(build/'distributed-observer.jar')==agent
        record(cap/'fixture/events.jsonl')
    first=root/'shared-array-first';graph=old.Reconstruction(first/'build',first/'full',['fixture'])
    cases=json.loads((first/'full/stdout.log').read_text().splitlines()[-1]);shared=[c for c in cases if c['mode']==14]
    assert len(shared)==2 and all(not graph.query(c['message'],'/text','fixture',boundary=old.BOUNDARY)['known'] for c in shared)
    save(out/'shared-array-regression.json',{'retained_first_failure':True,'final_expected_unknown':2,'note':'Original answer source happened to match, but private-result acceptance conditions were not satisfied.'})
    fixtures=None; snapshots=[];worker_diagnostics=[];transfer_counts={}
    for d in sorted((root/'business-frozen-first').glob('*-sockshop-*')):
        config=load(d/'configuration.json'); query=config['query']; mode=config['mode']
        p=load(d/'build/orders/plan.json'); path=d/'capture/orders/events.jsonl'
        fresh=plan_response(load(d/'build/orders/model.json'),query['entry'],query['target'],query['path'],
                            execution_kernel=True,application_calls=True)
        fresh['source_evidence']=True;fresh=attach_async_dependencies(fresh)
        assert fresh==p
        rows=[json.loads(s) for s in path.read_text().splitlines()];record(path)
        assert not any(r['kind']=='problem' for r in rows)
        verify_capture(d/'build',query['role'])
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
        replay=old.Reconstruction(d/'build',d/'capture',['orders']).local_queries['orders']
        transfer_counts[d.name]=collections.Counter(t['worker_status'] for r in replay['roots'] for t in r.get('async_transfers',[]))
        assert sum(transfer_counts[d.name].values())==66
        # Diagnostic worker replay uses the same unknown reference arguments as
        # the main engine, never a source boundary at helper parameters.
        for task in current['tasks']:
            if not task['gets']:continue
            begin=next(r for r in rows if r['kind']=='enter' and r['frame']==task['worker_frame'])
            assert all('value' not in a for a in begin['args'])
            value=infer_application(p,rows,{'frame':begin['frame'],'args':[Value(a,unknown=True) for a in begin['args']],
                'borrowed':[True]*len(begin['args']),'receiver':Value({'object':begin['receiver']},unknown=True),'budget':{'steps':0}})['worker_export']
            worker_diagnostics.append({'configuration':d.name,'task_id':task['task_id'],'method':begin['method'],'status':value['status'],
                'frames':value.get('frames',[]),'executed_opaque_calls':value.get('opaque_calls',[]),'scope':'Diagnostic replay, not another deployment or minimal causal slice.'})
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
        verify_capture(d/'build',role)
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
        verify_capture(d/'build','carts')
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
        verify_capture(d/'build','ticketinfo')
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
             'semantics_targets_per_mode':30,'semantics_known_exact_per_mode':18,'semantics_expected_unknown_per_mode':12,'semantics_faults_per_mode':6,
             'business_faults_per_configuration':8,'loop_exact_per_mode':60,'cart_pair_exact_per_mode':2,
             'ticketinfo_exact_per_mode':21,
             'legacy_offline_correct':213,'legacy_offline_unknown':88,'heldout_unexamined':29,
             'worker_dependency_transfer':True,'no_performance':True,'full_62_acceptance_complete':False}
    save(out/'capture-reuse.json',reuse)
    save(out/'raw-sha256.json',raw);save(out/'task-receipts.json',protocols)
    save(out/'orders-instances.json',snapshots);save(out/'business-mutations.json',mutations)
    save(out/'worker-diagnostics.json',worker_diagnostics);save(out/'transfer-counts.json',transfer_counts)
    save(out/'audit.json',summary);save(HERE/'async-dependency-results-20261021.json',summary)
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();audit(a.root.resolve(),a.out.resolve())
