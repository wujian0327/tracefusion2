#!/usr/bin/env python3
"""Check diagnostic-toggle parity and identical mandatory refusal checks."""
import argparse,copy,json
from pathlib import Path
from run_planned_service import load,save,sha
from run_bound_query_cost import query
from infer_distributed_fields import Reconstruction
import run_response_binding_revision as old


def audit(root):
    results={}
    for kind in ('cart','train'):
        q=query(kind);role=q['role'];signatures=[];specs=[]
        for raw in (False,True):
            for mode in ('full','selective'):
                name=kind+('-raw' if raw else '-required')+'-'+mode;d=root/'bound-calibration'/name;b=root/(kind+('-raw-build' if raw else '-cost-build'))
                m=load(d/'metrics.json');assert m['status']=='passed' and load(d/'cleanup.json')['returncode']==0
                plan=load(b/role/'plan.json');assert bool(plan.get('source_evidence'))==raw
                assert plan['read_forward_contracts']['version']==2
                spec=json.dumps(load(d/'capture/compose.json'),sort_keys=True).replace(str(d/'capture'),'$CAPTURE').replace(str(b),'$BUILD').replace('-Dservice.mode='+mode,'-Dservice.mode=$MODE');specs.append(spec)
                score=load(d/'field-results.json');signature=[(r['case'],r['path'],r['known'],r['exact'],r['tp'],r['fp'],r['fn']) for r in score['queries']];signatures.append(signature)
                rows=[json.loads(l) for l in (d/'capture'/role/'events.jsonl').read_text().splitlines()];c=load(d/'warmup.json')['requests'][0];path=old.leaves(c['response'],q['path'])[0][0];faults={}
                for fault in ('missing-runtime','missing-summary','missing-call-start','missing-call-end','missing-source','wrong-pairing','wrong-source-version','ambiguous-message'):
                    broken=copy.deepcopy(rows)
                    at=next(i for i,r in enumerate(broken) if r.get('message')==c['message'] and r['kind']=={'missing-runtime':'binding-call-summary','missing-summary':'binding-call-summary','missing-call-start':'binding-call-enter','missing-call-end':'binding-call-exit','missing-source':'binding-source','wrong-pairing':'binding-call-exit','wrong-source-version':'binding-source','ambiguous-message':'http-json'}[fault])
                    if kind=='train' and fault in ('missing-source','wrong-source-version'):
                        # Original retrieve returns its SECOND findById. Removing
                        # the unused first source must not poison that answer.
                        at=[i for i,r in enumerate(broken) if r.get('message')==c['message'] and r['kind']=='binding-source'][-1]
                    if fault=='missing-runtime':broken=[r for r in broken if r['kind']!='binding-call-runtime']
                    elif fault.startswith('missing'):broken.pop(at)
                    elif fault=='wrong-pairing':broken[at]['call_id']='unrelated-call'
                    elif fault=='wrong-source-version':
                        for f in broken[at]['fields']:f['version']+=100
                    else:
                        victim=next(r for r in broken if r['kind']=='http-json' and r.get('message')==c['message'] and r['phase']=='write');broken.append(copy.deepcopy(victim))
                    for i,r in enumerate(broken,1):r['seq']=i
                    try:
                        g=Reconstruction(b,d/'capture',[role],decoded_rows={role:broken});assert not g.query(c['message'],path,role,boundary=old.BOUNDARY)['known'],(name,fault)
                    except ValueError:pass
                    faults[fault]='refused or unknown'
                results[name]={'summary':m['offline']['summary'],'raw_http_source_facts':m['offline']['raw_http_source_facts'],'faults':faults,'plan_sha256':sha(b/role/'plan.json'),'capture_sha256':sha(d/'capture'/role/'events.jsonl')}
        assert all(s==signatures[0] for s in signatures),'Toggle/policy answers differ'
        assert all(s==specs[0] for s in specs),'Deployment difference beyond output/build paths and policy'
    save(root/'bound-calibration-audit.json',{'all_passed':True,'same_logical_answers_and_instance_exactness':True,'same_spec_except_paths_and_policy':True,'mandatory_fault_checks_per_configuration':8,'results':results,'interpretation':'Cart and Train use repository/entry facts, not raw HTTP bytes. Zero raw-source facts here is disclosed; price RPC toggle is checked separately.'})
    print('Bound query calibration audit passed',flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);audit(p.parse_args().root.resolve())
