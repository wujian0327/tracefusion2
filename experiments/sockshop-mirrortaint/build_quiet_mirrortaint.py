#!/usr/bin/env python3
"""Build a separate disclosed diagnostic variant; leave original JAR/bundles intact."""
import argparse
from pathlib import Path
import subprocess
from zipfile import ZipFile,ZIP_DEFLATED
from experiment_environment import java8_target
from run_planned_service import HERE,save,load,sha
from run_query_planner import JARS
import mirrortaint_instances as mt


def build(out,agent,plans):
    mt.build(out,agent,plans);classes=out/'quiet-classes';classes.mkdir()
    source=HERE/'QuietDiagnosticAgent.java'
    cmd=['javac',*java8_target()[1],'-cp',':'.join(map(str,JARS)),'-d',str(classes),str(source)]
    r=subprocess.run(cmd,capture_output=True,text=True)
    (out/'quiet-compile.log').write_text(r.stdout+r.stderr)
    if r.returncode:raise ValueError('Quiet adapter compilation failed')
    jar=out/'quiet-diagnostics.jar'
    with ZipFile(jar,'w',ZIP_DEFLATED) as z:
        z.writestr('META-INF/MANIFEST.MF','Manifest-Version: 1.0\nPremain-Class: QuietDiagnosticAgent\n\n')
        z.write(classes/'QuietDiagnosticAgent.class','QuietDiagnosticAgent.class')
        for dep in JARS[:2]:
            with ZipFile(dep) as lib:
                for name in lib.namelist():
                    if name.startswith('org/objectweb/asm/') and name.endswith('.class'):z.writestr(name,lib.read(name))
    manifest=load(out/'build.json');manifest['diagnostics']='quiet-agent-info'
    manifest['source_sha256'][str(source)]=sha(source)
    manifest['source_sha256'][str(Path(__file__).resolve())]=sha(Path(__file__))
    manifest['files_sha256']['quiet-diagnostics.jar']=sha(jar)
    manifest['diagnostic_scope']='Disclosed runtime adapter replaces only 3 agent-info methods in pinned G.D; keeps error channels, native propagation, native adapted labels and class dumps. Argument construction remains. Not an upstream supported off switch or minimum-overhead configuration.'
    save(out/'build.json',manifest);mt.verify(out)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('out','agent','build'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();build(a.out.resolve(),a.agent.resolve(),a.build.resolve())
