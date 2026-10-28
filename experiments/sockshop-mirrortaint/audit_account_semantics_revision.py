#!/usr/bin/env python3
"""Audit fresh frozen Account and historical regressions without editing captures."""
import argparse, copy, json
from collections import Counter
from pathlib import Path
from run_planned_service import ROOT, HERE, load, save, sha
from audit_application_call_revision import class_hashes
from audit_transport_observation_revision import key, signatures
from infer_distributed_fields import Reconstruction
import run_frozen_capability_acceptance as driver
from run_response_binding_revision import BOUNDARY


def immutable(root):
    freeze = load(root/'algorithm-freeze.json')
    for p, h in freeze['sources'].items():
        assert sha(Path(p)) == h, p
    for role, h in freeze['original_jars'].items():
        assert sha(root/'frozen-base'/role/'original.jar') == h, role
    protected = load(ROOT/'artifacts/monitor-reliability-account-20261028/protected-first-evidence.json')
    # Accept only the original explicit manifest, never inferred graph output.
    files = protected['files']
    for p, h in files.items():
        assert sha(ROOT/'artifacts/portability-first-20261028'/p) == h, p
    return {'core_files':len(freeze['sources']), 'original_jars':len(freeze['original_jars']),
            'protected_first_files':len(files), 'all_unchanged':True}


def guards(root, out):
    out.mkdir(parents=True, exist_ok=False)
    cases = []
    for mode in ('full', 'selective'):
        for index, label in [(11,'name'),(10,'date'),(13,'number'),(15,'enum'),(18,'default-null')]:
            source = root/'account-final/diagnostics/collector-preservation'/mode/('query-%03d'%index)
            raw = [json.loads(v) for v in (source/'capture/events.jsonl').read_text().splitlines()]
            plan = root/'account-final/planning-first/piggymetrics-2'/('%03d-plan.json'%index)
            path = load(plan)['response_binding']['path']
            message = next(c['message'] for c in load(source/'results.json')['cases'] if c['http_status']==200)
            positive=root/'account-score-first'/mode/('query-%03d'%index)
            baseline=Reconstruction(positive/'build',positive/'capture',['piggy-account'])
            assert baseline.query(message,path,'piggy-account',boundary=BOUNDARY)['known'], 'Guard lacks a working positive control'
            variants = ['missing-feign-future','wrong-feign-command','missing-listener-registry',
                        'missing-save-effect','capture-invalid-footer','missing-root-input'] if label=='name' else []
            variants += {'date':['missing-document-date','wrong-date-serializer'],
                         'number':['wrong-number-serializer'], 'enum':['wrong-enum-projection'],
                         'default-null':['missing-default-proof']} .get(label, [])
            for fault in variants:
                rows = copy.deepcopy(raw)
                if fault=='missing-feign-future':
                    rows=[r for r in rows if r['kind']!='feign-future']
                elif fault=='wrong-feign-command':
                    next(r for r in rows if r['kind']=='feign-worker-enter')['command']={'object':'wrong-same-value-command'}
                elif fault=='missing-listener-registry':
                    next(r for r in rows if r['kind']=='mongo-save-effect').pop('listener_registry')
                elif fault=='missing-save-effect':
                    rows=[r for r in rows if r['kind']!='mongo-save-effect']
                elif fault=='capture-invalid-footer':
                    rows[-1]['capture_invalid']=True
                elif fault=='missing-root-input':
                    rows=[r for r in rows if r['kind']!='binding-input']
                elif fault=='missing-document-date':
                    rows=[r for r in rows if r['kind']!='document-date-exit']
                elif fault=='wrong-date-serializer':
                    witness=next(r for r in rows if r['kind']=='date-serialization')
                    # Modify the actual serializer witness, not the business value.
                    hashes=witness['class_sha256']; hashes[next(iter(hashes))]='0'*64
                elif fault=='wrong-number-serializer':
                    witness=next(r for r in rows if r['kind']=='scalar-serialization')
                    witness['class_sha256']['com/fasterxml/jackson/databind/ser/std/NumberSerializer']='0'*64
                elif fault=='wrong-enum-projection':
                    next(r for r in rows if r['kind']=='scalar-serialization')['enum_class_sha256']='0'*64
                elif fault=='missing-default-proof':
                    rows=[r for r in rows if r['kind']!='execution-defaults']
                work=out/(mode+'-'+label+'-'+fault)
                (work/'build/piggy-account').mkdir(parents=True)
                (work/'capture/piggy-account').mkdir(parents=True)
                (work/'build/piggy-account/plan.json').write_bytes(plan.read_bytes())
                destination=work/'capture/piggy-account/events.jsonl'
                destination.write_text(''.join(json.dumps(r)+'\n' for r in rows))
                try:
                    graph=Reconstruction(work/'build',work/'capture',['piggy-account'])
                    answer=graph.query(message,path,'piggy-account',boundary=BOUNDARY)
                    assert not answer['known'], ('Damaged evidence certified',mode,label,fault)
                    status='unknown'
                except (ValueError,KeyError,AssertionError) as e:
                    if isinstance(e,AssertionError) and e.args and isinstance(e.args[0],tuple) and e.args[0][0]=='Damaged evidence certified':raise
                    status='refused'; reason=str(e)
                cases.append({'mode':mode,'target':path,'fault':fault,'state':status,
                              'reason':reason if status=='refused' else None,'original_sha256':sha(source/'capture/events.jsonl'),
                              'derived_sha256':sha(destination)})
    save(out/'results.json',{'all_passed':True,'checks':cases,'derived_only':True,'original_files_unchanged':immutable(root)})
    print({'real_Account_guard_checks':len(cases),'all_passed':True},flush=True)


