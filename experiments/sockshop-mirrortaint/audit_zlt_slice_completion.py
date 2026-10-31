"""Final ZLT positive-source gate; reused MT captures are explicitly labelled."""
import argparse,collections,json
from pathlib import Path
from run_planned_service import ROOT,load,save,sha
from audit_zlt_foundation_revision import audit


def run(root,out):
    out.mkdir(parents=True,exist_ok=False)
    audit(root/'zlt',out/'independent-score')
    summary=load(out/'independent-score/summary.json')
    records=load(out/'independent-score/instances.json')
    for mode in ('full','selective','mirrortaint'):
        assert summary['states'][mode]=={'known_correct':15}
        assert summary['adequate_oracles'][mode]==15
        assert all(r['business_equal'] and r['target_bound'] and r['source_paired'] and r['oracle_adequate']
                   for r in records if r['mode']==mode)
    assert all(r['business_equal'] and r['error'] is None for r in summary['receipts'])
    protocol=load(root/'final-protocol-before-business.json')
    for relative,digest in protocol['plans'].items():assert sha(root/relative)==digest
    assert sha(root/'historical/frozen-base/distributed-observer.jar')==protocol['agent_sha256']
    for api in ('ZLT-MP-1','ZLT-MP-4'):
        for mode in ('full','selective'):
            receipt=load(root/'zlt/runs'/api/mode/'revision-receipt.json')
            assert receipt['agent_sha256']==protocol['agent_sha256']
            raw=root/'zlt/runs'/api/mode/'capture/events.jsonl'
            events=[json.loads(line)for line in raw.read_text().splitlines()]
            source=next(q['oracle']['source']for q in load(root/'zlt/task-seal.json')['entries']if q['id']==api)
            calls=[r for r in events if r['kind']=='collection-call-enter'and r.get('callee')==source]
            ends={r['call_id']:r for r in events if r['kind']=='collection-call-exit'}
            assert len(calls)==6 and all(c['call_id']in ends for c in calls)
            for s in (r for r in events if r['kind']=='binding-source'):
                c=next(c for c in calls if c['call_id']==s['source_call_id'])
                assert c['seq']<s['seq']<ends[c['call_id']]['seq']
            r=next(r for r in summary['receipts']if r['api']==api and r['mode']==mode)
            r['interpreted_source_call_protocol']={'calls':6,'paired':True,'empty_return_still_has_call':True}
            r['legacy_protocol_counter_scope']='The inherited opaque-caller scanner counts only source-observation events, not these interpreted collection-call events.'
    summary.update(candidate_commit=protocol['candidate_commit'],reference='c1a4e5c',
        no_new_framework_contract=False,public_models_added=True,
        positive_correct_per_mode=15,new_TF_deployments=4,
        MT='Original B2.2/native capture reuse, unchanged binary/task/input/independent rules; not a new MT deployment',
        exposed_development_regression=True,unseen_transfer_evidence=False,
        agent_sha256=protocol['agent_sha256'],gate_passed=True)
    save(out/'summary.json',summary)
    (out/'instances.csv').write_bytes((out/'independent-score/instances.csv').read_bytes())
    print({k:summary[k] for k in ('candidate_commit','states','positive_correct_per_mode','gate_passed')})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();run(a.root.resolve(),a.out.resolve())
