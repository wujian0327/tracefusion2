#!/usr/bin/env python3
"""Replay unchanged historical captures with revised offline fast paths.

This is an offline regression, not a new deployment or new unseen input. Frozen
independent truth comes from the previous full capability audit, not inference.
"""
import argparse
from collections import Counter
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save,sha
import run_response_binding_revision as old


def run(out):
    out.mkdir(parents=True,exist_ok=False)
    source=ROOT/'artifacts/baseline-capability-20261020/audit-final-v3/instances.json'
    records=load(source);qs={q['id']:q for q in load(HERE/'capability-comparison-62-20261020.json')['queries']};graphs={};results=[]
    for record in records:
        if not record.get('tf_executed'):continue
        cap=Path(record['tf_capture']);q=qs[record['query']]
        if str(cap) not in graphs:graphs[str(cap)]=old.Reconstruction(cap.parent/'build',cap,load(cap/'run.json')['roles'])
        graph=graphs[str(cap)];cases=load(cap/'run.json')['cases']
        case=cases[0 if record['case']=='first-create' else 1] if record.get('supplementary') else next(c for c in cases if c['case']==record['case'])
        answer=graph.query(case['message'],record['path'],q['role'],boundary=old.BOUNDARY)
        assert answer['target']['observed'].get('value')==record['client_value']
        expected={tuple(x) for x in record['tf_expected']};actual={old.predicted_coord(s) for s in answer['sources']}
        state=('known_correct' if actual==expected else 'known_wrong') if answer['known'] else 'unknown'
        assert state==record['tf_state'],(record['query'],record['case'],state,record['tf_state'])
        results.append({'query':record['query'],'case':record['case'],'path':record['path'],'state':state,'capture':str(cap),'capture_plan_sha256':sha(cap.parent/'build'/q['role']/'plan.json')})
    counts=Counter(r['state'] for r in results);assert counts=={'known_correct':213,'unknown':88}
    save(out/'results.json',{'all_passed':True,'source_sha256':sha(source),'states':dict(counts),'captures':len(graphs),'scope':'Reused original capture and independent truth, revised offline fast paths; no new runtime validation.'})
    save(out/'instances.json',results);print(dict(counts))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=Path);a=p.parse_args();run(a.out.resolve())
