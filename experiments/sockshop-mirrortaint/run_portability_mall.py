#!/usr/bin/env python3
"""Original mall-swarm public endpoints, own MySQL/Redis/Mongo/Rabbit fixtures."""
import argparse,json,secrets,time,traceback,urllib.parse
from pathlib import Path
from run_portability_first import TASK_ROOT,verify
from run_planned_service import ROOT,load,save,sha
from sockshop import Deployment

def run(root,mode='original',api=None,index=None,attempt='attempt03'):
    verify(root);out=(root/'original/mall-swarm'/attempt if mode=='original'else root/'tool-runs'/api/mode/(('query-%03d'%index)if index is not None else'fixed-adapter'));out.mkdir(parents=True)
    password='tf2-portability-fixture-only';sql=root/'upstream/mall-swarm/document/sql/mall.sql';lock=load(ROOT/'artifacts/desktop-inputs/images-lock.json');mongo=next(k for k,v in lock.items()if any(s.endswith('/carts-db')for s in v.get('services',[])));rabbit=next(k for k,v in lock.items()if any(s.endswith('/rabbitmq')for s in v.get('services',[])))
    fixture=out/'schema-and-auth-fixtures.sql';allowed=('ums_admin','ums_member','ums_permission','ums_role','ums_admin_permission_relation','ums_admin_role_relation');lines=sql.read_text().splitlines();fixture.write_text('\n'.join(l for l in lines if not l.startswith('INSERT INTO ')or any(l.startswith('INSERT INTO `'+t+'`')for t in allowed))+'\n');save(out/'database-fixture-protocol.json',{'original_sql_sha256':sha(sql),'fixture_sha256':sha(fixture),'rule':'Original unmodified DDL for all tables; only public auth/user seed tables imported, unrelated product demo rows excluded. Business JAR unchanged. Prior all-demo import failure retained; no silent data truncation.'})
    spec={'services':{'mysql':{'image':'mysql:5.7','environment':{'MYSQL_ROOT_PASSWORD':password,'MYSQL_DATABASE':'mall'},'volumes':[str(fixture)+':/docker-entrypoint-initdb.d/01-mall.sql:ro'],'mem_limit':'512m','cpus':1},'redis':{'image':'redis:latest','mem_limit':'128m','cpus':1},'mongo':{'image':mongo,'mem_limit':'384m','cpus':1},'rabbitmq':{'image':rabbit,'environment':{'RABBITMQ_DEFAULT_USER':'mall','RABBITMQ_DEFAULT_PASS':password,'RABBITMQ_DEFAULT_VHOST':'/mall'},'mem_limit':'384m','cpus':1}},'networks':{'default':{'internal':True}}}
    for role,port in [('admin',8080),('portal',8085),('auth',8401)]:
        cmd=['-Xms32m','-Xmx384m','-XX:ParallelGCThreads=1','-XX:CICompilerCount=2','-Dspring.cloud.nacos.discovery.enabled=false','-Dspring.cloud.nacos.config.enabled=false','-jar','/app.jar','--spring.datasource.url=jdbc:mysql://mysql:3306/mall?useUnicode=true&characterEncoding=utf-8&serverTimezone=Asia/Shanghai&useSSL=false','--spring.datasource.username=root','--spring.datasource.password='+password,'--spring.redis.host=redis','--spring.rabbitmq.host=rabbitmq','--spring.rabbitmq.username=mall','--spring.rabbitmq.password='+password,'--spring.rabbitmq.virtual-host=/mall','--spring.data.mongodb.host=mongo','--spring.cloud.discovery.client.simple.instances.mall-admin[0].uri=http://admin:8080','--spring.cloud.discovery.client.simple.instances.mall-portal[0].uri=http://portal:8085','--spring.cloud.discovery.client.simple.instances.mall-auth[0].uri=http://auth:8401']
        spec['services'][role]={'image':'maven:3.8.6-eclipse-temurin-8','entrypoint':['/approved-jdk/bin/java'],'command':cmd,'volumes':[str(root/'business-jars'/('mall-auth-dependency.jar'if role=='auth'else'mall-'+role+'.jar'))+':/app.jar:ro','/usr/lib/jvm/java-8-openjdk-amd64:/approved-jdk:ro','/etc/java-8-openjdk:/etc/java-8-openjdk:ro'],'networks':{'default':{'aliases':['mall-'+role]}},'depends_on':['mysql','redis','mongo','rabbitmq'],'mem_limit':'768m','cpus':1,'restart':'no'}
    if mode!='original':
        from portability_tool_config import configure
        q=next(q for q in load(root/'task-seal.json')['entries']if q['id']==api);configure(root,out,spec['services']['portal'if q['role']=='mall-portal'else'admin'],q,mode,index)
    save(out/'compose.json',spec);dep=Deployment(argparse.Namespace(project='tf2-port-mall-'+secrets.token_hex(4)),out,out/'compose.json');result={'application':'mall-swarm','mode':mode,'state':'environment_failed','cases':[]}
    def request(label,role,method,path,body=None):
        cmd=['exec','-T','admin','curl','--noproxy','*','-sS','--max-time','15','-w','\n%{http_code}','-X',method,'-H','Content-Type: application/json']
        if body is not None:cmd+=['--data-binary',json.dumps(body)]
        p=dep.compose(*cmd,'http://'+role+':'+str(8080 if role=='admin'else 8085)+path,check=False);raw,status=p.stdout.rsplit('\n',1)if'\n'in p.stdout else(p.stdout,'0')
        try:value=json.loads(raw)
        except Exception:value=raw
        r={'http_status':int(status or'0'),'response':value,'method':method,'path':path,'body':body,'curl_returncode':p.returncode};save(out/(label+'.json'),r);return r
    cases={1:('portal','POST','/sso/login?username=fixture-member&password=fixture-password',None),2:('portal','POST','/sso/register?username={name}&password=fixture-password&telephone=18800000000&authCode={code}',None),3:('admin','POST','/admin/login',{'username':'admin','password':'macro123'}),4:('admin','POST','/admin/updatePassword',{'username':'fixture-admin','oldPassword':'fixture-password','newPassword':'fixture-password'}),5:('admin','POST','/admin/update/1',{'nickName':'fixture','email':'fixture@example.invalid'})}
    save(out/'cases-before-business.json',{'apis':cases,'six_cases':['normal','same-value-new-instance','repeat-or-overwrite','empty-list-or-map','invalid-input','normal-after-failure'],'source_sql_sha256':sha(sql),'auth':'Normal application token issuance only. No security/validation disabling. Protected API denial is retained, never counted as method success.','discovery':'Nacos config/discovery disabled for equivalent direct endpoint deployment; business/security/transactions unchanged.'})
    try:
        dep.compose('up','-d','mysql','redis','mongo','rabbitmq','--pull','never',timeout=180)
        deadline=time.monotonic()+120
        while time.monotonic()<deadline:
            ready=dep.compose('exec','-T','mysql','mysql','-uroot','-p'+password,'mall','-e','SELECT COUNT(*) FROM ums_admin',check=False)
            if ready.returncode==0:break
            time.sleep(2)
        else:raise ValueError('MySQL fixture initialization failed; original import logs retained')
        dep.compose('up','-d','--pull','never',timeout=180)
        deadline=time.monotonic()+180
        while time.monotonic()<deadline:
            logs=dep.compose('logs','--no-color',check=False).stdout;(out/'startup.log').write_text(logs)
            if 'APPLICATION FAILED TO START'in logs or 'Application run failed'in logs:raise ValueError('Original app startup failed; see startup.log')
            a=request('ready-admin','admin','GET','/actuator/health');b=request('ready-portal','portal','GET','/actuator/health')
            if a['http_status']in(200,401,403)and b['http_status']in(200,401,403):break
            time.sleep(3)
        else:raise ValueError('Original services readiness failed')
        # Actual public captcha generation, read our own test Redis fixture value.
        request('fixture-captcha','portal','GET','/sso/getAuthCode?telephone=18800000000')
        keys=dep.compose('exec','-T','redis','redis-cli','--scan','--pattern','*18800000000*',check=False).stdout.splitlines();code='000000'
        if len(keys)==1:code=dep.compose('exec','-T','redis','redis-cli','--raw','GET',keys[0],check=False).stdout.strip()
        try:code=json.loads(code)
        except Exception:pass
        code=urllib.parse.quote(str(code),safe='')
        request('fixture-register-member','portal','POST','/sso/register?username=fixture-member&password=fixture-password&telephone=18800000000&authCode='+code)
        request('fixture-register-admin','admin','POST','/admin/register',{'username':'fixture-admin','password':'fixture-password','email':'fixture@example.invalid'})
        for n,(role,method,path,body)in cases.items():
            if api and api!='mall-swarm-'+str(n):continue
            for i in range(6):
                payload=dict(body)if body else None
                if payload and i==4:payload={}
                if n==3 and i==4:payload['password']='intentionally-wrong'
                path1=path.format(name='fixture-member-'+str(1 if i==2 else i),code=code if i!=4 else'bad-code')
                if n==1 and i==4:path1=path1.replace('password=fixture-password','password=wrong-password')
                if n==2:
                    phone='1880000010'+str(i);request('fixture-captcha-'+str(i),'portal','GET','/sso/getAuthCode?telephone='+phone)
                    ks=dep.compose('exec','-T','redis','redis-cli','--scan','--pattern','*'+phone+'*',check=False).stdout.splitlines();cv=dep.compose('exec','-T','redis','redis-cli','--raw','GET',ks[0],check=False).stdout.strip()if len(ks)==1 else'bad-code'
                    try:cv=json.loads(cv)
                    except Exception:pass
                    path1=path1.replace('telephone=18800000000','telephone='+phone).replace('authCode='+code,'authCode='+urllib.parse.quote(str(cv),safe=''))
                r=request('mall-swarm-%d-input-%02d'%(n,i),role,method,path1,payload);result['cases'].append({'api':'mall-swarm-'+str(n),'case':'input-%02d'%i,**r});save(out/'results.json',result)
        result['state']='business_attempts_completed_access_and_target_entry_need_witness'
    except Exception as e:result['error']=str(e);(out/'failure.log').write_text(traceback.format_exc())
    finally:
        try:dep.diagnostics()
        finally:r=dep.compose('down','--volumes','--remove-orphans',timeout=120,check=False);result['cleanup_returncode']=r.returncode;save(out/'results.json',result)
    print({k:v for k,v in result.items()if k!='cases'},flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=TASK_ROOT);p.add_argument('--mode',default='original');p.add_argument('--api');p.add_argument('--index',type=int);p.add_argument('--attempt',default='attempt03');a=p.parse_args();run(a.root,a.mode,a.api,a.index,a.attempt)
