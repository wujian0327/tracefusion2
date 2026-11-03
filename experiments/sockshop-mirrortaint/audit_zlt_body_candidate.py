"""Final frozen-candidate gates; original exposed cohorts stay separate."""
import argparse,collections
from pathlib import Path
from run_planned_service import ROOT,load,save,sha


def mall(root,out):
    from audit_communication_identity_revision import mall as audit
    audit(root/'mall',out)
    old=ROOT/'artifacts/source-locality-effects-20261030/final-mall-03/evaluation'
    def records(home):
        return {(r['mode'],r['api'],r['case'],r['path']):r for p in home.glob('*/*/*/instances.json')for r in load(p)}
    before=records(old);after=records(root/'mall/evaluation');assert len(before)==len(after)==206 and set(before)==set(after)
    def signature(r):return collections.Counter((v[0],v[3],v[5],v[6])for v in r.get('expected',[]))
    for key,row in before.items():
        assert row['state']==after[key]['state'],key
        if row['state']=='known_correct':assert signature(row)==signature(after[key]),key
    summary=load(out/'summary.json')
    for mode,s in summary['modes'].items():
        assert s['states']=={'known_correct':98,'unknown':5}
        assert s['MT_correct_preserved']==88 and s['MT_positive_preserved']==62
    summary.update(reference='c1a4e5c, 98 known/5 oracle-unavailable unknown',
        all_98_states_and_logical_signatures_preserved=True,joint98_gate_passed=True,
        exposed_development_regression=True)
    if (root/'capture-reuse-receipt.json').exists():
        summary.update(fresh_deployments=0,captures_reused_from=load(root/'capture-reuse-receipt.json')['first_candidate'],
            final_code_normal_reconstruction_rescored=True,reference='7e4ad0b capability set; original C1 logical signature comparator retained')
    save(out/'summary.json',summary)


def historical(root,out):
    from audit_communication_identity_revision import historical as audit
    audit(root/'historical',out)
    summary=load(out/'summary.json');account=load(root/'historical/account-score-first/summary.json')
    save(out/'account-summary.json',account)
    summary['Account40']=account
    if (root/'capture-reuse-receipt.json').exists():
        receipt=load(root/'capture-reuse-receipt.json')
        summary.update(fresh_Agent_deployments=False,capture_provenance=receipt,
            changed_plan_new_deployments=2*sum(len(v)for v in receipt['changed_query_ids'].values()))
    save(out/'summary.json',summary)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['mall','historical']);p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    globals()[a.stage](a.root.resolve(),a.out.resolve())
