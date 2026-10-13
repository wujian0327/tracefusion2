#!/usr/bin/env python3
"""Independent JVM frame repair, preserving generated instructions and maps."""
import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess

import flowdist_preflight as tool


def run(repo, static, out):
    tool.verify_repository(repo)
    out.mkdir(parents=True, exist_ok=False)
    work = out / 'work'; work.mkdir()
    for name in ('classes', 'lib', 'NormalizedBranches'):
        shutil.copytree(static / 'work' / name, work / name)
    source = Path(__file__).with_name('FlowDistFrames.java')
    asm = source.parents[2] / 'artifacts/java-collection-deps/asm-9.7.1.jar'
    if hashlib.sha256(asm.read_bytes()).hexdigest() != '8cadd43ac5eb6d09de05faecca38b917a040bb9139c7edeb4cc81c740b713281':
        raise ValueError('ASM digest mismatch')
    shutil.copyfile(asm, work / 'asm.jar')
    launcher = work / 'launcher'; launcher.mkdir()
    subprocess.run(['javac','--release','8','-cp',str(asm),'-d',str(launcher),str(source)],
                   check=True,capture_output=True,timeout=30)
    cp = '/work/launcher:/work/asm.jar:/work/NormalizedBranches:/work/classes:/flowdist/tool/*'
    cp += ''.join(':/work/lib/' + p.name for p in sorted((work / 'lib').glob('*.jar')))
    tool.execute(repo,out,'verifier-frames',['-Xmx1g','-ea','-cp',cp,'FlowDistFrames',
        '/work/NormalizedBranches','/work/ReframedBranches'])
    import json
    manifest=json.loads((static/'manifest.json').read_text())
    manifest.update(verifier_frames_recomputed=True,verifier_frame_java_version=8,
        frame_source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),source_static_artifact=str(static))
    tool.save(out/'manifest.json',manifest)
    shutil.copyfile(static/'service-branches-stage.json',out/'service-branches-stage.json')


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('repo','static','out'):p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args();run(a.repo.resolve(),a.static.resolve(),a.out.resolve())
