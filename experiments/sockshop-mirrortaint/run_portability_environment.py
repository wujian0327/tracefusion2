#!/usr/bin/env python3
"""Original source-built application startup probes; explicit dependency failures.

These probes never count health/HTTP 403/404 as successful execution of a target.
No security, transaction, Seata or business validation mechanism is disabled.
"""
import argparse,concurrent.futures,json,secrets,time,traceback
from pathlib import Path
from run_portability_first import TASK_ROOT,verify,ROLES
from run_planned_service import load,save,sha
from sockshop import Deployment

def run_role(root,app,role):
    verify(root);out=root/'original'/app/('startup-'+role+'-02');out.mkdir(parents=True)
    java11=app in('goodsKill','SuperMarket');vol=[str(root/'business-jars'/(role+'.jar'))+':/app.jar:ro'];entry=['java']
    if not java11:vol+=['/usr/lib/jvm/java-8-openjdk-amd64:/approved-jdk:ro','/etc/java-8-openjdk:/etc/java-8-openjdk:ro'];entry=['/approved-jdk/bin/java']
    command=['-Xms32m','-Xmx512m','-XX:ParallelGCThreads=1','-XX:CICompilerCount=2','-jar','/app.jar'];env={'APP_PORT':'8080'}
    # Private project DNS aliases prevent historical public/IP defaults from
    # contacting unrelated machines. Missing infrastructure stays a failure.
    spec={'services':{'app':{'image':'maven:3.8.6-eclipse-temurin-'+('11'if java11 else'8'),'entrypoint':entry,'command':command,'volumes':vol,'environment':env,'cpus':1,'mem_limit':'768m','extra_hosts':['nacos:127.0.0.1','mysql:127.0.0.1','redis:127.0.0.1','mycat:127.0.0.1'],'restart':'no'}},'networks':{'default':{'internal':True}}}
    save(out/'compose.json',spec);save(out/'before-start.json',{'application':app,'role':role,'agent':False,'jar_sha256':sha(root/'business-jars'/(role+'.jar')),'runtime':'Declared JDK11 (no TF profile extension)'if java11 else'Existing approved Ubuntu OpenJDK8u504','purpose':'Dependency/configuration preparation attempt, NOT successful API coverage. Missing infra is not tool failure.','api_ids':[q['id']for q in load(root/'task-seal.json')['entries']if q['role']==role]})
    dep=Deployment(argparse.Namespace(project='tf2-port-env-'+secrets.token_hex(4)),out,out/'compose.json');result={'mode':'original','application':app,'role':role,'state':'environment_failed','target_entry_execution_verified':False}
    try:
        dep.compose('up','-d','--pull','never',timeout=90);deadline=time.monotonic()+75
        while time.monotonic()<deadline:
            info=dep.compose('ps','--all','--format','json',check=False);(out/'container-state.json').write_text(info.stdout)
            logs=dep.compose('logs','--no-color','app',check=False);(out/'startup.log').write_text((logs.stdout or'')+(logs.stderr or''))
            if 'APPLICATION FAILED TO START'in logs.stdout or 'Application run failed'in logs.stdout:break
            if 'Started 'in logs.stdout and ' seconds'in logs.stdout:
                result['state']='started_entry_not_yet_verified';break
            time.sleep(2)
        result['reason']='Original embedded configuration and dependency startup; inspect startup.log. No TF/MT instrumentation attempted before executable original control.'
        run=dep.compose('exec','-T','app',entry[0],'-version',check=False);(out/'java-version.log').write_text((run.stdout or'')+(run.stderr or''))
    except Exception as e:result['error']=str(e);(out/'failure.log').write_text(traceback.format_exc())
    finally:
        try:dep.diagnostics()
        finally:r=dep.compose('down','--volumes','--remove-orphans',timeout=90,check=False);result['cleanup_returncode']=r.returncode;save(out/'result.json',result)
    print(app,role,result['state'],flush=True);return result
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=TASK_ROOT);p.add_argument('--apps',nargs='+',default=['ZLT-MP','FEBS-Cloud','goodsKill','SuperMarket']);a=p.parse_args();jobs=[(app,r)for app in a.apps for r in dict.fromkeys(ROLES[app])]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2)as pool:
        futures=[pool.submit(run_role,a.root,app,r)for app,r in jobs]
        for f in futures:
            try:f.result()
            except Exception:traceback.print_exc()
