#!/usr/bin/env python3
"""One frozen live fixture set, native MT and each accepted TF Orders query.

Only the Orders JVM changes between configurations. User/Cart input data remain
the same. Its own output database is reset while Orders is stopped; no database
history is a source boundary. No timing/cost claims are made from this run.
"""
import argparse
import copy
import json
from pathlib import Path
import secrets
import time
import traceback
from run_planned_service import ROOT,HERE,load,save,sha
import run_response_binding_revision as old
import run_sockshop_model_revision as model
from build_mirror_capability import configure
from run_mirror_sock_capabilities import evaluate as native_evaluate


def ready(dep):
    client=old.Client(dep.out);deadline=time.monotonic()+240
    while time.monotonic()<deadline:
        try:client.request('GET','http://127.0.0.1:18582/health',label='readiness');return
        except Exception:time.sleep(2)
    raise ValueError('Original Orders readiness failed')


def requests(dest,prepared,baseline=None):
    cases=[]
    for item in prepared:
        case,_,fixture,request,contract=item;name=contract['case'];cd=dest/name;cd.mkdir();cl=old.Client(cd)
        cl.headers={'traceparent':contract['traceparent'],'tracestate':'research=matched-capability'}
        local=(case,cl,fixture,request,contract)
        result=old.submit(local,'http://127.0.0.1:18582',cd);assert result['business_passed'],result
        response=load(cd/'order-response.json')
        r={'case':name,'message':contract['message'],'http_status':result['http_status'],'response':response,'fixture':fixture,'request_body':request}
        save(cd/'contract-result.json',r);cases.append(r)
    return cases


def run(out,base,bundle,inventory):
    out.mkdir(parents=True,exist_ok=False)
    qs=[q for q in load(HERE/'capability-comparison-62-20261020.json')['queries'] if q['role']=='orders']
    native=out/'native';native.mkdir();capture=native/'capture';capture.mkdir()
    original=old.spec_for('original',capture,base,1,'768m');spec=copy.deepcopy(original)
    configure(spec,capture,base,bundle,qs[0]);save(capture/'compose.json',spec)
    project='tf2-matched-orders-'+secrets.token_hex(5)
    dep=old.CachedDeployment(argparse.Namespace(project=project,ready_timeout=240),capture,capture/'compose.json')
    overall={'status':'failed','project':project,'queries':[q['id'] for q in qs],'tf_queries':[]}
    templates=[{'items':[{'key':'a','quantity':1,'unitPrice':1.25}]},
        {'items':[{'key':'a','quantity':2,'unitPrice':2.5},{'key':'b','quantity':2,'unitPrice':2.5}]},
        {'items':[]},{'items':[{'key':'a','quantity':3,'unitPrice':0.}]},
        {'items':[{'key':'a','quantity':1,'unitPrice':5.}],'patch':{'key':'a','quantity':2,'unitPrice':5.}},
        {'items':[{'key':'a','quantity':1,'unitPrice':1.25}]}]
    save(out/'protocol.json',{'queries':qs,'templates':templates,'baseline_bundle_sha256':sha(bundle/'build.json'),'tf_commit':'2b3b9297e8382162865075d22459480980a45bbc','input_matching':'Prepare six users and carts once; same actual URLs, bodies, users, addresses, cards and cart state for each query. Only original Orders JVM instrumentation changes. Each query has its own automatically generated selective plan.','orders_database':'Reset only this project Orders database between stopped configurations; original newOrder has no pre-save database read. Other input stores retained.','performance':False})
    try:
        dep.start();inputs=out/'inputs';inputs.mkdir();prepared=[];trace=secrets.token_hex(16)
        for i,template in enumerate(templates):
            item=old.prepare({**template,'expected_target':True},'group-'+str(i),inputs/('group-'+str(i)),'http://127.0.0.1:18580','http://127.0.0.1:18581')
            span=secrets.token_hex(8);item[-1].update(message=trace+'/'+span,traceparent='00-'+trace+'-'+span+'-01');prepared.append(item)
            save(inputs/('group-'+str(i))/'frozen-contract.json',item[-1])
        nr={'status':'failed','project':project,'roles':['orders'],'cases':[]}
        nr['cases']=requests(capture,prepared);dep.compose('stop','-t','20','orders',timeout=40);nr['status']='business-completed';save(capture/'run.json',nr);dep.diagnostics()
        native_evaluate(capture,qs)
        print(json.dumps({'stage':'native-complete','queries':len(qs),'requests':len(nr['cases'])}),flush=True)
        for q in qs:
            planfile=inventory/q['id']/'plan.json'
            if not planfile.exists():overall['tf_queries'].append({'id':q['id'],'planning':'refused'});continue
            dest=out/('tf-'+q['id']);dest.mkdir();old.query_build(dest/'build',base,q,load(planfile));capt=dest/'capture';capt.mkdir()
            next_spec=copy.deepcopy(original)
            cfg=next_spec['services']['orders'];cfg['volumes']=[v for v in cfg['volumes'] if ':/tf2/app.jar:' not in v]
            old.observed(next_spec,'orders','orders',capt,dest/'build');next_spec['services']['orders']['entrypoint'][2]+=' --port=80'
            save(capt/'compose.json',next_spec)
            # The service is stopped before changing only its own output DB.
            dep.out=capt
            dep.compose('exec','-T','orders-db','mongo','data','--quiet','--eval','db.dropDatabase()')
            dep.file=capt/'compose.json';dep.compose('up','-d','--no-deps','--force-recreate','--pull','never','orders',timeout=180)
            run_={'status':'failed','project':project,'roles':['orders'],'cases':[]}
            try:
                ready(dep);run_['cases']=requests(capt,prepared)
                dep.compose('stop','-t','20','orders',timeout=40);run_['status']='business-completed';save(capt/'run.json',run_);dep.diagnostics()
                old.verify_build(dest/'build')
                original_oracle=old.oracle;old.oracle=model.oracle
                try:ev=old.evaluate(capt,dest/'build',q)
                finally:old.oracle=original_oracle
                matches=[]
                for a,b in zip(nr['cases'],run_['cases']):
                    assert a['request_body']==b['request_body'] and a['fixture']==b['fixture'] and a['message']==b['message']
                    assert old.leaves(a['response'],q['path'])==old.leaves(b['response'],q['path'])
                    matches.append({'case':a['case'],'same_input':True,'same_target_values':True})
                save(dest/'matched-input-audit.json',{'passed':True,'checks':matches,'baseline_capture':str(capture),'input_prepared_once':True})
                overall['tf_queries'].append({'id':q['id'],'planning':'accepted','targets':ev['target_instances'],'known':ev['known'],'unknown':ev['unknown'],'invalid':ev['evidence_invalid'],'oracle_unavailable':ev['oracle_unavailable']})
                print(json.dumps(overall['tf_queries'][-1]),flush=True)
            except Exception as e:
                dep.compose('stop','-t','20','orders',timeout=40,check=False);save(capt/'run.json',run_)
                save(dest/'error.json',{'error':str(e),'traceback':traceback.format_exc()});overall['tf_queries'].append({'id':q['id'],'status':'execution_or_evidence_failed','error':str(e)})
            save(out/'progress.json',overall)
        overall['status']='completed'
    finally:
        dep.diagnostics();r=dep.compose('down','--volumes','--remove-orphans',timeout=120,check=False);overall['cleanup_returncode']=r.returncode;save(out/'progress.json',overall)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('out','base','bundle','inventory'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();run(a.out.resolve(),a.base.resolve(),a.bundle.resolve(),a.inventory.resolve())
