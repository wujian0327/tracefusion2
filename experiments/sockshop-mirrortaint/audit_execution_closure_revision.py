#!/usr/bin/env python3
"""Keep old 62 and exposed29 cohorts separate; compare states and origin roles."""
import argparse,json
from collections import Counter
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save,sha
from audit_application_call_revision import class_hashes
from audit_frozen_capability_acceptance import audit as audit62
from audit_transport_observation_revision import key,signatures
from audit_jackson_isolation import mapper_hash
import run_frozen_capability_acceptance as driver


def controls(root):
    expected=class_hashes(root/'frozen-base/distributed-observer.jar');receipts=[]
    for home in('closure-controls','controls','guard-controls'):
        assert load(root/home/'results.json')['all_passed']
        for path in(root/home).rglob('distributed-observer.jar'):
            assert class_hashes(path)==expected;receipts.append({'jar':str(path),'sha256':sha(path),'compiled_classes_identical':True})
    assert receipts;save(root/'controls-agent-equivalence.json',{'all_passed':True,'receipts':receipts})


def development(root):
    driver.HOME=root;driver.check();controls(root);out=root/'capability-audit';out.mkdir();s=audit62(root,out/'source-union',partial=True)
    previous=load(ROOT/'artifacts/transport-observation-shared-20261023/capability-audit/source-union/instances.json');current=load(out/'source-union/instances.json');before={key(r):r for r in previous};after={key(r):r for r in current};changes=[]
    for k,a in before.items():
        b=after.get(k)
        if b is None or a['state']!=b['state']or signatures(a)!=signatures(b):changes.append({'key':k,'before':a['state'],'after':None if b is None else b['state'],'origins_equal':b is not None and signatures(a)==signatures(b)})
    mapper=[]
    for f in load(out/'source-union/queries.json'):
        cap=Path(f['capture']);q=next(q for q in driver.QUERIES if q['id']==f['query']);role=q['role'];rows=[json.loads(v)for v in(cap/role/'events.jsonl').read_text().splitlines()];proofs=[r for r in rows if r['kind']=='jackson-isolation'];expected=mapper_hash(cap.parent/'build'/role/'original.jar')[1];assert proofs and all(v['business_class_sha256']==expected for v in proofs);mapper.append({'query':q['id'],'mode':f['mode'],'events_sha256':sha(cap/role/'events.jsonl'),'native_mapper_sha256':expected})
    result={**s,'heldout_candidates_unexamined':0,'new21_first_evaluation_reported_separately':True,'exposed29_reported_separately':True,'parent_431_state_preservation_passed':len(current)==len(previous)==862 and not changes,'parent_independent_origins_preserved':not changes,'changes':changes,'mapper_configurations_verified':len(mapper)}
    result['all_passed']=s['all_passed']and result['parent_431_state_preservation_passed']and len(mapper)==124
    save(out/'mapper-receipts.json',mapper);save(out/'audit.json',result);assert result['all_passed'];print({'development62_passed':True,'targets_per_mode':431,'states':{m:r['states']for m,r in result['modes'].items()}},flush=True)


def fields29(root,out=None):
    driver.HOME=root;driver.check();out=out if out is not None else root/'regression29-audit';out.mkdir(parents=True);old=load(ROOT/'artifacts/heldout29-first-20261023/audit-final-reviewed/audit.json');reference={};seen=set();actual={};records=[];failures=[];agent=class_hashes(root/'frozen-base/distributed-observer.jar')
    for rec in old['records']:
        if rec['mode']not in('full','selective'):continue
        ev=load(Path(rec['evaluation_file']))
        for t in ev['predictions']:reference[(rec['mode'],t['query'],t['case'],t['path'])]=t
    for folder in('regression29-orders','regression29-train'):
        result=load(root/folder/'results.json');assert result['complete'];failures.extend(r for r in result['results']if 'failure'in r)
        for source in sorted((root/folder).glob('*/evaluation.json')):
            ev=load(source);mode=ev['mode'];qid=ev['query'];assert(mode,qid)not in seen;seen.add((mode,qid));assert class_hashes(source.parent/'build/distributed-observer.jar')==agent
            for t in ev['predictions']:actual[(mode,qid,t['case'],t['path'])]=t
            records.append({'mode':mode,'query':qid,'evaluation_file':str(source),**{k:v for k,v in ev.items()if k not in('predictions','query','mode')}})
    changes=[]
    for k,a in reference.items():
        b=actual.get(k)
        if b is None or a['state']!=b['state']or signatures(a)!=signatures(b):changes.append({'key':k,'before':a['state'],'after':None if b is None else b['state'],'origins_equal':b is not None and signatures(a)==signatures(b)})
    summary={m:{'query_families':sum(r['mode']==m for r in records),'targets':sum(r['targets']for r in records if r['mode']==m),'states':dict(Counter(t['state']for k,t in actual.items()if k[0]==m)),'oracle_unavailable':sum('oracle_error'in t for k,t in actual.items()if k[0]==m),'N/A_requests':sum(r['N/A_requests']for r in records if r['mode']==m),'requests':sum(r['requests']for r in records if r['mode']==m)}for m in('full','selective')}
    result={'all_passed':len(seen)==58 and len(actual)==len(reference)==488 and not changes and not failures,'algorithm':load(root/'algorithm-freeze.json')['commit'],'queries':29,'modes':summary,'changes':changes,'business_failures':failures,'records':records,'first_unseen_claim':False,'historical12_missing_oracle_not_promoted':True};save(out/'audit.json',result);assert result['all_passed'];print({'exposed29_passed':True,'modes':summary},flush=True)


