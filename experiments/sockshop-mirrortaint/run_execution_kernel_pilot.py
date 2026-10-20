#!/usr/bin/env python3
"""Original Station/Route loop pilot: full first, selective second, independent truth."""
import argparse
import json
import random
import secrets
import time
import traceback
from pathlib import Path
from build_distributed_plans import build
from plan_response_binding import plan_response
from run_planned_service import HERE,ROOT,load,save,sha
import run_response_binding_revision as old


def capture(dest,build,q,mode):
    dest.mkdir();role=q['role'];cfg=load(ROOT/'artifacts/trainticket-cost-preparation-20261016/inputs/inputs.json')
    mongo=next(k for k,v in load(ROOT/'artifacts/desktop-inputs/images-lock.json').items() if 'trainticket/ts-station-mongo' in v['services'])
    name='ts-'+role+'-service';db='ts-'+role+'-mongo';port=18820
    spec={'services':{name:{'image':cfg[role]['image'],'restart':'no','ports':['127.0.0.1:'+str(port)+':'+str(old.ROLES[role])],'mem_limit':'768m','cpus':1,'dns_search':['.'],'depends_on':[db]},
                      db:{'image':mongo,'restart':'no','volumes':['input-data:/data/db'],'mem_limit':'384m','cpus':1}},'volumes':{'input-data':{}}}
    old.observed(spec,name,role,dest,build);spec['services'][name]['environment']['JAVA_OPTS']=spec['services'][name]['environment']['JAVA_OPTS'].replace('-Dservice.mode=selective','-Dservice.mode='+mode)
    save(dest/'compose.json',spec);dep=old.Deployment(argparse.Namespace(project='tf2-execution-'+secrets.token_hex(5)),dest,dest/'compose.json');run={'status':'failed','roles':[role],'project':dep.args.project,'mode':mode,'cases':[]}
    rng=random.Random(20261020)
    try:
        save(dest/'images.json',{reference:json.loads(dep.command(['docker','image','inspect',reference]).stdout)[0] for reference in (cfg[role]['image'],mongo)})
        dep.compose('up','-d','--pull','never',timeout=180);client=old.Client(dest);deadline=time.monotonic()+240
        while time.monotonic()<deadline:
            try:client.request('GET','http://127.0.0.1:'+str(port)+'/api/v1/'+role+'service/welcome',label='readiness');break
            except Exception:time.sleep(2)
        else:raise ValueError('Original pilot readiness timeout')
        trace=secrets.token_hex(16)
        for index in range(6):
            cd=dest/('group-'+str(index));cd.mkdir();cl=old.Client(cd);message=old.context(cl,trace);docs=old.mongo_fixture(role,index,rng);old.database(dep,role,docs,cd)
            method,path=q['http'].split(' ',1)
            if role=='station':body=[d['_id'] if 'namelist' in path else d['name'] for d in docs]
            else:
                body=None;stations=docs[0]['stations'] if docs else ['MISSING-START','MISSING-END'];path=path.replace('{start}',stations[0]).replace('{terminal}',stations[-1])
            response,status=old.request_raw(cl,method,'http://127.0.0.1:'+str(port)+path,body);assert status==200
            case={'case':'group-'+str(index),'index':index,'message':message,'response':response,'http_status':status,'request_path':path,'request_body':body,'database_documents':docs};save(cd/'contract-result.json',case);run['cases'].append(case)
        dep.compose('stop','-t','20',name,timeout=40);old.verify_build(build);run['status']='business-completed'
    finally:old.cleanup(dep,run,dest)


def independent(q,case,path,rows):
    roots=[r for r in rows if r['kind']=='binding-return' and r.get('message')==case['message']];assert len(roots)==1
    sources=[r for r in rows if r['kind']=='binding-source' and r['frame']==roots[0]['frame']]
    if q['role']=='station':
        index=int(path.rsplit('/',1)[-1]);docs=case['database_documents'];request=case['request_body'];by_id='namelist' in case['request_path'];key='_id' if by_id else 'name';field='name' if by_id else 'id'
        # Source reads are paired by the actual original loop invocation order;
        # expected field is selected from original code and database facts only.
        assert len(sources)==len(request)
        present=[i for i,value in enumerate(request) if any(d[key]==value for d in docs)]
        selected=present[index] if by_id else index
        if selected not in present:return set()
        row=sources[selected];relative='/'+field
        db=next(d for d in docs if d[key]==request[selected]);wanted=db['name' if by_id else '_id']
    else:
        assert len(sources)==1;row=sources[0];start,terminal=case['request_path'].split('/')[-2:];docs=case['database_documents']
        selected=[i for i,d in enumerate(docs) if start in d['stations'] and terminal in d['stations'] and d['stations'].index(start)<d['stations'].index(terminal)]
        parts=path.split('/');doc_index=selected[int(parts[2])];relative='/'+str(doc_index)+'/'+'/'.join(parts[3:]);wanted=docs[doc_index]
        for part in parts[3:]:wanted=wanted[int(part)] if isinstance(wanted,list) else wanted[part]
    fields=[f for f in row['fields'] if f['path']==relative];assert len(fields)==1
    f=fields[0];assert f['observed'].get('value')==wanted
    return {old.source_coord(q['role'],row,f)}


