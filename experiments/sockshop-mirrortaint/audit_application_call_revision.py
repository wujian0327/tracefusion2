#!/usr/bin/env python3
"""Audit final call-stage code and original captures without rerunning business."""
import argparse,copy,json
from pathlib import Path
from zipfile import ZipFile
from run_planned_service import ROOT,HERE,load,save,sha
from plan_response_binding import plan_response
from infer_execution_kernel import infer_execution
from infer_distributed_fields import Reconstruction
from analysis_status import AnalysisLimit,failure_status
import run_execution_kernel_pilot as pilot


def class_hashes(jar):
    import hashlib
    with ZipFile(jar) as z:return {name:hashlib.sha256(z.read(name)).hexdigest() for name in z.namelist() if name.endswith('.class')}


def audit(root,out):
    out.mkdir(parents=True,exist_ok=False);freeze=load(root/'algorithm-freeze-final.json');base=root/'final-base-build'
    for file,digest in freeze['sources'].items():assert sha(Path(file))==digest,file
    assert sha(HERE/'execution-kernel-protocol-20261020.json')==freeze['reserved_protocol_sha256']
    assert len(load(HERE/'execution-kernel-protocol-20261020.json')['unexamined_candidates'])==29
    for role,digest in freeze['original_jars'].items():assert sha(base/role/'original.jar')==digest
    original_agent=class_hashes(root/'business-frozen-base-build/distributed-observer.jar');final_agent=class_hashes(base/'distributed-observer.jar');assert original_agent==final_agent
    proof=[];results=[];raw_hashes={}
    for d in sorted((root/'business-frozen').glob('*-trainticket-*')):
        q=load(d/'query.json');actual=load(d/'build'/q['role']/'plan.json');planned=plan_response(load(base/q['role']/'model.json'),q['entry'],q['target'],q['path'],execution_kernel=True,application_calls=True);assert planned==actual
        cap=d/'capture';raw=cap/q['role']/'events.jsonl';before=sha(raw);result=pilot.evaluate(cap,d/'build',q);assert result['exact']==result['targets'] and result['fp']==result['fn']==result['unknown']==0;assert sha(raw)==before;raw_hashes[str(raw.relative_to(ROOT))]=before
        results.append({k:v for k,v in result.items() if k!='answers'});proof.append({'capture':str(cap.relative_to(ROOT)),'plan_equal_to_final_generation':True,'plan_sha256':sha(d/'build'/q['role']/'plan.json'),'observer_classes_equal_to_final':True,'original_deployment_commit':'d06be34','offline_decoder_commit':freeze['commit']})
    assert len(results)==8
    totals={mode:{k:sum(x[k] for x in results if x['mode']==mode) for k in ('targets','exact','known','unknown','tp','fp','fn')} for mode in ('full','selective')}
    semantics=root/'semantics-source-schema-final';sem=load(semantics/'results.json');assert sem['all_passed']
    sem_plan=load(semantics/'build/fixture/plan.json');model=load(semantics/'build/fixture/model.json')
    new_plan=plan_response(model,sem_plan['entry'],sem_plan['target'],sem_plan['response_binding']['path'],execution_kernel=True,application_calls=True);assert new_plan==sem_plan
    assert class_hashes(semantics/'build/distributed-observer.jar')==final_agent
    extra={}
    for mode in ('full','selective'):
        cap=semantics/mode;raw=cap/'fixture/events.jsonl';rows=[json.loads(l) for l in raw.read_text().splitlines()];infer_execution(sem_plan,rows);raw_hashes[str(raw.relative_to(ROOT))]=sha(raw)
        low=copy.deepcopy(sem_plan);low['execution_kernel']['step_limit']=1
        try:infer_execution(low,rows)
        except AnalysisLimit as e:assert failure_status(e)=='analysis_limited';extra[mode+'-budget']='analysis_limited'
        else:raise AssertionError('Budget not classified')
        changed=copy.deepcopy(rows);enters=[r for r in changed if r['kind']=='enter'];enters[1]['frame']=enters[0]['frame']
        try:infer_execution(sem_plan,changed)
        except ValueError:extra[mode+'-duplicate-frame']='rejected'
        else:raise AssertionError('Duplicate invocation accepted')
    cart=load(root/'cart-final/results.json');assert cart['complete']
    for mode in ('full','selective'):
        d=root/'cart-final'/mode;cap=d/'capture';graph=Reconstruction(d/'build',cap,['carts']);report=load(d/'evaluation.json');assert report['known']==0 and report['unknown']==report['targets'] and report['targets']>0
        assert len(report['methods'])>=3
        raw_hashes[str((cap/'carts/events.jsonl').relative_to(ROOT))]=sha(cap/'carts/events.jsonl')
        config=load(d/'configuration-freeze.json');assert config['runtime_profile_sha256']==freeze['cart_runtime_config_sha256']
    refusal=load(root/'constructor-write-refusal.json');assert refusal['missing_constructor_write_permanently_refused']
    witness=root/'constructor-write-control';assert sha(witness/'events.jsonl')==refusal['raw_sha256']
    try:infer_execution(load(witness/'plan.json'),[json.loads(x) for x in (witness/'events.jsonl').read_text().splitlines()])
    except ValueError as e:assert 'constructor write' in str(e)
    else:raise AssertionError('Historical missing-write capture accepted')
    legacy=load(root/'legacy-offline-frozen/results.json');assert legacy['states']=={'known_correct':213,'unknown':88}
    for name in ('loop-semantics-frozen','legacy-lifecycle-frozen','legacy-binding-frozen','legacy-collection-frozen'):assert load(root/name/'results.json')['all_passed']
    summary={'all_passed':True,'algorithm_commit':freeze['commit'],'previous_algorithm_commit':freeze['predecessor'],'original_jars':len(freeze['original_jars']),
        'business_totals':totals,'business_capture_reuse':proof,'semantic_totals':{mode:{k:v for k,v in report.items() if k!='checks'} for mode,report in sem['modes'].items()},
        'extra_guards':extra,'cart_nested':cart,'constructor_write_failure_still_rejected':True,'legacy_offline':legacy,
        'remaining_baseline_gap_development_instances':109,'new_baseline_gaps_claimed_fixed':0,'remaining_reserved_candidates':29,
        'whole_62_full_selective_acceptance_run':False,'goal_382_of_431_met':False,'performance_measured':False,
        'scope':'Nonrecursive supported bytecode application calls; general libraries/save/async/arrays/lambda still outside this stage. Cart new generic path remains unknown; old read-forward profile retained.'}
    save(out/'audit.json',summary);save(out/'raw-sha256.json',raw_hashes);save(HERE/'application-call-results-20261020.json',summary)
    print(json.dumps({'business':totals,'cart':cart['results'],'core_commit':freeze['commit']},indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',required=True,type=Path);p.add_argument('--out',required=True,type=Path);a=p.parse_args();audit(a.root.resolve(),a.out.resolve())
