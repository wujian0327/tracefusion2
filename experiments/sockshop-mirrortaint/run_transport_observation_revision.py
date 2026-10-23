#!/usr/bin/env python3
"""Bounded transport observation optimization, preserving execution semantics."""
import argparse,copy,json,subprocess,sys,shutil
from pathlib import Path
from zipfile import ZipFile
from run_planned_service import ROOT,HERE,load,save,sha
from plan_capability_policy import choose,specialize_transport
import build_distributed_plans as builder
import run_frozen_capability_acceptance as driver
import run_quota_capability_acceptance as quota

PARENT=ROOT/'artifacts/jackson-isolation-20261022/candidate-v2/final-capability'


def prepare(root):
    assert not(root/'algorithm-freeze.json').exists();base=root/'frozen-base'
    old=load(PARENT/'frozen-base/build.json');builder.build(base,{k:v['query_config']for k,v in old['inputs'].items()})
    manifest=load(base/'build.json');sources=manifest['sources'];commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    plans=root/'frozen-plans';plans.mkdir();results=[]
    for q in driver.QUERIES:
        p,policy=choose(load(base/q['role']/'model.json'),q);previous=load(PARENT/'frozen-plans'/(q['id']+'.json'));without=copy.deepcopy(p);without.pop('transport_evidence_policy',None)
        assert without==previous,('Unexpected execution/semantic plan change',q['id'])
        save(plans/(q['id']+'.json'),p);results.append({'query':q,'status':'accepted','policy':policy,'plan_sha256':sha(plans/(q['id']+'.json')),'execution_plan_unchanged':True})
    save(plans/'planning.json',results)
    for name,h in sources.items():
        p=Path(name);assert sha(p)==h;d=root/'source-snapshot'/p.relative_to(ROOT);d.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,d)
    oldfreeze=load(PARENT/'algorithm-freeze.json');freeze={**oldfreeze,'commit':commit,'commit_at_build':commit,'algorithm_commit':commit,'base_build':str(base),'sources':sources,'planning_sha256':sha(plans/'planning.json'),'original_jars':{k:v['original_jar_sha256']for k,v in manifest['inputs'].items()},'parent_algorithm':'76d2050','scope':'Observation only; identical execution plans and original JARs. 29 candidates already evaluated separately at parent version; no new unseen-query claim.'}
    save(root/'algorithm-freeze.json',freeze);(root/'drivers').mkdir()
    for name in ('run_transport_observation_revision.py','run_quota_capability_acceptance.py','run_frozen_capability_acceptance.py','run_cart_reread_baseline_pair.py'):
        shutil.copyfile(HERE/name,root/'drivers'/('cart-pair-library-driver-at-launch.py'if name=='run_cart_reread_baseline_pair.py'else name))
    save(root/'protocol-before-business.json',{'algorithm':commit,'development_queries':62,'fixed_instances':431,'required_known_correct':428,'required_unknown':3,'modes':['full','selective'],'acceptance':'Fresh new-Agent captures, align every case/path and independently score physical origins. Preserve historical368/213 masks. No data-dependent retry or fallback.','semantics_changes':False,'observation_arms':['full_legacy','full_clean','selective_clean_without_projection','selective_clean_with_projection'],'full':'Shared direction-only proof cleanup; full internal and response-field evidence, same required validation rules.','selective':'Same global proof cleanup as full; project persisted response fields after complete pre/post snapshots and target serializer checks. All source, call, branch, constructor, effect and exception evidence retained.','format_compression':False,'instruction_or_call_slicing':False,'cost':'Only after capability and guards pass. Separate shared engineering cleanup from query specialization. Fixed existing load/JVM/resources; no old cost values in new table.','heldout29_reference':'e37d0ae, parent76d2050 first results; already exposed, do not reuse as unseen validation.'})
    print({'frozen':commit,'plans':len(results)},flush=True)


