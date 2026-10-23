#!/usr/bin/env python3
"""Real-JVM regression and metadata perturbations for application write values."""
import argparse,copy
from pathlib import Path
import run_application_call_semantics as controls
from run_planned_service import load,save,sha
from plan_capability_policy import choose
from infer_execution_kernel import infer_execution

def run(out):
    original=controls.build
    def build(dest,inputs):
        original(dest,inputs);manifest=load(dest/'build.json');cfg=inputs['fixture'];q={'entry':cfg['entry'],'target':cfg['targets'][0],'path':cfg['response_path']};plan,_=choose(load(dest/'fixture/model.json'),q);save(dest/'fixture/plan.json',plan);manifest['inputs']['fixture']['plan_sha256']=sha(dest/'fixture/plan.json');save(dest/'build.json',manifest)
    controls.build=build
    try:controls.run(out)
    finally:controls.build=original
    plan=load(out/'build/fixture/plan.json');rows=[controls.json.loads(v)for v in(out/'selective/fixture/events.jsonl').read_text().splitlines()];minimal=[r for r in rows if r['kind']=='write-version'];assert len(minimal)>0
    full=[controls.json.loads(v)for v in(out/'full/fixture/events.jsonl').read_text().splitlines()];assert not any(r['kind']=='write-version'for r in full)
    faults={}
    for label in ('wrong-owner','wrong-version','missing-record','extra-value','target-field','full-mode','disabled-policy'):
        changed=copy.deepcopy(rows);p=copy.deepcopy(plan);r=next(v for v in changed if v['kind']=='write-version')
        if label=='wrong-owner':r['owner']='same-valued-other-object'
        elif label=='wrong-version':r['version']+=1
        elif label=='missing-record':changed.remove(r)
        elif label=='extra-value':r['observed']={'value':'SAME'}
        elif label=='target-field':r['field']=plan['target']
        elif label=='full-mode':changed[0]['mode']='full'
        else:p['execution_observation_closure']['application_write_values']['enabled']=False
        try:infer_execution(p,changed)
        except ValueError:faults[label]=True
        else:raise AssertionError('Accepted corrupted version-only evidence: '+label)
    save(out/'write-cut-audit.json',{'all_passed':True,'version_only_events':len(minimal),'faults':faults,'scope':'Values omitted at statically unused application fields; write/version/site events, calls and paths retained. No performance measurements.'})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=Path);run(p.parse_args().out.resolve())
