#!/usr/bin/env python3
"""Inventory all exposed families, preserving historical versions and omissions."""
import argparse
import csv
import json
from pathlib import Path
from run_planned_service import HERE, ROOT, load, save, sha
from plan_response_binding import plan_response


def inventory(out,base):
    out.mkdir(parents=True,exist_ok=False)
    seal=HERE/'capability-comparison-62-20261020.json';queries=load(seal)['queries'];rows=[];instances=[]
    roots=[ROOT/'artifacts/response-binding-revision-20261019/development-final',
           ROOT/'artifacts/response-binding-revision-20261019/heldout-first',
           *[ROOT/'artifacts/sockshop-model-revision-20261020'/n for n in (
               'previous22-final-sockshop','previous22-final-trainticket','cart-final-selective',
               'heldout-first-sockshop','heldout-first-trainticket')],
           ROOT/'artifacts/call-lifecycle-revision-20261020/basic-mixed-same-config']
    for q in queries:
        d=out/q['id'];d.mkdir();save(d/'query.json',q)
        row={'id':q['id'],'application':q['application'],'entry':q['entry'],'exposure_group':q['exposure_group'],'baseline_state':'not_yet_run'}
        try:
            plan=plan_response(load(base/q['role']/'model.json'),q['entry'],q['target'],q['path'],read_forward_contracts=True)
            plan['source_evidence']=True
            if q['role']=='basic':plan['json_conversion_methods']=['edu/fudan/common/util/JsonUtils.conveterObject(Ljava/lang/Object;Ljava/lang/Class;)Ljava/lang/Object;']
            save(d/'plan.json',plan);row.update(planning='accepted',profile=plan['profile'])
        except ValueError as e:row.update(planning='refused',planning_reason=str(e))
        evidence=[r/q['id']/'capture/evaluation.json' for r in roots if (r/q['id']/'capture/evaluation.json').exists()]
        # This is a source index, not an invented matched-baseline run. Versions
        # must stay visible even if a newer planner still accepts the query.
        row['historical_evaluations']=[{'path':str(p.relative_to(ROOT)),'sha256':sha(p)} for p in evidence]
        if evidence:
            p=evidence[-1];ev=load(p)
            row['latest_recorded_tf']={k:ev.get(k) for k in ('requests','target_instances','known','unknown','evidence_invalid','oracle_unavailable','exact','tp','fp','fn','N/A_requests')}
            row['latest_recorded_tf']['evaluation_path']=str(p.relative_to(ROOT))
            row['latest_recorded_tf']['is_new_matched_run']=False
            for v in ev['predictions']:
                instances.append({'query':q['id'],'case':v['case'],'message':v.get('message'),'path':v['path'],'client_value':v.get('client_value'),'tf_recorded_state':v['status'],'baseline_state':'not_yet_run','tf_evaluation':str(p.relative_to(ROOT)),'oracle_available':'expected' in v})
        else:
            row['latest_recorded_tf']=None
            row['required_action']='Run original business inputs despite TF refusal; do not count unexecuted targets as N/A.'
        rows.append(row)
    save(out/'inventory.json',{'seal_sha256':sha(seal),'tf_algorithm_commit':'2b3b9297e8382162865075d22459480980a45bbc','queries':rows,'recorded_targets':instances,'capability_inclusion_proven':False,'reason':'Baseline matched-instance evaluation incomplete; historical TF states are not a new paired run.'})
    with (out/'families.csv').open('w') as f:
        writer=csv.writer(f);writer.writerow(['query','application','entry','planning_2b3b929','reason','historical_targets','historical_known','historical_unknown','historical_invalid','historical_oracle_unavailable','baseline_state'])
        for r in rows:
            ev=r['latest_recorded_tf'] or {};writer.writerow([r['id'],r['application'],r['entry'],r['planning'],r.get('planning_reason',''),*[ev.get(k,'') for k in ('target_instances','known','unknown','evidence_invalid','oracle_unavailable')],r['baseline_state']])
    with (out/'instances.csv').open('w') as f:
        keys=['query','case','message','path','client_value','tf_recorded_state','baseline_state','tf_evaluation','oracle_available'];w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(instances)
    summary={'families':len(rows),'accepted':sum(r['planning']=='accepted' for r in rows),'refused':sum(r['planning']=='refused' for r in rows),'distinct_entries':len({q['entry'] for q in queries}),'historical_recorded_targets':len(instances),'baseline_completed_families':0,'inclusion_proven':False}
    save(out/'summary.json',summary);print(json.dumps(summary),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);p.add_argument('--base',type=Path,required=True);a=p.parse_args();inventory(a.out.resolve(),a.base.resolve())
