#!/usr/bin/env python3
"""Restore isolated original ZLT DB/Redis addresses; no authentication bypass."""
import argparse,json,secrets,time,traceback
from pathlib import Path
from run_planned_service import ROOT,load,save,sha
from sockshop import Deployment

def run(home,nacos_image=None,redis_cluster=False):
 first=ROOT/'artifacts/portability-first-20261028';home.mkdir();up=first/'upstream/ZLT-MP';password='tf2-portability-fixture-only'
 mysql=[x for x in load(home.parent/'environment-images-before-tools.json')if'mysql:5.7'in x['RepoTags']][0]['Id'];redis=[x for x in load(home.parent/'environment-images-before-tools.json')if'redis:latest'in x['RepoTags']][0]['Id'];jvm=[x for x in load(home.parent/'environment-images-before-tools.json')if'maven:3.8.6-eclipse-temurin-8'in x['RepoTags']][0]['Id']
 spec={'services':{'mysql':{'image':mysql,'environment':{'MYSQL_ROOT_PASSWORD':password},'volumes':[str(up/'zlt-doc/sql/user-center.sql')+':/docker-entrypoint-initdb.d/01-user.sql:ro',str(up/'zlt-doc/sql/oauth-center.sql')+':/docker-entrypoint-initdb.d/02-auth.sql:ro'],'cpus':1,'mem_limit':'512m'},'redis':{'image':redis,'cpus':1,'mem_limit':'128m'}},'networks':{'default':{'internal':True}}}
 if redis_cluster:
  for name,port in(('redis',6379),('redis2',6380),('redis3',6381)):
   spec['services'][name]={'image':redis,'command':['redis-server','--port',str(port),'--cluster-enabled','yes','--cluster-config-file','nodes.conf','--cluster-node-timeout','5000','--requirepass',password,'--masterauth',password],'cpus':1,'mem_limit':'128m'}
 if nacos_image:spec['services']['nacos']={'image':nacos_image,'environment':{'MODE':'standalone','JVM_XMS':'128m','JVM_XMX':'384m','JVM_XMN':'128m'},'cpus':1,'mem_limit':'768m'}
 for role,port in [('zlt-user',7000),('zlt-uaa',8000)]:
  jar=first/'business-jars'/(role+'.jar');assert sha(jar)==load(first/'metadata'/role/'receipt.json')['jar_sha256']
  spec['services'][role]={'image':jvm,'entrypoint':['/approved-jdk/bin/java'],'command':['-Xms32m','-Xmx512m','-XX:ParallelGCThreads=1','-XX:CICompilerCount=2','-jar','/app.jar','--zlt.datasource.ip=mysql','--zlt.datasource.username=root','--zlt.datasource.password='+password,'--spring.redis.host=redis','--spring.redis.port=6379'],'volumes':[str(jar)+':/app.jar:ro','/usr/lib/jvm/java-8-openjdk-amd64:/approved-jdk:ro','/etc/java-8-openjdk:/etc/java-8-openjdk:ro'],'cpus':1,'mem_limit':'768m','restart':'no'}
  if nacos_image:spec['services'][role]['command']+=['--spring.cloud.nacos.discovery.server-addr=nacos:8848','--spring.cloud.nacos.config.server-addr=nacos:8848']
  if redis_cluster:spec['services'][role]['command']+=['--spring.redis.cluster.nodes=redis:6379,redis2:6380,redis3:6381','--spring.redis.password='+password]
 save(home/'protocol-before-start.json',{'agent':False,'scope':'Address/database infrastructure restoration only. Original JARs/security/transactions/configuration framework unchanged. No private signing material is read or used by the experiment driver; normal application startup only.','target_methods_executed_claim':False,'schema_sha256':{n:sha(up/'zlt-doc/sql'/n)for n in('user-center.sql','oauth-center.sql')},'original_jars':{r:sha(first/'business-jars'/(r+'.jar'))for r in('zlt-user','zlt-uaa')}});save(home/'compose.json',spec)
 dep=Deployment(argparse.Namespace(project='tf2-zlt-env-'+secrets.token_hex(5)),home,home/'compose.json');state={'agent':False,'roles':{},'target_entry_execution_verified':False}
 try:
  dep.compose('up','-d','mysql','redis',*(['redis2','redis3']if redis_cluster else[]),'--pull','never',timeout=120);deadline=time.monotonic()+120
  while time.monotonic()<deadline:
   p=dep.compose('exec','-T','mysql','mysql','-uroot','-p'+password,'-e','SELECT COUNT(*) FROM `user-center`.sys_user; SELECT COUNT(*) FROM `oauth-center`.oauth_client_details',check=False)
   if p.returncode==0:break
   time.sleep(2)
  else:raise ValueError('Original SQL fixture not ready')
  if redis_cluster:
   cluster=dep.compose('exec','-T','redis','redis-cli','-a',password,'--cluster','create','redis:6379','redis2:6380','redis3:6381','--cluster-replicas','0','--cluster-yes',check=False,timeout=90)
   (home/'redis-cluster-create.log').write_text((cluster.stdout or'')+(cluster.stderr or''))
   if cluster.returncode:raise ValueError('Own Redis cluster creation failed')
  if nacos_image:
   dep.compose('up','-d','nacos','--pull','never',timeout=120);nacos_deadline=time.monotonic()+120
   while time.monotonic()<nacos_deadline:
    probe=dep.compose('exec','-T','nacos','curl','-fsS','--max-time','5','http://127.0.0.1:8848/nacos/v1/ns/operator/metrics',check=False)
    if probe.returncode==0:break
    time.sleep(2)
   else:raise ValueError('Local Nacos readiness failed')
  dep.compose('up','-d','--pull','never',timeout=120);deadline=time.monotonic()+150
  while time.monotonic()<deadline:
   done=True
   for role in('zlt-user','zlt-uaa'):
    log=dep.compose('logs','--no-color',role,check=False).stdout;(home/(role+'-startup.log')).write_text(log)
    if'APPLICATION FAILED TO START'in log or'Application run failed'in log:state['roles'][role]='startup_failed'
    elif'Started 'in log and' seconds'in log:state['roles'][role]='started_entry_not_verified'
    else:done=False
   if done:break
   time.sleep(3)
  for role,port in [('zlt-user',7000),('zlt-uaa',8000)]:
   p=dep.compose('exec','-T',role,'curl','--noproxy','*','-sS','--max-time','10','-w','\n%{http_code}','http://127.0.0.1:'+str(port)+'/actuator/health',check=False);(home/(role+'-health.txt')).write_text((p.stdout or'')+(p.stderr or''))
  if redis_cluster:
   preflight=[]
   for api,role,port,path in [('ZLT-MP-1','zlt-uaa',8000,'/clients/list?page=1&limit=2'),('ZLT-MP-3','zlt-user',7000,'/users-anon/mobile?mobile=19900000000'),('ZLT-MP-4','zlt-user',7000,'/users?page=1&limit=2'),('ZLT-MP-5','zlt-user',7000,'/users/current')]:
    p=dep.compose('exec','-T',role,'curl','--noproxy','*','-sS','--max-time','20','-w','\n%{http_code}','http://127.0.0.1:'+str(port)+path,check=False);body,status=p.stdout.rsplit('\n',1)if'\n'in(p.stdout or'')else(p.stdout,'0');(home/(api+'-preflight-body.txt')).write_text(body or'');preflight.append({'api':api,'method':'GET','path':path,'http_status':int(status or'0'),'curl_returncode':p.returncode,'agent':False,'normal_authentication_prepared':False,'source_answer':None})
   state['read_only_preflight']=preflight;state['write_API_preflight']='Deferred until inputs/truth protocol; do not perform an unregistered write or invent an administrator token.'
 except Exception as e:state['error']=str(e);(home/'failure.log').write_text(traceback.format_exc())
 finally:
  try:dep.diagnostics()
  finally:p=dep.compose('down','--volumes','--remove-orphans',check=False,timeout=120);state['cleanup_returncode']=p.returncode;save(home/'results.json',state)
 print(state,flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--nacos-image');p.add_argument('--redis-cluster',action='store_true');a=p.parse_args();run(a.out.resolve(),a.nacos_image,a.redis_cluster)
