"""Audit all sealed denominators, including failures. No new execution/timing."""
import argparse,csv,json
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save,sha

H=ROOT/'artifacts/public-control-semantics-20261112'


def run(out):
    out.mkdir(parents=True,exist_ok=False)
    original=load(H/'protocol-before-implementation.json');candidate=load(H/'candidate-4d29ba6.json')
    assert all(sha(Path(p))==v for p,v in candidate['core_sources'].items())
    assert all(sha(H/p)==v for p,v in original['baseline_files'].items())
    assert all(sha(Path(p))==v for p,v in original['core_sources'].items()if p.endswith(('.java','.json')))
    assert sha(Path(original['Agent']))==original['Agent_sha256']
    assert not load(H/'baseline/selection-controls-02/results.json')['correctness_gate_passed']
    summaries=[];targets=[];guards=[];rewrites=[]
    cohorts=('original','direct','composition','exception','implicit','interface')
    for cohort in cohorts:
        home=H/('frozen-'+cohort);r=load(home/'results.json')
        assert r.get('normalized_equal',False)
        if cohort in('original','direct'):
            assert r['correctness_gate_passed']
            for mode,m in r['modes'].items():
                assert m['correct_nonempty_selector_targets']==m['data_correct']==m['version_correct']==2
                summaries.append({'cohort':cohort,'mode':mode,'targets':4,'complete_correct':2,'unknown':2,'raw_positive_gate':True})
                for g in m['guards']:
                    assert g['state']!='incorrect_known_answer';guards.append({'cohort':cohort,'mode':mode,**g})
                for check in m['checks']:
                    for a in check['answers']:
                        targets.append({'cohort':cohort,'mode':mode,'scenario':check['case'],'input':'','known':a['known'],'path':a['path'],'owner':a['owner'],'field':a['field'],'version':a['version'],'origins':a['origins'],'selectors':a['selectors'],'literal_expectation':check['expected']})
        else:
            expected_correct=60 if cohort=='composition'else 3 if cohort=='interface'else 12
            for mode,m in r['modes'].items():
                checks=load(home/mode/'checks.json');assert m['correct']==expected_correct
                if cohort=='composition':
                    assert not r['gate'] and {(x['scenario'],x['input'])for x in m['failed']}=={(s,n)for s in(14,16)for n in range(3)}
                    assert all(not c['answer']['known']for c in checks if c['scenario']in(14,16))
                else:assert r['gate']
                summaries.append({'cohort':cohort,'mode':mode,'targets':m['targets'],'complete_correct':m['correct'],'unknown':sum(not c['answer']['known']for c in checks),'raw_positive_gate':m['gate']})
                truth=load(home/mode/'truth-before-prediction.json')
                for c,t in zip(checks,truth):
                    a=c['answer'];targets.append({'cohort':cohort,'mode':mode,'scenario':c['scenario'],'input':c['input'],'known':a['known'],'path':a['path'],'owner':a['owner'],'field':a['field'],'version':a['version'],'origins':a['origins'],'selectors':a['selectors'],'literal_expectation':{'origins':t['origins'],'selectors':t['selectors'],'target_version':t['expected_target_version']}})
                for g in m['guards']:
                    assert g['state']!='incorrect-known';guards.append({'cohort':cohort,'mode':mode,**g})
                normalized=load(home/mode/'normalized.json')
                groups=((0,1),(2,10,11),(3,4),(7,8,19))if cohort=='composition'else((0,1),)if cohort=='exception'else((0,2),)if cohort=='implicit'else()
                for group in groups:
                    for n in range(3):
                        rows=[next(x for x in normalized if x['scenario']==s and x['input']==n)for s in group]
                        signature=[{k:v for k,v in x.items()if k not in('scenario','input')}for x in rows]
                        assert all(v==signature[0]for v in signature)
                        rewrites.append({'cohort':cohort,'mode':mode,'scenarios':list(group),'input':n,'normalized_equal':True})
        plan=home/'plan.json'
        for mode in ('full','static','selective'):
            path=home/mode/'events.jsonl';rows=[json.loads(l)for l in path.read_text().splitlines()]
            assert rows[0]['plan_sha256']==sha(plan)
            assert sum(x['kind']=='metrics'for x in rows)==1 and not any(x['kind']=='problem'or x['kind']=='metrics'and x.get('capture_invalid')for x in rows)
            from infer_execution_kernel import infer_execution
            replay=infer_execution(load(plan),rows)
            if cohort in('original','direct'):
                stored=[a for c in r['modes'][mode]['checks']for a in c['answers']]
            else:stored=load(home/mode/'prediction.json')['answers']
            assert replay['answers']==stored
            save(out/(cohort+'-'+mode+'-replay.json'),replay)
    old=load(H/'old-capture-comparison-final-core/results.json')
    assert len(old['captures'])==14
    assert all(x['new_status']==x['old_status']=='completed'and x['versions_equal']and x['explicit_data_changes']==0 for x in old['captures'])
    for x in old['captures']:
        if x['task'].startswith('ruoyi-2'):assert x['old_known']==x['new_known']==39 and x['selector_changes']==43
    save(out/'summary.json',{'source_commit':candidate['source_commit'],'Agent_sha256':original['Agent_sha256'],'Agent_and_30_contracts_unchanged':True,
        'cohorts':summaries,'raw_66_case_gate_passed':False,'revision_full_acceptance_passed':False,
        'remaining_unanswered_literal_positives_per_mode':6,'remaining_cases':'14/16 x inputs0/1/2: unclosed constructor effects, including untaken alternatives',
        'formal_performance':None,'business_deployments':0,'old_complete_captures':14,'new_JVM_controls':18,
        'guard_checks':len(guards),'all_guards_prevent_wrong_known':True,'rewrite_checks':len(rewrites),
        'no_old_business_selector_oracle_invented':True})
    save(out/'guards.json',guards);save(out/'rewrites.json',rewrites);save(out/'targets.json',targets);save(out/'old-captures.json',old)
    for name,rows in [('controls',targets),('guards',guards),('old-captures',old['captures']),('cohorts',summaries)]:
        fields=list(dict.fromkeys(k for r in rows for k in r))
        with(out/(name+'.csv')).open('w')as f:
            w=csv.DictWriter(f,fieldnames=fields,lineterminator='\n');w.writeheader()
            for r in rows:w.writerow({k:json.dumps(v,ensure_ascii=False,separators=(',',':'))if isinstance(v,(list,dict))else v for k,v in r.items()})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.out.resolve())
