#!/usr/bin/env python3
"""Additional original-app development guards: filtering, fallback, repeat calls.

Queries are existing exposed families. These fixtures are not unseen-query or
431-target coverage evidence and do not touch the 29 reserved candidates.
"""
import argparse
import copy
import json
import secrets
import time
import traceback
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save,sha
import run_response_binding_revision as old
import run_execution_kernel_pilot as pilot
ORIGINAL_ORACLE=pilot.independent


def fixtures(q):
    result=[]
    if q['role']=='station':
        docs=[{'_id':'ID-A','name':'NAME-A','stayTime':7,'_class':'fdse.microservice.entity.Station'},
              {'_id':'ID-B','name':'NAME-B','stayTime':7,'_class':'fdse.microservice.entity.Station'}]
        by_id='namelist' in q['http'];a='ID-A' if by_id else 'NAME-A';b='ID-B' if by_id else 'NAME-B'
        for name,request in [('missing-first',['ABSENT',a,a]),('reordered',[b,a,b]),('all-missing',['ABSENT']),('empty',[]),('following-normal',[a,b])]:
            result.append({'case':name,'database_documents':docs,'request_body':request,'request_path':q['http'].split(' ',1)[1]})
    else:
        base={'distances':[7,7,7],'startStationId':'S0','terminalStationId':'S2','_class':'route.entity.Route'}
        scenarios=[('middle-only',[['OTHER'],['S0','S1','S2'],['S2','S0']]),
                   ('last-only',[['OTHER'],['S2','S0'],['S0','S1','S2']]),
                   ('all-filtered',[['OTHER'],['S2','S0']]),('empty',[]),
                   ('nonadjacent',[['OTHER'],['S0','S1','S2'],['S2','S0'],['S0','S1','S2']])]
        for name,stations in scenarios:
            docs=[dict(base,_id='R-'+str(i),stations=s) for i,s in enumerate(stations)]
            result.append({'case':name,'database_documents':docs,'request_body':None,'request_path':q['http'].split(' ',1)[1].replace('{start}','S0').replace('{terminal}','S2')})
    return result


def capture(dest,build,q,mode,cases):
    dest.mkdir();role=q['role'];cfg=load(ROOT/'artifacts/trainticket-cost-preparation-20261016/inputs/inputs.json')
    mongo=next(k for k,v in load(ROOT/'artifacts/desktop-inputs/images-lock.json').items() if 'trainticket/ts-station-mongo' in v['services']);name='ts-'+role+'-service';db='ts-'+role+'-mongo'
    spec={'services':{name:{'image':cfg[role]['image'],'restart':'no','ports':['127.0.0.1:18821:'+str(old.ROLES[role])],'mem_limit':'768m','cpus':1,'dns_search':['.'],'depends_on':[db]},
                      db:{'image':mongo,'restart':'no','volumes':['input-data:/data/db'],'mem_limit':'384m','cpus':1}},'volumes':{'input-data':{}}}
    old.observed(spec,name,role,dest,build);spec['services'][name]['environment']['JAVA_OPTS']=spec['services'][name]['environment']['JAVA_OPTS'].replace('-Dservice.mode=selective','-Dservice.mode='+mode)
    save(dest/'compose.json',spec);dep=old.Deployment(argparse.Namespace(project='tf2-exec-guards-'+secrets.token_hex(5)),dest,dest/'compose.json');run={'status':'failed','roles':[role],'project':dep.args.project,'mode':mode,'cases':[]}
    try:
        dep.compose('up','-d','--pull','never',timeout=180);client=old.Client(dest);deadline=time.monotonic()+240
        while time.monotonic()<deadline:
            try:client.request('GET','http://127.0.0.1:18821/api/v1/'+role+'service/welcome',label='readiness');break
            except Exception:time.sleep(2)
        else:raise ValueError('Guard readiness timeout')
        trace=secrets.token_hex(16)
        for source in cases:
            c=copy.deepcopy(source);cd=dest/c['case'];cd.mkdir();cl=old.Client(cd);c['message']=old.context(cl,trace);old.database(dep,role,c['database_documents'],cd)
            method=q['http'].split(' ',1)[0];c['response'],c['http_status']=old.request_raw(cl,method,'http://127.0.0.1:18821'+c['request_path'],c['request_body']);assert c['http_status']==200
            save(cd/'contract-result.json',c);run['cases'].append(c)
        dep.compose('stop','-t','20',name,timeout=40);old.verify_build(build);run['status']='business-completed'
    finally:old.cleanup(dep,run,dest)


def independent(q,case,path,rows):
    if q['role']=='route':return ORIGINAL_ORACLE(q,case,path,rows)
    root=next(r for r in rows if r['kind']=='binding-return' and r.get('message')==case['message'])['frame'];docs=case['database_documents'];by_id='namelist' in case['request_path'];key='_id' if by_id else 'name';field='name' if by_id else 'id';request=case['request_body']
    present=[i for i,x in enumerate(request) if any(d[key]==x for d in docs)];index=int(path.rsplit('/',1)[-1]);selected=present[index] if by_id else index
    if selected not in present:return set()
    calls=[r for r in rows if r.get('frame')==root and r['kind']=='collection-call-enter' and 'Repository.findBy' in r['callee']];assert len(calls)==len(request)
    call=calls[selected];end=next(r for r in rows if r.get('frame')==root and r['kind']=='collection-call-exit' and r['pc']==call['pc'] and r['seq']>call['seq'])
    sources=[r for r in rows if r['kind']=='binding-source' and r.get('frame')==root and call['seq']<r['seq']<end['seq']];assert len(sources)==1;source=sources[0]
    f=next(f for f in source['fields'] if f['path']=='/'+field);db=next(d for d in docs if d[key]==request[selected]);assert f['observed']['value']==db['name' if by_id else '_id']
    return {old.source_coord(q['role'],source,f)}


def run(out,base):
    from plan_response_binding import plan_response
    out.mkdir(parents=True,exist_ok=False)
    queries=[q for q in load(HERE/'capability-comparison-62-20261020.json')['queries'] if q['role'] in ('station','route') and ('Batch' in q['entry'] or 'getRouteByStartAndTerminal' in q['entry'])]
    # Save all fixtures and source selection rules before new business execution.
    save(out/'protocol.json',{'queries':queries,'fixtures':{q['id']:fixtures(q) for q in queries},'scope':'Development guards on exposed entries; same original source boundary. No unseen-query claim.'})
    original=pilot.independent;pilot.independent=independent;results=[]
    try:
        for mode in ('full','selective'):
            for q in queries:
                dest=out/(mode+'-'+q['id']);dest.mkdir();source=dest/'build'
                plan=plan_response(load(base/q['role']/'model.json'),q['entry'],q['target'],q['path'],execution_kernel=True)
                old.query_build(source,base,q,plan)
                try:
                    capture(dest/'capture',source,q,mode,fixtures(q));result=pilot.evaluate(dest/'capture',source,q);assert result['exact']==result['targets'] and not result['unknown'] and result['fp']==result['fn']==0
                    results.append({k:v for k,v in result.items() if k!='answers'});print(json.dumps(results[-1]),flush=True)
                except Exception as e:save(dest/'failure.json',{'error':str(e),'traceback':traceback.format_exc()});raise
                finally:save(out/'progress.json',results)
    finally:pilot.independent=original
    save(out/'results.json',{'complete':True,'results':results,'new_query_families':0,'scope':'Additional original-app guards, separate from the original 431-target matrix'})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=Path);p.add_argument('--base-build',required=True,type=Path);a=p.parse_args();run(a.out.resolve(),a.base_build.resolve())
