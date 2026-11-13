#!/usr/bin/env python3
"""New direct-B capture entry. Round-one files and business are immutable inputs."""
import argparse
import datetime
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid
from run import ROOT,HERE,CORE,JARS,load,save,sha,command,free_port,http,build as prior_build

JAVA=ROOT/'artifacts/galette-static-baselines-20261111/runtime-base/java-8-openjdk-amd64/bin/java'


def build(out):
    prior_build(out,entry='read')
    sys.path.insert(0,str(CORE));from plan_session_history import attach
    model=load(out/'tf/B/model.json');plan=load(out/'tf/B/plan.json');prefix='lineage/business/Cache.';arg='(Llineage/business/Cache$Request;)'
    roots=[prefix+'read'+arg+'Llineage/business/Cache$Reply;',prefix+'replace'+arg+'V',prefix+'overwrite'+arg+'V',prefix+'publish()V']
    fields='lineage/business/Cache$Request.'
    plan=attach(plan,model,roots,[fields+'value',fields+'fallback'],[fields+'op',fields+'key'])
    save(out/'tf/B/plan.json',plan)
    tf_manifest=load(out/'tf/build.json');tf_manifest['inputs']['B']['plan_sha256']=sha(out/'tf/B/plan.json')
    tf_manifest['inputs']['B']['query_config']['session_history_roots']=roots
    save(out/'tf/build.json',tf_manifest)
    command(['javac','-cp',':'.join(map(str,[out/'classes',out/'adapters',out/'tf/distributed-observer.jar',*JARS])), '-d',out/'adapters',HERE/'RoundTwoBoundary.java'],out/'round-two-boundary-compile.log')
    manifest=load(out/'manifest.json');manifest['plans']['B']=sha(out/'tf/B/plan.json');manifest['session_history_version']=1;save(out/'manifest.json',manifest)


def capture(dest,build_dir,mode,case):
    dest.mkdir(parents=True);rd=dest/'B';rd.mkdir();receipt={'mode':mode,'ingress':'B','dispatch':'split','requests':[],'business_completed':False}
    port=free_port();native=Path(load(build_dir/'manifest.json')['native']);opts=[]
    if mode=='tracefusion':opts=['-javaagent:'+str(build_dir/'tf/distributed-observer.jar'),'-Dservice.plan='+str(build_dir/'tf/B/plan.json'),'-Dservice.mode=full','-Dservice.events='+str(rd/'events.jsonl'),'-Dlineage.observer=RoundTwoBoundary']
    if mode=='mirrortaint':opts=['-javaagent:'+str(native),'-Dtaint.env=remote','-Dtaint.app=lineage.business','-Dtaint.version=cross-request-round-two','-Duser.home='+str(rd),'-Dlineage.observer=MirrorBoundary','-Dlineage.native='+str(rd/'native.jsonl')]
    cmd=[str(JAVA),'-Xms32m','-Xmx256m','-Dlineage.dispatch=split','-Dlineage.source.role=B',*opts,'-cp',':'.join(map(str,[build_dir/'classes',build_dir/'adapters',native,*JARS])),'lineage.web.Server','B',str(port),'http://127.0.0.1:'+str(port),str(rd/'http.jsonl')]
    receipt['command']=cmd;process=None
    try:
        with (rd/'process.log').open('w') as log:
            process=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,cwd=rd)
            deadline=time.monotonic()+30
            while 'READY B'not in (rd/'process.log').read_text():
                if process.poll()is not None or time.monotonic()>deadline:raise RuntimeError('B startup failed')
                time.sleep(.05)
            for body in case['requests']:
                parent='00-'+uuid.uuid4().hex+'-'+uuid.uuid4().hex[:16]+'-01'
                response=http(port,body,parent);receipt['requests'].append(response);save(dest/'run.json',receipt)
                if response['status']!=200:raise RuntimeError('Business response failed')
            receipt['state']=http(port,path='/state')['response'];receipt['business_completed']=True
    except Exception as e:receipt['error']=repr(e)
    finally:
        if process:
            process.terminate()
            try:process.wait(timeout=15)
            except subprocess.TimeoutExpired:process.kill();process.wait()
            receipt['exit_code']=process.returncode
        save(dest/'run.json',receipt)
    return receipt


def run(out,repeats,capture_only=False):
    out.mkdir(parents=True,exist_ok=False);source=out/'experiment-source';source.mkdir()
    for p in HERE.iterdir():
        if p.is_file():shutil.copyfile(p,source/p.name)
    for n in ('workload.json','expected.json','expected-round-two.json'):shutil.copyfile(HERE/n,out/n)
    save(out/'freeze.json',{'head':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'worktree':subprocess.check_output(['git','status','--porcelain'],text=True),
        'expected_sha256':sha(out/'expected-round-two.json'),'workload_sha256':sha(out/'workload.json'),'old_expected_sha256':sha(out/'expected.json'),'sources':{str(p.relative_to(ROOT)):sha(p)for p in CORE.iterdir()if p.suffix in ('.py','.java','.json')}})
    command([JAVA,'-version'],out/'java-version.log');build(out/'build')
    for mode in ('plain','tracefusion','mirrortaint'):
        for repeat in range(1,repeats+1):
            for case in load(out/'workload.json')['cases']:
                dest=out/'captures'/mode/str(repeat)/case['id'];r=capture(dest,out/'build',mode,case)
                print(mode,repeat,case['id'],r['business_completed'],r.get('error'),flush=True)
                if not r['business_completed']:raise RuntimeError('Capture failed; first failure retained')
    command([sys.executable,HERE/'replay_round_two.py','--run',out,'--out',out/'predictions'],out/'analysis.log')
    if not capture_only:
        command([sys.executable,HERE/'score_round_two.py','--run',out,'--predictions',out/'predictions','--out',out/'scores'],out/'score.log')
        command([sys.executable,HERE/'check_round_two.py','--run',out,'--predictions',out/'predictions','--scores',out/'scores','--out',out/'negative-controls'],out/'negative-controls.log')
    save(out/'files.sha256.json',{str(p.relative_to(out)):sha(p)for p in out.rglob('*')if p.is_file()and not p.is_symlink()and p.name!='files.sha256.json'})
    print(out,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--repeats',type=int,default=2);p.add_argument('--capture-only',action='store_true');a=p.parse_args()
    if a.repeats<1:p.error('repeats must be positive')
    if a.repeats<2 and not a.capture_only:p.error('Full acceptance requires two repetitions; use --capture-only for development')
    run(a.out.resolve(),a.repeats,a.capture_only)
