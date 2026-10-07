#!/usr/bin/env python3
"""Two real Gin processes with observed HTTP response and decoded-field linking."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime,timezone
from functools import partial
import http.client
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import time
import traceback
import zipfile

from hybrid_provenance import ROOT,save
from hybrid_model import require
from gin_default_boundaries import default_scheduler
from gin_byte_provenance import build,fixtures,VARIANTS
from gin_byte_adapter import plan_binary
import gin_byte_capture
from string_capture import collect
from gin_cross_boundaries import bind_service,stitch

SCENARIO=ROOT/'scenarios/gin-cross-provenance'


def build_role(out,role,variant):
    return build(out,'assign' if role=='upstream' else variant,scenario=SCENARIO,
                 planner=partial(plan_binary,cross_role=role),extra_sources=(role+'.go',))


def readiness(out,process=None):
    deadline=time.monotonic()+60
    while time.monotonic()<deadline:
        p=out/'target.stdout'
        if p.exists():
            lines=p.read_text().splitlines()
            if lines:
                try:
                    ready=json.loads(lines[0]);require(ready['address'].startswith('127.0.0.1:'),'Loopback only');return ready
                except json.JSONDecodeError:pass
        if process and process.poll() is not None:raise RuntimeError('Collector exited before readiness; see upstream.log')
        time.sleep(0.05)
    raise TimeoutError('No server readiness')


def client(out):
    ready=readiness(out);require(ready['requests']==8 and ready['concurrency']==4,'Unexpected fixture')
    # A shared trace ID makes trace-ID-only matching ambiguous by construction.
    trace=secrets.token_hex(16);parents={i:'00-'+trace+'-'+secrets.token_hex(8)+'-01' for i in range(1,9)}
    def worker(index):
        conn=http.client.HTTPConnection(ready['address'],timeout=15);rows=[]
        try:
            for ticket in (index,index+4):
                selected='a' if ticket%2 else 'c'
                conn.request('GET',f'/account/summary?ticket={ticket}&source={selected}',headers={'traceparent':parents[ticket]})
                response=conn.getresponse();body=response.read().decode()
                rows.append(dict(ticket=ticket,selected=selected,trace=parents[ticket],status=response.status,
                                 content_type=response.getheader('Content-Type'),body=body))
        finally:conn.close()
        return rows
    with ThreadPoolExecutor(max_workers=4) as pool:rows=sum(pool.map(worker,range(1,5)),[])
    save(out/'client-responses.json',sorted(rows,key=lambda r:r['ticket']));return rows


def evaluate(joined,locals_,responses,plans,variant,captures):
    clients={r['trace']:r for r in responses};checks=[];tp=fp=fn=0
    for r in joined.get('results',[]):
        if r.get('status')!='resolved':checks.append(dict(passed=False,reason=r.get('reason')));continue
        c=clients.get(r['trace'],{});ticket=c.get('ticket');name='A.txt' if ticket and ticket%2 else 'C.txt'
        expected=set()
        if variant!='overwrite':expected.add(('upstream',str(Path(plans['upstream']['binary']).parent/'inputs'/str(ticket)/name)))
        if variant!='assign':expected.add(('downstream',str(Path(plans['downstream']['binary']).parent/'inputs'/str(ticket)/'B.txt')))
        actual={(s['id'].split('/')[0],s['path']) for s in r['sources']}
        tp+=len(actual&expected);fp+=len(actual-expected);fn+=len(expected-actual)
        checks.append(dict(ticket=ticket,passed=bool(c) and actual==expected and r['body']==c['body'] and
            json.loads(r['body'])=={'result':[83,65,77,69]} and c['status']==200 and c['content_type']=='application/json; charset=utf-8'
            and r['transfer_contributes']==(variant!='overwrite'),sources=sorted(actual),expected=sorted(expected)))
    correct=(joined.get('status')=='resolved' and len(checks)==len(responses)==8 and len(clients)==8 and
             {c.get('ticket') for c in checks}==set(range(1,9)) and all(c['passed'] for c in checks))
    scheduler={}
    for role,cap in captures.items():
        meta=[json.loads(line) for line in (cap/'target.stdout').read_text().splitlines()]
        scheduler[role]=(len(meta)==2 and default_scheduler(meta[0].get('scheduler')) and default_scheduler(meta[1].get('scheduler_final')))
    concurrency={role:r.get('concurrency',{}) for role,r in locals_.items()}
    overlap=all(c.get('max_active_scopes',0)>=2 for c in concurrency.values())
    return dict(passed=correct and all(scheduler.values()) and overlap,provenance_checks_passed=correct,
        default_scheduler_verified=scheduler,natural_concurrency_coverage_passed=overlap,concurrency=concurrency,
        checks=checks,source_relations=dict(tp=tp,fp=fp,fn=fn),migration_required=False)


def negative_checks(up,down):
    tests=[]
    for name in ('missing_upstream','ambiguous_context','same_body_wrong_span','wrong_received_body','missing_transfer_evidence'):
        a,b=deepcopy(up),deepcopy(down)
        if name=='missing_upstream':a['results']=[]
        elif name=='ambiguous_context':a['results']+=deepcopy(a['results'])
        elif name=='same_body_wrong_span':
            known={r['incoming_trace'] for r in a['results']}
            for r in b['results']:
                parts=r['transfer']['trace'].split('-');candidate=1
                while '-'.join([parts[0],parts[1],f'{candidate:016x}',parts[3]]) in known:candidate+=1
                r['transfer']['trace']='-'.join([parts[0],parts[1],f'{candidate:016x}',parts[3]])
        elif name=='wrong_received_body':
            for r in b['results']:r['transfer']['body']='{"result":[0,0,0,0]}'
        else:
            for r in b['results']:del r['transfer']
        result=stitch(a,b);tests.append(dict(case=name,passed=result['status']=='unknown' and all(r['status']=='unknown' for r in result['results'])))
    return tests


def worker(plan_path,input_path,out,role):
    def interrupted(signum,frame):raise RuntimeError('Collector interrupted by coordinator')
    signal.signal(signal.SIGTERM,interrupted)
    plan=json.loads(plan_path.read_text())
    doc=collect(Path(plan['binary']),plan,input_path.read_bytes(),out,transport=gin_byte_capture,
                driver=client if role=='downstream' else None,timeout_seconds=90)
    return int(bool(doc['capture_errors']) or doc['returncode']!=0)


def analyze_pair(pair,plans,captures,variant):
    locals_={}
    for role in ('upstream','downstream'):
        document=json.loads((captures[role]/'events.json').read_text())
        locals_[role]=bind_service(document,plans[role]);save(captures[role]/'inference.json',locals_[role])
    joined=stitch(locals_['upstream'],locals_['downstream']);save(pair/'joined.json',joined)
    report=evaluate(joined,locals_,json.loads((captures['downstream']/'client-responses.json').read_text()),plans,variant,captures)
    negatives=negative_checks(locals_['upstream'],locals_['downstream']) if all(v['status']=='resolved' for v in locals_.values()) else []
    report['negative_checks']=negatives;report['passed']=report['passed'] and len(negatives)==5 and all(n['passed'] for n in negatives)
    return report


def run(out,*,build_fn=build_role,worker_script=__file__,startup_fn=None,analyze_fn=analyze_pair,archive_output=True,variants=VARIANTS):
    passed=False
    try:
        reports=[]
        for variant in variants:
            pair=out/variant;pair.mkdir();plans={};captures={};procs={};logs=[]
            try:
                for role in ('upstream','downstream'):
                    print('Building '+variant+'/'+role,flush=True)
                    plans[role]=build_fn(pair/role,role,variant);fixtures(pair/role);captures[role]=pair/role/'capture'
                for role in ('upstream','downstream'):
                    upstream=readiness(captures['upstream'],procs['upstream'])['address'] if role=='downstream' else ''
                    boot=pair/role/'startup.json';settings=dict(Inputs=str(pair/role/'inputs'),Upstream=upstream)
                    if startup_fn:settings.update(startup_fn(role,pair,captures))
                    save(boot,settings)
                    log=(pair/(role+'.log')).open('w');logs.append(log)
                    print('Collecting '+variant+'/'+role,flush=True)
                    procs[role]=subprocess.Popen([sys.executable,str(worker_script),'collect','--plan',str(pair/role/'plan.json'),
                        '--input',str(boot),'--output',str(captures[role]),'--role',role],stdout=log,stderr=subprocess.STDOUT)
                for role in ('downstream','upstream'):
                    require(procs[role].wait(timeout=110)==0,'Collector failed: '+str(pair/(role+'.log')))
            finally:
                for process in procs.values():
                    if process.poll() is None:
                        process.terminate()
                        try:process.wait(timeout=10)
                        except subprocess.TimeoutExpired:process.kill();process.wait()
                for log in logs:log.close()
            report=analyze_fn(pair,plans,captures,variant)
            save(pair/'evaluation.json',report);reports.append(dict(variant=variant,**report))
        passed=all(r['passed'] for r in reports);save(out/'evaluation.json',dict(all_passed=passed,variants=reports))
        print(json.dumps({'all_passed':passed,'downstream_requests':8*len(variants),'upstream_requests':8*len(variants)}),flush=True)
    except Exception:
        error=traceback.format_exc();(out/'runner-error.txt').write_text(error);print(error,file=sys.stderr)
    finally:
        save(out/'run-status.json',dict(completed=passed))
        if archive_output:
            archive=out.with_suffix('.zip')
            with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
                for p in sorted(out.rglob('*')):
                    if p.is_file():z.write(p,p.relative_to(out.parent))
            if os.geteuid()==0 and os.environ.get('SUDO_UID','').isdigit():os.chown(archive,int(os.environ['SUDO_UID']),int(os.environ['SUDO_GID']))
            print('Return this archive: '+str(archive),flush=True)
    return int(not passed)


def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=('build','run','collect'));p.add_argument('--output',type=Path)
    p.add_argument('--plan',type=Path);p.add_argument('--input',type=Path);p.add_argument('--role',choices=('upstream','downstream'))
    args=p.parse_args()
    if args.command=='collect':return worker(args.plan,args.input,args.output,args.role)
    out=(args.output or ROOT/'artifacts'/('gin-cross-provenance-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f'))).resolve()
    out.mkdir(parents=True,exist_ok=False)
    if args.command=='run':return run(out)
    for variant in VARIANTS:
        for role in ('upstream','downstream'):
            plan=build_role(out/variant/role,role,variant);print(json.dumps({'variant':variant,'role':role,'sites':len(plan['sites'])}))
    return 0

if __name__=='__main__':raise SystemExit(main())
