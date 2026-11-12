"""Report strict failures as failures. Completion of this audit is not acceptance."""
import argparse,csv,json,subprocess,sys
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save,sha
from run_public_control_semantics import checked
from run_constructor_scope_controls import score
from check_constructor_scope_guards import run as guards

H=ROOT/'artifacts/constructor-effect-closure-20261112'


def csvwrite(p,rows):
    with p.open('w',newline='')as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)


def audit(out):
    out.mkdir(parents=True,exist_ok=False);initial=load(H/'protocol-before-change.json')
    assert all(sha(Path(p))==s for p,s in initial['core_sources'].items())
    assert all(sha(Path(p))==s for p,s in initial['original_66_inputs'].items())
    from run_generic_observation_rules import AGENT
    assert sha(AGENT)==initial['Agent_sha256']
    oldsource=ROOT/'artifacts/public-control-semantics-20261112/frozen-composition/candidate.json'
    assert sha(HERE/'PublicControlFixture.java')==load(oldsource)['fixture_sha256']
    cmd=[sys.executable,'-m','unittest','test_control_dependencies','test_call_write_effects','test_constructor_effect_scope_audit','-v']
    r=subprocess.run(cmd,cwd=HERE,capture_output=True,text=True);(out/'unit.log').write_text(r.stdout+r.stderr);assert r.returncode==0
    cases=load(H/'diagnosis-final-01/cases.json');diagnosis=[]
    for c in cases:
        diagnosis.append({'mode':c['mode'],'scenario':c['scenario'],'input':c['input'],'constructor_executed':c['constructor_executed'],'first_seq':c['first_uncertainty']['seq'],'first_PC':c['first_uncertainty']['pc'],'first_rule':c['first_uncertainty']['kind'],'actual_opaque_seq':';'.join(str(x['seq'])for x in c['transitions']if x['kind']=='actual-opaque-effect'),'data_set_matches':c['data_occurrences_match'],'selector_set_matches':c['selector_occurrences_match'],'known':c['complete_known'],'actually_affected_source_fields':json.dumps([{k:f[k]for k in ('owner','field','version')}for f in c['affected_source_fields']]),'potential_source_fields':json.dumps([{k:f[k]for k in ('owner','field','version')}for f in c['potential_source_fields']])})
    csvwrite(out/'diagnosis.csv',diagnosis)
    original=[];normal={}
    home=H/'new-original66-01';plan=load(home/'plan.json')
    for mode in ['full','static','selective']:
        rows=[json.loads(l)for l in(home/mode/'events.jsonl').read_text().splitlines()];result=checked(plan,rows);saved=load(home/mode/'prediction.json');assert result==saved
        checks=load(home/mode/'checks.json');truth=load(home/mode/'truth-before-prediction.json');norm=load(home/mode/'normalized.json');normal[mode]=norm
        for t,c in zip(truth,checks):
            a=c['answer'];original.append({'mode':mode,'scenario':t['scenario'],'input':t['input'],'correct':all(c['ok'].values()),'known':a['known'],'version':a['version'],'origins':json.dumps(a['origins']),'selectors':json.dumps(a['selectors']),'expected_origins':json.dumps(t['origins']),'expected_selectors':json.dumps(t['selectors'])})
        assert sum(all(c['ok'].values())for c in checks)==60
        assert {(c['scenario'],c['input'])for c in checks if not all(c['ok'].values())}=={(s,i)for s in [14,16]for i in [0,1,2]}
    assert normal['full']==normal['static']==normal['selective']
    csvwrite(out/'original66.csv',original)
    supplement=[];write_versions=[]
    home=H/'supplement-by-case-01'
    for scenario in range(10):
        d=home/('case-'+str(scenario));plan=load(d/'plan.json');normalized={}
        for mode in ['full','static','selective']:
            truth=load(d/mode/'truth-before-prediction.json');rows=[json.loads(l)for l in(d/mode/'events.jsonl').read_text().splitlines()]
            if scenario in (2,7,8,9):
                for t in truth:
                    old=next(r for r in t['raw']if r['role']=='10')
                    ret=next(r for r in rows if r['kind']=='binding-return'and r['message']==t['message'])
                    writes=[r for r in rows if r['kind']=='write'and r['owner']==old['owner']and r['field']==old['field']and old['token'][1]<r['seq']<ret['seq']]
                    expected=[]if scenario==7 and t['input']==0 else[2]
                    assert [r['version']for r in writes]==expected and old['version']==1
                    assert all(r['observed']['value']==7 for r in writes)
                    write_versions.append({'mode':mode,'scenario':scenario,'input':t['input'],'owner':old['owner'],'field':old['field'],'source_version':old['version'],'new_write_versions':json.dumps(expected),'same_value_preserved':True})
            try:prediction,checks,normalized[mode]=score(plan,rows,truth)
            except (ValueError,KeyError,AssertionError)as e:
                assert scenario==5 and str(e)=='Planned application frame evidence absent'
                for t in truth:supplement.append({'mode':mode,'scenario':scenario,'input':t['input'],'state':'rejected','matches_original_expectation':False,'known':False,'origins':'N/A','selectors':'N/A','expected_origins':json.dumps(t['origins']),'expected_selectors':json.dumps(t['selectors']),'reason':str(e)})
                continue
            for t,c in zip(truth,checks):
                a=c['answer'];ok=c['complete_correct'];state='correct'if a['known']and ok else'unknown'if not a['known']else'incorrect_selection'
                supplement.append({'mode':mode,'scenario':scenario,'input':t['input'],'state':state,'matches_original_expectation':ok,'known':a['known'],'origins':json.dumps(a['origins']),'selectors':json.dumps(a['selectors']),'expected_origins':json.dumps(t['origins']),'expected_selectors':json.dumps(t['selectors']),'reason':'one extra b.value selector at exceptional completion'if not ok else''})
        if normalized:assert normalized['full']==normalized['static']==normalized['selective']
    csvwrite(out/'supplement.csv',supplement)
    csvwrite(out/'write-versions.csv',write_versions)
    guards(home/'case-1',out/'guards');faults=load(out/'guards/results.json');assert faults['gate']
    csvwrite(out/'guards.csv',faults['checks'])
    preserved=load(H/'prior-call-write-audit-01/summary.json');assert preserved['unit_tests']==44 and preserved['new_JVM_complete_correct_per_mode']==22 and not preserved['revision_full_acceptance_passed']
    counts={m:{s:sum(c['mode']==m and c['state']==s for c in supplement)for s in ['correct','unknown','rejected','incorrect_selection']}for m in ['full','static','selective']}
    save(out/'results.json',{'starting_main':initial['starting_main'],'reference_offline_core':initial['reference_offline_core'],'core_changed':False,'Agent_changed':False,'framework_contracts_changed':False,'production_constructor_rule_enabled':False,'native_contract_enabled':False,'summary_review_is_runtime_license':False,'original_66_per_mode':{'correct':60,'unknown':6,'wrong_known':0},'supplement_split_counts':counts,'original_whole_supplement_batch':'three modes rejected; retained, not replaced by split counts','new_guards':len(faults['checks']),'unit_tests':54,'prior_old_control_captures_replayed':18,'prior_old_business_and_selection_captures_replayed':14,'prior_Galette_files_preserved':18,'original_full_acceptance_passed':False,'supplement_full_acceptance_passed':False,'all_implementation_work_complete':False,'stop_reason':'JDK/native effect and internal write-version/dispatch/class-initialization evidence not closed; no production authorization issued','additional_failures':['unsupported override frame expectation mismatch','one extra selector on exceptional constructor completion'],'performance':None})
    print(json.dumps({'core_changed':False,'original66':{'correct':60,'unknown':6},'supplement_split_counts':counts,'acceptance_passed':False},ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();audit(a.out.resolve())
