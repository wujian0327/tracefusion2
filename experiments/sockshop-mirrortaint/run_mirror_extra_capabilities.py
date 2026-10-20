#!/usr/bin/env python3
"""Remaining sealed Train Ticket loop, helper and TicketInfo entries."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import random
import secrets
import time
import traceback
from run_planned_service import ROOT,HERE,load,save,sha
import run_response_binding_revision as old
from build_mirror_capability import configure
from run_mirror_capability_probe import native_answer,read_events

PORTS={**old.ROLES,'ticketinfo':15681}


def capture(dest,base,bundle,q):
    dest.mkdir();role=q['role'];roles=list(old.ROLES) if role in ('basic','ticketinfo') else [role]
    if role=='ticketinfo':roles.append(role)
    cfg=load(ROOT/'artifacts/trainticket-cost-preparation-20261016/inputs/inputs.json')
    cfg['ticketinfo']={'image':load(ROOT/'artifacts/real-path-expansion-preflight-20261015/images.json')['ticketinfo']['digests'][0]}
    mongo=next(k for k,v in load(ROOT/'artifacts/desktop-inputs/images-lock.json').items() if 'trainticket/ts-station-mongo' in v['services'])
    spec={'services':{},'volumes':{}};ports={r:18740+i for i,r in enumerate(roles)}
    for r in roles:
        name='ts-'+r+'-service';spec['services'][name]={'image':cfg[r]['image'],'restart':'no','ports':['127.0.0.1:'+str(ports[r])+':'+str(PORTS[r])],'mem_limit':'768m','cpus':1,'dns_search':['.']}
        if r not in ('basic','ticketinfo'):
            db='ts-'+r+'-mongo';volume=r+'-data';spec['volumes'][volume]={};spec['services'][db]={'image':mongo,'restart':'no','volumes':[volume+':/data/db'],'mem_limit':'384m','cpus':1};spec['services'][name]['depends_on']=[db]
        old.observed(spec,name,r,dest,base)
    configure(spec,dest,base,bundle,q);save(dest/'compose.json',spec)
    dep=old.Deployment(argparse.Namespace(project='tf2-mt-extra-'+secrets.token_hex(5)),dest,dest/'compose.json');run={'status':'failed','project':dep.args.project,'roles':roles,'cases':[]}
    rng=random.Random(20261020)
    try:
        dep.compose('up','-d','--pull','never',timeout=180);client=old.Client(dest);deadline=time.monotonic()+240
        while time.monotonic()<deadline:
            try:
                for r in roles:client.request('GET','http://127.0.0.1:'+str(ports[r])+'/api/v1/'+r+'service/'+({'train':'trains/','price':'prices/'}.get(r,''))+'welcome',label='readiness')
                break
            except Exception:time.sleep(2)
        else:raise ValueError('Original extra-entry readiness timeout')
        if role in ('basic','ticketinfo'):
            from run_train_multisource import freeze
            temp=dest/'travel-inputs';freeze(temp,base,ROOT/'artifacts/trainticket-cost-preparation-20261016/inputs/inputs.json',20261020)
            for r,coll in load(temp/'database-fixtures.json').items():
                rd=dest/('db-'+r);rd.mkdir();old.database(dep,r,list(coll.values())[0],rd)
            cases=load(temp/'cases.json')[:8]
        else:cases=[{'case':'group-'+str(i),'index':i} for i in range(6)]
        trace=secrets.token_hex(16)
        for c in cases:
            cd=dest/c['case'];cd.mkdir();cl=old.Client(cd);message=old.context(cl,trace);method,path=q['http'].split(' ',1);docs=[]
            if role in ('basic','ticketinfo'):body=c['body']
            else:
                docs=old.mongo_fixture(role,c['index'],rng);old.database(dep,role,docs,cd)
                if role=='station':body=[d['_id'] if 'namelist' in path else d['name'] for d in docs]
                else:
                    body=None;stations=docs[0]['stations'] if docs else ['MISSING-START','MISSING-END'];path=path.replace('{start}',stations[0]).replace('{terminal}',stations[-1])
            response,status=old.request_raw(cl,method,'http://127.0.0.1:'+str(ports[role])+path,body)
            expected_status=c.get('expected_http_status',200)
            if status!=expected_status:raise ValueError('Original business status differs '+str(status)+' expected '+str(expected_status))
            r={**c,'message':message,'response':response,'http_status':status,'request_path':path,'request_body':body,'database_documents':docs};save(cd/'contract-result.json',r);run['cases'].append(r)
        for r in roles:dep.compose('stop','-t','20','ts-'+r+'-service',timeout=40)
        run['status']='business-completed'
    finally:old.cleanup(dep,run,dest)


def independent(q,c,path,rows,target):
    sources=[r for r in rows if r['kind']=='source' and r['root']==target['root'] and not r['call'].startswith('@argument')]
    if q['role']=='station':
        index=int(path.rsplit('/',1)[-1]);r=sources[index];field='name' if 'namelist' in c['request_path'] else 'id';relative='/'+field
    elif q['role']=='route':
        assert len(sources)==1;r=sources[0]
        # Original loop retains order, filters by station membership and index.
        start,terminal=c['request_path'].split('/')[-2:];docs=c['database_documents'];selected=[i for i,d in enumerate(docs) if start in d['stations'] and terminal in d['stations'] and d['stations'].index(start)<d['stations'].index(terminal)]
        parts=path.split('/');relative='/'+str(selected[int(parts[2])])+'/'+('/'.join(parts[3:]))
    elif q['role']=='basic' and path=='/data/status':return set()
    elif q['role']=='basic':
        matches=[r for r in sources if any(f['path']=='/body/data/averageSpeed' for f in r['fields'])];assert len(matches)==1;r=matches[0];relative='/body/data/'+path.rsplit('/',1)[-1]
    else:
        assert len(sources)==1;r=sources[0];relative='/body'+path
    fs=[f for f in r['fields'] if f['path']==relative];assert len(fs)==1
    f=fs[0];return {(r['call'],r['ordinal'],relative,f.get('owner'),f.get('field'),f.get('version'))}


def evaluate(dest,qs):
    rows=read_events(dest,qs[0]['role']);run=load(dest/'run.json');result=[]
    for q in qs:
        ts=[];na=0
        for c in run['cases']:
            leaves=old.leaves(c['response'],q['path']) if c['http_status']==200 else []
            if not leaves:na+=1
            for path,value in leaves:
                p={'query':q['id'],'case':c['case'],'message':c['message'],'path':path,'client_value':value};a=native_answer(rows,c['message'],path);p['answer']=a
                try:
                    targets=[r for r in rows if r['kind']=='target' and r['context'].get('message')==c['message']];assert len(targets)==1
                    expected=independent(q,c,path,rows,targets[0]);p['expected']=[list(v) for v in expected];actual={tuple(v) for v in a.get('sources',[])}
                    exported=next(f for f in targets[0]['fields'] if f['path']==path);assert exported['value']==value
                    p['state']=('known_correct' if actual==expected else 'known_wrong') if a['state']=='known' else a['state']
                    p.update(tp=len(actual&expected) if a['state']=='known' else 0,fp=len(actual-expected) if a['state']=='known' else 0,fn=len(expected-actual) if a['state']=='known' else len(expected))
                except (AssertionError,ValueError,IndexError,StopIteration) as e:p.update(state='oracle_unavailable',oracle_error=str(e))
                ts.append(p)
        result.append({'id':q['id'],'requests':len(run['cases']),'N/A_requests':na,'targets':ts})
    save(dest.parent/'native-evaluation.json',result);return result


def run(out,base,bundle):
    out.mkdir(parents=True,exist_ok=True);groups=defaultdict(list)
    for q in load(HERE/'capability-comparison-62-20261020.json')['queries']:
        if q['role'] in ('basic','ticketinfo') or any(s in q['http'] for s in ('{start}','namelist','idlist')):groups[q['entry']].append(q)
    # Smaller loop cases first. Travel uses five/six original Java services.
    progress=[]
    for entry,qs in sorted(groups.items(),key=lambda v:(v[1][0]['role'] in ('basic','ticketinfo'),v[0])):
        dest=out/qs[0]['id'];dest.mkdir(exist_ok=True);r={'entry':entry,'queries':[q['id'] for q in qs]}
        try:
            if not (dest/'capture').exists():capture(dest/'capture',base,bundle,qs[0])
            assert load(dest/'capture/run.json')['status']=='business-completed'
            ev=evaluate(dest/'capture',qs);r.update(status='evaluated',targets=sum(len(q['targets']) for q in ev),known_correct=sum(t['state']=='known_correct' for q in ev for t in q['targets']),known_wrong=sum(t['state']=='known_wrong' for q in ev for t in q['targets']),oracle_unavailable=sum(t['state']=='oracle_unavailable' for q in ev for t in q['targets']))
        except Exception as e:r.update(status='execution_or_evidence_invalid',error=str(e));save(dest/'error.json',{'error':str(e),'traceback':traceback.format_exc()})
        progress.append(r);save(out/'progress.json',{'entries':progress,'native_only':True,'matched_tf_evaluation_pending':True});print(json.dumps(r,ensure_ascii=False),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('out','base','bundle'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();run(a.out.resolve(),a.base.resolve(),a.bundle.resolve())
