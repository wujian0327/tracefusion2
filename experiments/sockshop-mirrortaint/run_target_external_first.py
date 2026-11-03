"""First frozen-core runs of the sealed RuoYi/TeaStore pool.

This driver only supplies task/deployment metadata and uses the existing fixed
MT B2.2 binaries. It never changes propagation or fills missing physical facts.
"""
import argparse
import copy
import hashlib
from io import BytesIO
import json
from pathlib import Path
import secrets
import subprocess
import sys
import time
from urllib.parse import quote
from zipfile import ZipFile
import yaml
from run_planned_service import ROOT,HERE,load,save,sha

HOME=ROOT/'artifacts/target-closure-revision-20261103'
FINAL=HOME/'final-candidate-02'
BASE=FINAL/'historical/frozen-base'
OUT=HOME/'external-first-01'


def verify():
    f=load(FINAL/'historical/algorithm-freeze.json')
    for p,h in f['sources'].items():assert sha(Path(p))==h,p
    assert sha(HERE/'build_distributed_plans.py')==f['builder_sha256']
    assert load(FINAL/'capability-compatibility-receipt.json')['passed']
    return f


def metadata(app,out):
    """Import actual original class bytes, including own dependency modules."""
    from run_query_planner import JARS,command
    from plan_distributed_fields import augment
    from contract_applicability import library_inventory
    jar=HOME/('external-candidates/ruoyi-cloud/ruoyi-modules/ruoyi-system/target/ruoyi-modules-system.jar'if app=='ruoyi'else
              'external-candidates/teastore/services/tools.descartes.teastore.persistence/target/tools.descartes.teastore.persistence.war')
    prefix='com/ruoyi/'if app=='ruoyi'else'tools/descartes/teastore/'
    classes=out/'classes';classes.mkdir(parents=True);manifest={}
    def put(name,data,origin):
        if name in manifest:assert manifest[name]['sha256']==hashlib.sha256(data).hexdigest(),name
        p=classes/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
        manifest[name]={'sha256':sha(p),'origin':origin}
    with ZipFile(jar)as z:
        for name in z.namelist():
            for root in ('BOOT-INF/classes/','WEB-INF/classes/'):
                if name.startswith(root)and name.endswith('.class'):put(name[len(root):],z.read(name),name)
            if name.startswith(('BOOT-INF/lib/','WEB-INF/lib/'))and name.endswith('.jar'):
                with ZipFile(BytesIO(z.read(name)))as dep:
                    for n in dep.namelist():
                        if n.startswith(prefix)and n.endswith('.class'):put(n,dep.read(n),name+'!/'+n)
    command(['java','-cp',':'.join(map(str,[BASE/'tools',*JARS])),'QueryBytecodeModel',str(classes),str(out/'model.json')],out/'metadata.log')
    model=load(out/'model.json')
    # WAR inventory unsupported by the frozen helper is a recorded limitation;
    # no invented BOOT-INF paths or contract compatibility claims.
    if app=='ruoyi':model['library_inventory']=library_inventory(jar)
    save(out/'model.json',model);p=augment(model,None)
    save(out/'schema.json',{'json_schema':p['json_schema'],'rejected_properties':p.get('rejected_properties',[]),
                          'scope':'Existing fixed MT reflection/JSON exporter schema; not a truth rule.'})
    save(out/'original-bytecode.json',{'original':str(jar),'sha256':sha(jar),'classes':manifest,'import_only':True})
    return model


