#!/usr/bin/env python3
"""Frozen TF four Basic queries on exactly the native baseline travel inputs."""
import argparse
import json
from pathlib import Path
import traceback
from run_planned_service import ROOT,HERE,load,save,sha
import run_response_binding_revision as old


def run(out,base,inventory):
    out.mkdir(parents=True,exist_ok=False)
    qs=[q for q in load(HERE/'capability-comparison-62-20261020.json')['queries'] if q['role']=='basic']
    native=ROOT/'artifacts/baseline-capability-20261020/extra-entries-calibrated07/trainticket-basic-queryForTravel-data-status/capture'
    baseline=load(native/'run.json');results=[]
    for q in qs:
        d=out/q['id'];d.mkdir();old.query_build(d/'build',base,q,load(inventory/q['id']/'plan.json'));capt=d/'capture';capt.mkdir()
        try:
            old.capture_train(capt,d/'build',q,20261020);ev=old.evaluate(capt,d/'build',q);actual=load(capt/'run.json')
            for a,b in zip(baseline['cases'],actual['cases']):
                assert all(a[k]==b[k] for k in ('case','body','request_path','database_documents','http_status'))
                left,right=a['response'],b['response']
                if a['http_status']>=400:
                    left={k:v for k,v in left.items() if k!='timestamp'};right={k:v for k,v in right.items() if k!='timestamp'}
                assert left==right
            for role in ('station','train','route','price'):
                assert load(native/('db-'+role)/'database-input.json')==load(capt/('db-'+role)/'database-input.json')
            save(d/'matched-input-audit.json',{'passed':True,'baseline_capture':str(native),'same_request_and_database_fixtures':True,'same_business_responses':True,'excluded_generated_nonquery_metadata':['HTTP>=400 response.timestamp']})
            results.append({'id':q['id'],'targets':ev['target_instances'],'known':ev['known'],'unknown':ev['unknown'],'invalid':ev['evidence_invalid'],'oracle_unavailable':ev['oracle_unavailable']})
        except Exception as e:results.append({'id':q['id'],'error':str(e)});save(d/'error.json',{'error':str(e),'traceback':traceback.format_exc()})
        save(out/'progress.json',results);print(json.dumps(results[-1]),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('out','base','inventory'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();run(a.out.resolve(),a.base.resolve(),a.inventory.resolve())
