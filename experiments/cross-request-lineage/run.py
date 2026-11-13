#!/usr/bin/env python3
"""One-command round-one capture; no expected data is passed to any analyzer."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import traceback
import urllib.request
import uuid
from zipfile import ZipFile, ZIP_DEFLATED

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CORE = ROOT / 'experiments/sockshop-mirrortaint'
sys.path.insert(0, str(CORE))
from run_query_planner import JARS
from build_distributed_plans import build as build_tf


def load(p): return json.loads(Path(p).read_text())
def save(p, value): Path(p).write_text(json.dumps(value, indent=2, ensure_ascii=False)+'\n')
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def now(): return dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat()


def command(cmd, log, **kwargs):
    r = subprocess.run(list(map(str, cmd)), capture_output=True, text=True, timeout=180, **kwargs)
    Path(log).write_text(r.stdout+r.stderr)
    if r.returncode: raise RuntimeError(f'{cmd[0]} failed; see {log}')
    return r


def build(out, entry='process'):
    out.mkdir(); classes = out/'classes'; classes.mkdir()
    cp = ':'.join(map(str, JARS))
    command(['javac', '-cp', cp, '-d', classes, *[HERE/n for n in ('Cache.java', 'Observer.java', 'Server.java')]], out/'business-compile.log')
    jar = out/'business.jar'
    with ZipFile(jar, 'w', ZIP_DEFLATED) as z:
        for f in classes.rglob('*.class'): z.write(f, 'BOOT-INF/classes/'+str(f.relative_to(classes)))
    build_tf(out/'tf', {'A': {'jar':str(jar), 'targets':['lineage/business/Cache$Reply.text']},
                       'B': {'jar':str(jar), 'entry':'lineage/business/Cache.'+entry+'(Llineage/business/Cache$Request;)Llineage/business/Cache$Reply;',
                             'targets':['lineage/business/Cache$Reply.text'], 'response_path':'/text', 'execution_kernel':True, 'application_calls':True}})
    # Observer configuration is shared source granularity, never case answers.
    plan = load(out/'tf/B/plan.json')
    plan['response_binding']['source_fields'] = ['lineage/business/Cache$Request.value', 'lineage/business/Cache$Request.fallback']
    save(out/'tf/B/plan.json', plan)
    native = ROOT/'artifacts/external-tools/mirrortaint/mirrorTaint.jar'
    lock = load(ROOT/'baselines/tools.lock.json')['tools']['mirrortaint']
    if sha(native) != lock['sha256']: raise ValueError('MirrorTaint JAR hash differs')
    adapter = out/'adapters'; adapter.mkdir()
    command(['javac','-cp',':'.join(map(str,[classes,out/'tf/distributed-observer.jar',native,*JARS])), '-d',adapter,
             HERE/'TraceBoundary.java',HERE/'MirrorBoundary.java'],out/'boundary-compile.log')
    save(out/'manifest.json', {'business_classes':{str(f.relative_to(classes)):sha(f) for f in classes.rglob('*.class')},
                              'native':str(native),'native_sha256':sha(native), 'dependencies':{str(p):sha(p) for p in JARS},
                              'tf_agent_sha256':sha(out/'tf/distributed-observer.jar'),
                              'plans':{r:sha(out/'tf'/r/'plan.json') for r in ('A','B')}})


def free_port():
    with socket.socket() as s: s.bind(('127.0.0.1',0)); return s.getsockname()[1]


def http(port, body=None, parent=None, path='/call'):
    payload = json.dumps(body, separators=(',',':')).encode() if body is not None else None
    headers = {'Content-Type':'application/json'}
    if parent: headers['traceparent'] = parent
    req = urllib.request.Request(f'http://127.0.0.1:{port}{path}', data=payload, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as r: status, raw, hs = r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e: status, raw, hs = e.code, e.read(), dict(e.headers)
    return {'traceparent':parent,'request_utf8':payload.decode() if payload else None,'status':status,
            'response_utf8':raw.decode(),'response':json.loads(raw),'response_headers':hs}


def capture(dest, build, mode, case, java='java', ingress='A', dispatch='original'):
    dest.mkdir(parents=True); processes = {}; logs = []; receipt = {'started_at':now(),'mode':mode,'case':case['id'],'commands':{},'requests':[],'ingress':ingress,'dispatch':dispatch}
    ports = {r:free_port() for r in ('A','B')}
    cp = ':'.join(map(str,[build/'classes',build/'adapters',*JARS]))
    try:
        for role in ('B','A'):
            rd = dest/role; rd.mkdir(); opts=[]
            if mode == 'tracefusion':
                opts = ['-javaagent:'+str(build/'tf/distributed-observer.jar'), '-Dservice.plan='+str(build/'tf'/role/'plan.json'),
                        '-Dservice.mode=full','-Dservice.events='+str(rd/'events.jsonl'),'-Dlineage.observer=TraceBoundary']
            elif mode == 'mirrortaint':
                native = load(build/'manifest.json')['native']
                opts = ['-javaagent:'+native,'-Dtaint.env=remote','-Dtaint.app=lineage.business','-Dtaint.version=cross-request-round1',
                        '-Duser.home='+str(rd),'-Dlineage.observer=MirrorBoundary','-Dlineage.native='+str(rd/'native.jsonl')]
                cp = ':'.join(map(str,[build/'classes',build/'adapters',native,*JARS]))
            cmd = [str(java),'-Xms32m','-Xmx256m','-Dlineage.dispatch='+dispatch,'-Dlineage.source.role='+ingress,*opts,'-cp',cp,'lineage.web.Server',role,str(ports[role]),
                   f'http://127.0.0.1:{ports["B"]}',str(rd/'http.jsonl')]
            receipt['commands'][role]=cmd
            log=(rd/'process.log').open('w');logs.append(log)
            processes[role]=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,cwd=rd)
            deadline=time.monotonic()+30
            while time.monotonic()<deadline:
                if processes[role].poll() is not None: raise RuntimeError(f'{role} exited during startup')
                if 'READY '+role in (rd/'process.log').read_text(): break
                time.sleep(.05)
            else: raise TimeoutError('Server readiness timeout '+role)
        for body in case['requests']:
            trace=uuid.uuid4().hex; span=uuid.uuid4().hex[:16]
            r=http(ports[ingress],body,'00-'+trace+'-'+span+'-01')
            receipt['requests'].append(r);save(dest/'run.json',receipt)
            if r['status']!=200: raise RuntimeError('Business request failed')
        receipt['state']=http(ports['B'],path='/state')['response']
        receipt['business_completed']=True
    except Exception as e:
        receipt.update(error=str(e),traceback=traceback.format_exc(),business_completed=False)
    finally:
        for r,p in processes.items():
            p.terminate()
            try:p.wait(timeout=15)
            except subprocess.TimeoutExpired:p.kill();p.wait()
        for log in logs:log.close()
        receipt['exit_codes']={r:p.returncode for r,p in processes.items()};receipt['finished_at']=now()
        save(dest/'run.json',receipt)
    return receipt


def run(out, repeats, java):
    out.mkdir(parents=True,exist_ok=False)
    snapshot=out/'experiment-source';snapshot.mkdir()
    for p in HERE.iterdir():
        if p.is_file():shutil.copyfile(p,snapshot/p.name)
    core_hashes={str(p.relative_to(ROOT)):sha(p) for p in CORE.iterdir() if p.suffix in ('.py','.java','.json')}
    # Frozen independent oracle is copied and hashed BEFORE building, execution, analysis.
    for name in ('expected.json','workload.json'): shutil.copyfile(HERE/name,out/name)
    save(out/'freeze.json',{'frozen_at':now(),'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
         'worktree':subprocess.check_output(['git','status','--porcelain','--untracked-files=all'],cwd=ROOT,text=True),
         'expected_sha256':sha(out/'expected.json'),'workload_sha256':sha(out/'workload.json'),
         'experiment_sources':{p.name:sha(p) for p in HERE.iterdir() if p.is_file()},'core_sources':core_hashes,
         'oracle_passed_to_analyzer':False,'source_boundary':'A external request /value and /fallback; no B sourcing'})
    command([java,'-version'],out/'java-version.log')
    build(out/'build');work=load(out/'workload.json')
    progress=[]
    # All uninstrumented cases complete before the first instrumented JVM.
    for mode in ('plain','tracefusion','mirrortaint'):
        for repeat in range(1,repeats+1):
            for c in work['cases']:
                dest=out/'captures'/mode/str(repeat)/c['id']
                r=capture(dest,out/'build',mode,c,java)
                progress.append({'mode':mode,'repeat':repeat,'case':c['id'],'business_completed':r['business_completed'],'error':r.get('error')})
                save(out/'progress.json',progress);print(progress[-1],flush=True)
                if mode=='plain' and not r['business_completed']:
                    raise RuntimeError('Uninstrumented business gate failed; retain capture and fix the harness before analyzing')
    # A new process sees only model/plans and observed events, never expected.json.
    command([sys.executable,HERE/'analyze.py','--run',out],out/'analysis.log')
    command([sys.executable,HERE/'score.py','--run',out],out/'score.log')
    changed=[p for p,h in core_hashes.items() if sha(ROOT/p)!=h]
    save(out/'completion.json',{'completed_at':now(),'core_changed':changed,'oracle_still_frozen':sha(out/'expected.json')==load(out/'freeze.json')['expected_sha256']})
    if changed:raise RuntimeError('Existing core changed')
    # Durable raw artifacts stay outside Git, with an inspectable integrity index.
    save(out/'files.sha256.json',{str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.name!='files.sha256.json'})
    print(out,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path);p.add_argument('--repeats',type=int,default=2)
    supported=ROOT/'artifacts/galette-static-baselines-20261111/runtime-base/java-8-openjdk-amd64/bin/java'
    p.add_argument('--java',default=str(supported) if supported.exists() else 'java',help='Common JVM for all three modes; must match an existing TF runtime profile')
    a=p.parse_args()
    if a.repeats<1:p.error('repeats must be positive')
    target=a.out or ROOT/'artifacts'/('cross-request-lineage-'+dt.datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8])
    run(target.resolve(),a.repeats,a.java)
