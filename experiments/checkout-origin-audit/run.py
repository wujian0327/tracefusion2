#!/usr/bin/env python3
"""Audit unmodified Online Boutique checkout code; no BPF/provenance support claim."""
import argparse
from collections import Counter
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from go_byte_adapter import assembly_rows,decode_function
from hybrid_model import require

COMMIT='474d0f2eb73d97525234995a40d7781b7923a07d'
FUNCTIONS=('prepOrderItems','convertCurrency','PlaceOrder')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkout',type=Path,required=True,help='Clean upstream checkout fixed at Online Boutique v0.10.4')
    parser.add_argument('--go',default=os.environ.get('TRACEFUSION_GO') or shutil.which('go'))
    parser.add_argument('--output',type=Path)
    args=parser.parse_args();require(args.go,'Go 1.25.4 required')
    source=args.checkout.resolve();module=source/'src/checkoutservice'
    out=(args.output or ROOT/'artifacts'/('checkout-origin-audit-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f'))).resolve()
    out.mkdir(parents=True,exist_ok=False)
    env=dict(os.environ,GOOS='linux',GOARCH='amd64',CGO_ENABLED='0',GOTOOLCHAIN='local',
        GOTELEMETRY='off',GOFLAGS='',GOEXPERIMENT='',GOAMD64='v1',GO111MODULE='on')
    def command(argv,cwd=module,timeout=600):
        p=subprocess.run(argv,cwd=cwd,env=env,text=True,capture_output=True,timeout=timeout)
        with (out/'commands.jsonl').open('a') as f:
            f.write(json.dumps(dict(command=list(map(str,argv)),returncode=p.returncode,stdout=p.stdout,stderr=p.stderr))+'\n')
        p.check_returncode();return p.stdout
    require(command(['git','rev-parse','HEAD'],source).strip()==COMMIT,'Wrong upstream revision')
    require(command(['git','status','--porcelain','--untracked-files=no'],source).strip()=='','Tracked upstream files changed')
    require(command([args.go,'env','GOVERSION']).strip()=='go1.25.4','Use pinned Go 1.25.4')
    before=hashlib.sha256((module/'main.go').read_bytes()).hexdigest()
    builds={}
    for mode,flags in [('default',[]),('noinline',['-gcflags=all=-l'])]:
        binary=out/('checkout-'+mode)
        command([args.go,'build','-mod=readonly','-buildvcs=false',*flags,'-o',str(binary),'.'])
        functions={}
        for name in FUNCTIONS:
            expression=r'^main\.\(\*checkoutService\)\.'+re.escape(name)+'$'
            asm=command([args.go,'tool','objdump','-s',expression,str(binary)])
            (out/(mode+'-'+name+'.asm')).write_text(asm)
            rows=assembly_rows(asm);require(rows,'Missing target function '+name)
            calls=Counter(r['asm'].split(None,1)[1] for r in rows if r['asm'].startswith('CALL '))
            branches=sum(r['asm'].split()[0].startswith('J') for r in rows)
            try:decode_function(rows);support=dict(accepted=True)
            except ValueError as exc:support=dict(accepted=False,first_rejection=str(exc))
            functions[name]=dict(instructions=len(rows),static_calls=sum(calls.values()),
                jump_instructions=branches,call_targets=dict(calls),current_leaf_decoder=support)
        builds[mode]=dict(binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),functions=functions)
    test=module/'tracefusion_audit_test.go'
    # Exclusive creation prevents overwriting a user's existing audit file.
    with test.open('xb') as f:f.write((HERE/'provenance_audit_test.go').read_bytes())
    try:
        env['TRACEFUSION_AUDIT_REPORT']=str(out/'runtime.json')
        command([args.go,'test','-mod=readonly','-run','^TestTraceFusionRealCheckoutAudit$','-count=1','-v','.'])
    finally:
        test.unlink()
    require(before==hashlib.sha256((module/'main.go').read_bytes()).hexdigest(),'Application source changed')
    require(command(['git','status','--porcelain','--untracked-files=no'],source).strip()=='','Tracked files changed')
    runtime=json.loads((out/'runtime.json').read_text());require(runtime['all_passed'],'Runtime audit failed')
    report=dict(upstream='https://github.com/GoogleCloudPlatform/microservices-demo',tag='v0.10.4',commit=COMMIT,
        go='go1.25.4',main_go_sha256=before,tracked_source_unchanged=True,builds=builds,runtime=runtime,
        tracefusion_bpf_executed=False,published_baseline_systems_executed=False,
        interpretation='Runtime boundary identity is sufficient in this controlled case; no new algorithm or universal minimum has been demonstrated')
    (out/'audit.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Audit result: '+str(out/'audit.json'))


if __name__=='__main__':main()
