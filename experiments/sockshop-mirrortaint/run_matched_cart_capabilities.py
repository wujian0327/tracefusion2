#!/usr/bin/env python3
"""Identical persisted Cart inputs across MT and per-query TF selective plans."""
import argparse
import copy
import json
from pathlib import Path
import secrets
import time
import traceback
from collections import defaultdict
from run_planned_service import ROOT,HERE,load,save,sha
import run_response_binding_revision as old
import run_sockshop_model_revision as model
from build_mirror_capability import configure
from run_mirror_sock_capabilities import evaluate as native_evaluate


def ready(out):
    cl=old.Client(out);deadline=time.monotonic()+180
    while time.monotonic()<deadline:
        try:cl.request('GET','http://127.0.0.1:19693/health',label='readiness');return
        except Exception:time.sleep(2)
    raise ValueError('Original Cart readiness timeout')


def requests(dest,fixtures,q,trace):
    cases=[]
    for i,fixture in enumerate(fixtures):
        cd=dest/('group-'+str(i));cd.mkdir();cl=old.Client(cd);span=f'{i+1:016x}';message=trace+'/'+span
        cl.headers={'traceparent':'00-'+trace+'-'+span+'-01','tracestate':'research=matched-capability'}
        method,path=q['http'].split(' ',1);path=path.replace('{customerId}',fixture['customer_id']);item=next(iter(fixture['expected_items']),'missing-item-group-'+str(i));path=path.replace('{itemId}',item)
        body={'itemId':item,'quantity':2,'unitPrice':4.75} if method=='POST' else None
        response,status=old.request_raw(cl,method,'http://127.0.0.1:19693'+path,body)
        if status not in (200,201):
            assert not fixture['expected_items'] and '{itemId}' in q['http'] and status==500
            assert response['exception']=='java.lang.IllegalArgumentException' and response['message']=='Cannot find item in cart'
        r={'case':'group-'+str(i),'message':message,'http_status':status,'response':response,'fixture':fixture,'request_path':path,'request_body':body};cases.append(r);save(cd/'contract-result.json',r)
    return cases


def run(out,base,bundle,inventory,native_refused=False):
    out.mkdir(parents=True,exist_ok=False)
    selected=[q for q in load(HERE/'capability-comparison-62-20261020.json')['queries'] if q['role']=='carts' and
              (not (inventory/q['id']/'plan.json').exists() if native_refused else '.getItems(' in q['entry'] or q['id']=='sockshop-carts-get-customerId')]
    groups=defaultdict(list)
    for q in selected:groups[q['entry']].append(q)
    prior=load(ROOT/'artifacts/baseline-capability-20261020/sock-entries-calibrated07/sockshop-carts-get-customerId/capture/run.json')['cases']
    fixtures=[copy.deepcopy(c['fixture']) for c in prior]
    prep=out/'setup';prep.mkdir();original=old.spec_for('original',prep,base,1,'768m');original['services']={k:v for k,v in original['services'].items() if k in ('carts','carts-db')};original.pop('networks',None)
    original['services']['carts']['ports']=['127.0.0.1:19693:80'];save(prep/'compose.json',original)
    project='tf2-matched-cart-'+secrets.token_hex(5);dep=old.Deployment(argparse.Namespace(project=project),prep,prep/'compose.json')
    progress={'project':project,'status':'failed','groups':[]}
    try:
        dep.compose('up','-d','--pull','never',timeout=180);ready(prep);cl=old.Client(prep)
        for fixture in fixtures:
            uid=fixture['customer_id'];cl.request('GET','http://127.0.0.1:19693/carts/'+uid,label='create-empty-cart')
            for body in fixture['expected_items'].values():cl.request('POST','http://127.0.0.1:19693/carts/'+uid+'/items',body,label='prepare-cart-item')
            actual=cl.request('GET','http://127.0.0.1:19693/carts/'+uid+'/items',label='independent-setup-check')
            assert len(actual)==len(fixture['expected_items'])
            for item in actual:assert all(item[k]==fixture['expected_items'][item['itemId']][k] for k in ('quantity','unitPrice'))
            fixture['fixture_read_items']=actual
        save(out/'frozen-inputs.json',fixtures);dep.compose('stop','-t','20','carts',timeout=40)
        for entry,qs in groups.items():
            group=out/qs[0]['id'];group.mkdir();native=group/'native';native.mkdir();capt=native/'capture';capt.mkdir();spec=copy.deepcopy(original);configure(spec,capt,base,bundle,qs[0]);save(capt/'compose.json',spec);dep.file=capt/'compose.json'
            dep.out=capt;dep.compose('up','-d','--no-deps','--force-recreate','--pull','never','carts',timeout=180);ready(capt)
            trace=secrets.token_hex(16);nr={'project':project,'status':'failed','roles':['carts'],'cases':requests(capt,fixtures,qs[0],trace)}
            dep.compose('stop','-t','20','carts',timeout=40);nr['status']='business-completed';save(capt/'run.json',nr);dep.diagnostics();native_evaluate(capt,qs)
            row={'entry':entry,'native':'completed','tf':[]}
            for q in qs:
                if native_refused:row['tf'].append({'id':q['id'],'planning':'refused'});continue
                dest=group/('tf-'+q['id']);dest.mkdir();old.query_build(dest/'build',base,q,load(inventory/q['id']/'plan.json'));tc=dest/'capture';tc.mkdir();spec=copy.deepcopy(original)
                spec['services']['carts']['volumes']=[v for v in spec['services']['carts'].get('volumes',[]) if ':/tf2/app.jar:' not in v]
                old.observed(spec,'carts','carts',tc,dest/'build');spec['services']['carts']['entrypoint'][2]+=' --port=80';save(tc/'compose.json',spec);dep.file=tc/'compose.json'
                dep.out=tc;dep.compose('up','-d','--no-deps','--force-recreate','--pull','never','carts',timeout=180);ready(tc)
                run_={'project':project,'status':'failed','roles':['carts'],'cases':requests(tc,fixtures,q,trace)}
                dep.compose('stop','-t','20','carts',timeout=40);run_['status']='business-completed';save(tc/'run.json',run_);dep.diagnostics()
                original_oracle=old.oracle;old.oracle=model.oracle
                try:ev=old.evaluate(tc,dest/'build',q)
                finally:old.oracle=original_oracle
                for a,b in zip(nr['cases'],run_['cases']):assert all(a[k]==b[k] for k in ('fixture','request_path','response','message'))
                save(dest/'matched-input-audit.json',{'passed':True,'baseline_capture':str(capt),'shared_actual_database':True,'matching':['fixture','request_path','response','message']})
                row['tf'].append({'id':q['id'],'targets':ev['target_instances'],'known':ev['known'],'unknown':ev['unknown'],'invalid':ev['evidence_invalid']});print(json.dumps(row['tf'][-1]),flush=True)
            progress['groups'].append(row);save(out/'progress.json',progress)
        progress['status']='completed'
    except Exception as e:progress.update(error=str(e),traceback=traceback.format_exc());raise
    finally:
        dep.diagnostics();r=dep.compose('down','--volumes','--remove-orphans',timeout=120,check=False);progress['cleanup_returncode']=r.returncode;save(out/'progress.json',progress)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('out','base','bundle','inventory'):p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--native-only-refused',action='store_true');a=p.parse_args();run(a.out.resolve(),a.base.resolve(),a.bundle.resolve(),a.inventory.resolve(),a.native_only_refused)
