#!/usr/bin/env python3
"""Immutable first evaluation at five sealed create/update service entries.

Literal source projections below follow reviewed original business bytecode.
They inspect raw entry arguments, not dependency propagation or taint labels.
"""
import argparse,copy,json,uuid,base64,secrets,time,traceback
from collections import Counter
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save,sha
import run_frozen_capability_acceptance as driver
import run_response_binding_revision as business
from run_quota_capability_acceptance import qualified_options
from plan_capability_policy import choose

SEAL=HERE/'execution-closure-heldout-20261023.json'


def cases(query):
    role=query['role'];update='.update'in query['entry'];result=[]
    for i in range(6):
        ident='new-entry-%02d'%i
        if role=='station':
            body={'id':ident,'name':None if i==3 else ''if i==4 else 'same-name'if i in(1,2)else 'Station-'+str(i),'stayTime':0 if i==4 else 7+i}
            before={'_id':ident,'name':'before','stayTime':90,'_class':'fdse.microservice.entity.Station'}
            exists=not(i==1)if update else i in(1,2)
            expected=body if(not update or exists)else None
        elif role=='price':
            identifier=uuid.UUID(int=231023*100+i+1);ident=str(identifier);raw=identifier.bytes
            body={'id':ident,'routeId':'same-route'if i in(1,2)else 'Route-'+str(i),'trainType':None if i==3 else 'Train-'+str(i),'basicPriceRate':0.0 if i==4 else 2.5+i,'firstClassPriceRate':0.0 if i==4 else 2.5+i}
            before={'_id':{'uuid_legacy_base64':base64.b64encode(raw[:8][::-1]+raw[8:][::-1]).decode()},'routeId':'before','trainType':'before','basicPriceRate':90.0,'firstClassPriceRate':91.0,'_class':'price.entity.PriceConfig'}
            exists=not(i==1)if update else i in(1,2)
            expected=body if(not update or exists)else None
        else:
            # Provided IDs deliberately select the original modify/create-with-
            # supplied-ID branch; generated UUID truth is outside this suite.
            stations=['A','B','A']if i in(1,2)else ['A']if i==4 else ['A','B','C'];distances=[0,5,5]if i in(1,2)else [0]if i==4 else [0,5,12]
            body={'id':ident,'startStation':'A','endStation':'B','stationList':','.join(stations),'distanceList':','.join(map(str,distances))}
            if i==3:body['distanceList']='0'
            before={'_id':ident,'startStationId':'before','terminalStationId':'before','stations':['before'],'distances':[99],'_class':'route.entity.Route'};exists=i in(1,2)
            expected=None if i==3 else {'id':ident,'startStationId':body['startStation'],'terminalStationId':body['endStation'],'stations':stations,'distances':distances}
        result.append({'case':f'input-{i:02d}','body':body,'database_documents':[before]if exists else [],'expected_data':expected,'shape':['normal','missing-update-or-existing-create','duplicate-values','null-field-or-length-mismatch','empty-field-or-single-element','normal-following-edge'][i]})
    return result


def protocol(root):
    out=root/'heldout21-first';out.mkdir();seal=load(SEAL);assert sha(SEAL)==load(root/'seal.json')['protocol_sha256']
    groups={q['entry']:q for q in seal['queries']}
    p={'algorithm':load(root/'algorithm-freeze.json')['commit'],'seal_sha256':sha(SEAL),'queries':seal['queries'],'entry_count':5,'input_cases_by_entry':{entry:cases(q)for entry,q in groups.items()},'truth':'Literal reviewed original DTO copy/setter/constructor and split/parse projections. Source is root argument0 physical field snapshot before writes, with actual argument object, field version, frame and message. Route list elements depend on stationList/distanceList input field; no control dependencies added. Save/output is not a source. No TF graph is called to construct expected coordinates.','input_boundary':'Six cases per query, same predefined structure per entry. IDs supplied on Route/Price creation; generated-ID branch is not exercised. Null fields, missing updates, duplicate values, list length mismatch and normal-following-edge are included.','baseline':'N/A: no new-entry MirrorTaint adapter calibration in this first TF-only suite. Historical masks remain separate.','failure_policy':'No replacement or core repair after first planning. Rejections retained without forced execution; all runtime statuses retained. No retries selected by success.','experiment_source_sha256':sha(Path(__file__))}
    save(out/'protocol-before-planning.json',p);print({'truth_protocol_saved':True,'queries':21,'entries':5},flush=True)


def check(root):
    driver.HOME=root;driver.check();out=root/'heldout21-first';p=load(out/'protocol-before-planning.json');assert sha(SEAL)==p['seal_sha256'];assert sha(Path(__file__))==p['experiment_source_sha256'];assert p['algorithm']==load(root/'algorithm-freeze.json')['commit'];return p


def plan_all(root):
    p=check(root);out=root/'heldout21-first';plans=out/'plans';plans.mkdir();records=[]
    for q in p['queries']:
        r={'query':q}
        try:
            plan,policy=choose(load(root/'frozen-base'/q['role']/'model.json'),q);save(plans/(q['id']+'.json'),plan);r.update(accepted=True,profile=plan['profile'],policy=policy,plan_sha256=sha(plans/(q['id']+'.json')))
        except Exception as error:r.update(accepted=False,rejection=str(error),exception_type=type(error).__name__)
        records.append(r)
    save(plans/'planning.json',records);print({'accepted':sum(r['accepted']for r in records),'rejected':sum(not r['accepted']for r in records)},flush=True)


