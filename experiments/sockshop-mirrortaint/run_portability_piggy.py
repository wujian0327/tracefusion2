#!/usr/bin/env python3
"""Real unmodified PiggyMetrics services; no forged identities or business mocks."""
import argparse,copy,json,secrets,time,subprocess,urllib.request,urllib.error,base64
from pathlib import Path
from run_planned_service import ROOT,load,save,sha
from run_portability_first import verify,TASK_ROOT
from sockshop import Deployment

PASSWORD='tf2-portability-fixture-only'
PORTS={'auth':23500,'account':23600,'notification':23800}
LOCAL_DEP=None


def cases():
    result={}
    for n in range(1,6):
        entries=[]
        for i,kind in enumerate(('normal','same-value-new-instance','repeat-or-overwrite','empty-list-or-map','invalid-input','normal-after-failure')):
            if n in (2,3):
                name=('port-account-'if n==2 else'port-user-')+str(1 if i==2 else i)
                body={'username':name,'password':'fixture-password-123'}
                if i==4:body={'username':'','password':''}
            elif n==1:
                body={'name':'tf2-current','note':'SAME'if i in(1,2)else'case-'+str(i),'incomes':[],'expenses':[],'saving':{'amount':0,'currency':'USD','interest':0,'deposit':False,'capitalization':False}}
                if i==4:body['saving']=None
            elif n==5:
                body={'accountName':'ignored-input-name','email':'fixture@example.invalid','scheduledNotifications':{}if i==3 else{'BACKUP':{'active':False,'frequency':'MONTHLY','lastNotified':None},'REMIND':{'active':False,'frequency':'MONTHLY','lastNotified':None}}}
                if i==4:body['email']='not-an-email'
            else:body=None
            method='GET'if n==4 else'POST'if n in(2,3)else'PUT';url={1:'/accounts/current',2:'/accounts/',3:'/uaa/users',4:'/uaa/users/current',5:'/notifications/recipients/current'}[n]
            entries.append({'case':'input-%02d'%i,'kind':'missing-authentication'if n==4 and i==4 else kind,'method':method,'path':url,'body':body,'expected_auth':'absent'if n==4 and i==4 else'ordinary user token'if n in(1,4,5)else'account-service client_credentials'})
        result['piggymetrics-'+str(n)]=entries
    return result


def request(out,label,method,url,body=None,headers=None):
    data=None if body is None else body if isinstance(body,bytes)else json.dumps(body).encode();h={'Content-Type':'application/json'};h.update(headers or {})
    if LOCAL_DEP is not None:
        parts=urllib.parse.urlsplit(url);role=next(k for k,v in PORTS.items()if v==parts.port);target='http://'+role+'-service:'+str({'auth':5000,'account':6000,'notification':8000}[role])+parts.path+('?' + parts.query if parts.query else'');cmd=['exec','-T','auth-service','curl','--noproxy','*','-sS','--max-time','25','-w','\n%{http_code}','-X',method]
        for k,v in h.items():cmd+=['-H',k+': '+v]
        if data is not None:cmd+=['--data-binary',data.decode()]
        proc=LOCAL_DEP.compose(*cmd,target,check=False);text,status=proc.stdout.rsplit('\n',1)if'\n'in proc.stdout else('', '0')
        try:value=json.loads(text)
        except Exception:value=text
        record={'method':method,'url':url,'body':body.decode()if isinstance(body,bytes)else body,'http_status':int(status or'0'),'response':value,'client_transport':'curl in original service container over isolated Docker network; no application method bypass','curl_returncode':proc.returncode};save(out/(label+'.json'),record);return record
    req=urllib.request.Request(url,data=data,headers=h,method=method)
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=25)as r:status=r.status;raw=r.read();response_headers=dict(r.headers)
    except urllib.error.HTTPError as e:status=e.code;raw=e.read();response_headers=dict(e.headers)
    except Exception as e:
        v={'method':method,'url':url,'body':body,'error':str(e),'state':'network_error'};save(out/(label+'.json'),v);return v
    try:value=json.loads(raw)
    except Exception:value=raw.decode(errors='replace')
    record={'method':method,'url':url,'body':body,'http_status':status,'response':value,'response_headers':response_headers};save(out/(label+'.json'),record);return record


