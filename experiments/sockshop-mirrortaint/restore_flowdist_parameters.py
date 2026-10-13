#!/usr/bin/env python3
"""Restore Spring-visible original parameter names, without changing instructions."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from zipfile import ZipFile
from flowdist_preflight import save


def restore(static, original, out):
    metadata=json.loads((static/'manifest.json').read_text())
    if hashlib.sha256(original.read_bytes()).hexdigest()!=metadata['shipping_jar_sha256']:
        raise ValueError('Original JAR mismatch')
    out.mkdir(parents=True,exist_ok=False)
    work=out/'work';work.mkdir()
    for name in ('classes','lib','NormalizedBranches'):
        shutil.copytree(static/'work'/name,work/name)
    inputs=work/'original-parameter-classes';inputs.mkdir()
    with ZipFile(original) as archive:
        for name in archive.namelist():
            if name.startswith('BOOT-INF/classes/') and name.endswith('.class'):
                file=inputs/name.removeprefix('BOOT-INF/classes/');file.parent.mkdir(parents=True,exist_ok=True)
                file.write_bytes(archive.read(name))
    here=Path(__file__).parent;deps=here.parents[1]/'artifacts/java-collection-deps'
    jars=[deps/'asm-9.7.1.jar',deps/'asm-tree-9.7.1.jar']
    expected=['8cadd43ac5eb6d09de05faecca38b917a040bb9139c7edeb4cc81c740b713281','9929881f59eb6b840e86d54570c77b59ce721d104e6dfd7a40978991c2d3b41f']
    if any(hashlib.sha256(p.read_bytes()).hexdigest()!=sha for p,sha in zip(jars,expected)):
        raise ValueError('ASM digest mismatch')
    classes=work/'parameter-launcher';classes.mkdir()
    source=here/'FlowDistParameterNames.java'
    cp=':'.join(map(str,jars))
    subprocess.run(['javac','--release','8','-cp',cp,'-d',str(classes),str(source)],check=True,capture_output=True,timeout=30)
    input=static/'work'/('ReframedBranches' if metadata.get('verifier_frames_recomputed') else 'NormalizedBranches')
    command=['java','-cp',str(classes)+':'+cp,'FlowDistParameterNames',str(inputs),str(input),str(work/'ReframedBranches')]
    result=subprocess.run(command,capture_output=True,text=True,timeout=30)
    (out/'parameter-restoration.log').write_text(result.stdout+result.stderr)
    if result.returncode:raise ValueError('Parameter restoration failed: '+result.stderr[-1800:])
    metadata.update(parameter_names_restored=True,parameter_source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                    parameter_restoration_command=command,parameter_restore_source_artifact=str(static),verifier_frames_recomputed=True)
    save(out/'manifest.json',metadata)
    shutil.copyfile(static/'service-branches-stage.json',out/'service-branches-stage.json')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for flag in ('static','original','out'):parser.add_argument('--'+flag,type=Path,required=True)
    args=parser.parse_args();restore(args.static.resolve(),args.original.resolve(),args.out.resolve())
