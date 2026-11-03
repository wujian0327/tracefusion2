"""Final integrity and provenance checks, without changing original results."""
import argparse,collections,csv,json,subprocess
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save,sha


def audit(home,final,out):
    out.mkdir(parents=True,exist_ok=False);old=ROOT/'artifacts/target-closure-revision-20261103';run=final.parent
    freeze=load(final/'historical/algorithm-freeze.json')
    for p,v in freeze['sources'].items():assert sha(Path(p))==v,p
    assert sha(HERE/'build_distributed_plans.py')==freeze['builder_sha256']
    previous=load(old/'delivery-integrity-04/summary.json')
    for name,v in previous['delivery_sources'].items():assert sha(HERE/name)==v,name
    before=load(old/'final-candidate-02/historical/algorithm-freeze.json')
    contracts=[Path(p)for p in before['sources']if p.endswith('.json')]
    for p in contracts:assert p.read_bytes()==subprocess.check_output(['git','show','1308589:'+str(p.relative_to(ROOT))]),p
    protected=0
    for line in(old/'external-before-read-permission.sha256').read_text().splitlines():
        v,name=line.split('  ',1);p=old/'external-first-01/runs'/Path(name).relative_to('/work');assert sha(p)==v,p;protected+=1
    guard=load(old/'final-guard-receipt-02/summary.json')
    for p,v in guard['control_results'].items():assert sha(old/p)==v,p
    retained=load(old/'final-compatibility-pass-02/audit-mall/captures-manifest.json')['files']
    for p,v in retained.items():assert sha(old/'final-candidate-02/mall'/p)==v,p
    timing=load(home/'offline-paired-02/summary.json');assert timing['complete']and timing['all_public_answers_and_raw_scores_equal']
    for row in timing['rows']:
        for p,v in row['capture_hashes'].items():assert sha(Path(p))==v,p
    lock=load(home/'offline-paired-02/source-lock-before-timing.json')
    reference=home/'reference-core/infer_application_execution.py'
    assert reference.read_bytes()==subprocess.check_output(['git','show','1308589:experiments/sockshop-mirrortaint/infer_application_execution.py'])
    assert sha(reference)==lock['reference_application_sha256']
    py_models={p:v for p,v in lock['sources'].items()if Path(p).suffix in('.py','.json')}
    for p,v in py_models.items():assert sha(Path(p))==v,p
    assert load(home/'selection-replay-01/summary.json')['passed']and load(home/'index-guards-01/results.json')['passed']
    from infer_distributed_fields import Reconstruction
    failed=home/'final-attempt-04/candidate/historical/account-final';rejected=[]
    for mode in('full','selective'):
        for i in range(10,20):
            events=failed/'diagnostics/collector-preservation'/mode/('query-%03d'%i)/'capture/events.jsonl'
            before_hash=sha(events);view=out/'retained-account-rejections'/mode/str(i)
            (view/'build/role').mkdir(parents=True);(view/'capture/role').mkdir(parents=True)
            (view/'build/role/plan.json').write_bytes((failed/'planning-first/piggymetrics-2'/('%03d-plan.json'%i)).read_bytes())
            (view/'capture/role/events.jsonl').symlink_to(events.resolve())
            try:Reconstruction(view/'build',view/'capture',['role'])
            except ValueError as e:assert str(e)=='Collector problem',str(e)
            else:raise AssertionError('Previously damaged Account capture was certified')
            assert sha(events)==before_hash
            rejected.append({'mode':mode,'query_index':i,'capture_sha256':before_hash,'still_rejected':True})
    save(out/'retained-account-rejections.json',rejected)
    from audit_application_call_revision import class_hashes
    agent=final/'historical/frozen-base/distributed-observer.jar';classes=class_hashes(agent)
    control_agents=[home/'map-controls-16/build/distributed-observer.jar',run/'closure-controls/build/distributed-observer.jar',run/'sql-early-state-controls/build/distributed-observer.jar',run/'locality-controls/build/distributed-observer.jar']
    for path in control_agents:assert class_hashes(path)==classes,path
    capability=load(run/'capability-pass-01/summary.json');assert capability['complete']and capability['passed']
    histories=load(run/'capability-pass-01/audit-historical/summary.json')
    mall=load(run/'capability-pass-01/audit-mall/summary.json');zlt=load(run/'capability-pass-01/audit-zlt/summary.json')
    groups={'Mall':{m:{k:v for k,v in d.items()if k in('targets','states','positive_correct','known_empty_correct','MT_correct_preserved','MT_positive_preserved')}for m,d in mall['modes'].items()},
        'Account':histories['Account40']['modes'],'ZLT':zlt['states'],
        'historical62':{m:{k:v for k,v in d.items()if k in('expected_targets','actual_targets','states','baseline_correct_preserved','old_tf_correct_preserved','tp','fp','fn_including_unknown')}for m,d in histories['historical62'].items()},
        'fields29':histories['fields29']['modes'],'writes15':histories['write15']}
    save(out/'inherited-audit-scope-clarification.json',{'reference_for_this_revision':'1308589',
        'ZLT_legacy_audit_reference':zlt['reference'],'ZLT_old_public_models_added_field':'Inherited comparator relative to c1a4e5c, not a claim of new ZLT framework models in this revision.',
        'this_revision':'23 original public contracts unchanged; one finite target-Map observation model added, not used to create ZLT sources.',
        'Mall_old_previous_correct_43_field':'Inherited older comparator; the separate all_98_states_and_logical_signatures_preserved gate is the present retention requirement.'})
    c1_folder='facts-ruoyi-C1-02'if(run/'facts-ruoyi-C1-02/summary.json').exists()else'facts-ruoyi-C1'
    c1=load(run/c1_folder/'summary.json');c2=load(run/'facts-ruoyi-C2/summary.json')
    for s,n in((c1,89),(c2,5)):
        for mode in('full','selective'):
            assert s['states'][mode]=={'evidence_invalid':n}and s['facts'][mode]['target_bound']==n
    native=run/'ruoyi-C2/runs/ruoyi-4/mirrortaint';receipt=load(native/'binary-receipt.json')
    for p,v in receipt['files'].items():assert sha(Path(p))==v,p
    fixed=load(old/'external-first-01/runs/ruoyi-1/mirrortaint/binary-receipt.json')
    matched={p:v for p,v in receipt['files'].items()if p in fixed['files']}
    assert len(matched)==4 and all(fixed['files'][p]==v for p,v in matched.items())
    save(out/'native-reuse-clarification.json',{'actual_native_and_adapter_files':matched,'bytes_equal_to_original_fixed_configuration':True,
        'old_receipt_boolean':'Old core_agent_contract_changes:true was an experiment-wrapper metadata flag, not a native-MT change. Original receipt preserved; new driver records the flag separately by mode.',
        'new_MT_deployment_in_final_TF_candidate':False})
    summary={'candidate':freeze['commit'],'agent_sha256':sha(agent),'core_sources':len(freeze['sources']),'builder_unchanged':True,
        'original_public_contracts_unchanged':len(contracts),'old_first_files_unchanged':protected,'old_Mall_files_unchanged':len(retained),
        'old_reports_and_delivery_sources_unchanged':len(previous['delivery_sources']),'old_strict_guard_result_files_unchanged':len(guard['control_results']),
        'timed_Python_and_model_files_unchanged':len(py_models),'complete_old_captures_unchanged':True,'full_internal_state_and_selection_replay_passed':True,
        'superseded_Account_damaged_captures_still_rejected':len(rejected),
        'required_guard_results_preserved':True,'final_business_capability_passed':True,'new_RuoYi_source_certifications':0,
        'capability_groups':groups,'historical_state_and_signature_changes':{'62':histories['historical62_changes'],'29':histories['fields29']['changes'],'writes15':histories['write15_changes'],'Mall98':not mall['all_98_states_and_logical_signatures_preserved']},
        'RuoYi_C1':c1,'RuoYi_C2':c2,'capture_provenance':'New final-TF-Agent business deployments; offline costs reuse original complete captures. Native C1 and compatible same-configuration C2 captures reused explicitly.',
        'no_online_cost_rewrite':True,'no_push':True}
    save(out/'summary.json',summary)
    save(HERE/'ruoyi-zlt-refinement-results-20261103.json',summary)
    rows=[]
    first=load(old/'external-first-audit-03/instances.json')
    previous_instances={(r['query'],r['mode'],r['case'],r['path']):r for r in first}
    calibrated_mt={(r['query'],r['case'],r['path']):r for r in load(run/'audit-ruoyi-C2/instances.json')if r['mode']=='mirrortaint'}
    for config,folder in(('C1',c1_folder),('C2','facts-ruoyi-C2')):
        for r in load(run/folder/'instances.json'):
            before=previous_instances[(r['query'],r['mode'],r['case'],r['path'])]
            mt=previous_instances[(r['query'],'mirrortaint',r['case'],r['path'])]
            fixed=calibrated_mt[(r['query'],r['case'],r['path'])]if config=='C2'else mt
            rows.append({'configuration':config,**r,'original_C1_TF_state':before['state'],'original_C1_target_bound':before['target_bound'],
                'original_C1_MT_state':mt['state'],'same_configuration_MT_state':fixed['state']})
    keys=['configuration','query','mode','case','path','original_C1_TF_state','original_C1_target_bound','original_C1_MT_state','same_configuration_MT_state','business_preserved_except_seed_clock','target_bound','capture_closed','capture_integrity_valid','declared_source_paired','raw_identity_rule_matches','oracle_adequate','state']
    with(HERE/'ruoyi-wrapper-paired-20261103.csv').open('w')as f:
        w=csv.DictWriter(f,keys,extrasaction='ignore',lineterminator='\n');w.writeheader();w.writerows(rows)
    print({'integrity_passed':True,'candidate':freeze['commit'],'protected_first_files':protected},flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);p.add_argument('--final',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();audit(a.home.resolve(),a.final.resolve(),a.out.resolve())
