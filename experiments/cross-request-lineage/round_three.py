#!/usr/bin/env python3
"""Independent A->B entry; previous business and experiments are immutable."""
import argparse
import http.client as http_client
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid
import traceback
from run import ROOT,HERE,CORE,JARS,load,save,sha,command,free_port
from round_two import JAVA,build as build_two


def http(port,body=None,parent=None,path='/call'):
    """Direct real loopback HTTP; do not inherit environment proxy routing."""
    data=json.dumps(body,separators=(',',':')).encode()if body is not None else None
    headers={'Content-Type':'application/json','Connection':'close'}
    if parent:headers['traceparent']=parent
    connection=http_client.HTTPConnection('127.0.0.1',port,timeout=20)
    try:
        connection.request('POST'if data is not None else'GET',path,body=data,headers=headers)
        local=connection.sock.getsockname();peer=connection.sock.getpeername();wire=[str(local[0]),str(local[1]),str(peer[0]),str(peer[1])]
        response=connection.getresponse();raw=response.read()
        return {'traceparent':parent,'request_utf8':data.decode()if data else None,'status':response.status,'response_utf8':raw.decode(),'response':json.loads(raw),'response_headers':dict(response.getheaders()),'driver_connection':wire}
    finally:connection.close()


def build(out):
    build_two(out)
    cp=':'.join(map(str,[out/'classes',out/'adapters',out/'tf/distributed-observer.jar',load(out/'manifest.json')['native'],*JARS]))
    command(['javac','-cp',cp,'-d',out/'adapters',*[HERE/n for n in ('RoundThreeObserver.java','RoundThreeServer.java','RoundThreeBoundary.java','RoundThreeMirror.java')]],out/'round-three-compile.log')
    proof={'version':1,'scope':'blocking-http-json-one-exchange-per-connection','adapter_sha256':sha(out/'adapters/RoundThreeBoundary.class'),'server_sha256':sha(out/'adapters/RoundThreeServer.class')}
    manifest=load(out/'manifest.json');tf=load(out/'tf/build.json')
    for role in ('A','B'):
        p=out/'tf'/role/'plan.json';plan=load(p);plan['http_exchange']={**proof,'input_role':'external'if role=='A'else'intermediate'}
        if role=='B':plan['session_history'].update(version=2,scope='sequential-http-intermediate-input-and-application-roots')
        save(p,plan);manifest['plans'][role]=sha(p);tf['inputs'][role]['plan_sha256']=sha(p)
    manifest['session_history_version']=2;manifest['http_exchange']=proof;save(out/'manifest.json',manifest);save(out/'tf/build.json',tf)


def capture(dest,build,mode,case,same_trace=False):
    dest.mkdir(parents=True);ports={r:free_port()for r in ('A','B')};processes={};logs=[]
    receipt={'mode':mode,'ingress':'A','dispatch':'split','commands':{},'requests':[],'business_completed':False};native=load(build/'manifest.json')['native']
    cp=':'.join(map(str,[build/'classes',build/'adapters',build/'tf/distributed-observer.jar',native,*JARS]))
    try:
        for role in ('B','A'):
            rd=dest/role;rd.mkdir();opts=[]
            if mode=='tracefusion':opts=['-javaagent:'+str(build/'tf/distributed-observer.jar'),'-Dservice.plan='+str(build/'tf'/role/'plan.json'),'-Dservice.mode=full','-Dservice.events='+str(rd/'events.jsonl'),'-Dlineage.observer=RoundThreeBoundary']
            if mode.startswith('mirror'):
                opts=['-javaagent:'+native,'-Dtaint.env=remote','-Dtaint.app=lineage.business','-Dtaint.version=cross-request-round-three','-Duser.home='+str(rd),'-Dlineage.observer=RoundThreeMirror','-Dlineage.native='+str(rd/'native.jsonl'),'-Dlineage.mirror.local-boundaries='+str(mode=='mirror-composed').lower()]
            cmd=[JAVA,'-Xms32m','-Xmx256m','-Dlineage.source.role=A',*opts,'-cp',cp,'RoundThreeServer',role,str(ports[role]),str(ports['B']),str(rd/'http.jsonl')];receipt['commands'][role]=list(map(str,cmd))
            log=(rd/'process.log').open('w');logs.append(log);processes[role]=subprocess.Popen(list(map(str,cmd)),stdout=log,stderr=subprocess.STDOUT,cwd=rd)
            until=time.monotonic()+30
            while 'READY '+role not in(rd/'process.log').read_text():
                if processes[role].poll()is not None or time.monotonic()>until:raise RuntimeError(role+' startup failed')
                time.sleep(.05)
        trace=uuid.uuid4().hex
        for body in case['requests']:
            parent='00-'+(trace if same_trace else uuid.uuid4().hex)+'-'+uuid.uuid4().hex[:16]+'-01';r=http(ports['A'],body,parent);receipt['requests'].append(r);save(dest/'run.json',receipt)
            if r['status']!=200:raise RuntimeError('Business request failed')
        receipt['state']=http(ports['B'],path='/state')['response'];receipt['business_completed']=True
    except Exception as e:
        receipt['error']=repr(e);receipt['traceback']=traceback.format_exc()
        for role,proc in processes.items():
            try:
                dump=subprocess.run(['jstack',str(proc.pid)],capture_output=True,text=True,timeout=10);(dest/role/'failure-threads.log').write_text(dump.stdout+dump.stderr)
            except Exception as diagnostic:(dest/role/'failure-threads.log').write_text(repr(diagnostic))
    finally:
        for proc in processes.values():
            proc.terminate()
            try:proc.wait(timeout=15)
            except subprocess.TimeoutExpired:proc.kill();proc.wait()
        for f in logs:f.close()
        receipt['exit_codes']={r:p.returncode for r,p in processes.items()};save(dest/'run.json',receipt)
    return receipt


