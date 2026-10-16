#!/usr/bin/env python3
"""Fresh real Train/Route/Price/Station -> Basic travel-price validation.

Fixture facts and business/source oracle live in this driver, never in the
planner, observer or reconstructor. No service or business bytecode is replaced.
"""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import random
import secrets
import threading
import time
import uuid
from run_planned_service import ROOT,HERE,load,save,sha
from run_distributed_paths import observed,cleanup
from sockshop import Deployment,Client
from infer_distributed_fields import Reconstruction

ROLES={'station':12345,'train':14567,'route':11178,'price':16579,'basic':15680}


def freeze(out,build,inputs,seed):
    out.mkdir(parents=True,exist_ok=False);rng=random.Random(seed)
    # All values are generated only after observer/library rules and plans exist.
    manifest=load(build/'build.json');token=str(rng.getrandbits(48));train='T-'+token
    stations=[{'_id':'S-'+str(i)+'-'+token,'name':'N-'+str(i)+'-'+token,'stayTime':1,'_class':'fdse.microservice.entity.Station'} for i in range(4)]
    types=[{'_id':train,'economyClass':100,'confortClass':50,'averageSpeed':200,'_class':'train.entity.TrainType'}]
    routes=[];prices=[];cases=[]
    kinds=['normal','equal-values','permuted','short-distances','missing-route','missing-price','missing-station','missing-train']
    for i,kind in enumerate(kinds):
        rid='R-'+str(i)+'-'+token;ids=[s['_id'] for s in stations[:3]];dist=[rng.randrange(1,8),rng.randrange(10,20),rng.randrange(30,50)]
        if kind=='equal-values':dist=[7,7,7]
        if kind=='permuted':ids=[ids[2],ids[0],ids[1]]
        if kind=='short-distances':dist=dist[:1]
        route={'_id':rid,'stations':ids,'distances':dist,'startStationId':ids[0],'terminalStationId':ids[-1],'_class':'route.entity.Route'}
        if kind!='missing-route':routes.append(route)
        rate=rng.choice([.5,1.25,2.5]);first=rate if kind=='equal-values' else rate*2
        tid='MISSING-'+train if kind=='missing-train' else train
        price={'routeId':rid,'trainType':'' if kind=='missing-train' else train,'basicPriceRate':rate,'firstClassPriceRate':first,'_class':'price.entity.PriceConfig'}
        identifier=uuid.UUID(int=rng.getrandbits(128));raw=identifier.bytes
        price['_id']={'uuid_legacy_base64':base64.b64encode(raw[:8][::-1]+raw[8:][::-1]).decode(),'uuid_text':str(identifier)}
        if kind!='missing-price':prices.append(price)
        start=stations[0]['name'] if kind!='missing-station' else 'ABSENT-'+token
        body={'trip':{'trainTypeId':tid,'routeId':rid},'startingPlace':start,'endPlace':stations[2]['name']}
        fallback=kind in ('short-distances','missing-price','missing-station')
        a=ids.index(stations[0]['_id']);b=ids.index(stations[2]['_id'])
        distance=0 if kind=='missing-route' else None if fallback else dist[b]-dist[a]
        expected={'economyClass':'95.0','confortClass':'120.0'} if fallback else {'economyClass':str(float(distance*rate)),'confortClass':str(float(distance*first))}
        cases.append({'case':kind,'kind':kind,'body':body,'expected_prices':None if kind=='missing-train' else expected,'expected_status':None if kind=='missing-train' else 0 if kind=='missing-station' else 1,'expected_http_status':500 if kind=='missing-train' else 200,'fallback':fallback,'distance_indices':[] if kind=='missing-route' or fallback else [a,b]})
    for i in range(4):cases.append({**cases[i%3],'case':'repeat-'+str(i)})
    for i in range(8):cases.append({**cases[i%3],'case':'parallel-'+str(i)})
    save(out/'cases.json',cases);save(out/'database-fixtures.json',{'station':{'station':stations},'train':{'trainType':types},'route':{'routes':routes},'price':{'price_config':prices}})
    snapshot=out/'sources';snapshot.mkdir()
    for filename in [*manifest['sources'],str(Path(__file__).resolve())]:
        source=Path(filename);target=snapshot/source.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(source.read_bytes())
    save(out/'freeze.json',{'seed':seed,'build_sha256':sha(build/'build.json'),'cases_sha256':sha(out/'cases.json'),'fixtures_sha256':sha(out/'database-fixtures.json'),'inputs_sha256':sha(inputs),
        'driver_sha256':sha(Path(__file__)),'new_inputs_after_rules_build':True,'independently_authored_blind_benchmark':False,
        'query':'Two actual serialized prices entries; explicit data operands from actual Route/Price HTTP responses. Branch/index selection evidence retained separately, not scored as value origins.',
        'source_boundary':'Concrete Route.distances[index] and PriceConfig rate at response serialization; no database/internal JSON-library origin claim.'})


