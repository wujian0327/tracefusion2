#!/usr/bin/env python3
"""Separate DUA override for unsupported Java 8 reference-valued invokedynamic.

Original tools remain intact. Explicitly extends the reference-type model; does
not model lambda captures/callbacks or qualify accuracy.
"""
import argparse
import hashlib
from pathlib import Path
import subprocess
import shutil
from zipfile import ZipFile, ZIP_DEFLATED

import flowdist_preflight as tool


def build(repo, out):
    tool.verify_repository(repo)
    out.mkdir(parents=True, exist_ok=False)
    here = Path(__file__).parent
    cache = here.parents[1] / 'artifacts/java-collection-deps'
    expected = {'asm':'8cadd43ac5eb6d09de05faecca38b917a040bb9139c7edeb4cc81c740b713281',
                'asm-tree':'9929881f59eb6b840e86d54570c77b59ce721d104e6dfd7a40978991c2d3b41f'}
    jars = [cache / (name + '-9.7.1.jar') for name in expected]
    for name, jar in zip(expected, jars):
        if hashlib.sha256(jar.read_bytes()).hexdigest() != expected[name]: raise ValueError('ASM digest mismatch')
    with ZipFile(repo / 'tool/DUA1.jar') as archive: original = archive.read('dua/util/Util.class')
    if hashlib.sha256(original).hexdigest() != '32f22cc649d22089e183d04e4d7c526ae9df98299f0175d6162530ca8c17f917':
        raise ValueError('Unexpected original reference-type helper')
    (out / 'Util.original.class').write_bytes(original)
    classes = out / 'classes'; classes.mkdir()
    patcher = here / 'FlowDistLambdaUtilPatch.java'
    subprocess.run(['javac','--release','8','-cp',':'.join(map(str,jars)),'-d',str(classes),str(patcher)], check=True, capture_output=True, timeout=30)
    target = classes / 'dua/util/Util.class'; target.parent.mkdir(parents=True)
    subprocess.run(['java','-cp',':'.join(map(str,[classes,*jars])),'FlowDistLambdaUtilPatch',str(out/'Util.original.class'),str(target)], check=True, capture_output=True, timeout=30)
    with ZipFile(repo/'tool/DUA1.jar') as archive:
        original_object=archive.read('dua/method/CFGDefUses$ObjVariable.class')
    object_input=out/'ObjVariable.original.class';object_input.write_bytes(original_object)
    object_target=classes/'dua/method/CFGDefUses$ObjVariable.class';object_target.parent.mkdir(parents=True)
    subprocess.run(['java','-cp',':'.join(map(str,[classes,*jars])),'FlowDistLambdaUtilPatch',str(object_input),str(object_target)],check=True,capture_output=True,timeout=30)
    deps = out / 'compile-deps'
    with ZipFile(repo / 'tool/soot-trunk.jar') as archive:
        for name in archive.namelist():
            if name.endswith('.class') and not name.startswith('/'):
                file=deps/name;file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(archive.read(name))
    helper = here / 'flowdist/FlowDistDynamicTargets.java'
    subprocess.run(['javac','--release','8','-cp',str(deps)+':'+str(repo/'tool/DUA1.jar'),'-d',str(classes),str(helper)], check=True,capture_output=True,timeout=30)
    jar = out / 'flowdist-lambda-adapter.jar'
    with ZipFile(jar,'w',ZIP_DEFLATED) as archive:
        for name in ('dua/util/Util.class','dua/util/FlowDistDynamicTargets.class','dua/method/CFGDefUses$ObjVariable.class'):
            archive.write(classes/name,name)
    test=here/'flowdist/FlowDistLambdaModelTest.java'
    work=out/'work';work.mkdir()
    tests=work/'test-classes';tests.mkdir()
    subprocess.run(['javac','--release','8','-cp',':'.join(map(str,[jar,deps,repo/'tool/DUA1.jar'])),
        '-d',str(tests),str(test)],check=True,capture_output=True,timeout=30)
    shutil.copyfile(jar,work/'adapter.jar')
    tool.execute(repo,out,'lambda-model-test',['-Xmx512m','-ea','-cp',
        '/work/test-classes:/work/adapter.jar:/flowdist/tool/*','FlowDistLambdaModelTest'],timeout=30)
    tool.save(out/'manifest.json',{'kind':'flowdist-invokedynamic-reference-model-extension',
        'upstream_commit':tool.COMMIT,'jar_sha256':hashlib.sha256(jar.read_bytes()).hexdigest(),
        'original_util_sha256':hashlib.sha256(original).hexdigest(),
        'adapted_util_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
        'original_object_variable_sha256':hashlib.sha256(original_object).hexdigest(),
        'adapted_object_variable_sha256':hashlib.sha256(object_target.read_bytes()).hexdigest(),
        'source_sha256':{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in (patcher,helper,test)},
        'java8_model_checks_passed':True,
        'original_engine_jars_modified':False,'assertions_disabled':False,
        'reference_model_extended':True,'lambda_capture_and_callback_dependencies_modeled':False,
        'unknown_lambda_alias_model':'type-compatible may-alias, without an empty points-to approximation',
        'lambda_must_equal_model':'expression identity, matching original allocation/Local rule',
        'accuracy_eligible':False,'performance_eligible':False})


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();build(a.repo.resolve(),a.out.resolve())
