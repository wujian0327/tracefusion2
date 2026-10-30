"""Constructor-stage paired answers, retained source signatures and first loss.

The diagnostic reads interpreter state; only the separate existing oracle
scores answers. Unknown truth remains distinct from a missing tool answer.
"""
import argparse,collections,json
from pathlib import Path
from run_planned_service import ROOT,load,save,sha
from audit_communication_identity_revision import mall as audit_mall,preserved_first
from diagnose_source_loss import run as diagnose

PARENT=ROOT/'artifacts/communication-identity-revision-20261029'

def signature(record):
    return collections.Counter((v[0],v[3],v[5],v[6])for v in record.get('expected',[]))

def run(home,out):
    out.mkdir(parents=True,exist_ok=False);audit_mall(home,out/'paired')
    before={(r['mode'],r['api'],r['case'],r['path']):r for r in load(PARENT/'audit-final-mall-02/instances.json')}
    # Path components are API / mode / query; no dependency on directory order.
    current=[r for p in sorted((home/'evaluation').glob('*/*/*/instances.json'))for r in load(p)]
    after={(r['mode'],r['api'],r['case'],r['path']):r for r in current}
    assert set(after)==set(before)and len(after)==206
    paired=load(out/'paired/instances.json');modes={};changes=[];signature_changes=[]
    for r in paired:
        k=(r['mode'],r['api'],r['case'],r['path']);old=before[k]
        r['previous_TF_state']=old['state']
        if old['state']!=r['state']:changes.append({'key':k,'before':old['state'],'after':r['state']})
        if old['state']=='known_correct'and signature(old)!=signature(after[k]):signature_changes.append(k)
    summary=load(out/'paired/summary.json')
    for mode,s in summary['modes'].items():
        selected=[r for r in paired if r['mode']==mode]
        s['previous_correct_preserved']=sum(r['previous_TF_state']=='known_correct'and r['state']=='known_correct'for r in selected)
        unresolved=[r for r in selected if r['api']=='mall-swarm-5'and r['path']=='/data']
        assert len(unresolved)==5 and all(r['state']=='unknown'for r in unresolved)
        s['oracle_unavailable_unknown']=len(unresolved)
        s['joint_gate_passed']=s['MT_correct_preserved']==88 and s['previous_correct_preserved']==68 and s['states'].get('known_correct',0)>=98 and not s['states'].get('known_wrong',0)
        modes[mode]=s
    diagnostics=[]
    for mode in ('full','selective'):
        tasks=load(home/'planning-summary.json')
        for task in tasks:
            if not task['query']['id'].startswith('mall-swarm-3-'):continue
            index=task['index'];plan=home/'planning-first/mall-swarm-3'/('%03d-plan.json'%index)
            raw=home/'tool-runs/mall-swarm-3'/mode/('query-%03d'%index)/'capture/events.jsonl'
            dest=out/'first-loss'/mode/('%03d'%index);diagnose(plan,raw,dest)
            lost=load(dest/'source-first-loss.json')['first_losses']
            targets=load(home/'evaluation/mall-swarm-3'/mode/('%03d'%index)/'instances.json')
            for target in targets:
                assert target['positive']and target.get('expected')
                for v in target['expected']:
                    matches=[r for r in lost if (r['source_seq'],r['source_owner'],r['source_field'],r['source_version'])==(v[2],v[4],v[5],v[6])]
                    assert len(matches)==1,(mode,index,target['case'],matches)
                    diagnostics.append({'mode':mode,'index':index,'case':target['case'],'path':target['path'],'tool_state':target['state'],'independent_expected_source':v,'diagnostic_only':True,**matches[0]})
    assert len(diagnostics)==60
    # Protect both the older first/C1 manifests and the immediately preceding
    # communication captures. This hashes original bytes without rewriting them.
    protected=preserved_first()
    for label,base,manifest in [('communication_mall',PARENT/'final-mall-02',PARENT/'audit-final-mall-02/captures-manifest.json')]:
        files=load(manifest)['files']
        for p,h in files.items():assert sha(base/p)==h,p
        protected[label]=len(files)
    summary.update(modes=modes,previous_reference='59dbdf8 communication final-mall-02:68/103',state_changes=changes,retained_source_signature_changes=signature_changes,positive_first_loss_targets=len(diagnostics),protected_files_unchanged=protected,joint98_gate_passed=all(s['joint_gate_passed']for s in modes.values()),prior68_answers_preserved=all(s['previous_correct_preserved']==68 for s in modes.values())and not signature_changes)
    save(out/'paired/instances.json',paired)
    import csv
    with(out/'paired/instances.csv').open('w',newline='')as f:
        fields=['api','mode','query_index','case','path','state','positive','TP','FP','FN','previous_TF_state','MT_state','MT_positive','MT_correct_preserved','error','oracle_gap'];w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore',lineterminator='\n');w.writeheader();w.writerows(paired)
    save(out/'positive-target-first-loss.json',diagnostics);save(out/'summary.json',summary)
    assert summary['prior68_answers_preserved']and summary['full_selective_states_equal']and not signature_changes
    print({m:{k:v for k,v in s.items()if k!='MT_gap'}for m,s in modes.items()},flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--home',required=True,type=Path);p.add_argument('--out',required=True,type=Path);a=p.parse_args();run(a.home.resolve(),a.out.resolve())