def compose(root,out):
    import yaml
    original=root/'upstream/piggymetrics/config/src/main/resources/shared';config=out/'config';config.mkdir();common=yaml.safe_load((original/'application.yml').read_text());services={}
    mongo=next(k for k,v in load(ROOT/'artifacts/desktop-inputs/images-lock.json').items()if any(s.endswith('/carts-db')for s in v.get('services',[])))
    rabbit=next(k for k,v in load(ROOT/'artifacts/desktop-inputs/images-lock.json').items()if any(s.endswith('/rabbitmq')for s in v.get('services',[])))
    services['mongo']={'image':mongo,'restart':'no','environment':{'MONGO_INITDB_ROOT_USERNAME':'user','MONGO_INITDB_ROOT_PASSWORD':PASSWORD},'volumes':['db:/data/db'],'mem_limit':'384m','cpus':1}
    services['rabbitmq']={'image':rabbit,'restart':'no','mem_limit':'384m','cpus':1}
    for role in ('auth','account','notification'):
        name=role+'-service';specific=yaml.safe_load((original/(name+'.yml')).read_text());specific.setdefault('spring',{})['data']={'mongodb':{'uri':'mongodb://user:'+PASSWORD+'@mongo:27017/piggy-'+role+'?authSource=admin'}}
        specific['spring'].setdefault('cloud',{})['config']={'enabled':False};specific['spring']['cloud']['discovery']={'enabled':False};specific['eureka']={'client':{'enabled':False,'registerWithEureka':False,'fetchRegistry':False}}
        for other in ('auth-service','statistics-service'):specific[other]={'ribbon':{'listOfServers':other+(':'+str(5000 if other.startswith('auth')else 7000))}}
        specific['ribbon']={'eureka':{'enabled':False}}
        if role=='notification':specific['spring'].setdefault('mail',{})['host']='mail-disabled.invalid'
        (config/(role+'.yml')).write_text(yaml.safe_dump(specific));(config/'common.yml').write_text(yaml.safe_dump(common))
        jar=root/'business-jars'/('piggy-'+role+'.jar');port={'auth':5000,'account':6000,'notification':8000}[role]
        services[name]={'image':'maven:3.8.6-eclipse-temurin-8','entrypoint':['/approved-jdk/bin/java'],'command':['-Xms64m','-Xmx384m','-XX:ParallelGCThreads=1','-XX:CICompilerCount=2','-Dspring.cloud.config.enabled=false','-Dspring.cloud.config.fail-fast=false','-jar','/app.jar','--spring.config.additional-location=file:/runconfig/common.yml,file:/runconfig/'+role+'.yml'],'volumes':[str(jar)+':/app.jar:ro',str(config)+':/runconfig:ro','/usr/lib/jvm/java-8-openjdk-amd64:/approved-jdk:ro','/etc/java-8-openjdk:/etc/java-8-openjdk:ro'],'ports':['127.0.0.1:'+str(PORTS[role])+':'+str(port)],'environment':{'ACCOUNT_SERVICE_PASSWORD':PASSWORD,'STATISTICS_SERVICE_PASSWORD':PASSWORD,'NOTIFICATION_SERVICE_PASSWORD':PASSWORD,'MONGODB_PASSWORD':PASSWORD,'CONFIG_SERVICE_PASSWORD':PASSWORD},'depends_on':['mongo','rabbitmq'],'mem_limit':'768m','cpus':1}
    spec={'services':services,'volumes':{'db':{}},'networks':{'default':{'internal':True}}};save(out/'compose.json',spec);return spec


