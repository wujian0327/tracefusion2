#!/usr/bin/env python3
"""Original Cart read restoration via shared contracts, independent source coordinates."""
import argparse,copy,json,secrets
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save,sha
from plan_response_binding import plan_response
import run_response_binding_revision as old
import run_matched_cart_capabilities as cart


def run(out,base,runtime_profile=None):
    out.mkdir(parents=True,exist_ok=False);q=next(q for q in load(HERE/'capability-comparison-62-20261020.json')['queries'] if q['id']=='sockshop-carts-getItems-each-itemId')
    fixtures=[copy.deepcopy(c['fixture']) for c in load(ROOT/'artifacts/baseline-capability-20261020/sock-entries-calibrated07/sockshop-carts-get-customerId/capture/run.json')['cases']]
    prep=out/'setup';prep.mkdir();spec=old.spec_for('original',prep,base,1,'768m');spec['services']={k:v for k,v in spec['services'].items() if k in ('carts','carts-db')};spec.pop('networks',None);spec['services']['carts']['ports']=['127.0.0.1:19693:80'];save(prep/'compose.json',spec)
    dep=old.Deployment(argparse.Namespace(project='tf2-app-call-cart-'+secrets.token_hex(5)),prep,prep/'compose.json');state={'status':'failed','roles':['carts'],'project':dep.args.project,'cases':[]};results=[]
    try:
        dep.compose('up','-d','--pull','never',timeout=180);cart.ready(prep);client=old.Client(prep)
        for f in fixtures:
            uid=f['customer_id'];client.request('GET','http://127.0.0.1:19693/carts/'+uid,label='prepare-cart')
            for item in f['expected_items'].values():client.request('POST','http://127.0.0.1:19693/carts/'+uid+'/items',item,label='prepare-item')
            f['fixture_read_items']=client.request('GET','http://127.0.0.1:19693/carts/'+uid+'/items',label='independent-setup-check')
        save(out/'frozen-inputs.json',fixtures);dep.compose('stop','-t','20','carts',timeout=40)
        for mode in ('full','selective'):
            d=out/mode;d.mkdir();p=plan_response(load(base/'carts/model.json'),q['entry'],q['target'],q['path'],execution_kernel=True,application_calls=True)
            if runtime_profile:p['execution_kernel']['runtime_profiles'].append(load(runtime_profile))
            save(d/'configuration-freeze.json',{'driver_sha256':sha(Path(__file__)),'runtime_profile':str(runtime_profile),'runtime_profile_sha256':sha(runtime_profile) if runtime_profile else None,'query':q,'plan':p})
            old.query_build(d/'build',base,q,p);cap=d/'capture';cap.mkdir()
            active=copy.deepcopy(spec);active['services']['carts']['volumes']=[v for v in active['services']['carts'].get('volumes',[]) if ':/tf2/app.jar:' not in v];old.observed(active,'carts','carts',cap,d/'build');active['services']['carts']['entrypoint'][2]+=' --port=80';active['services']['carts']['environment']['JAVA_OPTS']=active['services']['carts']['environment']['JAVA_OPTS'].replace('-Dservice.mode=selective','-Dservice.mode='+mode)
            save(cap/'compose.json',active);dep.file=cap/'compose.json';dep.out=cap;dep.compose('up','-d','--no-deps','--force-recreate','--pull','never','carts',timeout=180);cart.ready(cap)
            cases=cart.requests(cap,fixtures,q,secrets.token_hex(16));dep.compose('stop','-t','20','carts',timeout=40);dep.diagnostics();save(cap/'run.json',{'status':'business-completed','roles':['carts'],'cases':cases,'mode':mode})
            graph=old.Reconstruction(d/'build',cap,['carts']);rows=graph.rows['carts'];predictions=[]
            for case in cases:
                root=next(r for r in rows if r['kind']=='binding-return' and r.get('message')==case['message']);family={root['frame']}
                for _ in range(20):family.update(r['frame'] for r in rows if r['kind']=='enter' and r.get('parent') in family)
                sources=[r for r in rows if r['kind']=='binding-source' and r['frame'] in family and '.findByCustomerId(' in r['callee']];assert len(sources)==1
                for path,value in old.leaves(case['response'],q['path']):
                    expected=next(f for f in sources[0]['fields'] if f['path']=='/0/items'+path);assert expected['observed']['value']==value
                    answer=graph.query(case['message'],path,'carts',boundary=old.BOUNDARY)
                    assert answer['known'] and {old.predicted_coord(s) for s in answer['sources']}=={old.source_coord('carts',sources[0],expected)},(case,answer,expected)
                    predictions.append({'case':case['case'],'path':path,'status':'correct','independent_expected':old.source_coord('carts',sources[0],expected),'answer':answer})
            entries=[r for r in rows if r['kind']=='enter'];assert any('CartsController.get(' in r['method'] for r in entries) and any('FirstResultOrDefault.get(' in r['method'] for r in entries)
            result={'mode':mode,'requests':len(cases),'targets':len(predictions),'unknown':0,'known':len(predictions),'exact':len(predictions),'application_frames':len(entries),'methods':sorted({r['method'] for r in entries}),'predictions':predictions};save(d/'evaluation.json',result);results.append({k:v for k,v in result.items() if k!='predictions'});print(results[-1],flush=True)
        state['status']='business-completed'
    finally:old.cleanup(dep,state,out)
    save(out/'results.json',{'complete':True,'results':results,'scope':'Original Cart shared-kernel read restoration; not a new baseline-gap repair.'})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=Path);p.add_argument('--base-build',required=True,type=Path);p.add_argument('--runtime-profile',type=Path);a=p.parse_args();run(a.out.resolve(),a.base_build.resolve(),a.runtime_profile.resolve() if a.runtime_profile else None)
