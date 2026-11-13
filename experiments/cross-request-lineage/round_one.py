#!/usr/bin/env python3
"""Complete repeatable round: primary first, separate diagnostics, raw verification."""
import argparse
import datetime
from pathlib import Path
import subprocess
import sys
import uuid

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path)
    p.add_argument('--repeats',type=int,default=2)
    p.add_argument('--java',default=str(ROOT/'artifacts/galette-static-baselines-20261111/runtime-base/java-8-openjdk-amd64/bin/java'))
    p.add_argument('--primary-only',action='store_true')
    a=p.parse_args()
    if a.repeats<1:p.error('repeats must be positive')
    out=(a.out or ROOT/'artifacts'/('cross-request-round1-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8])).resolve()
    out.mkdir(parents=True,exist_ok=False)
    for script,name in [('run.py','primary')]+([] if a.primary_only else [('diagnose.py','diagnostics')]):
        subprocess.run([sys.executable,str(HERE/script),'--out',str(out/name),'--java',a.java,'--repeats',str(a.repeats)],check=True,cwd=ROOT)
    subprocess.run([sys.executable,str(HERE/'verify.py'),'--run',str(out/'primary'),'--out',str(out/'verification')],check=True,cwd=ROOT)
    if not a.primary_only:subprocess.run([sys.executable,str(HERE/'check_diagnostics.py'),'--run',str(out/'diagnostics'),'--out',str(out/'diagnostic-verification')],check=True,cwd=ROOT)
    print('Primary report: '+str(out/'primary/REPORT.md'),flush=True)
    if not a.primary_only:print('Separate diagnostics: '+str(out/'diagnostics/score.json'),flush=True)


if __name__=='__main__':main()
