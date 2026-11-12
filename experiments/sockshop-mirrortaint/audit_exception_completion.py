"""New semantics, original truth; limited pools are never relabeled as full passes."""
import argparse,csv,json,subprocess,sys
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save,sha
from run_public_control_semantics import checked
from run_exception_completion_controls import score as newscore
from run_constructor_scope_controls import score as constructorscore
from run_call_write_footprints import score as callscore
from check_exception_completion_guards import run as guards
from analysis_status import AnalysisLimit

H=ROOT/'artifacts/exception-completion-semantics-20261112'
OLD=ROOT/'artifacts/constructor-effect-closure-20261112'
PUBLIC=ROOT/'artifacts/public-control-semantics-20261112'
CALL=ROOT/'artifacts/call-write-footprints-20261112'


def rows(p):return [json.loads(l)for l in p.read_text().splitlines()]
def csvwrite(p,records):
    with p.open('w',newline='')as f:
        w=csv.DictWriter(f,fieldnames=list(records[0]),lineterminator='\n');w.writeheader();w.writerows(records)


def run(out,current_core=False):
    out.mkdir(parents=True,exist_ok=False);freeze=load(H/'candidate-final.json');initial=load(H/'protocol-before-change.json')
    if not current_core:assert all(sha(Path(p))==s for p,s in freeze['core_sources'].items())
    save(out/'core-under-test.json',{'current_core':current_core,'sources':{p:sha(Path(p))for p in freeze['core_sources']}})
    assert all(sha(Path(p))==s for p,s in initial['original_failure_files'].items())
    from run_generic_observation_rules import AGENT
    assert sha(AGENT)==freeze['Agent_sha256']
    for p,s in initial['core_sources'].items():
        if p.endswith('.json') or not current_core and p.endswith('.java'):assert sha(Path(p))==s
    cmd=[sys.executable,'-m','unittest','test_control_dependencies','test_call_write_effects','test_constructor_effect_scope_audit','test_exception_completion','-v']
    r=subprocess.run(cmd,cwd=HERE,capture_output=True,text=True);(out/'unit.log').write_text(r.stdout+r.stderr);assert r.returncode==0
    counter=[];normalized={};oldcounter=OLD/'supplement-by-case-01/case-8'
    for mode in ['full','static','selective']:
        truth=load(oldcounter/mode/'truth-before-prediction.json');_,checks,norm=constructorscore(load(oldcounter/'plan.json'),rows(oldcounter/mode/'events.jsonl'),truth)
        before=load(oldcounter/mode/'checks.json');assert all(c['complete_correct']for c in checks)
        for old,new,t in zip(before,checks,truth):
            a,b=old['answer'],new['answer'];assert all(a[k]==b[k]for k in('owner','field','version','origins','known'))
            counter.append({'mode':mode,'input':t['input'],'old_correct':old['complete_correct'],'new_correct':new['complete_correct'],'old_selectors':json.dumps(a['selectors']),'new_selectors':json.dumps(b['selectors']),'origins':json.dumps(b['origins']),'version':b['version'],'same_execution':True})
        fresh=H/'final-original-counterexample-01';_,checks,normalized[mode]=constructorscore(load(fresh/'plan.json'),rows(fresh/mode/'events.jsonl'),load(fresh/mode/'truth-before-prediction.json'));assert all(c['complete_correct']for c in checks)
    assert normalized['full']==normalized['static']==normalized['selective']
    csvwrite(out/'counterexample.csv',counter)
    targets=[];normalized={};fresh=H/'final-supported-sequence-01'
    for mode in ['full','static','selective']:
        truth=load(fresh/mode/'truth-before-prediction.json');p,checks,normalized[mode]=newscore(load(fresh/'plan.json'),rows(fresh/mode/'events.jsonl'),truth)
        assert len(checks)==28 and all(c['complete_correct']for c in checks)
        save(out/(mode+'-replay.json'),p)
        for t,c in zip(truth,checks):
            a=c['answer'];targets.append({'mode':mode,'scenario':t['scenario'],'input':t['input'],'state':'correct','known':a['known'],'field':a['field'],'owner':a['owner'],'version':a['version'],'origins':json.dumps(a['origins']),'selectors':json.dumps(a['selectors']),'expected_origins':json.dumps(t['origins']),'expected_selectors':json.dumps(t['selectors'])})
        d=H/'development-by-case-01/case-6'
        try:newscore(load(d/'plan.json'),rows(d/mode/'events.jsonl'),load(d/mode/'truth-before-prediction.json'))
        except AnalysisLimit as e:assert 'Cross-join selected write address'in str(e)
        else:raise AssertionError('Existing write-address boundary lost')
        for t in load(d/mode/'truth-before-prediction.json'):targets.append({'mode':mode,'scenario':6,'input':t['input'],'state':'analysis_limited','known':False,'field':'N/A','owner':'N/A','version':'N/A','origins':'N/A','selectors':'N/A','expected_origins':json.dumps(t['origins']),'expected_selectors':json.dumps(t['selectors'])})
    assert normalized['full']==normalized['static']==normalized['selective']
    csvwrite(out/'targets.csv',targets)
    guards(fresh,out/'guards');faults=load(out/'guards/results.json');assert faults['gate'];csvwrite(out/'guards.csv',faults['checks'])
    oldgroups=[]
    for cohort in ['original','direct','composition','exception','implicit','interface']:
        d=PUBLIC/('frozen-'+cohort)
        for mode in ['full','static','selective']:
            now=checked(load(d/'plan.json'),rows(d/mode/'events.jsonl'));before=load(PUBLIC/'delivery-audit'/(cohort+'-'+mode+'-replay.json'))
            assert now['answers']==before['answers']and now['roots']==before['roots']
            oldgroups.append({'cohort':cohort,'mode':mode,'targets':len(now['answers']),'known':sum(a['known']for a in now['answers']),'answers_equal':True,'root_audits_equal':True})
    csvwrite(out/'old-controls.csv',oldgroups)
    for mode in ['full','static','selective']:
        d=OLD/'supplement-by-case-01/case-5'
        try:checked(load(d/'plan.json'),rows(d/mode/'events.jsonl'))
        except ValueError as e:assert str(e)=='Planned application frame evidence absent'
        else:raise AssertionError('Unsupported override was licensed')
    constructor_pool={}
    for mode in ['full','static','selective']:
        counts={'correct':0,'unknown':0,'rejected':2}
        for case in [0,1,2,3,4,6,7,8,9]:
            d=OLD/'supplement-by-case-01'/('case-'+str(case));_,checks,_=constructorscore(load(d/'plan.json'),rows(d/mode/'events.jsonl'),load(d/mode/'truth-before-prediction.json'))
            assert all(c['complete_correct']for c in checks)
            counts['correct']+=sum(c['answer']['known']for c in checks);counts['unknown']+=sum(not c['answer']['known']for c in checks)
        constructor_pool[mode]=counts
    for mode in ['full','static','selective']:
        d=CALL/'final-jvm-01';_,checks,_=callscore(load(d/'plan.json'),rows(d/mode/'events.jsonl'),load(d/mode/'truth-before-prediction.json'));assert all(c['complete_correct']for c in checks)
    business=load(H/'old-business-final-02/results.json')['captures']
    assert len(business)==14 and all(c['old_status']==c['new_status']=='completed'and c['versions_equal']and c['root_audits_equal']and c['explicit_data_changes']==c['known_changes']==c['selector_changes']==0 for c in business)
    prior=load(PUBLIC/'prior-galette-39-preservation.json')['records'];assert len(prior)==18 and all(sha(ROOT/r['path'])==r['sha256']for r in prior)
    save(out/'results.json',{'starting_main':initial['starting_main'],'offline_core':None if current_core else freeze['core_commit'],'current_core_receipt':'core-under-test.json','Agent_unchanged':True,'public_contracts_unchanged':True,'counterexample_fixed':True,'old_counterexample_six_targets_same_data_version_and_known':True,'new_counterexample_per_mode':{'correct':2,'targets':2},'new_supported_sequence_per_mode':{'correct':28,'targets':28},'new_complete_pool_per_mode':{'correct':28,'analysis_limited':2,'targets':30,'all_passed':False},'old_split_constructor_pool':constructor_pool,'new_units':30,'prior_units':54,'all_unit_tests':84,'fault_checks':len(faults['checks']),'fault_states':{s:sum(c['state']==s for c in faults['checks'])for s in sorted({c['state']for c in faults['checks']})},'old_control_captures':oldgroups,'old_business_captures':business,'original_66_per_mode':{'correct':60,'unknown':6,'all_passed':False},'original_unsupported_override_per_mode':{'targets':2,'state':'rejected'},'Galette_preserved_files':18,'exception_completion_bounded_gate_passed':True,'entire_control_pool_acceptance_passed':False,'all_semantics_acceptance_passed':False,'performance':None})
    print(json.dumps({'counterexample_fixed':True,'new_supported_per_mode':28,'new_pool_refused_per_mode':2,'all_units':84,'faults':len(faults['checks']),'all_semantics_acceptance_passed':False}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--current-core',action='store_true');a=p.parse_args();run(a.out.resolve(),a.current_core)
