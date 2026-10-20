#!/usr/bin/env python3
"""Replay planning, retain every original exposed target, never count rejection as success."""
import argparse,json
from pathlib import Path
from run_planned_service import HERE,ROOT,load,save,sha
from plan_response_binding import plan_response


def run(out,base):
    out.mkdir(parents=True,exist_ok=False)
    protocol=load(HERE/'kernel-contract-protocol-20261020.json')
    original=ROOT/'artifacts/baseline-capability-20261020/audit-final-v3/instances.json'
    rows=load(original);checks=[];instances=[]
    for q in protocol['queries']:
        targets=[r for r in rows if r['query']==q['id']]
        assert all(r['baseline_state']=='known_correct' for r in targets)
        try:
            p=plan_response(load(base/q['role']/'model.json'),q['entry'],q['target'],q['path'],execution_kernel=True,application_calls=True)
            save(out/(q['id']+'-plan.json'),p);status='accepted_not_executed';reason=None
        except ValueError as error:status='planning_rejected';reason=str(error)
        checks.append({'query':q['id'],'targets':len(targets),'status':status,'reason':reason})
        for row in targets:
            instances.append({'query':q['id'],'case':row['case'],'path':row['path'],'client_value':row['client_value'],'new_status':status,'new_reason':reason,'newly_correct':False,'baseline_state':row['baseline_state'],'baseline_expected':row['baseline_expected'],'original_baseline_capture':row['baseline_capture'],'matched_input_truth_reused':True,'business_rerun':False})
    assert len(instances)==36
    result={'scope':'Six exposed query families; original 36 target/input instances reused because planning rejection occurs before business execution. Not new runtime unknowns.','protocol_sha256':sha(HERE/'kernel-contract-protocol-20261020.json'),'original_instances_sha256':sha(original),'queries':checks,'target_instances':len(instances),'newly_correct':0,'remaining_gaps':109,'instances':instances}
    save(out/'results.json',result);print(json.dumps(checks,ensure_ascii=False,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=Path);p.add_argument('--base-build',required=True,type=Path);a=p.parse_args();run(a.out.resolve(),a.base_build.resolve())
