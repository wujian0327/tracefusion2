#!/usr/bin/env python3
"""Build/run the new two-process boundary preflight, not a provenance benchmark."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

from contract import HERE, COMMIT, manifest
from verify import verify_directory

ROOT=HERE.parents[1]


def require(ok, why):
    if not ok:raise ValueError(why)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, data):
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')


def run(args):
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    source=args.source.resolve();go=args.go.resolve()
    env=dict(os.environ,GOROOT=str(go.parent.parent),GOTOOLCHAIN='local',GOTELEMETRY='off',
             GOOS='linux',GOARCH='amd64',GOAMD64='v1',CGO_ENABLED='0',GOFLAGS='',GOEXPERIMENT='')
    env['PATH']=str(go.parent)+os.pathsep+env.get('PATH','')
    (out/'tmp').mkdir()
    env.update(TMPDIR=str(out/'tmp'),GOTMPDIR=str(out/'tmp'))
    report=dict(status='running',accuracy_eligible=False,performance_eligible=False,
                tracefusion_provenance_executed=False,external_tool_executed=False)
    def command(argv,cwd,timeout=600):
        p=subprocess.run(list(map(str,argv)),cwd=cwd,env=env,capture_output=True,text=True,timeout=timeout)
        with (out/'commands.jsonl').open('a') as f:
            f.write(json.dumps(dict(command=list(map(str,argv)),cwd=str(cwd),returncode=p.returncode,
                                    stdout=p.stdout,stderr=p.stderr))+'\n')
        if p.returncode:raise RuntimeError(p.stderr[-4000:]+p.stdout[-4000:])
        return p.stdout
    server=None
    try:
        require(command(['git','rev-parse','HEAD'],source).strip()==COMMIT,'upstream commit')
        require(not command(['git','status','--porcelain','--untracked-files=no'],source).strip(),'upstream modified')
        require(command([go,'env','GOVERSION'],source).strip()=='go1.25.4','pinned Go 1.25.4 required')
        truth=manifest(source/'src/productcatalogservice/products.json')
        save(out/'contract.json',truth) # Frozen before any native test or engine output.
        packages={}
        original={}
        for role,package,test in [('catalog','productcatalogservice','catalog_test.go'),
                                  ('checkout','checkoutservice','checkout_test.go')]:
            src=source/'src'/package;dst=out/'source'/package
            shutil.copytree(src,dst)
            original.update({str(p.relative_to(source)):digest(p) for p in src.rglob('*') if p.is_file()})
            shutil.copyfile(HERE/'observer_test.go',dst/'tracefusion_rq1_observer_test.go')
            shutil.copyfile(HERE/test,dst/'tracefusion_rq1_driver_test.go')
            packages[role]=dst
        original['protos/demo.proto']=digest(source/'protos/demo.proto')
        shutil.copyfile(source/'protos/demo.proto',out/'source'/'demo.proto')
        save(out/'source-manifest.json',original)
        # Explicit source contracts, not a claim of general frontend support.
        main=(packages['checkout']/'main.go').read_text()
        require('Convert(context.TODO(), &pb.CurrencyConversionRequest{' in main and
                'From:   from,' in main and 'product.GetPriceUsd()' in main,'consumer boundary source contract')
        for role,dst in packages.items():
            command([go,'test','-c','-mod=readonly','-buildvcs=false','-o',out/(role+'-workload'),'.'],dst)
            require(digest(dst/'go.mod')==original['src/'+dst.name+'/go.mod'] and
                    digest(dst/'go.sum')==original['src/'+dst.name+'/go.sum'],'module lock changed')
        # Run original handlers in separate processes, connected by native TCP gRPC.
        common=dict(env,RQ1_CASES=str(HERE/'cases.json'))
        server_log=(out/'catalog.stdout').open('w')
        try:
            server=subprocess.Popen([str(out/'catalog-workload'),'-test.run=^TestRQ1CatalogServer$','-test.v'],
                                    cwd=packages['catalog'],env=dict(common,RQ1_LOG=str(out/'catalog.jsonl'),
                                    RQ1_READY=str(out/'ready.json')),stdin=subprocess.PIPE,
                                    stdout=server_log,stderr=subprocess.STDOUT)
            deadline=time.monotonic()+60
            while not (out/'ready.json').exists():
                require(server.poll() is None,'catalog server exited; inspect catalog.stdout')
                require(time.monotonic()<deadline,'catalog startup timeout')
                time.sleep(.05)
            ready=json.loads((out/'ready.json').read_text())
            env.update(common,RQ1_CATALOG_ADDR=ready['address'],RQ1_LOG=str(out/'checkout.jsonl'))
            text=command([out/'checkout-workload','-test.run=^TestRQ1CheckoutClient$','-test.v'],packages['checkout'],120)
            (out/'checkout.stdout').write_text(text)
            server.stdin.write(b'x');server.stdin.flush();server.stdin.close()
            require(server.wait(timeout=30)==0,'catalog server failure')
            server=None
        finally:server_log.close()
        report=verify_directory(out)
        report.update(upstream_commit=COMMIT,go='go1.25.4',source_sha256=original,
                      binary_sha256={role:digest(out/(role+'-workload')) for role in packages},
                      observer_source_sha256={p.name:digest(p) for p in HERE.iterdir() if p.suffix in ('.py','.go','.json')},
                      business_source_modified=False,
                      instrumentation='Test-only SDK exporter, gRPC stats observer and interceptors; no production startup',
                      wire_capture=False,second_human_truth_review=False)
        require(not command(['git','status','--porcelain','--untracked-files=no'],source).strip(),'upstream changed during run')
    except Exception as e:
        report.update(status='failed',error=str(e));raise
    finally:
        if server is not None:
            server.kill();server.wait(timeout=10)
        save(out/'validation.json',report)
        print(json.dumps({k:report.get(k) for k in ('status','workload_instances','product_rpc_attempts',
                                                    'confirmed_target_fields','no_target_checks','error')}))
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--go',type=Path,required=True)
    p.add_argument('--output',type=Path,default=ROOT/'artifacts'/('otel-field-rq1-preflight-'+
                   datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')))
    run(p.parse_args())