def capture(d,root,q,mode,inputs):
    role=q['role'];cap=d/'capture';cap.mkdir();config=load(ROOT/'artifacts/trainticket-cost-preparation-20261016/inputs/inputs.json');port={'station':19220,'route':19221,'price':19222}[role];internal=business.ROLES[role]
    mongo=next(k for k,v in load(ROOT/'artifacts/desktop-inputs/images-lock.json').items()if 'trainticket/ts-station-mongo'in v['services']);name='ts-'+role+'-service';db='ts-'+role+'-mongo'
    spec={'services':{name:{'image':config[role]['image'],'restart':'no','ports':[f'127.0.0.1:{port}:{internal}'],'dns_search':['.'],'mem_limit':'768m','cpus':1,'depends_on':[db]},db:{'image':mongo,'restart':'no','volumes':['mongo-data:/data/db'],'mem_limit':'384m','cpus':1}},'volumes':{'mongo-data':{}}}
    driver.mode_config(spec,name,role,cap,d/'build',mode);spec['services'][name]['environment']['JAVA_OPTS']=qualified_options(spec['services'][name]['environment']['JAVA_OPTS']);save(cap/'compose.json',spec)
    dep=business.Deployment(argparse.Namespace(project='tf2-newentry-'+secrets.token_hex(4)),cap,cap/'compose.json');run={'status':'failed','roles':[role],'project':dep.args.project,'mode':mode,'cases':[]}
    try:
        save(cap/'images.json',{v['image']:json.loads(dep.command(['docker','image','inspect',v['image']]).stdout)[0]for v in spec['services'].values()});dep.compose('up','-d','--pull','never',timeout=180);client=business.Client(cap);deadline=time.monotonic()+240
        while time.monotonic()<deadline:
            try:client.request('GET',f'http://127.0.0.1:{port}/api/v1/{role}service/'+('prices/'if role=='price'else '')+'welcome',label='readiness');break
            except Exception:time.sleep(2)
        else:raise ValueError('New-entry readiness timeout')
        for c in inputs:
            cd=cap/c['case'];cd.mkdir();business.database(dep,role,c['database_documents'],cd);cl=business.Client(cd);message=business.context(cl,secrets.token_hex(16));method,path=q['http'].split(' ',1);response,status=business.request_raw(cl,method,f'http://127.0.0.1:{port}'+path,c['body']);actual={**c,'message':message,'request_body':c['body'],'response':response,'http_status':status}
            assert 200<=status<300 and response['data']==c['expected_data'],(c['case'],response,c['expected_data']);run['cases'].append(actual);save(cd/'contract-result.json',actual)
        dep.compose('stop','-t','20',name,timeout=40);business.verify_build(d/'build');run['status']='business-completed'
    finally:business.cleanup(dep,run,cap)


def independent(q,c,path,rows):
    role=q['role'];rs=rows[role];roots=[r for r in rs if r['kind']=='enter'and r['method']==q['entry']and any(v['kind']=='binding-return'and v.get('message')==c['message']and v['frame']==r['frame']for v in rs)];assert len(roots)==1
    inputs=[r for r in rs if r['kind']=='binding-input'and r['frame']==roots[0]['frame']and r['argument']==0];assert len(inputs)==1;s=inputs[0]
    field=path.split('/')[2];field={'stations':'stationList','distances':'distanceList','startStationId':'startStation','terminalStationId':'endStation'}.get(field,field)if role=='route'else field
    fs=[f for f in s['fields']if f['path']=='/'+field];assert len(fs)==1 and fs[0]['observed'].get('value')==c['body'][field]
    return [business.source_coord(role,s,fs[0])]


def run(root,role):
    p=check(root);out=root/'heldout21-first';jobs=out/('runtime-'+role);jobs.mkdir();records=[];driver.independent=independent
    for mode in ('full','selective'):
        for record in load(out/'plans/planning.json'):
            q=record['query']
            if q['role']!=role:continue
            if not record['accepted']:continue
            check(root);d=jobs/(mode+'-'+q['id']);d.mkdir();business.query_build(d/'build',root/'frozen-base',q,load(out/'plans'/(q['id']+'.json')))
            try:capture(d,root,q,mode,p['input_cases_by_entry'][q['entry']]);r=driver.evaluate(d,q)
            except Exception as error:r={'query':q['id'],'mode':mode,'failure':str(error)};save(d/'failure.json',{**r,'traceback':traceback.format_exc()})
            records.append(r);save(jobs/'results.json',{'complete':False,'results':records});print(r,flush=True)
    save(jobs/'results.json',{'complete':True,'results':records})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',required=True,type=Path);p.add_argument('--stage',choices=('protocol','plan','run'),required=True);p.add_argument('--role',choices=('station','route','price'));a=p.parse_args();root=a.root.resolve()
    if a.stage=='protocol':protocol(root)
    elif a.stage=='plan':plan_all(root)
    else:run(root,a.role)