def prepare():
    freeze=verify();OUT.mkdir(exist_ok=False)
    protocol=load(HOME/'external-query-seal-v3-before-tools.json');save(OUT/'task-seal.json',protocol)
    save(OUT/'protocol-before-tools.json',{'candidate':freeze['commit'],'core_sources':freeze['sources'],
       'driver_sha256':sha(Path(__file__)),'task_sha256':sha(HOME/'external-query-seal-v3-before-tools.json'),
       'order':['ruoyi-1..6','tea-1..6'],'fixed_MT':'Native unchanged plus existing B2.2 exporter/adapter/runtime witness.',
       'original40_preserved':sha(ROOT/'MIRRORTAINT-PORTABILITY-PLAN-20261028.json'),
       'scope':'No query replacement, new model, runtime registration, source shift or performance claim. Source/target/oracle gaps remain unscored.',
       'chronology':'v1/v2 query selection before core edits; SysConfig Java owner correction v3 after core development, before any new query tool planning/run. Exact originals/digests completed during environment preparation. Not full blind preregistration.'})
    from plan_capability_policy import choose
    names=set()
    for name,key in [('kernel-contract-runtimes-20261020.json','profiles'),('foundation-value-contracts-20261028.json','jdk_profiles')]:
        for item in load(HERE/name)[key]:names.update(item['class_sha256'])
    raw=subprocess.check_output(['/usr/lib/jvm/java-8-openjdk-amd64/bin/java','-cp',str(BASE/'tools'),'JdkContractProbe',*sorted(names)],text=True)
    (OUT/'runtime-probe.txt').write_text(raw);runtime=dict(line.split('=',1)for line in raw.splitlines())
    environment={'runtime':{'java_runtime_version':runtime.pop('java.runtime.version'),'class_sha256':runtime}}
    save(OUT/'deployment-environment.json',environment)
    for app,tasks in protocol['tasks'].items():
        dest=OUT/'metadata'/app;model=metadata(app,dest)
        for q in tasks:
            place=OUT/'plans'/q['id'];place.mkdir(parents=True)
            if app=='teastore':
                save(place/'result.json',{'state':'runtime_contract_rejected','no_TF_business_deployment':True,
                    'reason':'Independent Java 11 control preserved business but frozen offline runtime check rejected: Application runtime pin differs.',
                    'additional_conditions':'Jakarta/Tomcat/JAX-RS response and JPA binding not certified by this frozen version; MT remains a separate first-run question.'})
                continue
            target,path=q['target'].split('@',1)
            if q.get('target_representation'):
                save(place/'result.json',{'state':'target_binding_unsupported','reason':q['target_representation'],'no_TF_business_deployment':True});continue
            try:
                p,route=choose(model,{'entry':q['entry'],'target':target,'path':path,'source_calls':q['source_calls']},deployment=environment)
                save(place/'plan.json',p);save(place/'route.json',route)
                save(place/'result.json',{'state':'conditional','reason':'Plan generated; actual Spring/MyBatis dispatch, decoder, converter and source pairing still require first execution.','profile':p['profile']})
            except Exception as e:save(place/'result.json',{'state':'planning_rejected','reason':str(e),'no_TF_business_deployment':True})
    verify()


