#!/usr/bin/env python3
"""Real requests for two applications with one immutable distributed observer."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import random
import secrets
import shutil
import subprocess
import threading
import time
import urllib.request
from run_planned_service import HERE,ROOT,save,load,sha
from host import prepare,submit
from flowdist_full_order import CachedDeployment
from sockshop import Deployment,Client


def freeze(out,build,seed):
    out.mkdir(parents=True,exist_ok=False);rng=random.Random(seed);cases=load(HERE/'cases.json')['cases']
    for i in range(10):cases.append({'id':'new-'+str(i),'items':[{'key':str(j),'quantity':rng.randint(1,3),'unitPrice':rng.choice([0.,1.25,2.5,5.])} for j in range(rng.randint(0,4))],'expected_target':True})
    station=[{'id':'Success','name':'Success','stayTime':1}, {'id':'ID-OTHER','name':'NAME-OTHER','stayTime':1}]
    station += [{'id':'ID-'+str(i),'name':'NAME-'+str(i),'stayTime':i+1} for i in range(6)]
    train_cases=[{'case':'station-'+str(i),'name':s['name'],'expected_id':s['id']} for i,s in enumerate(station)]
    train_cases += [{'case':'repeat-'+str(i),'name':'Success','expected_id':'Success'} for i in range(4)]
    train_cases += [{'case':'new-'+str(i),'name':station[k]['name'],'expected_id':station[k]['id']} for i in range(10) for k in [rng.randrange(len(station))]]
    train_cases += [{'case':'parallel-'+str(i),'name':'Success','expected_id':'Success'} for i in range(8)]
    train_cases += [{'case':'missing','name':'DOES-NOT-EXIST','expected_id':None}]
    save(out/'cases.json',{'sockshop':cases,'stations':station,'trainticket':train_cases})
    save(out/'freeze.json',{'build':str(build),'build_sha256':sha(build/'build.json'),'cases_sha256':sha(out/'cases.json'),'seed':seed,
        'query_contracts':['Sock Shop Carts response fields to Orders.total and returned items; outbound Shipment fields round-trip via Shipping.',
                           'Train Ticket Station decoded entity.id through response.data, Basic and TicketInfo; missing station gives constant null.'],
        'new_inputs':'Generated after collector/plan freeze; not an independently authored blind benchmark.'})


def check(out,build):
    f=load(out/'freeze.json');b=load(build/'build.json')
    if sha(build/'build.json')!=f['build_sha256'] or sha(out/'cases.json')!=f['cases_sha256']:raise ValueError('Frozen inputs changed')
    for path,expected in {**b['sources'],**b['dependencies']}.items():
        if sha(Path(path))!=expected:raise ValueError('Frozen analysis/observer source changed: '+path)
    if sha(build/'distributed-observer.jar')!=b['agent_sha256']:raise ValueError('Collector changed')
    for role,m in b['inputs'].items():
        for file,key in [('original.jar','original_jar_sha256'),('plan.json','plan_sha256'),('model.json','model_sha256')]:
            if sha(build/role/file)!=m[key]:raise ValueError('Frozen application/plan changed')


def observed(spec,role,brole,dest,build):
    cfg=spec['services'][role];capture=dest/brole;capture.mkdir();capture.chmod(0o777)
    cfg.setdefault('volumes',[]).extend([str(build/brole/'original.jar')+':/tf2/app.jar:ro',str(build/'distributed-observer.jar')+':/tf2/observer.jar:ro',str(build/brole/'plan.json')+':/tf2/plan.json:ro',str(capture)+':/tf2/capture:rw'])
    cfg['entrypoint']=['sh','-c','exec java $$JAVA_OPTS -jar /tf2/app.jar']
    cfg.setdefault('environment',{})['JAVA_OPTS']='-Xms32m -Xmx256m -Djava.security.egd=file:/dev/urandom -Dspring.zipkin.enabled=false -javaagent:/tf2/observer.jar -Dservice.plan=/tf2/plan.json -Dservice.events=/tf2/capture/events.jsonl -Dservice.mode=selective'


def cleanup(dep,result,dest):
    dep.diagnostics();r=dep.compose('down','--volumes','--remove-orphans',timeout=90,check=False);result['cleanup_returncode']=r.returncode;save(dest/'run.json',result)


def capture_sockshop(out,build):
    check(out,build);dest=out/'sockshop';dest.mkdir();spec=load(ROOT/'scenarios/sockshop/compose.json')
    spec['networks']={'default':{'ipam':{'config':[{'subnet':'10.254.249.0/24'}]}}}
    for cfg in spec['services'].values():cfg['restart']='no'
    for role,port in [('front-end',18580),('carts',18581),('orders',18582),('shipping',18583)]:spec['services'][role]['ports']=['127.0.0.1:'+str(port)+':'+str(8079 if role=='front-end' else 80)]
    spec['services']['rabbitmq']['environment']={'RABBITMQ_SERVER_ADDITIONAL_ERL_ARGS':'+S 2:2 +A 8'}
    for role in ('orders','carts','shipping'):observed(spec,role,role,dest,build)
    # Sock Shop image JAR defaults to port 80 through its packaged configuration.
    for role in ('orders','carts','shipping'):spec['services'][role]['entrypoint'][2]+=' --port=80'
    save(dest/'compose.json',spec);dep=CachedDeployment(argparse.Namespace(project='tf2-paths-'+secrets.token_hex(5),ready_timeout=180),dest,dest/'compose.json');result={'status':'failed','cases':[],'project':dep.args.project}
    try:
        dep.start()
        def run_case(case,name,shared=False):
            p=dest/name;prepared=prepare(case,name,p,'http://127.0.0.1:18580','http://127.0.0.1:18581',shared=shared);message=secrets.token_hex(16);prepared[1].headers['X-TraceFusion-Message']=message;prepared[-1]['message']=message;save(p/'query-contract.json',prepared[-1]);return prepared
        for case in load(out/'cases.json')['sockshop']:
            prepared=run_case(case,case['id']);r=submit(prepared,'http://127.0.0.1:18582',dest/case['id']);r['message']=prepared[-1]['message'];result['cases'].append(r)
            if not r['business_passed']:raise ValueError(r)
        prepared=[run_case(load(out/'cases.json')['sockshop'][0],'parallel-'+str(i),True) for i in range(8)];barrier=threading.Barrier(8)
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures=[pool.submit(submit,p,'http://127.0.0.1:18582',dest/('parallel-'+str(i)),barrier) for i,p in enumerate(prepared)]
            for p,f in zip(prepared,futures):
                r=f.result();r['message']=p[-1]['message'];result['cases'].append(r)
                if not r['business_passed']:raise ValueError(r)
        for role in ('orders','carts','shipping'):dep.compose('stop','-t','20',role,timeout=35)
        result['status']='business-passed';print('Sock Shop',len(result['cases']),'requests passed',flush=True)
    finally:cleanup(dep,result,dest)


def capture_train(out,build):
    check(out,build);dest=out/'trainticket';dest.mkdir();manifest=load(ROOT/'artifacts/real-path-expansion-preflight-20261015/images.json');ports={'station':12345,'basic':15680,'ticketinfo':15681}
    services={}
    for role,port in ports.items():
        image=manifest[role]['digests'][0];services['ts-'+role+'-service']={'image':image,'platform':'linux/amd64','restart':'no','ports':['127.0.0.1:'+str(18600+list(ports).index(role))+':'+str(port)]}
    services['ts-station-mongo']={'image':'mongo:4.4','restart':'no','volumes':['station-data:/data/db']}
    spec={'services':services,'volumes':{'station-data':{}},'networks':{'default':{'ipam':{'config':[{'subnet':'10.254.249.0/24'}]}}}}
    for role in ports:observed(spec,'ts-'+role+'-service',role,dest,build)
    spec['services']['ts-station-service']['depends_on']=['ts-station-mongo']
    save(dest/'compose.json',spec);dep=Deployment(argparse.Namespace(project='tf2-train-paths-'+secrets.token_hex(5)),dest,dest/'compose.json');result={'status':'failed','cases':[],'project':dep.args.project}
    try:
        images={}
        for cfg in spec['services'].values():
            info=json.loads(dep.command(['docker','image','inspect',cfg['image']]).stdout)[0];images[cfg['image']]={'id':info['Id'],'digests':info.get('RepoDigests')};cfg['image']=info['RepoDigests'][0]
        save(dest/'images.json',images);save(dest/'compose.lock.json',spec);dep.file=dest/'compose.lock.json';dep.compose('up','-d','--pull','never',timeout=150)
        client=Client(dest);deadline=time.monotonic()+180
        while time.monotonic()<deadline:
            try:
                for i,role in enumerate(ports):client.request('GET','http://127.0.0.1:'+str(18600+i)+'/api/v1/'+role+'service/welcome',label='readiness')
                break
            except Exception:time.sleep(3)
        else:raise ValueError('Train Ticket readiness timeout')
        # Original CRUD requires an administrator. Initialize only our fresh lab
        # database, leaving the application's authentication and business code
        # intact. The evaluated path is its public read API.
        fixtures=[{'_id':s['id'],'name':s['name'],'stayTime':s['stayTime'],'_class':'fdse.microservice.entity.Station'} for s in load(out/'cases.json')['stations']]
        save(dest/'database-fixtures.json',fixtures)
        dep.compose('exec','-T','ts-station-mongo','mongo','ts','--quiet','--eval','db.station.insertMany('+json.dumps(fixtures)+');')
        # Independent database facts, separate from collector input and engine.
        audit=dep.compose('exec','-T','ts-station-mongo','mongo','ts','--quiet','--eval','JSON.stringify(db.station.find({},{_id:1,name:1,stayTime:1}).toArray())').stdout
        (dest/'independent-database.json').write_text(audit)
        def run_case(c,barrier=None):
            d=dest/c['case'];d.mkdir();cl=Client(d);message=secrets.token_hex(16);cl.headers={'X-TraceFusion-Message':message}
            if barrier:barrier.wait(timeout=30)
            response=cl.request('GET','http://127.0.0.1:18602/api/v1/ticketinfoservice/ticketinfo/'+c['name'],'target-query')
            expected_status=0 if c['expected_id'] is None else 1
            if response.get('status')!=expected_status or response.get('data')!=c['expected_id']:raise ValueError('Independent business oracle differs: '+str(response))
            r={**c,'message':message,'response':response,'business_passed':True};save(d/'contract-result.json',r);return r
        cases=load(out/'cases.json')['trainticket']
        for c in cases:
            if not c['case'].startswith('parallel-'):result['cases'].append(run_case(c))
        parallel=[c for c in cases if c['case'].startswith('parallel-')];barrier=threading.Barrier(len(parallel))
        with ThreadPoolExecutor(max_workers=len(parallel)) as pool:
            for f in [pool.submit(run_case,c,barrier) for c in parallel]:result['cases'].append(f.result())
        for role in ports:dep.compose('stop','-t','20','ts-'+role+'-service',timeout=35)
        result['status']='business-passed';print('Train Ticket',len(result['cases']),'requests passed',flush=True)
    finally:cleanup(dep,result,dest)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('stage',choices=('freeze','sockshop','trainticket'));p.add_argument('--out',type=Path,required=True);p.add_argument('--build',type=Path,required=True);p.add_argument('--seed',type=int,default=151028);a=p.parse_args()
    if a.stage=='freeze':freeze(a.out.resolve(),a.build.resolve(),a.seed)
    elif a.stage=='sockshop':capture_sockshop(a.out.resolve(),a.build.resolve())
    else:capture_train(a.out.resolve(),a.build.resolve())