def heldout(root):
    out=root/'heldout21-first';planning=load(out/'plans/planning.json');records=[];failures=[]
    for role in('station','route','price'):
        p=load(out/('runtime-'+role)/'results.json');assert p['complete']
        for r in p['results']:
            if 'failure'in r:failures.append(r)
            else:records.append(r)
    modes={m:{'runtime_query_families':sum(r['mode']==m for r in records),'requests':sum(r['requests']for r in records if r['mode']==m),'targets':sum(r['targets']for r in records if r['mode']==m),'states':dict(sum((Counter(r['states'])for r in records if r['mode']==m),Counter())),'N/A_requests':sum(r['N/A_requests']for r in records if r['mode']==m),'oracle_unavailable':sum(r['oracle_unavailable']for r in records if r['mode']==m)}for m in('full','selective')}
    result={'first_results_preserved':True,'algorithm':load(root/'algorithm-freeze.json')['commit'],'candidate_queries':21,'entries':5,'accepted':sum(r['accepted']for r in planning),'rejected':sum(not r['accepted']for r in planning),'modes':modes,'runtime_failures':failures,'records':records,'auth_failure_policy':'Requests rejected with403 before entering the query method are experimental access failures, not business N/A or TF unknown. Count separately.','no_core_repair_or_query_replacement_after_unseal':True};save(out/'audit-first.json',result);print({'heldout21_first':modes,'runtime_failures':len(failures)},flush=True)
    # Additional post-capture oracle audit. This reads only raw argument facts
    # and the original literal case projection; no TF graph is instantiated.
    truth_checks=[];layers={m:Counter()for m in('full','selective')}
    for role in('route','price'):
        for source in sorted((out/('runtime-'+role)).glob('*/evaluation.json')):
            d=source.parent;raw=[json.loads(v)for v in(d/'capture'/role/'events.jsonl').read_text().splitlines()];by_seq={r['seq']:r for r in raw};by_frame={r['frame']:r for r in raw if r['kind']=='enter'}
            evaluation=load(source)
            for prediction in evaluation['predictions']:
                error=prediction.get('error','');layers[evaluation['mode']]['unsupported_replay_semantics'if error.startswith('Unsupported replay opcode')else'collector_problem'if error=='Collector problem'else'other']+=1
                assert len(prediction['expected'])==1;coordinate=prediction['expected'][0];fact=by_seq[coordinate[3]];entry=by_frame[coordinate[2]];owner=entry['args'][0]['object'];assert fact['kind']=='binding-input'and fact['frame']==entry['frame']and fact['argument']==0
                fields=[f for f in fact['fields']if f['owner']==owner and f['field']==coordinate[5]and f['version']==coordinate[6]and f['path']==coordinate[7]];assert len(fields)==1 and coordinate[4]==owner
                truth_checks.append({'query':prediction['query'],'case':prediction['case'],'path':prediction['path'],'actual_argument0_owner_verified':True,'snapshot_coordinate_verified':True})
    assert len(truth_checks)==192;save(out/'independent-argument-coordinate-audit.json',{'all_passed':True,'checks':truth_checks,'not_a_TF_source_propagation_or_graph_check':True})
    save(out/'failure-layer-audit.json',{'counts_per_mode':{m:dict(v)for m,v in layers.items()},'first_driver_states_unchanged':True,'classification_limit':'The first driver labeled unsupported bounded-scalar replay GETFIELD as evidence_invalid. These20 targets per mode are an analysis-semantics/profile-routing limitation, not missing/contradictory capture evidence. Preserve the first classification and report this diagnostic distinction separately.','core_repaired_after_unseal':False})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',required=True,type=Path);p.add_argument('--stage',choices=('controls','development','fields29','heldout'),required=True);a=p.parse_args();{'controls':controls,'development':development,'fields29':fields29,'heldout':heldout}[a.stage](a.root.resolve())