def check(out,build,inputs):
    f=load(out/'freeze.json');m=load(build/'build.json')
    for file,key in [(build/'build.json','build_sha256'),(out/'cases.json','cases_sha256'),(out/'database-fixtures.json','fixtures_sha256'),(inputs,'inputs_sha256'),(Path(__file__),'driver_sha256')]:
        if sha(file)!=f[key]:raise ValueError('Frozen input differs: '+str(file))
    for file,h in {**m['sources'],**m['dependencies']}.items():
        if sha(Path(file))!=h:raise ValueError('Frozen source differs: '+file)
    if sha(build/'distributed-observer.jar')!=m['agent_sha256']:raise ValueError('Observer differs')
    for role,v in m['inputs'].items():
        for name,key in [('original.jar','original_jar_sha256'),('model.json','model_sha256'),('plan.json','plan_sha256')]:
            if sha(build/role/name)!=v[key]:raise ValueError('Frozen application/plan differs')


def capture(out,build,inputs,mode):
    check(out,build,inputs);dest=out/mode;dest.mkdir();config=load(inputs);services={};volumes={}
    mongo=next(k for k,v in load(ROOT/'artifacts/desktop-inputs/images-lock.json').items() if 'trainticket/ts-station-mongo' in v['services'])
    for i,(role,port) in enumerate(ROLES.items()):
        name='ts-'+role+'-service';services[name]={'image':config[role]['image'],'platform':'linux/amd64','restart':'no','ports':['127.0.0.1:'+str(18700+i)+':'+str(port)],'dns_search':['.'],'mem_limit':'768m','cpus':1}
        if role!='basic':
            db='ts-'+role+'-mongo';volume=role+'-data';volumes[volume]={};services[db]={'image':mongo,'restart':'no','volumes':[volume+':/data/db'],'dns_search':['.'],'mem_limit':'384m','cpus':1};services[name]['depends_on']=[db]
    spec={'services':services,'volumes':volumes}
    for role in ROLES:
        observed(spec,'ts-'+role+'-service',role,dest,build)
        name='ts-'+role+'-service';services[name]['environment']['JAVA_OPTS']=services[name]['environment']['JAVA_OPTS'].replace('-Dservice.mode=selective','-Dservice.mode='+mode)
    save(dest/'compose.json',spec);dep=Deployment(argparse.Namespace(project='tf2-travel-'+secrets.token_hex(5)),dest,dest/'compose.json');result={'status':'failed','mode':mode,'cases':[],'project':dep.args.project}
    try:
        images={}
        for cfg in services.values():
            if cfg['image'] in images:continue
            r=json.loads(dep.command(['docker','image','inspect',cfg['image']]).stdout)[0]
            if cfg['image'] not in r['RepoDigests']:raise ValueError('Unpinned image')
            images[cfg['image']]={'id':r['Id'],'digests':r['RepoDigests']}
        save(dest/'images.json',images);dep.compose('up','-d','--pull','never',timeout=180)
        cl=Client(dest);deadline=time.monotonic()+240
        while time.monotonic()<deadline:
            try:
                for i,role in enumerate(ROLES):cl.request('GET','http://127.0.0.1:'+str(18700+i)+'/api/v1/'+role+'service/'+({'train':'trains/','price':'prices/'}.get(role,''))+'welcome',label='readiness')
                break
            except Exception:time.sleep(2)
        else:raise ValueError('Readiness timeout')
        db=load(out/'database-fixtures.json');audit={}
        for role,collections in db.items():
            for collection,docs in collections.items():
                script='db.'+collection+'.deleteMany({}); db.'+collection+'.insertMany(('+json.dumps(docs)+').map(function(d){if(d._id && d._id.uuid_legacy_base64)d._id=BinData(3,d._id.uuid_legacy_base64);return d;}));'
                dep.compose('exec','-T','ts-'+role+'-mongo','mongo','ts','--quiet','--eval',script)
                audit[role]=dep.compose('exec','-T','ts-'+role+'-mongo','mongo','ts','--quiet','--eval','JSON.stringify(db.'+collection+'.find({}).toArray())').stdout
        save(dest/'independent-database.json',audit)
        shared_trace=secrets.token_hex(16)
        def request(case,barrier=None):
            d=dest/case['case'];d.mkdir();client=Client(d);span=secrets.token_hex(8);message=shared_trace+'/'+span
            client.headers={'traceparent':'00-'+shared_trace+'-'+span+'-01','tracestate':'research=multisource'}
            if barrier:barrier.wait(timeout=30)
            try:response=client.request('POST','http://127.0.0.1:18704/api/v1/basicservice/basic/travel',case['body'],label='target-query')
            except RuntimeError:
                event=client.events[-1];response=event['response']
                if case['expected_http_status']!=500 or event['status']!=500 or response.get('exception')!='org.springframework.web.client.HttpClientErrorException' or '404' not in response.get('message',''):raise
            available=case['expected_http_status']==200
            passed=client.events[-1]['status']==case['expected_http_status'] and (not available or response.get('status')==case['expected_status'] and response.get('data',{}).get('prices')==case['expected_prices'])
            r={**case,'message':message,'response':response,'target_available':available,'business_passed':passed}
            save(d/'contract-result.json',r)
            if not r['business_passed']:raise ValueError('Independent business oracle differs: '+str(r))
            return r
        cases=load(out/'cases.json')
        for c in cases:
            if not c['case'].startswith('parallel-'):result['cases'].append(request(c))
        parallel=[c for c in cases if c['case'].startswith('parallel-')];barrier=threading.Barrier(len(parallel))
        with ThreadPoolExecutor(max_workers=len(parallel)) as pool:
            for f in [pool.submit(request,c,barrier) for c in parallel]:result['cases'].append(f.result())
        for role in ROLES:dep.compose('stop','-t','20','ts-'+role+'-service',timeout=40)
        check(out,build,inputs)
        result['status']='business-passed'
    finally:cleanup(dep,result,dest)