def evaluate(capture,build,q):
    run=load(capture/'run.json');rows=[json.loads(s) for s in (capture/q['role']/'events.jsonl').read_text().splitlines()]
    assert run['status']=='business-completed' and run.get('cleanup_returncode')==0
    graph=old.Reconstruction(build,capture,[q['role']]);answers=[];na=0
    for case in run['cases']:
        leaves=old.leaves(case['response'],q['path']);na+=not bool(leaves)
        for path,value in leaves:
            truth=independent(q,case,path,rows);answer=graph.query(case['message'],path,q['role'],boundary=old.BOUNDARY)
            assert answer['target']['observed'].get('value')==value
            actual={old.predicted_coord(s) for s in answer['sources']}
            answers.append({'case':case['case'],'path':path,'known':answer['known'],'exact':answer['known'] and actual==truth,'expected':sorted(truth,key=str),'actual':sorted(actual,key=str),'tp':len(actual&truth) if answer['known'] else 0,'fp':len(actual-truth) if answer['known'] else 0,'fn':len(truth-actual) if answer['known'] else len(truth),'answer':answer})
    result={'id':q['id'],'mode':run['mode'],'requests':len(run['cases']),'targets':len(answers),'known':sum(x['known'] for x in answers),'exact':sum(x['exact'] for x in answers),'unknown':sum(not x['known'] for x in answers),'N/A_requests':na,'tp':sum(x['tp'] for x in answers),'fp':sum(x['fp'] for x in answers),'fn':sum(x['fn'] for x in answers),'answers':answers}
    save(capture/'evaluation.json',result);save(capture/'field-graph.json',graph.export());return result


def run(out,base,only=None):
    out.mkdir(parents=True,exist_ok=False);seal=load(HERE/'capability-comparison-62-20261020.json')
    queries=[q for q in seal['queries'] if ('Batch' in q['entry'] or 'getRouteByStartAndTerminal' in q['entry']) and q['role'] in ('station','route')]
    if only:queries=[q for q in queries if only in q['id']]
    assert queries
    current=out.parent/(out.name+'-base-build')
    inputs={}
    for role in load(base/'build.json')['inputs']:
        original_model=load(base/role/'model.json')
        # Retain original dependency DTO bytecode (notably Response), exactly as
        # the previous build did; never recompile business or wrapper classes.
        targets=[owner+'.'+c['fields'][0]['name'] for owner,c in original_model['classes'].items() if c['fields']]
        inputs[role]={'jar':str((base/role/'original.jar').resolve()),'targets':targets}
    build(current,inputs);progress=[]
    # Entire full set precedes any selective deployment.
    for mode in ('full','selective'):
        for q in queries:
            dest=out/(mode+'-'+q['id']);dest.mkdir();save(dest/'query.json',q)
            plan=plan_response(load(current/q['role']/'model.json'),q['entry'],q['target'],q['path'],execution_kernel=True)
            old.query_build(dest/'build',current,q,plan)
            try:
                capture(dest/'capture',dest/'build',q,mode);result=evaluate(dest/'capture',dest/'build',q)
                progress.append({k:v for k,v in result.items() if k!='answers'});assert result['exact']==result['targets'] and result['fp']==result['fn']==0
            except Exception as e:
                save(dest/'failure.json',{'error':str(e),'traceback':traceback.format_exc()});raise
            finally:save(out/'progress.json',progress)
            print(json.dumps(progress[-1]),flush=True)
    for q in queries:
        a=load(out/('full-'+q['id'])/'capture/run.json')['cases'];b=load(out/('selective-'+q['id'])/'capture/run.json')['cases']
        assert len(a)==len(b)
        for x,y in zip(a,b):assert all(x[k]==y[k] for k in ('request_path','request_body','database_documents','response','http_status'))
    save(out/'results.json',{'complete':True,'queries':len(queries),'deployments':len(progress),'results':progress,'remaining_candidates_untouched':29,'performance':False})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=Path);p.add_argument('--base',type=Path,default=ROOT/'artifacts/call-lifecycle-revision-20261020/base-build');p.add_argument('--only');a=p.parse_args();run(a.out.resolve(),a.base.resolve(),a.only)
