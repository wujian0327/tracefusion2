#!/usr/bin/env python3
"""Historical Apollo proxy, original assembly JAR in three normal child profiles."""
import argparse,json,secrets,time,traceback
from pathlib import Path
from run_portability_first import TASK_ROOT,verify
from run_planned_service import load,save,sha
from sockshop import Deployment

def run(root,attempt='attempt01'):
    verify(root);out=root/'original/apollo'/attempt;out.mkdir(parents=True);password='tf2-portability-fixture-only';sql=root/'upstream/apollo/scripts/sql';fixture=out/'03-fixture.sql'
    fixture.write_text("USE ApolloPortalDB; INSERT INTO App(AppId,Name,OwnerName) VALUES('TF2Sample','same','apollo'); INSERT INTO AppNamespace(Name,AppId) VALUES('application','TF2Sample'); USE ApolloConfigDB; INSERT INTO App(AppId,Name) VALUES('TF2Sample','same'); INSERT INTO Cluster(Name,AppId) VALUES('default','TF2Sample'); INSERT INTO Namespace(AppId,ClusterName,NamespaceName) VALUES('TF2Sample','default','application'); INSERT INTO `Release`(Id,ReleaseKey,Name,AppId,ClusterName,NamespaceName,Configurations) VALUES(1,'tf2-release-1','same','TF2Sample','default','application','{}'); INSERT INTO Instance(Id,AppId,ClusterName,Ip) VALUES(1,'TF2Sample','default','127.0.0.1'); INSERT INTO InstanceConfig(InstanceId,ConfigAppId,ConfigClusterName,ConfigNamespaceName,ReleaseKey) VALUES(1,'TF2Sample','default','application','tf2-release-1'); UPDATE ServerConfig SET Value='http://config:8080/eureka/' WHERE `Key`='eureka.service.url';\n")
    services={'mysql':{'image':'mysql:5.7','environment':{'MYSQL_ROOT_PASSWORD':password},'volumes':[str(sql/'apolloconfigdb.sql')+':/docker-entrypoint-initdb.d/01-config.sql:ro',str(sql/'apolloportaldb.sql')+':/docker-entrypoint-initdb.d/02-portal.sql:ro',str(fixture)+':/docker-entrypoint-initdb.d/03-fixture.sql:ro'],'mem_limit':'512m','cpus':1}}
    for role,flag,port,db in [('config','configservice',8080,'ApolloConfigDB'),('admin','adminservice',8090,'ApolloConfigDB'),('portal','portal',8070,'ApolloPortalDB')]:
        command=['-Xms32m','-Xmx512m','-XX:ParallelGCThreads=1','-XX:CICompilerCount=2','-D'+flag+'=true','-Dapollo_profile=github,auth'if role=='portal'else'-Dapollo_profile=github','-Dspring_datasource_url=jdbc:mysql://mysql:3306/'+db+'?characterEncoding=utf8&useSSL=false','-Dspring_datasource_username=root','-Dspring_datasource_password='+password,'-Dserver.port='+str(port),'-Ddev_meta=http://config:8080','-Dlogging.file.name=/tmp/apollo.log','-jar','/app.jar']
        services[role]={'image':'maven:3.8.6-eclipse-temurin-8','entrypoint':['/approved-jdk/bin/java'],'command':command,'volumes':[str(root/'business-jars/apollo-proxy.jar')+':/app.jar:ro','/usr/lib/jvm/java-8-openjdk-amd64:/approved-jdk:ro','/etc/java-8-openjdk:/etc/java-8-openjdk:ro'],'depends_on':['mysql'],'mem_limit':'768m','cpus':1,'restart':'no'}
    spec={'services':services,'networks':{'default':{'internal':True}}};save(out/'compose.json',spec);dep=Deployment(argparse.Namespace(project='tf2-port-apollo-'+secrets.token_hex(4)),out,out/'compose.json');result={'application':'apollo','mode':'original','paper_version_reproduced':False,'state':'environment_failed','cases':[]}
    def curl(label,service,port,path,form=None):
        cmd=['exec','-T','portal','curl','--noproxy','*','-sS','--max-time','15','-w','\n%{http_code}','-b','/tmp/cookies','-c','/tmp/cookies']
        if form:cmd+=['--data',form]
        p=dep.compose(*cmd,'http://'+service+':'+str(port)+path,check=False);raw,status=p.stdout.rsplit('\n',1)if'\n'in p.stdout else(p.stdout,'0')
        try:value=json.loads(raw)
        except Exception:value=raw
        r={'http_status':int(status or'0'),'path':path,'response':value,'curl_returncode':p.returncode};save(out/(label+'.json'),r);return r
    inputs=[]
    for n in range(1,6):
        for i in range(6):
            app='TF2Missing'if i==4 else'TF2Sample';path={1:'/apps/'+app+'/envs/DEV/clusters/default/namespaces/application',2:'/apps/'+app+'/envs/DEV/clusters/default/namespaces/application/releases/active?page=0&size=10',3:'/instances/by-namespace/count?appId='+app+'&clusterName=default&namespaceName=application',4:'/apps/'+app+'/envs/DEV/clusters/default/namespaces/application/branches',5:'/envs/DEV/instances/by-release?appId='+app+'&releaseId=1&page=0&size=10'}[n];inputs.append({'api':'apollo-'+str(n),'case':'input-%02d'%i,'service':'admin'if n==3 else'portal','port':8090 if n==3 else 8070,'path':path})
    save(out/'inputs-before-business.json',{'cases':inputs,'fixture_sha256':sha(fixture),'control':'Original JAR, legitimate public default apollo account sign-in only; no auth disabling; source-built historical proxy not paper commit.'})
    try:
        dep.compose('up','-d','mysql','--pull','never',timeout=120);deadline=time.monotonic()+120
        while time.monotonic()<deadline:
            r=dep.compose('exec','-T','mysql','mysqladmin','ping','-uroot','-p'+password,check=False)
            if r.returncode==0:break
            time.sleep(2)
        else:raise ValueError('MySQL readiness failed')
        # Ensure init scripts completed, not the temporary initialization server.
        while time.monotonic()<deadline:
            r=dep.compose('exec','-T','mysql','mysql','-uroot','-p'+password,'-e',"SELECT AppId FROM ApolloConfigDB.App WHERE AppId='TF2Sample'",check=False)
            if r.returncode==0 and'TF2Sample'in r.stdout:break
            time.sleep(2)
        dep.compose('up','-d','--pull','never',timeout=180);deadline=time.monotonic()+180
        while time.monotonic()<deadline:
            logs=dep.compose('logs','--no-color',check=False).stdout;(out/'startup.log').write_text(logs)
            if 'APPLICATION FAILED TO START'in logs or'Application run failed'in logs:raise ValueError('Original app startup failed')
            r=curl('ready','portal',8070,'/signin')
            if r['http_status']in(200,302):break
            time.sleep(3)
        else:raise ValueError('Portal readiness failed')
        deadline=time.monotonic()+100
        while time.monotonic()<deadline:
            services_ready=curl('ready-admin-discovery','config',8080,'/services/admin')
            if services_ready['http_status']==200 and isinstance(services_ready['response'],list) and services_ready['response']:break
            time.sleep(3)
        else:raise ValueError('Apollo config meta service has no registered admin instance')
        curl('fixture-login','portal',8070,'/signin','username=apollo&password=admin')
        deadline=time.monotonic()+100
        while time.monotonic()<deadline:
            live=curl('ready-portal-admin-path','portal',8070,'/apps/TF2Sample/envs/DEV/clusters/default/namespaces/application/branches')
            if live['http_status']==200:break
            time.sleep(3)
        else:raise ValueError('Portal admin address cache did not become usable')
        for c in inputs:r=curl(c['api']+'-'+c['case'],c['service'],c['port'],c['path']);result['cases'].append({**c,**r})
        result['state']='business_attempts_completed_entry_and_target_generation_need_witness'
    except Exception as e:result['error']=str(e);(out/'failure.log').write_text(traceback.format_exc())
    finally:
        try:dep.diagnostics()
        finally:r=dep.compose('down','--volumes','--remove-orphans',timeout=120,check=False);result['cleanup_returncode']=r.returncode;save(out/'results.json',result)
    print({k:v for k,v in result.items()if k!='cases'},flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=TASK_ROOT);p.add_argument('--attempt',default='attempt01');a=p.parse_args();run(a.root,a.attempt)
