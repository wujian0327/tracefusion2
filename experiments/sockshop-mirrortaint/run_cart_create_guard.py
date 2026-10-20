#!/usr/bin/env python3
"""Original Cart first-create/save versus existing-read guard, same output value.

Supplementary DEVELOPMENT test of an already used query, not a held-out query.
"""
import argparse,copy,json,secrets,time
from pathlib import Path
import run_sockshop_model_revision as n
from infer_distributed_fields import Reconstruction


def run(out,base):
    old=n.old;out.mkdir();q=next(q for q in old.queries('development') if q['id']=='sockshop-carts-get-customerId')
    p=old.plan_response(n.load(base/'carts/model.json'),q['entry'],q['target'],q['path'],read_forward_contracts=True);p['source_evidence']=True
    old.query_build(out/'build',base,q,p);capture=out/'capture';capture.mkdir()
    spec=old.spec_for('tracefusion',capture,out/'build',1,'768m');spec['services']={k:v for k,v in spec['services'].items() if k in ('carts','carts-db')}
    spec['services']['carts']['ports']=['127.0.0.1:19681:80'];spec['networks']={'default':{'ipam':{'config':[{'subnet':'10.254.246.0/24'}]}}}
    n.save(capture/'compose.json',spec);n.save(out/'protocol-before-runtime.json',{'query':q,'stage':'supplementary development guard','requests':['first GET for absent Cart: argument zero origin, expected unknown because creation/save unsupported','second GET same ID: actual first repository Cart.customerId origin, expected known'],'same_value_different_origin':True,'implementation_changes':False})
    dep=old.Deployment(argparse.Namespace(project='tf2-create-guard-'+secrets.token_hex(5)),capture,capture/'compose.json');run={'roles':['carts'],'status':'failed','project':dep.args.project,'cases':[]}
    try:
        dep.compose('up','-d','--pull','never',timeout=180);cl=old.Client(capture);deadline=time.monotonic()+180
        while time.monotonic()<deadline:
            try:cl.request('GET','http://127.0.0.1:19681/health',label='readiness');break
            except Exception:time.sleep(2)
        else:raise ValueError('Original Cart readiness failed')
        uid=secrets.token_hex(12);trace=secrets.token_hex(16)
        for i in range(2):
            cd=capture/('request-'+str(i));cd.mkdir();client=old.Client(cd);message=old.context(client,trace)
            response=client.request('GET','http://127.0.0.1:19681/carts/'+uid,label='target-query')
            assert response['customerId']==uid
            c={'index':i,'message':message,'response':response};run['cases'].append(c);n.save(cd/'response.json',c)
        dep.compose('stop','-t','20','carts',timeout=40);old.verify_build(out/'build');run['status']='business-completed'
    finally:old.cleanup(dep,run,capture)
    graph=Reconstruction(out/'build',capture,['carts']);rows=graph.rows['carts'];checks=[]
    for c in run['cases']:
        ret=next(r for r in rows if r['kind']=='binding-return' and r.get('message')==c['message']);root=next(r for r in rows if r['kind']=='enter' and r['frame']==ret['frame'])
        if c['index']==0:
            arg=root['args'][0];expected=[('carts',None,None,root['seq'],arg['object'],'@argument:0',0,None)]
        else:
            sources=[r for r in rows if r['kind']=='binding-source' and r['frame']==root['frame']]
            assert len(sources)==1 and len(sources[0]['fields'])==1
            f=sources[0]['fields'][0];assert f['path']=='/0/customerId' and f['field']=='works/weave/socks/cart/entities/Cart.customerId'
            expected=[old.source_coord('carts',sources[0],f)]
        answer=graph.query(c['message'],'/customerId','carts',boundary=old.BOUNDARY)
        assert answer['known']==(c['index']==1)
        actual={old.predicted_coord(s) for s in answer['sources']}
        if c['index']==1:assert actual==set(expected)
        checks.append({'request':c['index'],'message':c['message'],'client_customerId':c['response']['customerId'],'expected':expected,'known':answer['known'],'answer':answer})
    n.save(out/'checks.json',{'all_passed':True,'query':q['id'],'supplementary_development_only':True,'same_client_value':checks[0]['client_customerId']==checks[1]['client_customerId'],'checks':checks,'known':1,'unknown':1,'known_exact':1,'tp':1,'fn_including_unknown':1,'not_a_known_empty_origin':True})
    print({'first_create':'unknown as required','second_read':'known exact','same_output_value':True},flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);p.add_argument('--base',type=Path,required=True);a=p.parse_args();run(a.out.resolve(),a.base.resolve())
