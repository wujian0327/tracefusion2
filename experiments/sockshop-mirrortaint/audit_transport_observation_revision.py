#!/usr/bin/env python3
"""Require exact parent431 state preservation and independent instance truth."""
import argparse,copy,json
from pathlib import Path
from collections import Counter
from run_planned_service import ROOT,HERE,load,save,sha
from audit_frozen_capability_acceptance import audit as source_audit
from audit_application_call_revision import class_hashes
from audit_jackson_isolation import mapper_hash
from infer_response_binding import matches
import run_frozen_capability_acceptance as driver


def key(r):return(r['mode'],r['query'],r['case'],r['path'])
def signatures(r):return Counter((v[0],v[5],v[6],v[-1])for v in r.get('expected',[]))


def audit(root,out):
    out.mkdir(parents=True,exist_ok=False);driver.HOME=root;driver.check();s=source_audit(root,out/'source-union',partial=True)
    # The compatibility auditor's old heldout metadata is not a new claim.
    save(out/'source-union/audit-at-compatibility-return.json',s)
    s['heldout_candidates_unexamined']=0;s['heldout29_reference']='e37d0ae: first at parent76d2050; exposed before this observation revision.';save(out/'source-union/audit.json',s)
    previous=load(ROOT/'artifacts/jackson-isolation-20261022/candidate-v2/audit-final-first/source-union/instances.json');actual=load(out/'source-union/instances.json');old={key(r):r for r in previous};new={key(r):r for r in actual};state_changes=[];origin_changes=[]
    assert len(old)==862
    for k,a in old.items():
        b=new.get(k)
        if b is None or a['state']!=b['state']:state_changes.append({'key':k,'before':a['state'],'after':None if b is None else b['state']})
        if b is not None and signatures(a)!=signatures(b):origin_changes.append({'key':k,'before':str(signatures(a)),'after':str(signatures(b))})
    classes=class_hashes(root/'frozen-base/distributed-observer.jar');receipts=[];errors=[];queries={q['id']:q for q in driver.QUERIES}
    for r in load(out/'source-union/queries.json'):
        cap=Path(r['capture']);role=queries[r['query']]['role'];mode=r['mode'];d=cap.parent;plan=load(d/'build'/role/'plan.json');rows=[json.loads(v)for v in (cap/role/'events.jsonl').read_text().splitlines()];native=mapper_hash(root/'frozen-base'/role/'original.jar');proofs=[v for v in rows if v['kind']=='jackson-isolation'];assert proofs
        assert all(v['business_class_sha256']==native[1]and v['agent_class_sha256']==classes['tracefusion/internal/jackson/databind/ObjectMapper.class']for v in proofs)
        returns={v.get('message')for v in rows if v['kind']=='binding-return'};policy=plan.get('transport_evidence_policy');request_cfg=plan.get('execution_kernel',{}).get('request_entity_contracts');response_count=0;outbound_count=0;field_count=0
        for v in rows:
            if v['kind']!='http-json'or v['phase']!='write':continue
            if v['direction']=='request'and request_cfg:
                assert 'request_serialization'in v,('Necessary outbound observation missing',r['query'],mode);outbound_count+=1
            if v['direction']=='response'and v['message']in returns:
                response_count+=1;field_count+=len(v['fields'])
                if mode=='selective'and policy:
                    assert 'request_serialization'not in v
                    assert all(matches(policy['response_path'],f['path'])for f in v['fields'])
                elif mode=='full'and request_cfg:assert 'request_serialization'in v
        if (d/'reconstruction-error.txt').exists():errors.append(str(d/'reconstruction-error.txt'))
        receipts.append({'query':r['query'],'role':role,'mode':mode,'native_mapper_sha256':native[1],'bound_responses':response_count,'response_fields':field_count,'outgoing_request_proofs_retained':outbound_count,'policy_enabled':bool(policy),'events_sha256':sha(cap/role/'events.jsonl')})
    for mode in ('full','selective'):
        d=root/'cart-create-pair'/mode;rows=[json.loads(v)for v in (d/'capture/carts/events.jsonl').read_text().splitlines()];native=mapper_hash(root/'frozen-base/carts/original.jar');proofs=[v for v in rows if v['kind']=='jackson-isolation'];assert proofs and all(v['business_class_sha256']==native[1]for v in proofs)
        receipts.append({'query':'supplemental-create-read','mode':mode,'role':'carts','native_mapper_sha256':native[1],'events_sha256':sha(d/'capture/carts/events.jsonl')})
    assert load(root/'controls/results.json')['all_passed']and load(root/'guard-controls/results.json')['all_passed']and load(root/'controls-agent-equivalence.json')['all_passed']
    result={**s,'parent_431_state_preservation_passed':len(new)==862 and not state_changes,'parent_independent_origin_signatures_preserved':not origin_changes,'state_changes':state_changes,'origin_signature_changes':origin_changes,'native_configurations_verified':len(receipts),'all_actual_known_answers_independently_scored':True,'batch_reconstruction_errors':errors,'observation_only':True,'first_unseen_evaluation_reference':'e37d0ae at76d2050, not repeated as unseen here'}
    result['all_passed']=s['all_passed']and result['parent_431_state_preservation_passed']and not origin_changes and len(receipts)==126 and not errors
    save(out/'native-and-scope-receipts.json',receipts);save(out/'audit.json',result);save(HERE/'transport-observation-acceptance-20261023.json',result)
    print(json.dumps({k:v for k,v in result.items()if k in ('all_passed','modes','state_changes','origin_signature_changes','native_configurations_verified')},ensure_ascii=False),flush=True)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();r=audit(a.root.resolve(),a.out.resolve());assert r['all_passed']
