#!/usr/bin/env python3
"""Independent population/integrity audit; does not import any TF algorithm."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[2]


def read(p): return json.loads(p.read_text())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()


def audit(out, planning_override=None):
    freeze=read(out/'freeze.json');pool=read(out/'pool.json')
    planning=planning_override if planning_override is not None else read(out/'planning.json')
    assert sha(out/'frozen-code.tar')==freeze['source_archive_sha256']
    for name,digest in freeze['sources'].items(): assert sha(out/'code'/name)==digest,name
    for name,digest in freeze['dependencies'].items(): assert sha(ROOT/name)==digest,name
    for role,entry in freeze['jars'].items():
        assert sha(ROOT/entry['frozen'])==entry['sha256'],role
        assert sha(out/'planning/build'/role/'original.jar')==entry['sha256'],role
    assert planning['pool_sha256']==sha(out/'pool.json')
    registered=subprocess.check_output(['git','show','dfd929c:experiments/sockshop-mirrortaint/query-coverage-pool-20261019.json'],cwd=ROOT)
    assert hashlib.sha256(registered).hexdigest()==sha(out/'pool.json')
    assert len({q['id'] for q in pool['candidates']})==len(pool['candidates'])
    assert len({(q['role'],q['entry'],q['path']) for q in pool['candidates']})==len(pool['candidates'])
    exclusions={(q['role'],q['entry'],q['path']) for q in pool['excluded_known_targets']}
    assert not exclusions.intersection((q['role'],q['entry'],q['path']) for q in pool['candidates'])
    expected_selected=[]
    for app in ('sockshop','trainticket'):
        groups=defaultdict(list)
        for q in pool['candidates']:
            assert q['rank']==hashlib.sha256(('query-coverage-20261019\n'+q['id']).encode()).hexdigest()
            if q['application']==app:groups[q['role']].append(q)
        ordered={r:sorted(qs,key=lambda q:q['rank']) for r,qs in groups.items()}
        chosen=[];i=0
        while len(chosen)<min(10,sum(map(len,groups.values()))):
            for role in sorted(ordered):
                if i<len(ordered[role]) and len(chosen)<10:chosen.append(ordered[role][i]['id'])
            i+=1
        expected_selected+=chosen
    assert expected_selected==pool['selected_ids']
    assert [r['id'] for r in planning['results']]==expected_selected,'Missing/reordered/extra query result'
    targets=read(out/'target-declaration-audit.json')
    assert targets['all_passed'] and {q['query'] for q in targets['queries']}==set(expected_selected)
    declarations={q['query']:q for q in targets['queries']}
    attempts=Counter();reasons=defaultdict(Counter);apps={}
    for r in planning['results']:
        q=next(q for q in pool['candidates'] if q['id']==r['id']);assert r['query']==q
        saved=read(out/'planning'/r['id']/'result.json');assert saved==r
        j=out/'planning'/r['id']/'original-target-javap.txt'
        assert sha(j)==declarations[r['id']]['javap_sha256']
        assert declarations[r['id']]['declared_field_exists']
        assert all(a['status'] in ('accepted','rejected') for a in r['attempts']),'Experiment error is not a rejection'
        assert r['attempts'][0]['function']=='plan_service'
        assert any(a['function']=='plan_collection' for a in r['attempts'])
        if r['attempts'][0]['status']=='rejected':assert r['attempts'][1]['function']=='copy_plan'
        accepted=[a for a in r['attempts'] if a['status']=='accepted']
        assert (r['status']=='planning-accepted')==bool(accepted)
        assert (r['chosen_plan'] is not None)==bool(accepted)
        for a in r['attempts']:
            attempts[a['function']]+=1
            if a['status']=='rejected':
                reasons[a['function']][a['reason'].split(':')[0]]+=1
                trace=out/'planning'/r['id']/(a['configuration']+'-'+a['function']+'.traceback.txt')
                assert a['reason'] in trace.read_text()
        if accepted:assert (out/r['chosen_plan']).exists()
    controls=read(out/'historical-positive-controls.json')
    assert controls['all_passed'] and len(controls['controls'])==4 and all(r['accepted'] for r in controls['controls'])
    for app in ('sockshop','trainticket'):
        rows=[r for r in planning['results'] if r['application']==app]
        default=sum(any(a['status']=='accepted' and a['configuration']=='native-default' for a in r['attempts']) for r in rows)
        total=sum(r['status']=='planning-accepted' for r in rows)
        apps[app]={'candidate_queries':sum(q['application']==app for q in pool['candidates']),
                   'selected_queries':len(rows),'native_default_accepted':default,
                   'accepted_including_explicit_profile':total,'planning_rejected':len(rows)-total,
                   'planning_acceptance_rate':total/len(rows) if rows else None,
                   'runtime_requests':0,'generated_target_instances':0,'known':0,'unknown':0,
                   'no_target_NA':0,'invalid_evidence':0,'unexecuted_rejected_queries':len(rows)-total,
                   'answerability_rate':None,'known_answer_exact_rate':None,
                   'known_answer_relation_tp':0,'known_answer_relation_fp':0,'known_answer_relation_fn':0}
    # This first-pass audit intentionally refuses to invent runtime populations.
    assert all(x['accepted_including_explicit_profile']==0 for x in apps.values()),'Runtime results required for accepted queries'
    return {'all_passed':True,'algorithm_commit':freeze['algorithm_commit'],'pool_commit':'dfd929c',
            'pool_sha256':sha(out/'pool.json'),'apps':apps,'attempt_counts':dict(attempts),
            'rejection_counts_by_function':{k:dict(v) for k,v in reasons.items()},
            'historical_positive_controls':'4/4 accepted, not held-out coverage',
            'core_or_library_changes':0,'new_business_runs':0,
            'auditor_sha256':sha(Path(__file__)),
            'scope':'Audit of preselection, all selected planner outcomes, original field declarations and frozen files. No runtime source-instance accuracy evaluated because no query was accepted.'}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,default=ROOT/'artifacts/query-coverage-first-20261019');args=p.parse_args();out=args.out.resolve()
    result=audit(out)
    broken=read(out/'planning.json');broken['results'].pop()
    try:audit(out,broken)
    except AssertionError:result['negative_controls']={'dropped_query_rejected':True}
    else:raise AssertionError('Dropped query accepted')
    result['recorded_at_utc']=datetime.now(timezone.utc).isoformat()
    (out/'independent-audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    (out/'logs/03-independent-audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
