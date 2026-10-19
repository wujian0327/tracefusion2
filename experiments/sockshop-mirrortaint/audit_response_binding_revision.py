#!/usr/bin/env python3
"""Audit denominators and independently grounded source-instance predictions."""
import argparse
import hashlib
import json
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save,sha


def stage(root):
    plans=load(root/'planning.json');runtime={}
    for q in plans:
        p=root/q['id']/'capture/evaluation.json'
        if p.exists():runtime[q['id']]=load(p)
    groups={}
    for app in ('sockshop','trainticket'):
        ps=[p for p in plans if p['application']==app];rs=[runtime[p['id']] for p in ps if p['id'] in runtime]
        d={'selected':len(ps),'accepted':sum(p['status']=='accepted' for p in ps),'rejected':sum(p['status']=='rejected' for p in ps),'runtime_queries':len(rs)}
        for key in ('requests','target_instances','known','unknown','N/A_requests','evidence_invalid','oracle_unavailable','known_oracle_checked','exact','tp','fp','fn'):d[key]=sum(r.get(key,0) for r in rs)
        assert d['target_instances']==d['known']+d['unknown']+d['evidence_invalid']
        d['answerability']=d['known']/d['target_instances'] if d['target_instances'] else None
        d['known_exact_rate']=d['exact']/d['known_oracle_checked'] if d['known_oracle_checked'] else None
        d['accepted_with_known_answer']=sum(r['known']>0 for r in rs)
        d['known_without_independent_oracle']=d['known']-d['known_oracle_checked']
        for r in rs:
            for q in r['predictions']:
                if q['status']=='known':
                    a=q['answer'];assert a['known'] and a['target']['observed'].get('value')==q['client_value']
                    assert all(s['kind'] in ('binding-source','http-json','argument','field-read') for s in a['sources'])
                    # Root-return/output witnesses may never turn into origins.
                    assert all(s['kind']!='http-json' or (s['phase'],s['direction'])==('read','response') for s in a['sources'])
                    if 'expected' in q:assert {tuple(x) for x in q['actual']}=={tuple(x) for x in q['expected']},q
        groups[app]=d
    return {'groups':groups,'queries':[{**p,**({k:v for k,v in runtime[p['id']].items() if k!='predictions'} if p['id'] in runtime else {})} for p in plans]}


def audit(root,development,heldout=None):
    checks={};first=load(ROOT/'artifacts/query-coverage-first-20261019/planning.json')
    # The first report is preserved rather than overwritten by development fixes.
    checks['original_first_pass_preserved']=len(first['results'])==20
    sealed=load(HERE/'response-binding-heldout-20261019.json');pool=load(ROOT/'artifacts/query-coverage-first-20261019/pool.json')
    dev=set(pool['selected_ids']);test={q['id'] for q in sealed['queries']}
    assert not dev&test and len(dev)==20 and len(test)==22
    dev_entries={q['entry'] for q in pool['candidates'] if q['id'] in dev}
    assert all(q['entry'] not in dev_entries for q in sealed['queries'] if q['application']=='trainticket')
    assert all(q['entry'] in dev_entries for q in sealed['queries'] if q['application']=='sockshop')
    checks['holdout_disjoint_ids_and_declared_entry_tiers']=True
    assert sha(HERE/'response-binding-heldout-20261019.json')==load(root/'logs/00-heldout-sealed.json')['sha256']
    checks['holdout_seal_unchanged']=True
    result={'development':stage(development),'checks':checks}
    assert {q['id'] for q in result['development']['queries']}==dev
    if heldout:
        freeze=load(root/'algorithm-freeze.json')
        for file,value in freeze['sources'].items():assert sha(ROOT/file)==value,file
        result['heldout']=stage(heldout)
        assert {q['id'] for q in result['heldout']['queries']}==test
        checks['frozen_algorithm_sources_unchanged_after_test']=True
    for name in ('semantics-final','collection-controls-final'):
        r=load(root/name/'results.json');assert r['all_passed'];checks[name]=True
    old=load(root/'legacy-offline-final/comparison.json')['results']
    assert old['sockshop']['queries']==old['sockshop']['exact']==198 and old['sockshop']['tp']==258
    assert old['trainticket']['queries']==old['trainticket']['exact']==31 and old['trainticket']['tp']==30
    for role in old.values():assert not(role['unknown'] or role['fp'] or role['fn'])
    checks['historical_original_business_correctness']=True
    price={m:load(root/'price-offline-final'/m/'evaluation.json') for m in ('full','selective')}
    assert all(r['exact']==r['queries']==38 and r['tp']==92 and r['fp']==r['fn']==r['unknown']==0 for r in price.values())
    checks['historical_multisource_prices']=True
    assert load(root/'historical-positive-controls.json')['all_passed'];checks['four_planning_positive_controls']=True
    for group in ('development','heldout'):
        if group not in result:continue
        for d in result[group]['groups'].values():assert d['known_without_independent_oracle']==0
    result['all_passed']=all(checks.values());result['historical_business']=old
    result['price_regression']={m:{k:v for k,v in r.items() if k not in ('target_unavailable_queries',)} for m,r in price.items()}
    save(root/'audit.json',result);print(json.dumps({k:v for k,v in result.items() if k not in ('development','heldout')},ensure_ascii=False,indent=2));return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--development',type=Path,required=True);p.add_argument('--heldout',type=Path);a=p.parse_args();audit(a.root.resolve(),a.development.resolve(),a.heldout.resolve() if a.heldout else None)
