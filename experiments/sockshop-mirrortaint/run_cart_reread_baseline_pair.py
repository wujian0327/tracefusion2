#!/usr/bin/env python3
"""Original Cart creation/repeat with independent actual-read oracle; no save purity rule."""
import argparse,json,secrets,time
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save
from plan_response_binding import plan_response
import run_response_binding_revision as old


def run(out,base):
    out.mkdir(parents=True,exist_ok=False);q=next(q for q in load(HERE/'capability-comparison-62-20261020.json')['queries'] if q['id']=='sockshop-carts-get-customerId');results=[]
    uid='56e8f576709b70d0ace01fb0'; sequence=[0,0]
    save(out/'protocol-before-runtime.json',{'query':q,'customerId':uid,'requests':sequence,'expected':'Every target matches its actual second read on creation, first read on repeats; save remains opaque','source_boundary':'Repository returns: first request uses SECOND read; second request uses FIRST. No source from output snapshot or initial argument.'})
    for mode in ('full','selective'):
        dest=out/mode;dest.mkdir();p=plan_response(load(base/'carts/model.json'),q['entry'],q['target'],q['path'],execution_kernel=True,application_calls=True);old.query_build(dest/'build',base,q,p);cap=dest/'capture';cap.mkdir()
        spec=old.spec_for('tracefusion',cap,dest/'build',1,'768m');spec['services']={k:v for k,v in spec['services'].items() if k in ('carts','carts-db')};spec.pop('networks',None);spec['services']['carts']['ports']=['127.0.0.1:19681:80'];spec['services']['carts']['environment']['JAVA_OPTS']=spec['services']['carts']['environment']['JAVA_OPTS'].replace('-Dservice.mode=selective','-Dservice.mode='+mode);save(cap/'compose.json',spec)
        dep=old.Deployment(argparse.Namespace(project='tf2-kernel-create-'+secrets.token_hex(5)),cap,cap/'compose.json');run={'roles':['carts'],'status':'failed','project':dep.args.project,'cases':[]}
        try:
            dep.compose('up','-d','--pull','never',timeout=180);client=old.Client(cap);deadline=time.monotonic()+180
            while time.monotonic()<deadline:
                try:client.request('GET','http://127.0.0.1:19681/health',label='readiness');break
                except Exception:time.sleep(2)
            else:raise ValueError('Original Cart readiness failed')
            seen=set()
            for index,customer in enumerate(sequence):
                created=customer not in seen;seen.add(customer)
                d=cap/('request-'+str(index));d.mkdir();cl=old.Client(d);message=old.context(cl,secrets.token_hex(16));response=cl.request('GET','http://127.0.0.1:19681/carts/'+uid,label='target-query');assert response['customerId']==uid;run['cases'].append({'index':index,'created':created,'customerId':uid,'message':message,'response':response})
            dep.compose('stop','-t','20','carts',timeout=40);run['status']='business-completed'
        finally:old.cleanup(dep,run,cap)
        graph=old.Reconstruction(dest/'build',cap,['carts']);rows=graph.rows['carts'];checks=[]
        for case in run['cases']:
            ret=next(r for r in rows if r['kind']=='binding-return' and r.get('message')==case['message']);family={ret['frame']}
            for _ in range(30):family.update(r['frame'] for r in rows if r['kind']=='enter' and r.get('parent') in family)
            sources=[r for r in rows if r['kind']=='binding-source' and r.get('frame') in family and '.findByCustomerId(' in r['callee']];assert len(sources)==1
            field=next(f for f in sources[0]['fields'] if f['path']=='/0/customerId');assert field['observed']['value']==case['customerId']
            calls=[r for r in rows if r['kind']=='collection-call-enter' and r.get('frame') in family and r['callee']==sources[0]['callee']];assert len(calls)==(2 if case['created'] else 1)
            answer=graph.query(case['message'],'/customerId','carts',boundary=old.BOUNDARY);assert answer['known'],(case,answer)
            expected=old.source_coord('carts',sources[0],field)
            if answer['known']:assert {old.predicted_coord(s) for s in answer['sources']}=={expected}
            checks.append({'request':case['index'],'known':answer['known'],'expected':expected,'source_read_ordinal':2 if case['created'] else 1,'actual_repository_reads':len(calls),'answer':answer})
        result={'mode':mode,'known_exact':len(checks),'unknown':0,'same_output_value':True,'checks':checks,'scope':'Exact original baseline customer ID and absent/repeat structure; first target is the original one-gap challenge'};save(dest/'evaluation.json',result);results.append(result);print(mode,'all creation/repeat targets known exact',flush=True)
    save(out/'results.json',{'all_passed':True,'results':results})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=Path);p.add_argument('--base-build',required=True,type=Path);a=p.parse_args();run(a.out.resolve(),a.base_build.resolve())
