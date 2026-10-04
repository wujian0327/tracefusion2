#!/usr/bin/env python3
"""Two Gin services using real OpenTelemetry SDK spans and eBPF provenance."""
import argparse
from copy import deepcopy
from datetime import datetime,timezone
from functools import partial
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess

from hybrid_model import require
from hybrid_provenance import ROOT,save
from gin_byte_provenance import build,VARIANTS
from gin_byte_adapter import plan_binary
from gin_cross_provenance import readiness,run as run_pair,evaluate,negative_checks
from gin_cross_boundaries import bind_service
from gin_otel_boundaries import read_spans,stitch_otel,negative_span_checks
import gin_byte_capture
from string_capture import collect

SCENARIO=ROOT/'scenarios/gin-otel-provenance'
MODULES={name:'v1.38.0' for name in ('go.opentelemetry.io/otel','go.opentelemetry.io/otel/sdk',
          'go.opentelemetry.io/otel/trace','go.opentelemetry.io/otel/exporters/stdout/stdouttrace')}
MODULES.update({name:'v0.63.0' for name in (
 'go.opentelemetry.io/contrib/instrumentation/github.com/gin-gonic/gin/otelgin',
 'go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp')})


def build_role(out,role,variant):
    return build(out,'assign' if role=='upstream' else variant,scenario=SCENARIO,
        planner=partial(plan_binary,cross_role=role,tracing='otel'),
        extra_sources=(role+'.go','tracing.go'),expected_modules=MODULES)


def build_client(out):
    out.mkdir(parents=True);src=out/'sources';src.mkdir()
    for name in ('go.mod','go.sum','client.go','tracing.go'):shutil.copyfile(SCENARIO/name,src/name)
    go=os.environ.get('TRACEFUSION_GO') or shutil.which('go');require(go,'Go not visible')
    env=dict(os.environ,GOOS='linux',GOARCH='amd64',CGO_ENABLED='0',GO111MODULE='on',GOTOOLCHAIN='local',
             GOFLAGS='',GOEXPERIMENT='',GOAMD64='v1',GOTELEMETRY='off')
    version=subprocess.check_output([go,'env','GOVERSION'],env=env,text=True).strip()
    require(version=='go1.25.4','Reuse pinned Go 1.25.4; found '+version)
    binary=out/'otel-client'
    cmd=[go,'build','-buildvcs=false','-mod=readonly','-buildmode=exe','-gcflags=all=-l','-o',str(binary),'.']
    proc=subprocess.run(cmd,cwd=src,env=env,capture_output=True,text=True,timeout=600)
    save(out/'build.json',dict(command=cmd,go=version,stdout=proc.stdout,stderr=proc.stderr,returncode=proc.returncode))
    proc.check_returncode()
    save(out/'identity.json',dict(binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),go=version,
        source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in src.iterdir()}))
    return binary


def client(out,binary):
    ready=readiness(out);require(ready['requests']==8 and ready['concurrency']==4,'Unexpected fixture')
    settings=dict(Address=ready['address'],TraceFile=str(out/'client-spans.jsonl'),Responses=str(out/'client-responses.json'))
    result=subprocess.run([str(binary)],input=json.dumps(settings),text=True,capture_output=True,timeout=50)
    save(out/'client-run.json',dict(returncode=result.returncode,stdout=result.stdout,stderr=result.stderr))
    result.check_returncode()
    return json.loads((out/'client-responses.json').read_text())


def worker(plan_path,input_path,out,role):
    def interrupted(signum,frame):raise RuntimeError('Collector interrupted by coordinator')
    signal.signal(signal.SIGTERM,interrupted)
    plan=json.loads(plan_path.read_text());boot=json.loads(input_path.read_text())
    doc=collect(Path(plan['binary']),plan,input_path.read_bytes(),out,transport=gin_byte_capture,
        driver=partial(client,binary=Path(boot['ClientBinary'])) if role=='downstream' else None,timeout_seconds=90)
    return int(bool(doc['capture_errors']) or doc['returncode']!=0)


def analyze_pair(pair,plans,captures,variant):
    locals_={}
    for role in ('upstream','downstream'):
        doc=json.loads((captures[role]/'events.json').read_text())
        locals_[role]=bind_service(doc,plans[role]);save(captures[role]/'inference.json',locals_[role])
    try:
        spans=read_spans(captures)
        joined=stitch_otel(locals_['upstream'],locals_['downstream'],spans)
    except (OSError,ValueError) as exc:
        spans={};joined=dict(status='unknown',reason='SDK export incomplete: '+str(exc),results=[])
    save(pair/'joined.json',joined)
    # The response oracle keys the external request; cross-service trace retains
    # the actual downstream CLIENT span. Adapt evaluation only, never inference.
    evaluation_view=deepcopy(joined)
    for row in evaluation_view['results']:row['trace']=row['request_trace']
    report=evaluate(evaluation_view,locals_,json.loads((captures['downstream']/'client-responses.json').read_text()),plans,variant,captures)
    negatives=[]
    if joined['status']=='resolved':
        negatives=negative_checks(locals_['upstream'],locals_['downstream'])+negative_span_checks(locals_['upstream'],locals_['downstream'],spans)
    report.update(negative_checks=negatives,trace_validation=joined.get('trace_validation'),inference_status=joined['status'],
                  inference_reason=joined.get('reason'))
    report['passed']=report['passed'] and len(negatives)==11 and all(n['passed'] for n in negatives)
    return report


def main():
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=('build','run','collect'))
    parser.add_argument('--output',type=Path);parser.add_argument('--plan',type=Path);parser.add_argument('--input',type=Path)
    parser.add_argument('--role',choices=('upstream','downstream'));args=parser.parse_args()
    if args.command=='collect':return worker(args.plan,args.input,args.output,args.role)
    out=(args.output or ROOT/'artifacts'/('gin-otel-provenance-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f'))).resolve()
    out.mkdir(parents=True,exist_ok=False)
    client_binary=out/'client/otel-client'
    def builder(directory,role,variant):
        if not client_binary.exists():build_client(out/'client')
        return build_role(directory,role,variant)
    if args.command=='run':
        return run_pair(out,build_fn=builder,worker_script=__file__,analyze_fn=analyze_pair,
            startup_fn=lambda role,pair,captures:dict(Service=role,TraceFile=str(captures[role]/'spans.jsonl'),ClientBinary=str(client_binary)))
    for variant in VARIANTS:
        for role in ('upstream','downstream'):
            plan=builder(out/variant/role,role,variant);print(json.dumps(dict(variant=variant,role=role,sites=len(plan['sites']))),flush=True)
    return 0

if __name__=='__main__':raise SystemExit(main())
