"""Original-only RuoYi environment preparation; no TF planning or instrumentation.

All SQL/config changes are confined to new disposable experiment services.
Authentication uses the original /login and public seed credentials.
"""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import time
import yaml

ROOT=Path(__file__).resolve().parents[2]


def prepare(home,attempt):
    out=home/attempt;out.mkdir(parents=True,exist_ok=False)
    src=home/'external-candidates/ruoyi-cloud'
    original_sql=src/'sql/ry_20260417.sql'
    (out/'01-original.sql').write_bytes(original_sql.read_bytes())
    (out/'02-repeated-values.sql').write_text("UPDATE sys_dept SET dept_name='tf_repeat' WHERE dept_id IN (101,102);\nUPDATE sys_post SET post_name='tf_repeat' WHERE post_id IN (1,2);\n")
    config={
      'spring.cloud.nacos.discovery.enabled':False,'spring.cloud.nacos.config.enabled':False,
      'spring.cloud.sentinel.enabled':False,
      'spring.cloud.discovery.client.simple.instances.ruoyi-system[0].uri':'http://system:9201',
      'spring.redis.host':'redis','spring.redis.port':6379,
      'spring.datasource.dynamic.primary':'master',
      'spring.datasource.dynamic.datasource.master.driver-class-name':'com.mysql.cj.jdbc.Driver',
      'spring.datasource.dynamic.datasource.master.url':'jdbc:mysql://mysql:3306/ry-cloud?useUnicode=true&characterEncoding=utf8&serverTimezone=UTC&useSSL=false&allowPublicKeyRetrieval=true',
      'spring.datasource.dynamic.datasource.master.username':'root',
      'spring.datasource.dynamic.datasource.master.password':'tf2-disposable-fixture',
      'mybatis.type-aliases-package':'com.ruoyi.**.domain',
      'mybatis.mapper-locations':'classpath*:mapper/**/*Mapper.xml',
      'spring.datasource.dynamic.druid.initial-size':1,'spring.datasource.dynamic.druid.min-idle':1,
      'spring.datasource.dynamic.druid.max-active':4}
    (out/'application.yml').write_text(yaml.safe_dump(config))
    def inspect(name):
        return json.loads(subprocess.check_output(['docker','image','inspect',name],text=True))[0]
    image_names=['maven:3.8.6-eclipse-temurin-8','mysql:5.7','redis:latest','badouralix/curl-jq:latest']
    images={name:{'id':inspect(name)['Id'],'digests':inspect(name).get('RepoDigests',[])}for name in image_names}
    jdk=Path('/usr/lib/jvm/java-8-openjdk-amd64').resolve()
    apps={
      'system':src/'ruoyi-modules/ruoyi-system/target/ruoyi-modules-system.jar',
      'auth':src/'ruoyi-auth/target/ruoyi-auth.jar'}
    services={
      'mysql':{'image':images['mysql:5.7']['id'],'command':['--character-set-server=utf8mb4','--collation-server=utf8mb4_unicode_ci'],
               'environment':{'MYSQL_ROOT_PASSWORD':'tf2-disposable-fixture','MYSQL_DATABASE':'ry-cloud'},
               'volumes':[str(out/'01-original.sql')+':/docker-entrypoint-initdb.d/01.sql:ro',str(out/'02-repeated-values.sql')+':/docker-entrypoint-initdb.d/02.sql:ro']},
      'redis':{'image':images['redis:latest']['id']},
      'client':{'image':images['badouralix/curl-jq:latest']['id'],'entrypoint':['/bin/sh','-c','while true; do sleep 60; done']}}
    for name,jar in apps.items():
        services[name]={'image':images['maven:3.8.6-eclipse-temurin-8']['id'],
             'volumes':[str(jar)+':/work/app.jar:ro',str(jdk)+':/opt/task-jdk:ro',str(out/'application.yml')+':/work/application.yml:ro'],
             'command':['/opt/task-jdk/bin/java','-Xms32m','-Xmx384m','-XX:ParallelGCThreads=1','-XX:CICompilerCount=2','-jar','/work/app.jar','--spring.config.additional-location=file:/work/application.yml']}
    for service in services.values():
        service.update(cpus=1,mem_limit='768m',dns_search=['.'])
    spec={'services':services,'networks':{'default':{'internal':True}}};(out/'compose.yml').write_text(yaml.safe_dump(spec,sort_keys=False))
    receipt={'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
             'stage':'original_only_environment','sealed_queries_not_TF_planned':True,
             'source_commit':'86527f4da8448a11630ea8dcd03a585cdd6565c6','images':images,
             'files':{str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in [original_sql,out/'02-repeated-values.sql',out/'application.yml',*apps.values()]},
             'discovery':'Original Spring Cloud SimpleDiscoveryClient replacing external Nacos addresses in disposable environment; no business or security code edits.',
             'authentication':'Normal original /login with public SQL seed admin/admin123; no private JWT/signing config read or forged identity.'}
    (out/'environment-before-original.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(str(out))


def start(out):
    command=['docker','compose','-p','tf2-closure-ruoyi-original','-f',str(out/'compose.yml')]
    with(out/'up.log').open('w')as log:
        subprocess.run([*command,'up','-d','mysql','redis','client'],stdout=log,stderr=subprocess.STDOUT,check=True)
    for attempt in range(90):
        probe=subprocess.run([*command,'exec','-T','mysql','mysql','-uroot','-ptf2-disposable-fixture','-e',
                             'SELECT COUNT(*) FROM `ry-cloud`.sys_config'],text=True,capture_output=True)
        if probe.returncode==0:break
        time.sleep(2)
    else:raise RuntimeError('Original SQL fixture did not initialize')
    with(out/'up-applications.log').open('w')as log:
        subprocess.run([*command,'up','-d','system','auth'],stdout=log,stderr=subprocess.STDOUT,check=True)
    statuses=[]
    for attempt in range(90):
        result=subprocess.run([*command,'exec','-T','client','curl','-sS','--max-time','5','-w','\n%{http_code}','http://system:9201/config/1'],text=True,capture_output=True)
        statuses.append({'attempt':attempt,'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
        (out/'startup-probes.json').write_text(json.dumps(statuses,indent=2)+'\n')
        if result.returncode==0 and result.stdout.endswith('200'):break
        time.sleep(2)
    with(out/'startup.log').open('w')as log:subprocess.run([*command,'logs','--no-color'],stdout=log,stderr=subprocess.STDOUT)
    print('startup probes',len(statuses),statuses[-1]['returncode'])


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['prepare','start']);parser.add_argument('--home',type=Path,required=True)
    parser.add_argument('--attempt',default='ruoyi-original-01')
    a=parser.parse_args();home=a.home.resolve()
    if a.stage=='prepare':prepare(home,a.attempt)
    else:start(home/a.attempt)
