#!/usr/bin/env python3
"""Original Orders Date query, fresh legal fixtures shared by full and selective."""
import argparse,copy,json,secrets
from pathlib import Path
from datetime import datetime,timezone
from run_planned_service import ROOT,HERE,load,save,sha
from plan_response_binding import plan_response
import run_response_binding_revision as old
from run_matched_orders_capabilities import requests,ready

TEMPLATES=[{'items':[{'key':'a','quantity':1,'unitPrice':1.25}]},{'items':[{'key':'a','quantity':2,'unitPrice':2.5},{'key':'b','quantity':2,'unitPrice':2.5}]},{'items':[]},{'items':[{'key':'a','quantity':3,'unitPrice':0.}]},{'items':[{'key':'a','quantity':1,'unitPrice':5.}],'patch':{'key':'a','quantity':2,'unitPrice':5.}},{'items':[{'key':'a','quantity':1,'unitPrice':1.25}]}]

def run(out,base):
    out.mkdir(parents=True,exist_ok=False);q=load(HERE/'date-projection-protocol-20261020.json')['query'];setup=out/'setup';setup.mkdir();spec=old.spec_for('original',setup,base,1,'768m');spec.pop('networks',None);save(setup/'compose.json',spec)
    dep=old.CachedDeployment(argparse.Namespace(project='tf2-date-'+secrets.token_hex(5),ready_timeout=240),setup,setup/'compose.json');progress=[];state={'status':'failed','project':dep.args.project}
    try:
        dep.start();prepared=[];inputs=out/'inputs';inputs.mkdir();trace=secrets.token_hex(16)
        for i,template in enumerate(TEMPLATES):
            item=old.prepare({**template,'expected_target':True},'group-'+str(i),inputs/('group-'+str(i)),'http://127.0.0.1:18580','http://127.0.0.1:18581');span=secrets.token_hex(8);item[-1].update(message=trace+'/'+span,traceparent='00-'+trace+'-'+span+'-01');prepared.append(item);save(inputs/('group-'+str(i))/'frozen-contract.json',item[-1])
        save(out/'input-protocol.json',{'templates':TEMPLATES,'actual_fixtures_sha256':{p.parent.name:sha(p) for p in inputs.glob('*/fixture.json')},'identity':'Fresh legal registration creates new user/address/card/database IDs; retained identically between full and selective. Six original input shapes and item values preserved. Date is environmental, not an equal-output-value comparison.','original_62_query':q,'no_baseline_rerun':True})
        dep.compose('stop','-t','20','orders',timeout=40)
        for mode in ('full','selective'):
            d=out/mode;d.mkdir();p=plan_response(load(base/'orders/model.json'),q['entry'],q['target'],q['path'],read_forward_contracts=True);old.query_build(d/'build',base,q,p);cap=d/'capture';cap.mkdir();active=copy.deepcopy(spec);active['services']['orders']['volumes']=[v for v in active['services']['orders'].get('volumes',[]) if ':/tf2/app.jar:' not in v];old.observed(active,'orders','orders',cap,d/'build');active['services']['orders']['entrypoint'][2]+=' --port=80';opts=active['services']['orders']['environment'];opts['JAVA_OPTS']=opts['JAVA_OPTS'].replace('-Dservice.mode=selective','-Dservice.mode='+mode);save(cap/'compose.json',active)
            dep.out=cap;dep.compose('exec','-T','orders-db','mongo','data','--quiet','--eval','db.dropDatabase()');dep.file=cap/'compose.json';dep.compose('up','-d','--no-deps','--force-recreate','--pull','never','orders',timeout=180);ready(dep);cases=requests(cap,prepared);dep.compose('stop','-t','20','orders',timeout=40);dep.diagnostics();save(cap/'run.json',{'status':'business-completed','roles':['orders'],'cases':cases,'mode':mode});old.verify_build(d/'build')
            result=evaluate(d,q);progress.append({'mode':mode,**result});save(out/'results.json',{'complete':len(progress)==2,'results':progress,'no_performance':True});print(progress[-1],flush=True)
        state['status']='completed'
    finally:
        dep.diagnostics();r=dep.compose('down','--volumes','--remove-orphans',timeout=120,check=False);state['cleanup_returncode']=r.returncode;save(out/'cleanup.json',state)

def evaluate(d,q):
    cap=d/'capture';rows=[json.loads(s) for s in (cap/'orders/events.jsonl').read_text().splitlines()];run=load(cap/'run.json');truth=[]
    for case in run['cases']:
        target=[r for r in rows if r['kind']=='binding-return' and r.get('message')==case['message']];assert len(target)==1
        f=next(f for f in target[0]['fields'] if f['path']=='/date');calls=[r for r in rows if r['kind']=='date-call' and r.get('frame')==target[0]['frame'] and r['callee']=='java/util/Calendar.getTime()Ljava/util/Date;'];assert len(calls)==1
        assert all(calls[0]['result'][k]==f['observed'][k] for k in ('object','date_epoch_ms','date_type'))
        instant=datetime.strptime(case['response']['date'],'%Y-%m-%dT%H:%M:%S.%f%z');delta=instant.astimezone(timezone.utc)-datetime(1970,1,1,tzinfo=timezone.utc);epoch=delta.days*86400000+delta.seconds*1000+instant.microsecond//1000;assert epoch==f['observed']['date_epoch_ms']
        truth.append({'case':case['case'],'message':case['message'],'path':'/date','expected_field_sources':[],'environment':'Calendar default-provider time; not a constant or an all-source empty answer','raw_clock_seq':calls[0]['seq'],'date':f['observed'],'client_iso':case['response']['date']})
    save(d/'independent-truth.json',{'basis':'Original newOrder bytecode Calendar.getInstance/getTime supplied to constructor, concrete call/Date identity, target field version and independent ISO/epoch conversion. No TF graph or propagation decides expected origins.','targets':truth})
    g=old.Reconstruction(d/'build',cap,['orders']);pred=[]
    for t in truth:
        a=g.query(t['message'],'/date','orders',boundary=old.BOUNDARY);pred.append({**t,'status':'known_correct' if a['known'] and not a['sources'] else 'known_wrong' if a['known'] else 'unknown','answer':a})
    result={'targets':len(pred),'known_correct':sum(v['status']=='known_correct' for v in pred),'unknown':sum(v['status']=='unknown' for v in pred),'known_wrong':sum(v['status']=='known_wrong' for v in pred),'oracle_unavailable':0,'N/A_requests':0,'evidence_invalid':0,'empty_field_boundary_not_constant':True};save(d/'evaluation.json',{**result,'predictions':pred});return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--base-build',type=Path,required=True);a=p.parse_args();run(a.out.resolve(),a.base_build.resolve())