def final(root, out):
    from audit_frozen_capability_acceptance import audit
    from audit_execution_closure_revision import fields29
    out.mkdir(parents=True, exist_ok=False)
    driver.HOME=root
    current=audit(root,out/'source-union',partial=True)
    parent=ROOT/'artifacts/contract-routing-revision-20261023/final-v2'
    before={key(r):r for r in load(parent/'capability-audit/source-union/instances.json')}
    after={key(r):r for r in load(out/'source-union/instances.json')}
    assert set(before)==set(after) and len(after)==862
    changes=[{'key':k,'before':a['state'],'after':after[k]['state']} for k,a in before.items()
             if a['state']!=after[k]['state'] or signatures(a)!=signatures(after[k])]
    fields29(root,out/'fields29')
    writes=[]; write_changes=[]; agent=class_hashes(root/'frozen-base/distributed-observer.jar')
    for role in ('route','price'):
        home=root/('development-'+role+'-frozen')
        status=load(home/'results.json'); assert status['complete'] and not any('failure' in r for r in status['results'])
        for p in sorted(home.glob('*/evaluation.json')):
            ev=load(p); old=load(parent/('development-'+role+'-frozen')/p.parent.name/'evaluation.json')
            assert class_hashes(p.parent/'build/distributed-observer.jar')==agent
            a={(v['case'],v['path']):v for v in old['predictions']}
            b={(v['case'],v['path']):v for v in ev['predictions']}
            assert set(a)==set(b)
            for k,v in a.items():
                if v['state']!=b[k]['state'] or signatures(v)!=signatures(b[k]):write_changes.append([ev['query'],ev['mode'],k])
            writes.append({'mode':ev['mode'],'query':ev['query'],'targets':ev['targets'],'states':ev['states'],
                           'evaluation':str(p),'evaluation_sha256':sha(p)})
    assert len(writes)==30
    save(out/'write15.json',{'all_passed':not write_changes,'changes':write_changes,'records':writes,
                           'modes':{m:{'targets':sum(r['targets'] for r in writes if r['mode']==m),
                                       'states':dict(sum((Counter(r['states']) for r in writes if r['mode']==m),Counter()))} for m in ('full','selective')}})
    control_receipts=[]
    for folder in ('foundation-controls','scalar-controls','feign-controls','mongo2-controls','application-controls',
                   'date-controls','received-controls','legacy-collection-controls','binding-full-controls','binding-selective-controls'):
        jars=list((root/folder).rglob('distributed-observer.jar')); assert jars, folder
        for jar in jars:
            assert class_hashes(jar)==agent, str(jar)
            control_receipts.append({'file':str(jar),'sha256':sha(jar),'class_bytes_equal':True})
    reliability=load(root/'reliability-controls/checks.json')
    assert reliability['agent_sha256']==sha(root/'frozen-base/distributed-observer.jar')
    assert len(reliability['checks'])==2 and all(r['business_rows_equal']==27 and r['parent_scope_checks']==5
        and r['no_residual_state_after_each_root'] and r['original_exception_identity_and_finally_preserved']
        and r['damaged_capture_has_problem_sidecar_and_footer'] for r in reliability['checks'])
    framework=load(root/'reliability-controls/framework-checks.json')
    assert len(framework)==2 and all(r['business_rows_equal']==8 and r['RPC_parent_and_idempotent_completion']==4
        and r['invalid_capture_stays_invalid'] for r in framework)
    control_receipts.append({'file':str(root/'reliability-controls/checks.json'),
                             'sha256':sha(root/'reliability-controls/checks.json'),'original_frozen_Agent_used':True})
    foundations=load(root/'foundation-controls/results.json'); assert foundations['complete']
    for mode in ('full','selective'):
        binding=load(root/('binding-'+mode+'-controls/results.json'))
        assert binding['all_passed'] and sum(r['queries'] for r in binding['cases'].values())==54
        assert sum(r['known'] for r in binding['cases'].values())==48
    for mode in ('full','selective'):
        groups=[v[mode] for v in foundations['groups'].values()]
        assert sum(v['targets'] for v in groups)==66 and sum(v['known'] for v in groups)==51
        assert sum(v['unknown'] for v in groups)==15 and all(all(v['guards'].values()) for v in groups)
        feign=load(root/'feign-controls/results.json')[mode]
        assert feign=={'targets':10,'known':7,'unknown':3,'aborted':1}
        assert all(load(root/'feign-controls'/mode/'guards.json').values())
        mongo=load(root/'mongo2-controls/results.json')
        for field,known in [('text',10),('date',6)]:
            r=mongo[field][mode]; assert r['targets']==22 and r['known']==known and r['unknown']==22-known and all(r['guards'].values())
    scalars=load(root/'scalar-controls/results.json')
    for field, records in scalars.items():
        for name,r in records.items():
            if name.startswith(('full-','selective-')):
                assert r['known']==r['targets']==8 and all(r['guards'].values())
            else:assert r['business_completed'] and r['capture_invalid']
    recipient=load(root/'recipient-final-audit/checks.json')['checks']
    assert len(recipient)==4 and all(r['responses_and_saving_match_original']==6 and r['single_worker']
        and r['capture_still_invalid'] and r['subsequent_roots_parent_none']==5 for r in recipient)
    original_cases=[c for c in load(ROOT/'artifacts/portability-first-20261028/original/piggymetrics/attempt04-approved8/results.json')['cases']
                    if c['api']=='piggymetrics-2']
    assert len(original_cases)==6
    account_business=[]
    for mode in ('full','selective'):
        for index in range(10,20):
            home=root/'account-final/diagnostics/collector-preservation'/mode/('query-%03d'%index)
            cases=load(home/'results.json')['cases'];assert len(cases)==6
            for before,after in zip(original_cases,cases):
                assert before['case']==after['case'] and before['body']==after['body'] and before['http_status']==after['http_status']
                if after['http_status']==200:
                    a,b=copy.deepcopy(before['response']),copy.deepcopy(after['response'])
                    a.pop('lastSeen');b.pop('lastSeen');assert a==b
            account_business.append({'mode':mode,'query_index':index,'requests':6,'normal_200':4,'invalid_400':2,
                                     'source':str(home/'results.json'),'sha256':sha(home/'results.json')})
    save(out/'account-business-parity.json',{'checks':account_business,'all_passed':True,
        'clock_policy':'Compare lastSeen with this deployment own DB in independent Account oracle, not equality across JVM clocks.',
        'relevant_read_state_calibrated':True,'whole_initial_databases_byte_identical':False})
    account=load(root/'account-score-first/summary.json')
    assert account['complete40'] and all(v['known_correct']==40 and v['historic_MT_correct_preserved']==36 for v in account['modes'].values())
    assert load(root/'account-evidence-guards/results.json')['all_passed']
    result={'algorithm_commit':load(root/'algorithm-freeze.json')['commit'],'account':account['modes'],
            'historical62':current['modes'],'historical62_changes':changes,
            'fields29':load(out/'fields29/audit.json')['modes'],
            'write15':load(out/'write15.json')['modes'],'control_Agent_receipts':control_receipts,
            'immutable':immutable(root),'audit_source_sha256':sha(Path(__file__)),
            'no_performance':True,'fresh_business_deployments':True,
            'all_passed':current['all_passed'] and not changes and not write_changes}
    save(out/'summary.json',result);assert result['all_passed']
    print({'final_all_passed':True,'algorithm':result['algorithm_commit']},flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--stage',choices=('guards','final'),required=True);a=p.parse_args()
    {'guards':guards,'final':final}[a.stage](a.root.resolve(),a.out.resolve())
