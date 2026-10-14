#!/usr/bin/env python3
"""Build the full-trace all-query driver against the unchanged author JAR.

Only decoding/qualification glue and the optional sequential-stream model are
compiled. Never shadow DynTransferGraph or author search classes.
"""
import argparse
import hashlib
from pathlib import Path
import subprocess
from zipfile import ZipFile
import flowdist_preflight as tool


def build(repo,out):
    tool.verify_repository(repo);out.mkdir(parents=True,exist_ok=False);deps=out/'compile-deps'
    with ZipFile(repo/'tool/soot-trunk.jar') as archive:
        for name in archive.namelist():
            if name.endswith('.class') and not name.startswith('/'):
                target=deps/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(archive.read(name))
    sources=[Path(__file__).with_name('FlowDistFieldDecision.java'),Path(__file__).parent/'flowdist/FlowDistStreamModel.java']
    classes=out/'launcher';classes.mkdir()
    command=['javac','--release','8','-cp',str(deps)+':'+str(repo/'tool/FLOWDIST.jar'),'-d',str(classes),*map(str,sources)]
    compiled=subprocess.run(command,capture_output=True,text=True,timeout=30)
    (out/'compile.log').write_text(compiled.stdout+compiled.stderr)
    if compiled.returncode:raise ValueError('Full-trace launcher compilation failed')
    if (classes/'disttaint/DynTransferGraph.class').exists():raise ValueError('Refusing engine override')
    tool.save(out/'manifest.json',{'kind':'flowdist-author-all-query-full-trace-driver','upstream_commit':tool.COMMIT,
        'upstream_engine_sha256':tool.TOOL_HASHES['FLOWDIST.jar'],'engine_class_overridden':False,
        'builder':'Original DynTransferGraph.buildGraph(DynTransferGraph,boolean)',
        'optional_library_model':'Direct sequential List.stream/mapToDouble/sum callback return summary',
        'source_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
        'class_sha256':{str(p.relative_to(classes)):hashlib.sha256(p.read_bytes()).hexdigest() for p in classes.rglob('*.class')},
        'compile_command':command})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for flag in ('repo','out'):parser.add_argument('--'+flag,type=Path,required=True)
    a=parser.parse_args();build(a.repo.resolve(),a.out.resolve())
