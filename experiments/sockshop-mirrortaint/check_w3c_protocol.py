#!/usr/bin/env python3
"""Run protocol and async boundary checks against a built observer on this host."""
import argparse
from pathlib import Path
import subprocess
from zipfile import ZipFile
from run_planned_service import HERE, save, sha
from experiment_environment import java8_target


def check(build,out):
    dest=out/'protocol-checks';dest.mkdir(parents=True,exist_ok=False);libs=[]
    with ZipFile(build/'orders/original.jar') as jar:
        for name in jar.namelist():
            if name.startswith(('BOOT-INF/lib/spring-web-','BOOT-INF/lib/spring-core-')):
                path=dest/Path(name).name;path.write_bytes(jar.read(name));libs.append(path)
    if len(libs)!=2:raise ValueError('Expected original Spring web/core dependencies')
    cp=':'.join(map(str,[dest,build/'distributed-observer.jar',*libs]));results=[]
    commands=[['javac',*java8_target()[1],'-cp',cp,'-d',str(dest),*[str(HERE/name) for name in ('W3CTraceContextCheck.java','W3CAsyncContextCheck.java')]]]
    commands += [['java','-cp',cp,name] for name in ('W3CTraceContextCheck','W3CAsyncContextCheck')]
    for command in commands:
        result=subprocess.run(command,capture_output=True,text=True,timeout=45)
        results.append({'command':command,'stdout':result.stdout,'stderr':result.stderr,'returncode':result.returncode})
        if result.returncode:raise RuntimeError(result.stdout+result.stderr)
        print(result.stdout,end='')
    save(out/'protocol-checks.json',{'all_passed':True,'results':results,'dependencies':{str(p):sha(p) for p in libs}})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--build',type=Path,required=True);parser.add_argument('--out',type=Path,required=True);args=parser.parse_args()
    check(args.build.resolve(),args.out.resolve())
