#!/usr/bin/env python3
"""Verify frozen source integrity, original-app truth, paired inputs and refusal guards."""
import argparse
import copy
import json
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save,sha
import run_execution_kernel_pilot as pilot
import run_execution_kernel_guards as guards
import run_response_binding_revision as old
from infer_execution_kernel import infer_execution


def audit(root,out):
    out.mkdir(parents=True,exist_ok=False);freeze=load(root/'algorithm-freeze.json')
    for file,digest in freeze['sources'].items():assert sha(ROOT/file)==digest,('Frozen source differs',file)
    for role,digest in freeze['jars'].items():assert sha(root/'pilot-frozen-base-build'/role/'original.jar')==digest
    assert sha(root/'protocol.json')==freeze['reserved_candidates_sha256']
    assert len(load(root/'protocol.json')['unexamined_candidates'])==29
    assert sha(HERE/'BASELINE-CAPABILITY-20261020.md')==load(root/'protocol.json')['old_report_sha256']
    main=load(root/'pilot-frozen/results.json');guard=load(root/'guards-frozen/results.json');assert main['complete'] and guard['complete']
    records=[];matched=[];manifests={};qs=load(HERE/'capability-comparison-62-20261020.json')['queries'];groups={}
    for q in qs:groups.setdefault(q['entry'],[]).append(q)
    for scope in ('pilot-frozen','guards-frozen'):
        for dest in sorted((root/scope).glob('full-*')):
            ident=dest.name.removeprefix('full-');q=next(q for q in qs if q['id']==ident);other=root/scope/('selective-'+ident)
            left=load(dest/'capture/run.json');right=load(other/'capture/run.json');assert len(left['cases'])==len(right['cases'])
            for a,b in zip(left['cases'],right['cases']):
                for k in ('case','request_path','request_body','database_documents','response','http_status'):assert a[k]==b[k],(ident,k)
            primary=groups[q['entry']][0]['id']
            if scope=='pilot-frozen':
                native=ROOT/'artifacts/baseline-capability-20261020/extra-entries-calibrated07'/primary/'capture'
                for a,b in zip(left['cases'],load(native/'run.json')['cases']):
                    for k in ('case','request_path','request_body','database_documents','response','http_status'):assert a[k]==b[k],('Prior baseline inputs',ident,k)
            matched.append({'scope':scope,'query':ident,'same_full_selective_inputs':True,'matched_prior_baseline_inputs':scope=='pilot-frozen','requests_per_mode':len(left['cases'])})
            for mode,path in [('full',dest),('selective',other)]:
                cap=path/'capture';role=q['role'];raw=cap/role/'events.jsonl';before=sha(raw)
                if scope=='guards-frozen':
                    oracle=pilot.independent;pilot.independent=guards.independent
                    try:result=pilot.evaluate(cap,path/'build',q)
                    finally:pilot.independent=oracle
                else:result=pilot.evaluate(cap,path/'build',q)
                assert result['exact']==result['targets'] and not result['unknown'] and result['fp']==result['fn']==0
                assert sha(raw)==before
                manifests[str(raw.relative_to(ROOT))]=before
                for name in ('compose.json','run.json','images.json'):
                    if (cap/name).exists():manifests[str((cap/name).relative_to(ROOT))]=sha(cap/name)
                manifests[str((path/'build'/role/'plan.json').relative_to(ROOT))]=sha(path/'build'/role/'plan.json')
                records.append({'scope':scope,**{k:v for k,v in result.items() if k!='answers'}})
    # Real application evidence faults: identity/iteration/return versions and
    # missing or ambiguous boundary facts must not yield incorrect known answers.
    faults={}
    dest=next((root/'pilot-frozen').glob('full-*stations-each'));q=load(dest/'query.json');plan=load(dest/'build'/q['role']/'plan.json');raw=dest/'capture'/q['role']/'events.jsonl';rows=[json.loads(x) for x in raw.read_text().splitlines()]
    variants={}
    x=copy.deepcopy(rows);event=next(r for r in x if r['kind']=='collection-call-exit' and r['result'].get('object') and r.get('result_type')=='route.entity.Route');event['result']['object']='forged-same-valued-object';variants['wrong-iterator-member']=x
    x=copy.deepcopy(rows);event=next(r for r in x if r['kind']=='binding-return');event['fields'][0]['version']+=1;variants['wrong-output-version']=x
    x=copy.deepcopy(rows);event=next(r for r in x if r['kind']=='collection-call-exit');x.remove(event);variants['missing-completion']=x
    for name,altered in variants.items():
        try:result=infer_execution(plan,altered)
        except ValueError:faults[name]='rejected'
        else:
            assert any(not a['known'] for a in result['answers']),name
            faults[name]='unknown'
    for name in ('missing-source-fields','ambiguous-source-fields'):
        x=copy.deepcopy(rows)
        for event in x:
            if event['kind']=='binding-source':
                if name=='missing-source-fields':event['fields']=[]
                else:event['fields']+=copy.deepcopy(event['fields'])
        result=infer_execution(plan,x);assert result['answers'] and all(not a['known'] for a in result['answers']);faults[name]='unknown'
    legacy=load(root/'legacy-offline-frozen/results.json');assert legacy['all_passed'] and legacy['states']=={'known_correct':213,'unknown':88}
    semantics=load(root/'semantics-03/results.json');assert semantics['all_passed'] and len(semantics['faults'])==16
    for directory in ('legacy-collection-frozen','legacy-binding-frozen','legacy-lifecycle-frozen'):assert load(root/directory/'results.json')['all_passed']
    totals={}
    for scope in ('pilot-frozen','guards-frozen'):
        totals[scope]={mode:{k:sum(r[k] for r in records if r['scope']==scope and r['mode']==mode) for k in ('requests','targets','known','exact','unknown','tp','fp','fn','N/A_requests')} for mode in ('full','selective')}
    result={'all_passed':True,'algorithm_commit':freeze['commit'],'frozen_source_files':len(freeze['sources']),'original_jar_count':len(freeze['jars']),
            'new_kernel_original_queries':4,'totals':totals,'paired_inputs':matched,'real_capture_faults':faults,'standalone_semantics':semantics,
            'legacy_offline':legacy,'old_431_report_unchanged':True,'unexamined_candidates':29,'performance_measured':False,
            'overall_382_of_431_acceptance_passed':False,'whole_431_new_runtime_validation':False,
            'limitations':['Only explicit execution_kernel opt-in queries use the new root interpreter.','Opaque general calls remain a conservative barrier; save/async/arrays/lambda/Date not implemented.','No new unseen-query coverage; all four families were previously exposed.','Selective retains all modeled root calls and relevant writes; no new cost-reduction claim.','Legacy213 correctness is an offline replay of original captures, complemented by new-Agent controlled semantics; not213 fresh deployments.']}
    save(out/'audit.json',result);save(out/'raw-sha256.json',manifests);save(out/'deployments.json',records)
    save(HERE/'execution-kernel-pilot-results-20261020.json',result)
    print(json.dumps(totals,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',required=True,type=Path);p.add_argument('--out',required=True,type=Path);a=p.parse_args();audit(a.root.resolve(),a.out.resolve())
