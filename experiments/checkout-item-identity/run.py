#!/usr/bin/env python3
"""Build or collect one-call checkout Item/Cost identity experiments; archive failures too."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import traceback

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import observer
from hybrid_model import require
from string_capture import collect

COMMIT='474d0f2eb73d97525234995a40d7781b7923a07d'
CASES=('empty','one','equal-eight','equal-thirty-two','aliased-input',
       'product-error-second','currency-error-second')


def save(path,doc):path.write_text(json.dumps(doc,indent=2)+'\n')


def build_target(args,out):
    require(args.go,'Go 1.25.4 must be on PATH or supplied with --go')
    env=dict(os.environ,GOOS='linux',GOARCH='amd64',CGO_ENABLED='0',GOTOOLCHAIN='local',
             GOTELEMETRY='off',GOFLAGS='',GOEXPERIMENT='',GOAMD64='v1',GO111MODULE='on')
    source=(args.checkout or ROOT/'artifacts/online-boutique-v0.10.4').resolve()
    module=source/'src/checkoutservice'
    def command(argv,cwd=module,extra=None,input=None):
        p=subprocess.run(list(map(str,argv)),cwd=cwd,env=env if extra is None else dict(env,**extra),
                         input=input,text=True,capture_output=True,timeout=600)
        with (out/'commands.jsonl').open('a') as f:
            f.write(json.dumps(dict(command=list(map(str,argv)),returncode=p.returncode,stdout=p.stdout,stderr=p.stderr))+'\n')
        if p.returncode:
            print(f'Command failed ({p.returncode}): {list(map(str,argv))}',file=sys.stderr,flush=True)
            if p.stdout:print(p.stdout,file=sys.stderr,end='' if p.stdout.endswith('\n') else '\n',flush=True)
            if p.stderr:print(p.stderr,file=sys.stderr,end='' if p.stderr.endswith('\n') else '\n',flush=True)
            print('Full command log: '+str(out/'commands.jsonl'),file=sys.stderr,flush=True)
        p.check_returncode();return p.stdout
    if not source.exists():
        source.parent.mkdir(parents=True,exist_ok=True)
        command(['git','clone','--depth','1','--branch','v0.10.4',
                 'https://github.com/GoogleCloudPlatform/microservices-demo.git',source],cwd=ROOT)
    require(command(['git','rev-parse','HEAD'],source).strip()==COMMIT,'Wrong upstream revision')
    require(command(['git','status','--porcelain','--untracked-files=no'],source).strip()=='','Upstream tracked changes')
    # Reject extra Go sources: an unrelated test/TestMain can invalidate the one-call contract.
    require(not command(['git','ls-files','--others','--exclude-standard','--','*.go'],module).strip(), 'Untracked Go files in upstream module')
    require(command([args.go,'env','GOVERSION']).strip()=='go1.25.4','Use Go 1.25.4')
    before=hashlib.sha256((module/'main.go').read_bytes()).hexdigest()
    fixture=module/'tracefusion_identity_test.go'
    with fixture.open('xb') as f:f.write((HERE/'identity_test.go').read_bytes())
    binary=out/'checkout-identity'
    try:
        print('Building original checkout function with independent test fixture',flush=True)
        command([args.go,'test','-c','-mod=readonly','-buildvcs=false','-o',binary,'.'])
    finally:fixture.unlink()
    require(before==hashlib.sha256((module/'main.go').read_bytes()).hexdigest(),'Business source changed')
    require(command(['git','status','--porcelain','--untracked-files=no'],source).strip()=='','Upstream tracked files changed')
    plan=observer.plan_binary(binary,lambda argv:command([args.go,*argv]),
                              HERE.parent/'checkout-origin-audit/inspect_layout.go',out)
    save(out/'plan.json',plan)
    print(f'Planned {len(plan["sites"])} probe sites; ELF bytes and DWARF checked',flush=True)
    for strategy in ('boundaries','current','dense_stores'):
        selected=observer.strategy_plan(plan,strategy)
        save(out/('plan-'+strategy+'.json'),selected)
        if 'selection' in selected:save(out/('selection-'+strategy+'.json'),selected['selection'])
        print(f'{strategy}: {len(selected["sites"])} probe sites',flush=True)
    return binary,plan,before,command


def execute(args,out):
    binary,plan,before,command=build_target(args,out)
    if args.mode=='compare':
        from benchmark import compare
        compare(args,out,binary,plan,command,CASES)
        return
    rows=[]
    for case in CASES:
        folder=out/case;folder.mkdir()
        truth=folder/'truth.json'
        extra=dict(TRACEFUSION_IDENTITY_CASE=case,TRACEFUSION_IDENTITY_TRUTH=str(truth))
        if args.mode=='build':
            command([binary],extra=extra,input='x')
            doc=json.loads(truth.read_text())
            rows.append(dict(case=case,native_fixture_passed=True,outputs=len(doc['outputs']),
                             conversions=len(doc['conversions'])))
        else:
            print('Collecting '+case,flush=True)
            previous={k:os.environ.get(k) for k in extra}
            os.environ.update(extra)
            try:captured=collect(binary,plan,b'x',folder/'capture',transport=observer,timeout_seconds=60)
            finally:
                for k,v in previous.items():
                    if v is None:os.environ.pop(k,None)
                    else:os.environ[k]=v
            # Observer consumes only binary plan and kernel events. Truth is opened afterward.
            inference=observer.infer(plan,captured)
            save(folder/'inference.json',inference)
            rows.append(observer.evaluate(inference,json.loads(truth.read_text())))
    report=dict(mode=args.mode,schema_version=plan['schema_version'],cases=rows,all_passed=True,bpf_executed=args.mode=='run',
                upstream_commit=COMMIT,main_go_sha256=before,tracked_source_unchanged=True,
                scope=plan['scope'],deployment='test executable; local mock gRPC peers; not full shop or production binary')
    save(out/'summary.json',report)
    print(json.dumps(report),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('build','run','compare'))
    parser.add_argument('--checkout',type=Path)
    parser.add_argument('--go',default=os.environ.get('TRACEFUSION_GO') or shutil.which('go'))
    parser.add_argument('--output',type=Path)
    parser.add_argument('--repeats',type=int,default=5,help='Measured comparison rounds (default 5)')
    parser.add_argument('--warmups',type=int,default=1,help='Unmeasured fresh-process rounds (default 1)')
    parser.add_argument('--seed',type=int,default=20261009,help='Reproducible within-round strategy shuffle')
    args=parser.parse_args()
    require(args.repeats>=3 and args.warmups>=0,'Use at least 3 measured rounds and nonnegative warmups')
    out=(args.output or ROOT/'artifacts'/('checkout-item-identity-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f'))).resolve()
    out.mkdir(parents=True,exist_ok=False)
    try:execute(args,out)
    except Exception:
        (out/'failure.txt').write_text(traceback.format_exc())
        raise
    finally:
        archive=shutil.make_archive(str(out),'zip',root_dir=out.parent,base_dir=out.name)
        print('Return this result archive: '+archive,flush=True)


if __name__=='__main__':main()
