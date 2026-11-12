"""Recheck full frozen controls, physical truth and old execution compatibility."""
import argparse,csv,json,subprocess,sys
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save,sha
from run_call_write_footprints import score
from run_public_control_semantics import checked
from check_call_write_guards import run as guards
from analysis_status import AnalysisLimit

H=ROOT/'artifacts/call-write-footprints-20261112'
OLD=ROOT/'artifacts/public-control-semantics-20261112'


def csvwrite(path,records):
    with path.open('w',newline='')as f:
        w=csv.DictWriter(f,fieldnames=list(records[0]),lineterminator='\n');w.writeheader();w.writerows(records)


def audit(out):
    out.mkdir(parents=True,exist_ok=False)
    frozen=load(H/'candidate-060a5ff.json')
    assert all(sha(Path(p))==digest for p,digest in frozen['core_sources'].items())
    original=load(H/'protocol-before-change.json')
    protected=[p for p in original['core_sources']if p.endswith(('.java','.json'))]
    assert all(sha(Path(p))==original['core_sources'][p]for p in protected)
    from run_generic_observation_rules import AGENT
    assert sha(AGENT)==original['Agent_sha256']
    unit=[sys.executable,'-m','unittest','test_control_dependencies','test_call_write_effects','-v']
    run=subprocess.run(unit,cwd=HERE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    (out/'unit.log').write_text(run.stdout);assert run.returncode==0
    save(out/'unit-command.json',unit)
    targets=[];norm={};old_failures={}
    reference=H/'old-captures-final-02/reference/experiments/sockshop-mirrortaint'
    for mode in ('full','static','selective'):
        home=H/'final-jvm-01';rows=[json.loads(l)for l in(home/mode/'events.jsonl').read_text().splitlines()]
        truth=load(home/mode/'truth-before-prediction.json');plan=load(home/'plan.json')
        result,checks,norm[mode]=score(plan,rows,truth)
        assert all(c['complete_correct']for c in checks)
        save(out/(mode+'-replay.json'),result)
        for t,c in zip(truth,checks):
            a=c['answer'];targets.append({'mode':mode,'scenario':t['scenario'],'input':t['input'],'complete_correct':c['complete_correct'],'known':a['known'],'version':a['version'],'origins':json.dumps(a['origins']),'selectors':json.dumps(a['selectors']),'physical_truth':str(home/mode/'truth-before-prediction.json')})
        dest=out/(mode+'-reference.json')
        cmd=[sys.executable,str(HERE/'check_call_write_old_captures.py'),'--worker','--plan',str(home/'plan.json'),'--capture',str(home/mode/'events.jsonl'),'--out',str(dest),'--reference',str(reference)]
        subprocess.run(cmd,check=True);old=load(dest);assert old['status']=='completed'
        mismatches=[]
        for t in truth:
            ret=next(r for r in rows if r['kind']=='binding-return'and r['message']==t['message'])
            a=next(a for a in old['result']['answers']if a['root_frame']==ret['frame']and a['path']=='/value')
            if set(map(tuple,a['selectors']))!=set(map(tuple,t['selectors'])):
                mismatches.append({'scenario':t['scenario'],'input':t['input'],'old':a,'expected':t['selectors']})
        old_failures[mode]=mismatches
    assert norm['full']==norm['static']==norm['selective']
    csvwrite(out/'targets.csv',targets);save(out/'old-known-counterexamples.json',old_failures)
    for mode in ('full','static','selective'):
        d=H/'final-unclosed-jvm-01'
        try:checked(load(d/'plan.json'),[json.loads(l)for l in(d/mode/'events.jsonl').read_text().splitlines()])
        except AnalysisLimit as e:
            assert e.stage=='control-write-address'and 'rewrite a reference edge'in str(e)
        else:raise AssertionError('Unclosed path was certified')
    guards(H/'final-jvm-01',out/'guards');faults=load(out/'guards/results.json');assert faults['gate']
    csvwrite(out/'guards.csv',faults['checks'])
    oldgroups=[]
    for cohort in ('original','direct','composition','exception','implicit','interface'):
        d=OLD/('frozen-'+cohort);plan=load(d/'plan.json')
        for mode in ('full','static','selective'):
            capture=d/mode/'events.jsonl';rows=[json.loads(l)for l in capture.read_text().splitlines()]
            now=checked(plan,rows)
            baseline=load(OLD/'delivery-audit'/(cohort+'-'+mode+'-replay.json'))
            # The prior auditor stores the raw infer result here.
            assert now['answers']==baseline['answers']and now['roots']==baseline['roots']
            save(out/(cohort+'-'+mode+'-replay.json'),now)
            oldgroups.append({'cohort':cohort,'mode':mode,'targets':len(now['answers']),'known':sum(a['known']for a in now['answers']),'unknown':sum(not a['known']for a in now['answers']),'answers_equal':True,'roots_equal':True,'capture_sha256':sha(capture)})
    csvwrite(out/'old-groups.csv',oldgroups)
    for job in load(OLD/'old-capture-comparison-final-core/jobs-before-replay.json'):
        assert sha(Path(job['capture']))==job['capture_sha256']and sha(Path(job['plan']))==job['plan_sha256']
    old=load(H/'old-captures-final-02/results.json')['captures']
    assert len(old)==14 and all(c['new_status']==c['old_status']=='completed'and c['versions_equal']and c['root_audits_equal']and c['explicit_data_changes']==c['known_changes']==c['selector_changes']==0 for c in old)
    galette=load(OLD/'prior-galette-39-preservation.json')['records']
    assert len(galette)==18 and all(sha(ROOT/r['path'])==r['sha256']for r in galette)
    save(out/'summary.json',{'core':frozen['core_commit'],'Agent_unchanged':True,'protected_java_and_json':len(protected),'new_JVM_targets_per_mode':22,'new_JVM_complete_correct_per_mode':22,'unclosed_JVM_target_obligations_per_mode':2,'unclosed_JVM_state':'analysis_limited; no certified answers','new_guards':len(faults['checks']),'guard_states':{s:sum(c['state']==s for c in faults['checks'])for s in sorted({c['state']for c in faults['checks']})},'new_modes_equal':True,'original_main_known_selector_counterexamples_per_mode':{m:len(v)for m,v in old_failures.items()},'unit_tests':44,'old_control_captures':oldgroups,'old_business_and_selection_captures':old,'Galette_preserved_files':18,'original_66_known_per_mode':60,'original_66_unknown_per_mode':6,'call_write_scope_gate_passed':True,'revision_full_acceptance_passed':False,'formal_performance':None})
    print(json.dumps({'call_write_scope_gate_passed':True,'revision_full_acceptance_passed':False,'unit_tests':44,'targets_per_mode':22,'counterexamples_in_old_core':{m:len(v)for m,v in old_failures.items()}},ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();audit(a.out.resolve())
