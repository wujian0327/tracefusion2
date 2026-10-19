#!/usr/bin/env python3
"""Historical original-JAR regression, with an explicitly isolated lab subnet."""
import argparse
from pathlib import Path
import run_distributed_paths as paths
from run_planned_service import save,sha,load
from zipfile import ZipFile
import hashlib


def reuse(out,build,previous,previous_build):
    def classes(jar):
        with ZipFile(jar) as z:return {n:hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist() if n.endswith('.class')}
    assert classes(build/'distributed-observer.jar')==classes(previous_build/'distributed-observer.jar')
    for role in load(build/'build.json')['inputs']:
        assert sha(build/role/'plan.json')==sha(previous_build/role/'plan.json'),role
    paths.freeze(out,build,191019,previous)
    for app in ('sockshop','trainticket'):
        dest=out/app;dest.mkdir()
        for file in (previous/app).iterdir():
            if file.name in ('field-results.json','inference-graph.json'):continue
            (dest/file.name).symlink_to(file.resolve(),target_is_directory=file.is_dir())
    save(out/'reuse.json',{'original_captures':str(previous),'original_build_sha256':sha(previous_build/'build.json'),
        'original_observer_sha256':sha(previous_build/'distributed-observer.jar'),'new_observer_sha256':sha(build/'distributed-observer.jar'),
        'all_compiled_observer_class_hashes_identical':True,'all_six_plan_hashes_identical':True,
        'scope':'Fresh revision development deployments replayed under final offline implementation; this is not another deployment or performance repeat.'})


def reuse_price(out,build,previous,previous_build):
    """Existing price plans already selected all 37 newly required call sites."""
    def classes(jar):
        with ZipFile(jar) as z:return {n:hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist() if n.endswith('.class')}
    assert classes(build/'distributed-observer.jar')==classes(previous_build/'distributed-observer.jar')
    ignored={'algorithm','collection_exception_calls'}
    for role in load(build/'build.json')['inputs']:
        old=load(previous_build/role/'plan.json');new=load(build/role/'plan.json')
        assert {k:v for k,v in old.items() if k not in ignored}=={k:v for k,v in new.items() if k not in ignored},role
        if new.get('collection_exception_calls'):assert set(new['collection_exception_calls'])<=set(old['collection_selected_calls'])
    out.mkdir(parents=True,exist_ok=False)
    for file in ('freeze.json','cases.json','database-fixtures.json'):(out/file).symlink_to(previous/file)
    for mode in ('full','selective'):
        dest=out/mode;dest.mkdir()
        for file in (previous/mode).iterdir():
            if file.name in ('predictions.json','field-graph.json','evaluation.json'):continue
            (dest/file.name).symlink_to(file.resolve(),target_is_directory=file.is_dir())
    save(out/'reuse.json',{'original_captures':str(previous),'actual_capture_build':str(previous_build),
        'actual_capture_build_sha256':sha(previous_build/'build.json'),'candidate_build_sha256':sha(build/'build.json'),
        'all_compiled_observer_class_hashes_identical':True,'effective_plans_identical':True,'all_required_exception_calls_already_observed':True,
        'ignored_plan_metadata':sorted(ignored),'scope':'Original plan bytes/hash retained for evidence verification; final offline algorithm replay, not new deployments.'})


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('application',choices=('sockshop','trainticket','reuse','reuse-price'));p.add_argument('--out',type=Path,required=True);p.add_argument('--build',type=Path,required=True);p.add_argument('--previous',type=Path);p.add_argument('--previous-build',type=Path);a=p.parse_args()
    if a.application=='reuse':
        reuse(a.out.resolve(),a.build.resolve(),a.previous.resolve(),a.previous_build.resolve());raise SystemExit(0)
    if a.application=='reuse-price':
        reuse_price(a.out.resolve(),a.build.resolve(),a.previous.resolve(),a.previous_build.resolve());raise SystemExit(0)
    original_pin=paths.pin_images
    def pin(spec,application):
        spec=original_pin(spec,application)
        if application=='trainticket':spec['networks']={'default':{'ipam':{'config':[{'subnet':'10.254.248.0/24'}]}}}
        return spec
    paths.pin_images=pin
    save(a.out/'regression-network.json',{'driver_sha256':sha(Path(__file__)),'train_subnet':'10.254.248.0/24','reason':'Isolate correctness deployment from other task-owned lab projects; no performance comparison.'})
    if a.application=='sockshop':paths.capture_sockshop(a.out.resolve(),a.build.resolve())
    else:paths.capture_train(a.out.resolve(),a.build.resolve())