def attach(cfg,out,app,q,mode):
    role='system'if app=='ruoyi'else'persistence';s=cfg['services'][role]
    cap=out/'capture';cap.mkdir();cap.chmod(0o777);options=[];mounts={}
    if mode in ('full','selective'):
        mounts={BASE/'distributed-observer.jar':'/tf2/observer.jar',OUT/'plans'/q['id']/'plan.json':'/tf2/plan.json'}
        options=['-javaagent:/tf2/observer.jar','-Dservice.plan=/tf2/plan.json','-Dservice.events=/tf2/capture/events.jsonl','-Dservice.mode='+mode]
    elif mode=='mirrortaint':
        b=ROOT/'artifacts/offline-zlt-revision-20261031/mt-class-build-04'
        native=ROOT/'artifacts/external-tools/mirrortaint/mirrorTaint.jar'
        save(out/'mt-config.json',{'entry':q['entry'],'prefix':'com/ruoyi/'if app=='ruoyi'else'tools/descartes/teastore/',
                                 'source_calls':q['source_calls']})
        mounts={native:'/tf2/mirrorTaint.jar',b/'adapter/integration-adapter.jar':'/tf2/adapter.jar',b/'capability.jar':'/tf2/capability.jar',
                b/'runtime-witness.jar':'/tf2/runtime-witness.jar',out/'mt-config.json':'/tf2/mt-config.json',OUT/'metadata'/app/'schema.json':'/tf2/schema.json'}
        options=['-javaagent:/tf2/runtime-witness.jar','-Dnative.library.events=/tf2/capture/native-library.jsonl',
          '-Dtaint.env=remote','-Dtaint.app='+('com.ruoyi'if app=='ruoyi'else'tools.descartes.teastore'),'-Dtaint.version=capability','-Duser.home=/tf2/capture',
          '-javaagent:/tf2/adapter.jar=strings','-javaagent:/tf2/adapter.jar=streams','-javaagent:/tf2/mirrorTaint.jar',
          *['-javaagent:/tf2/adapter.jar='+v for v in ('returns','sources','fields','threads','logging')],
          '-javaagent:/tf2/capability.jar','-Dcapability.config=/tf2/mt-config.json','-Dcapability.events=/tf2/capture/native-capability.jsonl',
          '-javaagent:/tf2/capability.jar=transport','-Dinstance.schema=/tf2/schema.json','-Dinstance.events=/tf2/capture/instances.jsonl']
    s['volumes'] += [str(p)+':'+name+':ro'for p,name in mounts.items()]+[str(cap)+':/tf2/capture:rw']
    if app=='ruoyi':s['command'][s['command'].index('-jar'):s['command'].index('-jar')]=options
    else:
        s['environment']['JAVA_OPTS']+=' '+' '.join(options)
        if mode=='mirrortaint':
            # Independent Java 11 preflight showed the early adapter needs the
            # unchanged native dependencies visible before native premain.
            s['environment']['CLASSPATH']='/tf2/mirrorTaint.jar'
            startup=out/'mt-setenv.sh'
            startup.write_text('CLASSPATH="${CLASSPATH:+$CLASSPATH:}/tf2/mirrorTaint.jar"\n')
            s['volumes'].append(str(startup)+':/usr/local/tomcat/bin/setenv.sh:ro')
    save(out/'binary-receipt.json',{'files':{str(p):sha(p)for p in mounts},'mode':mode,'core_agent_contract_changes':False})