def run(out,repeats,capture_only=False):
    out.mkdir(parents=True,exist_ok=False);src=out/'experiment-source';src.mkdir()
    for p in HERE.iterdir():
        if p.is_file():shutil.copyfile(p,src/p.name)
    for n in ('workload.json','expected-round-three.json','expected-round-three-seeded-calibration.json'):shutil.copyfile(HERE/n,out/n)
    save(out/'freeze.json',{'head':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'worktree':subprocess.check_output(['git','status','--porcelain'],text=True),'expected_sha256':sha(out/'expected-round-three.json'),'seeded_expected_sha256':sha(out/'expected-round-three-seeded-calibration.json'),'workload_sha256':sha(out/'workload.json'),'core_sources':{str(p):sha(p)for p in CORE.iterdir()if p.suffix in ('.py','.java','.json')}})
    command([JAVA,'-version'],out/'java-version.log');build(out/'build')
    calibration={'id':'same-trace-no-cache','requests':[{'op':0,'key':'k','value':'SAME','fallback':'SAME'},{'op':0,'key':'k','value':'SAME','fallback':'SAME'}]}
    seeded={'id':'seeded-same-trace','requests':[{'op':1,'key':'k','value':'SAME','fallback':'SAME'},{'op':0,'key':'other','value':'SAME','fallback':'SAME'}]}
    for mode in ('plain','tracefusion','mirror-online','mirror-composed'):
        for repeat in range(1,repeats+1):
            for c in [*load(out/'workload.json')['cases'],calibration,seeded]:
                r=capture(out/'captures'/mode/str(repeat)/c['id'],out/'build',mode,c,c is calibration or c is seeded);print(mode,repeat,c['id'],r['business_completed'],r.get('error'),flush=True)
                if not r['business_completed']:raise RuntimeError('Capture failed; first failure retained')
    command([sys.executable,HERE/'replay_round_three.py','--run',out,'--out',out/'predictions'],out/'analysis.log')
    if not capture_only:
        command([sys.executable,HERE/'score_round_three.py','--run',out,'--predictions',out/'predictions','--out',out/'scores'],out/'score.log')
        command([sys.executable,HERE/'check_round_three.py','--run',out,'--predictions',out/'predictions','--scores',out/'scores','--out',out/'negative-controls'],out/'negative.log')
        command([sys.executable,HERE/'audit_round_three.py','--run',out,'--predictions',out/'predictions','--scores',out/'scores','--negatives',out/'negative-controls','--out',out/'audit'],out/'audit.log')
    save(out/'files.sha256.json',{str(p.relative_to(out)):sha(p)for p in out.rglob('*')if p.is_file()and not p.is_symlink()and p.name!='files.sha256.json'})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--repeats',type=int,default=2);p.add_argument('--capture-only',action='store_true');a=p.parse_args()
    if a.repeats<1 or a.repeats<2 and not a.capture_only:p.error('Full acceptance requires at least two independent repetitions')
    run(a.out.resolve(),a.repeats,a.capture_only)