def evaluate(out,build,mode):
    dest=out/mode;run=load(dest/'run.json')
    if run['status']!='business-passed' or run['cleanup_returncode']:raise ValueError('Deployment incomplete')
    graph=Reconstruction(build,dest,list(ROLES));predictions=[];unavailable=[];tp=fp=fn=exact=unknown=0
    for c in run['cases']:
        if not c['target_available']:
            # Original train endpoint returns 404; Basic propagates an HTTP
            # failure before prices exist. Never count absent targets as exact.
            if any(r['kind']=='http-json' and r['message']==c['message'] and r['phase']=='write' and any(f['path'].startswith('/data/prices/') for f in r['fields']) for r in graph.rows['basic']):raise ValueError('Unexpected price on aborted path')
            unavailable.append({'case':c['case'],'queries':2,'status':'N/A','reason':'Original upstream train HTTP 404 aborts Basic before target creation'});continue
        # Actual RPC spans identify the source instances; fixture labels/values
        # never enter the reconstruction engine. Select independently by this
        # root's concrete parent span plus declared endpoint role.
        rpcs=[r for r in graph.rows['basic'] if r['kind']=='http-rpc-enter' and r.get('parent_message')==c['message']]
        route_rpc=[r for r in rpcs if 'ts-route-service:' in r['uri']];price_rpc=[r for r in rpcs if 'ts-price-service:' in r['uri']]
        if len(route_rpc)!=1 or len(price_rpc)!=1:raise ValueError('Independent source request instances ambiguous')
        for key,rate in [('economyClass','basicPriceRate'),('confortClass','firstClassPriceRate')]:
            answer=graph.query(c['message'],'/data/prices/'+key,'basic',boundary=[{'service':r,'kind':'http-json','phase':'write','direction':'response'} for r in ('route','price')])
            actual={(s['service'],s['message'],s['path']) for s in answer['sources']}
            expected=set()
            if not c['fallback']:
                expected.add(('price',price_rpc[0]['message'],'/data/'+rate))
                for index in c['distance_indices']:expected.add(('route',route_rpc[0]['message'],'/data/distances/'+str(index)))
            stp=len(actual&expected);sfp=len(actual-expected);sfn=len(expected-actual);tp+=stp;fp+=sfp;fn+=sfn;exact+=int(answer['known'] and actual==expected);unknown+=int(not answer['known'])
            predictions.append({'case':c['case'],'key':key,'known':answer['known'],'expected':sorted(expected),'actual':sorted(actual),'answer':answer})
    summary={'requests':len(run['cases']),'completed_price_requests':sum(c['target_available'] for c in run['cases']),'queries':len(predictions),'exact':exact,'tp':tp,'fp':fp,'fn':fn,'unknown':unknown,'target_unavailable_queries':unavailable,'events':sum(s['events'] for s in graph.stats.values()),'bytes':sum(s['log_bytes'] for s in graph.stats.values())}
    save(dest/'predictions.json',predictions);save(dest/'field-graph.json',graph.export());save(dest/'evaluation.json',summary)
    print(mode,json.dumps(summary),flush=True)
    if exact!=len(predictions) or fp or fn or unknown:raise ValueError('Origin correctness failed; unknowns retained')
    return summary


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('stage',choices=('freeze','capture','evaluate'));p.add_argument('--out',type=Path,required=True);p.add_argument('--build',type=Path,required=True);p.add_argument('--inputs',type=Path,required=True);p.add_argument('--mode',choices=('full','selective'),default='selective');p.add_argument('--seed',type=int,default=161019);a=p.parse_args()
    if a.stage=='freeze':freeze(a.out.resolve(),a.build.resolve(),a.inputs.resolve(),a.seed)
    elif a.stage=='capture':capture(a.out.resolve(),a.build.resolve(),a.inputs.resolve(),a.mode)
    else:evaluate(a.out.resolve(),a.build.resolve(),a.mode)
