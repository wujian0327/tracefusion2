#!/usr/bin/env python3
"""Default-scheduler Gin integration of the frozen byte-source assignment suite."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime,timezone
import hashlib
import http.client
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback
from types import SimpleNamespace
import zipfile

from hybrid_provenance import ROOT,save
from hybrid_model import require
from gin_default_boundaries import default_scheduler
from gin_byte_adapter import plan_binary
from gin_byte_boundaries import bind
import gin_byte_capture
from string_capture import collect

VARIANTS=('assign','partial','overwrite')
SCENARIO=ROOT/'scenarios/gin-byte-provenance'


def build(out,variant,*,scenario=SCENARIO,planner=plan_binary,extra_sources=(),expected_modules=None,operation_source=None):
    out.mkdir(parents=True);src=out/'sources';src.mkdir()
    for name in ('go.mod','go.sum'):
        modules=scenario if (scenario/'go.mod').exists() else ROOT/'scenarios/gin-default-provenance'
        shutil.copyfile(modules/name,src/name)
    shutil.copyfile(scenario/'main.go',src/'main.go')
    for name in extra_sources:shutil.copyfile(scenario/name,src/name)
    shutil.copyfile(operation_source or ROOT/'scenarios/go-byte-provenance'/(variant+'.go'),src/'operations.go')
    go=os.environ.get('TRACEFUSION_GO') or shutil.which('go');require(go,'Go not visible')
    env=dict(os.environ,GOOS='linux',GOARCH='amd64',CGO_ENABLED='0',GO111MODULE='on',
             GOTOOLCHAIN='local',GOFLAGS='',GOEXPERIMENT='',GOAMD64='v1',GOTELEMETRY='off')
    version=subprocess.check_output([go,'env','GOVERSION'],env=env,text=True).strip()
    require(version=='go1.25.4','Reuse pinned Gin toolchain Go 1.25.4; found '+version)
    binary=out/'gin-byte-target'
    cmd=[go,'build','-buildvcs=false','-mod=readonly','-tags=nomsgpack','-buildmode=exe','-gcflags=all=-l','-o',str(binary),'.']
    proc=subprocess.run(cmd,cwd=src,env=env,capture_output=True,text=True,timeout=600)
    save(out/'build.json',dict(command=cmd,go=version,stdout=proc.stdout,stderr=proc.stderr,returncode=proc.returncode))
    proc.check_returncode()
    gin=json.loads(subprocess.check_output([go,'list','-m','-json','github.com/gin-gonic/gin'],cwd=src,env=env,text=True))
    require(gin['Version']=='v1.11.0' and 'Replace' not in gin,'Unexpected Gin module')
    if expected_modules:
        inventory=subprocess.check_output([go,'list','-m','-json','all'],cwd=src,env=env,text=True)
        (out/'modules.jsonl').write_text(inventory)
        found={};remaining=inventory.strip();decoder=json.JSONDecoder()
        while remaining:
            module,end=decoder.raw_decode(remaining);found[module['Path']]=module;remaining=remaining[end:].strip()
        for name,wanted in expected_modules.items():
            require(name in found and found[name].get('Version')==wanted and 'Replace' not in found[name],
                    'Unexpected tracing dependency: '+name)
    root=Path(gin['Dir']);files=[root/'render/json.go',root/'response_writer.go',*(root/'codec/json').glob('*.go')]
    save(out/'identity.json',dict(binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),go=version,gin=gin['Version'],
        source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in src.iterdir()},
        framework_sha256={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}))
    plan=planner(binary,go,env,out);save(out/'plan.json',plan)
    # Exercise the actual planner -> transport interface before launching a
    # target or importing BCC. Placeholder PID/namespace: generation only.
    preview=gin_byte_capture.source(plan,1,SimpleNamespace(st_dev=0,st_ino=0))
    (out/'collector.preview.c').write_text(preview)
    return plan


def fixtures(out):
    folder=out/'inputs';folder.mkdir()
    for ticket in range(1,9):
        directory=folder/str(ticket);directory.mkdir()
        for name in ('A','B','C'):(directory/(name+'.txt')).write_bytes(b'SAME')
    return folder


def client(out):
    deadline=time.monotonic()+15;ready=None
    while time.monotonic()<deadline:
        lines=(out/'target.stdout').read_text().splitlines()
        if lines:
            ready=json.loads(lines[0]);break
        time.sleep(0.02)
    require(ready is not None,'No server readiness')
    require(ready['requests']==8 and ready['concurrency']==4,'Unexpected server fixture')
    address=ready['address'];require(address.startswith('127.0.0.1:'),'Loopback only')
    def worker(index):
        rows=[];conn=http.client.HTTPConnection(address,timeout=10)
        try:
            for ticket in (index,index+4):
                chosen='a' if ticket%2 else 'c'
                conn.request('GET',f'/account/summary?ticket={ticket}&source={chosen}')
                res=conn.getresponse();body=res.read().decode()
                rows.append(dict(ticket=ticket,selected=chosen,status=res.status,body=body,content_type=res.getheader('Content-Type')))
        finally:conn.close()
        return rows
    with ThreadPoolExecutor(max_workers=4) as pool:responses=sum(pool.map(worker,range(1,5)),[])
    save(out/'client-responses.json',sorted(responses,key=lambda x:x['ticket']))
    return responses


def evaluate(inferred,responses,stdout,variant,folder):
    checks=[];tickets=[];tp=fp=fn=0
    clients={r['ticket']:r for r in responses}
    for result in inferred.get('results',[]):
        paths=[Path(p) for p in result['read_paths']];ticket=int(paths[0].parent.name);tickets.append(ticket)
        actual=set(result['local_sources']);chosen='source:1' if ticket%2 else 'source:3'
        expected={chosen} if variant=='assign' else {chosen,'source:2'} if variant=='partial' else {'source:2'}
        prefix='request:%d:'%result['request_id'];prov=result['provenance']
        removed=[prefix+chosen] if variant=='overwrite' else []
        versions=[[prefix+chosen]]
        if variant!='assign':versions.append(sorted([prefix+chosen,prefix+'source:2']))
        if variant=='overwrite':versions.append([prefix+'source:2'])
        c=clients.get(ticket,{})
        checks.append(dict(ticket=ticket,passed=(actual==expected and
            paths==[folder/str(ticket)/(name+'.txt') for name in ('A','B','C')] and
            result['body']==c.get('body') and json.loads(result['body'])=={'result':[83,65,77,69]} and
            c.get('status')==200 and c.get('content_type')=='application/json; charset=utf-8' and
            prov['overwritten_sources']==removed and [v['sources'] for v in prov['source_versions']]==versions),
            sources=sorted(actual),expected_sources=sorted(expected)))
        tp+=len(actual&expected);fp+=len(actual-expected);fn+=len(expected-actual)
    metadata=[json.loads(line) for line in stdout.splitlines()]
    defaults=(len(metadata)==2 and default_scheduler(metadata[0].get('scheduler')) and default_scheduler(metadata[1].get('scheduler_final')))
    correct=(inferred.get('status')=='resolved' and len(checks)==len(responses)==8 and set(tickets)==set(clients)==set(range(1,9)) and all(c['passed'] for c in checks))
    overlap=inferred.get('concurrency',{}).get('max_active_scopes',0)>=2
    return dict(passed=correct and defaults and overlap,provenance_checks_passed=correct,
        default_scheduler_verified=defaults,natural_concurrency_coverage_passed=overlap,
        concurrency=inferred.get('concurrency',{}),checks=checks,source_relations=dict(tp=tp,fp=fp,fn=fn),
        migration_required=False)


def negative_checks(doc,plan):
    checks=[]
    for name in ('missing_scope','wrong_g','wrong_writer','changed_payload','missing_store','capture_loss'):
        bad=deepcopy(doc)
        ordered=sorted(bad['events'],key=lambda e:(e['timestamp'],e['sequence']))
        if name=='missing_scope':bad['events'].remove(next(e for e in ordered if e['site']==plan['scope_entry']))
        elif name=='wrong_g':next(e for e in ordered if e['op']=='instruction')['g']^=1
        elif name=='wrong_writer':next(e for e in ordered if e['op']=='writer' and e['phase']=='pre')['registers']['rax']^=1
        elif name=='changed_payload':
            v=next(e for e in ordered if e['op']=='writer' and e['phase']=='pre')['values']['json'];v['hex']='00'+v['hex'][2:]
        elif name=='missing_store':
            sites={n['site'] for n in plan['instructions'] if n['op']=='mov' and n['args'][1]['kind']=='mem'}
            bad['events'].remove(next(e for e in ordered if e['site'] in sites))
        else:bad['capture_errors']=['injected loss']
        for i,e in enumerate(bad['events']):e['sequence']=i
        bad['stats']['submitted']=len(bad['events'])
        result=bind(bad,plan);checks.append(dict(case=name,passed=result['status']=='unknown',reason=result.get('reason')))
    return checks


def run(out):
    passed=False
    try:
        reports=[]
        for variant in VARIANTS:
            print('Building '+variant,flush=True);plan=build(out/variant,variant)
            folder=fixtures(out/variant);capture=out/variant/'capture'
            doc=collect(Path(plan['binary']),plan,json.dumps(str(folder)).encode(),capture,transport=gin_byte_capture,driver=client)
            inferred=bind(doc,plan);save(capture/'inference.json',inferred)
            require(not doc['capture_errors'] and doc['returncode']==0,'Capture failed: '+str(doc['capture_errors']))
            report=evaluate(inferred,json.loads((capture/'client-responses.json').read_text()),(capture/'target.stdout').read_text(),variant,folder)
            negative=negative_checks(doc,plan);report['negative_checks']=negative
            report['passed']=report['passed'] and all(c['passed'] for c in negative)
            save(capture/'evaluation.json',report);reports.append(dict(variant=variant,**report))
        passed=all(r['passed'] for r in reports);save(out/'evaluation.json',dict(all_passed=passed,variants=reports))
        print(json.dumps({'all_passed':passed,'requests':24}),flush=True)
    except Exception:
        error=traceback.format_exc();(out/'runner-error.txt').write_text(error);print(error,file=sys.stderr)
    finally:
        save(out/'run-status.json',{'completed':passed});archive=out.with_suffix('.zip')
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
            for p in sorted(out.rglob('*')):
                if p.is_file():z.write(p,p.relative_to(out.parent))
        if os.geteuid()==0 and os.environ.get('SUDO_UID','').isdigit():os.chown(archive,int(os.environ['SUDO_UID']),int(os.environ['SUDO_GID']))
        print('Return this archive: '+str(archive),flush=True)
    return int(not passed)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=('build','run'));parser.add_argument('--output',type=Path)
    args=parser.parse_args();out=(args.output or ROOT/'artifacts'/('gin-byte-provenance-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f'))).resolve()
    out.mkdir(parents=True,exist_ok=False)
    if args.command=='run':return run(out)
    for variant in VARIANTS:
        p=build(out/variant,variant);print(json.dumps({'variant':variant,'sites':len(p['sites']),'instructions':len(p['instructions'])}))
    return 0

if __name__=='__main__':raise SystemExit(main())