def run(root,attempt='attempt01',mode='original',api=None,index=None,diagnostic_single_worker=False):
    global LOCAL_DEP
    verify(root);home=(root/'diagnostics/collector-preservation'/mode/(('query-%03d'%index)if index is not None else'control') if diagnostic_single_worker else root/'original/piggymetrics'/attempt if mode=='original' else root/'tool-runs'/api/mode/(('query-%03d'%index)if index is not None else'fixed-adapter')); home.mkdir(parents=True);save(home/'cases-before-business.json',{'cases':cases(),'targets':'All scalar/null response leaves and original persistence/write arguments; void is not N/A.','oracle':'Original source projections and raw DB facts. Actual object/version/call coordinates must be supplied by separate tool witnesses; unavailable truth never counted correct.','source_sha256':sha(root/'upstream/piggymetrics/account-service/src/main/java/com/piggymetrics/account/service/AccountServiceImpl.java'),'no_algorithms_modified':True})
    spec=compose(root,home)
    if diagnostic_single_worker:
        for cfg in spec['services'].values():
            if cfg.get('command') and '-jar' in cfg['command']:cfg['command']+=['--server.tomcat.max-threads=1','--server.tomcat.min-spare-threads=1']
        save(home/'diagnostic-protocol.json',{'frozen_core':load(root/'protocol-start.json')['TF_commit'],'algorithm_or_contract_changes':False,'purpose':'Repeated normal/empty/invalid requests on one Tomcat worker; causal reproduction only, separate from the original FIRST results','no_performance_measurement':True})
    if mode!='original':
        from portability_tool_config import configure
        q=next(q for q in load(root/'task-seal.json')['entries']if q['id']==api);service={'piggy-auth':'auth-service','piggy-account':'account-service','piggy-notification':'notification-service'}[q['role']];configure(root,home,spec['services'][service],q,mode,index);save(home/'compose.json',spec)
    dep=Deployment(argparse.Namespace(project='tf2-port-piggy-'+secrets.token_hex(4)),home,home/'compose.json');result={'application':'piggymetrics','mode':mode,'agent':mode!='original','status':'environment_failed','cases':[]}
    try:
        dep.compose('up','-d','--pull','never',timeout=180);LOCAL_DEP=dep;deadline=time.monotonic()+240
        while time.monotonic()<deadline:
            r=request(home,'readiness-auth','POST','http://127.0.0.1:'+str(PORTS['auth'])+'/uaa/oauth/token',None)
            if r.get('http_status')in (400,401,403,405):break
            state=dep.compose('ps','--all','--format','json',check=False).stdout
            if '"ExitCode":134' in state or '"State":"exited"' in state:raise ValueError('Service exited before readiness; inspect preserved diagnostics')
            time.sleep(3)
        for role,path in [('account','/accounts/current'),('notification','/notifications/recipients/current')]:
            deadline=time.monotonic()+180
            while time.monotonic()<deadline:
                r=request(home,'readiness-'+role,'GET','http://127.0.0.1:'+str(PORTS[role])+path)
                if r.get('http_status')in (200,400,401,403,405):break
                state=dep.compose('ps','--all','--format','json',check=False).stdout
                if '"State":"exited"' in state:raise ValueError('Service exited before readiness; inspect preserved diagnostics')
                time.sleep(2)
            else:raise ValueError('Original service not ready: '+role)
        # Obtain normal test identities from the application's public OAuth
        # endpoint. These are fixture-owned clients, not signed-token forging.
        form=urllib.parse.urlencode({'grant_type':'client_credentials','scope':'server'}).encode();basic=base64.b64encode(('account-service:'+PASSWORD).encode()).decode();response=request(home,'fixture-server-token','POST','http://127.0.0.1:'+str(PORTS['auth'])+'/uaa/oauth/token',form,{'Authorization':'Basic '+basic,'Content-Type':'application/x-www-form-urlencoded'});assert response['http_status']==200,response;token=response['response']['access_token']
        server={'Authorization':'Bearer '+token}
        created=request(home,'fixture-create-user','POST','http://127.0.0.1:'+str(PORTS['auth'])+'/uaa/users',{'username':'tf2-current','password':'fixture-password-123'},server);assert created['http_status']in (200,201),created
        form=urllib.parse.urlencode({'grant_type':'password','username':'tf2-current','password':'fixture-password-123','scope':'ui'}).encode();basic=base64.b64encode(b'browser:').decode();response=request(home,'fixture-user-token','POST','http://127.0.0.1:'+str(PORTS['auth'])+'/uaa/oauth/token',form,{'Authorization':'Basic '+basic,'Content-Type':'application/x-www-form-urlencoded'});assert response['http_status']==200,response;user_token=response['response']['access_token']
        user={'Authorization':'Bearer '+user_token}
        seed="db=db.getSiblingDB('piggy-account');db.accounts.insert({_id:'tf2-current',_class:'com.piggymetrics.account.domain.Account',note:'fixture',incomes:[],expenses:[],saving:{amount:'0',currency:'USD',interest:'0',deposit:false,capitalization:false}});"
        proc=dep.compose('exec','-T','mongo','mongo','--quiet','-u','user','-p',PASSWORD,'--authenticationDatabase','admin','--eval',seed);(home/'fixture-database-seed.log').write_text(proc.stdout)
        snapshot="['piggy-auth','piggy-account','piggy-notification'].forEach(function(n){var d=db.getSiblingDB(n);d.getCollectionNames().sort().forEach(function(c){print(JSON.stringify({database:n,collection:c,documents:d[c].find().sort({_id:1}).toArray()}))})});"
        for q,inputs in cases().items():
            if api and q!=api:continue
            n=int(q.rsplit('-',1)[1]);role='account'if n in(1,2)else'auth'if n in(3,4)else'notification'
            for case in inputs:
                trace=secrets.token_hex(16);span=secrets.token_hex(8);headers={}if case['expected_auth']=='absent'else dict(user if n in(1,4,5)else server);headers.update(traceparent='00-'+trace+'-'+span+'-01',tracestate='research=portability')
                before=dep.compose('exec','-T','mongo','mongo','--quiet','-u','user','-p',PASSWORD,'--authenticationDatabase','admin','--eval',snapshot);(home/(q+'-'+case['case']+'-database-before.jsonl')).write_text(before.stdout)
                record=request(home,q+'-'+case['case'],case['method'],'http://127.0.0.1:'+str(PORTS[role])+case['path'],case['body'],headers);result['cases'].append({'api':q,**case,**record,'message':trace+'/'+span})
                after=dep.compose('exec','-T','mongo','mongo','--quiet','-u','user','-p',PASSWORD,'--authenticationDatabase','admin','--eval',snapshot);(home/(q+'-'+case['case']+'-database-after.jsonl')).write_text(after.stdout)
                save(home/'results.json',result)
        result['status']='business_attempts_completed'
    except Exception as e:
        import traceback
        result['error']=str(e);(home/'failure.log').write_text(traceback.format_exc())
    finally:
        try:dep.diagnostics()
        finally:cleanup=dep.compose('down','--volumes','--remove-orphans',timeout=120,check=False);result['cleanup_returncode']=cleanup.returncode;save(home/'results.json',result);LOCAL_DEP=None
    print({k:v for k,v in result.items()if k!='cases'},flush=True)


if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--root',type=Path,default=TASK_ROOT);a.add_argument('--attempt',default='attempt01');a.add_argument('--mode',default='original',choices=['original','mirrortaint','full','selective']);a.add_argument('--api');a.add_argument('--index',type=int);a.add_argument('--diagnostic-single-worker',action='store_true');v=a.parse_args();run(v.root.resolve(),v.attempt,v.mode,v.api,v.index,v.diagnostic_single_worker)
