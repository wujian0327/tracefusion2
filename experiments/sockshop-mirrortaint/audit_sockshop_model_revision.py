#!/usr/bin/env python3
"""Recompute query/entry/instance denominators without rerunning applications."""
import argparse,json
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save,sha
from audit_response_binding_revision import stage


def summary(path):
    r=stage(path)
    for app,d in r['groups'].items():
        qs=[q for q in r['queries'] if q['application']==app]
        d['selected_entries']=len({q['entry'] for q in qs})
        d['accepted_entries']=len({q['entry'] for q in qs if q['status']=='accepted'})
        d['entries_with_known_answer']=len({q['entry'] for q in qs if q.get('known',0)})
        assert d['known_without_independent_oracle']==0
        assert d['runtime_queries']==d['accepted'],'Missing accepted-query evaluation: '+str(path)
        assert d['known']==d['exact'] and not(d['fp'] or d['fn']),'Known source mismatch'
        d['all_target_exact_rate_known_required']=d['exact']/d['target_instances'] if d['target_instances'] else None
    return r


def audit(root,require_heldout=False):
    freeze=load(root/'algorithm-freeze.json');checks={}
    for name,value in freeze['sources'].items():assert sha(ROOT/name)==value,name
    checks['frozen_core_unchanged']=True
    assert sha(HERE/'sockshop-model-heldout-20261020.json')==freeze['heldout_sha256']
    seal=load(HERE/'sockshop-model-heldout-20261020.json');pool=load(ROOT/'artifacts/query-coverage-first-20261019/pool.json')
    ids={q['id'] for q in seal['queries']};dev=set(seal['development_ids']);all_ids={q['id'] for q in pool['candidates']}
    assert len(ids)==20 and len(dev)==42 and not ids&dev and len(all_ids-ids-dev)==29
    checks['selection_seal_and_untested29_preserved']=True
    first=load(ROOT/'artifacts/query-coverage-first-20261019/planning.json');assert all(r['status']=='planning-rejected' for r in first['results']) and len(first['results'])==20
    checks['first0of20_unchanged']=True
    result={'checks':checks,'scope':'Query/entry groups, requests, actual target instances and relationships use distinct denominators. No new performance evidence.',
            'freeze_commit':freeze['commit'],'previous22':{},'cart_development':{}}
    for app in ('sockshop','trainticket'):result['previous22'][app]=summary(root/('previous22-final-'+app))
    for mode in ('full','selective'):result['cart_development'][mode]=summary(root/('cart-final-'+mode))
    for mode,v in result['cart_development'].items():
        d=v['groups']['sockshop'];assert d['known']==d['target_instances']==d['exact']==18 and not d['unknown'] and not d['evidence_invalid'],mode
    checks['representative_cart_chain_full_selective_exact']=True
    for directory in ('semantics-final','legacy-semantics-final','collection-controls-final'):
        assert load(root/directory/'results.json')['all_passed'];checks[directory]=True
    for label,file in [('original_exception_version_faults','additional-refusal-audit.json'),
                       ('real_cart_evidence_faults','cart-final-selective/sockshop-carts-getItems-each-quantity/fault-audit.json'),
                       ('independent_original_decoder','independent-decoding-final/checks.json')]:
        assert load(root/file)['all_passed'];checks[label]=True
    assert load(root/'historical-positive-controls.json')['all_passed'];checks['historical4planning']=True
    historical=load(root/'historical-business/comparison.json')['results']
    assert historical['sockshop']['queries']==historical['sockshop']['exact']==198 and historical['sockshop']['tp']==258
    assert historical['trainticket']['queries']==historical['trainticket']['exact']==31 and historical['trainticket']['tp']==30
    assert all(not(r['unknown'] or r['fp'] or r['fn']) for r in historical.values());checks['historical_real_business']=True
    result['historical_business']=historical
    price={m:load(root/'price-business'/m/'evaluation.json') for m in ('full','selective')}
    assert all(r['queries']==r['exact']==38 and r['tp']==92 and not(r['unknown'] or r['fp'] or r['fn']) for r in price.values());checks['historical_prices_full_selective']=True
    result['historical_price']=price
    if require_heldout:
        result['heldout']={app:summary(root/('heldout-first-'+app)) for app in ('sockshop','trainticket')}
        seen={q['id'] for s in result['heldout'].values() for q in s['queries']};assert seen==ids
        checks['first_heldout_exact_selected_ids']=True
    result['all_passed']=all(checks.values());save(root/'audit.json',result)
    print(json.dumps({'all_passed':result['all_passed'],'checks':checks},indent=2));return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--heldout',action='store_true');a=p.parse_args();audit(a.root.resolve(),a.heldout)