def trial(app,q,mode):
    verify();out=OUT/'runs'/q['id']/mode;out.mkdir(parents=True,exist_ok=False)
    original=HOME/('ruoyi-original-03'if app=='ruoyi'else'teastore-original-02')
    cfg=yaml.safe_load((original/'compose.yml').read_text());attach(cfg,out,app,q,mode)
    save(out/'compose.json',cfg)
    from sockshop import Deployment
    dep=Deployment(argparse.Namespace(project='tf2-external-first-'+secrets.token_hex(5)),out,out/'compose.json')
    result={'query':q['id'],'mode':mode,'state':'environment_failed','cases':[]}
    try:
        deps=('mysql','redis','client')if app=='ruoyi'else('db','client')
        dep.compose('up','-d',*deps,'--pull','never',timeout=180)
        if app=='ruoyi':
            for _ in range(100):
                r=dep.compose('exec','-T','mysql','mysql','-uroot','-ptf2-disposable-fixture','-e','SELECT COUNT(*) FROM `ry-cloud`.sys_config;',check=False)
                if r.returncode==0:break
                time.sleep(2)
            else:raise RuntimeError('Original SQL initialization failed')
        dep.compose('up','-d','--pull','never',timeout=180)
        token=None
        for attempt in range(100):
            if attempt and attempt%4==0:
                logs=dep.compose('logs','--no-color','system'if app=='ruoyi'else'persistence',check=False).stdout
                failed_markers=('APPLICATION FAILED TO START','FATAL ERROR in native method','Error deploying web application archive')
                if any(marker in logs for marker in failed_markers):
                    (out/'startup-failure.log').write_text(logs)
                    raise RuntimeError('Instrumented application startup failed; complete first log retained')
            if app=='ruoyi':
                r=dep.compose('exec','-T','client','curl','-sS','--max-time','5','-H','Content-Type: application/json',
                     '--data-binary','{"username":"admin","password":"admin123"}','http://auth:9200/login',check=False)
                try:login=json.loads(r.stdout);token=login['data']['access_token']
                except (ValueError,KeyError,TypeError):token=None
                if token:save(out/'normal-login-response.json',login);break
            else:
                r=dep.compose('exec','-T','client','curl','-sS','--max-time','5','-w','\n%{http_code}',
                   'http://persistence:8080/tools.descartes.teastore.persistence/rest/categories?start=0&max=1',check=False)
                if r.returncode==0 and r.stdout.endswith('200'):break
            save(out/'readiness-last.json',{'attempt':attempt,'returncode':r.returncode,'response':r.stdout,'stderr':r.stderr});time.sleep(3)
        else:raise RuntimeError('Original normal login or TeaStore readiness failed')
        if app=='teastore':
            sql=(original/'sealed-original-requests/fixture-before-original.sql').read_text()
            r=subprocess.run(['docker','compose','-p',dep.args.project,'-f',str(dep.file),
                'exec','-T','db','mysql','-uroot','-prootpassword','teadb'],input=sql,text=True,capture_output=True)
            (out/'fixture-import.log').write_text((r.stdout or'')+(r.stderr or''));assert r.returncode==0
        for i,body in enumerate(q['inputs']):
            method,path=q['http'].split(' ',1)
            if method=='GET':
                if isinstance(body,dict):
                    for key,value in body.items():path=path.replace('{'+key+'}',quote(str(value),safe=''))
                elif '{'in path:
                    start=path.index('{');end=path.index('}',start);path=path[:start]+quote(str(body),safe='')+path[end+1:]
            digest=hashlib.sha256((q['id']+'|'+str(i)).encode()).hexdigest();message=digest[:32]+'/'+digest[32:48]
            prefix='http://system:9201'if app=='ruoyi'else'http://persistence:8080/tools.descartes.teastore.persistence'
            if app=='teastore':dep.compose('exec','-T','client','curl','-sS','--max-time','15','-X','DELETE',prefix+'/rest/cache/cache',check=False)
            args=['exec','-T','client','curl','-sS','--max-time','25','-w','\n%{http_code}',
                  '-H','traceparent: 00-'+digest[:32]+'-'+digest[32:48]+'-01']
            if token:args+=['-H','Authorization: Bearer '+token]
            if method!='GET':args+=['-X',method,'-H','Content-Type: application/json','--data-binary',json.dumps(body)]
            p=dep.compose(*args,prefix+path,check=False)
            raw,status=p.stdout.rsplit('\n',1)if'\n'in p.stdout else(p.stdout,'0')
            try:value=json.loads(raw)
            except ValueError:value=raw
            row={'query':q['id'],'case':i,'input':body,'path':path,'message':message,'http_status':int(status or 0),
                 'response':value,'returncode':p.returncode,'stderr':p.stderr}
            result['cases'].append(row);save(out/'progress.json',result)
        result['state']='captured'
    except Exception as e:result['error']=str(e)
    finally:
        try:dep.compose('stop','-t','30',*('system','auth')if app=='ruoyi'else('persistence','registry'),check=False,timeout=120);dep.diagnostics()
        finally:result['cleanup_returncode']=dep.compose('down','--volumes','--remove-orphans',check=False,timeout=120).returncode;save(out/'result.json',result)
    verify();print(q['id'],mode,result['state'],flush=True)


def run():
    protocol=load(OUT/'task-seal.json');results=[]
    for app,tasks in protocol['tasks'].items():
        for q in tasks:
            for mode in ('full','selective','mirrortaint'):
                p=load(OUT/'plans'/q['id']/'result.json')
                if mode!='mirrortaint'and not(OUT/'plans'/q['id']/'plan.json').exists():
                    results.append({'query':q['id'],'mode':mode,**p});save(OUT/'matrix-progress.json',{'complete':False,'results':results});continue
                try:trial(app,q,mode);r=load(OUT/'runs'/q['id']/mode/'result.json');results.append({'query':q['id'],'mode':mode,'state':r['state']})
                except Exception as e:results.append({'query':q['id'],'mode':mode,'state':'driver_failed','reason':str(e)})
                save(OUT/'matrix-progress.json',{'complete':False,'results':results})
    save(OUT/'matrix-progress.json',{'complete':True,'results':results,'frozen_core_unchanged':verify()['commit']})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['prepare','run']);a=p.parse_args()
    prepare()if a.stage=='prepare'else run()
