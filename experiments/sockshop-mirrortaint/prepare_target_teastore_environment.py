"""Bounded original Java11/Tomcat deployment, no TF query trials or adaptation."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time
import yaml


def prepare(home):
    out=home/'teastore-original-01';out.mkdir(parents=True,exist_ok=False)
    source=home/'external-candidates/teastore'
    def image(name):return json.loads(subprocess.check_output(['docker','image','inspect',name],text=True))[0]
    names=['tomcat:10.0.27-jdk11-temurin','mariadb:10.4.12','badouralix/curl-jq:latest']
    images={name:{'id':image(name)['Id'],'digests':image(name).get('RepoDigests',[])}for name in names}
    # Same JNDI entries as the official baseContext/start script, supplied as
    # external environment configuration. WAR and business classes unchanged.
    for role in ('registry','persistence'):
        entries={'servicePort':'8080','hostName':role,
                 'registryURL':'http://registry:8080/tools.descartes.teastore.registry/rest/services/',
                 'databaseHost':'db','databasePort':'3306','useHostIP':'false'}
        text='<Context><JarScanner scanClassPath="false"/><Loader delegate="true"/>'
        for name,value in entries.items():text+='<Environment name="'+name+'" value="'+value+'" type="java.lang.String" override="false"/>'
        text+='<Manager pathname=""/></Context>\n';(out/(role+'-context.xml')).write_text(text)
    db=source/'utilities/tools.descartes.teastore.database/setup.sql'
    services={'db':{'image':images['mariadb:10.4.12']['id'],'environment':{'MYSQL_ROOT_PASSWORD':'rootpassword'},
                    'volumes':[str(db)+':/docker-entrypoint-initdb.d/01.sql:ro'],'mem_limit':'512m'},
              'client':{'image':images['badouralix/curl-jq:latest']['id'],
                        'entrypoint':['/bin/sh','-c','while true; do sleep 60; done'],'mem_limit':'128m'}}
    artifacts=[]
    for role in ('registry','persistence'):
        name='tools.descartes.teastore.'+role
        war=source/'services'/name/'target'/(name+'.war');assert war.exists()
        services[role]={'image':images['tomcat:10.0.27-jdk11-temurin']['id'],
               'volumes':[str(war)+':/usr/local/tomcat/webapps/'+name+'.war:ro',
                          str(out/(role+'-context.xml'))+':/usr/local/tomcat/conf/context.xml:ro'],
               'environment':{'JAVA_OPTS':'-Xms32m -Xmx384m -XX:ParallelGCThreads=1 -XX:CICompilerCount=2'},
               'mem_limit':'768m'}
        artifacts.append({'path':str(war),'sha256':hashlib.sha256(war.read_bytes()).hexdigest()})
    for config in services.values():config.update(cpus=1,dns_search=['.'])
    (out/'compose.yml').write_text(yaml.safe_dump({'services':services,'networks':{'default':{'internal':True}}},sort_keys=False))
    receipt={'source':'34b37f7e7be433ce72d5f9455e66922a13116749','images':images,'original_wars':artifacts,
             'Agent':False,'tool_query_planning':False,'framework_adaptation':False,
             'configuration':'Original MariaDB credentials and JNDI host/port entries. No application class edits or custom converter.',
             'scope':'Bounded Java11/Tomcat original environment and independent compatibility probes only.'}
    (out/'before-original.json').write_text(json.dumps(receipt,indent=2)+'\n')


def start(out):
    command=['docker','compose','-p','tf2-closure-teastore-original','-f',str(out/'compose.yml')]
    with(out/'up.log').open('w')as log:subprocess.run([*command,'up','-d'],stdout=log,stderr=subprocess.STDOUT,check=True)
    probes=[]
    for i in range(90):
        result=subprocess.run([*command,'exec','-T','client','curl','-sS','--max-time','5','-w','\n%{http_code}',
           'http://persistence:8080/tools.descartes.teastore.persistence/rest/categories?start=0&max=2'],text=True,capture_output=True)
        probes.append({'attempt':i,'returncode':result.returncode,'response':result.stdout,'stderr':result.stderr})
        (out/'startup-probes.json').write_text(json.dumps(probes,indent=2)+'\n')
        if result.returncode==0 and result.stdout.endswith('200'):break
        time.sleep(2)
    with(out/'startup.log').open('w')as log:subprocess.run([*command,'logs','--no-color'],stdout=log,stderr=subprocess.STDOUT)
    print({'probes':len(probes),'last_status':probes[-1]['response'][-4:]})


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['prepare','start']);parser.add_argument('--home',type=Path,required=True)
    a=parser.parse_args();home=a.home.resolve()
    if a.stage=='prepare':prepare(home)
    else:start(home/'teastore-original-01')