def controls(root):
    # Direct semantic fixtures also exercise the shared transport guard,
    # including legacy nested-return/custom-serializer refusal controls.
    original=builder.plan_response
    def wrapped(*args,**kwargs):return specialize_transport(original(*args,**kwargs))
    builder.plan_response=wrapped
    out=root/'controls';out.mkdir();results={}
    from experiment_environment import java8_target
    cp=str(root/'prototype-build-01/distributed-observer.jar')
    classes=out/'policy-classes';classes.mkdir()
    subprocess.run(['javac',*java8_target()[1],'-cp',cp,'-d',str(classes),str(HERE/'TransportPolicyProbe.java')],check=True)
    p=subprocess.run(['java','-cp',str(classes)+':'+cp,'TransportPolicyProbe'],capture_output=True,text=True,check=True);(out/'policy.log').write_text(p.stdout+p.stderr);assert 'POLICY_GUARDS_PASSED=15'in p.stdout;results['policy_guards']=15
    import run_binding_semantics as binding
    binding.run(out/'nested-binding',root/'prototype-build-01',only='nested');results['target_serializer_and_binding']=True
    import run_kernel_contract_semantics as kernel
    kernel.run(out/'kernel');results['kernel_contracts']=True
    save(out/'results.json',{'all_passed':True,'checks':results})


def guards(root):
    original=builder.plan_response
    def wrapped(*args,**kwargs):return specialize_transport(original(*args,**kwargs))
    builder.plan_response=wrapped
    out=root/'guard-controls';out.mkdir();libs=out/'original-order-libs';libs.mkdir()
    with ZipFile(root/'prototype-build-01/orders/original.jar')as z:
        for name in z.namelist():
            if name.startswith('BOOT-INF/lib/')and name.endswith('.jar'):(libs/Path(name).name).write_bytes(z.read(name))
    import run_date_effect_semantics as date
    import run_received_mutation_semantics as received
    import run_collection_controls as collection
    import run_request_async_semantics as request
    date.run(out/'date',libs,root/'prototype-build-01')
    received.run(out/'received')
    collection.run(out/'legacy')
    request.run(out/'request',libs)
    for name,group in [('date-controls','date'),('received-controls','received'),('legacy-collection-controls','legacy')]:
        (root/name).symlink_to(out/group,target_is_directory=True)
    save(out/'results.json',{'all_passed':True,'groups':['date','received','legacy','request'],'note':'Actual new Agent and transport policy enabled; original typed bytecode and independent semantic truth preserved.'})


def request_guard(root):
    original=builder.plan_response
    def wrapped(*args,**kwargs):return specialize_transport(original(*args,**kwargs))
    builder.plan_response=wrapped
    out=root/'guard-controls'
    for group in ('date','received','legacy'):assert load(out/group/'results.json')['all_passed']
    import run_request_async_semantics as request
    request.run(out/'request-raw-frame-corrected',out/'original-order-libs')
    for name,group in [('date-controls','date'),('received-controls','received'),('legacy-collection-controls','legacy')]:
        (root/name).symlink_to(out/group,target_is_directory=True)
    save(out/'results.json',{'all_passed':True,'groups':['date','received','legacy','request-raw-frame-corrected'],'first_request_failure_retained':str(out/'request'),'evaluation_only_correction':'Old RequestAsync truth dropped the actual HTTP read frame; use raw read coordinate as in the existing frozen62 oracle. No dependency propagation copied into truth.'})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--stage',choices=('prepare','controls','guards','request-guard','worker'),required=True);p.add_argument('--worker',choices=('orders','reads','route','travel','cart','pair'));a=p.parse_args();root=a.root.resolve()
    if a.stage=='prepare':prepare(root)
    elif a.stage=='controls':controls(root)
    elif a.stage=='guards':guards(root)
    elif a.stage=='request-guard':request_guard(root)
    else:quota.worker(root,a.worker)
