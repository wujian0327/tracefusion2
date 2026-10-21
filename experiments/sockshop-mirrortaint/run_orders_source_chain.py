#!/usr/bin/env python3
"""Original Orders worker dependency replay; unchanged six inputs and independent truth."""
import argparse,copy,json,secrets
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save,sha
from plan_response_binding import plan_response
from run_orders_date_projection import TEMPLATES
from run_matched_orders_capabilities import ready,requests
import run_response_binding_revision as old
import run_sockshop_model_revision as source_model

def evaluate(d,q):
    cap=d/'capture';rows=[json.loads(s) for s in (cap/'orders/events.jsonl').read_text().splitlines()];cases=load(cap/'run.json')['cases'];truth=[]
    for c in cases:
        if q['path']=='/date':
            root=next(r for r in rows if r['kind']=='binding-return' and r.get('message')==c['message']);f=next(f for f in root['fields'] if f['path']=='/date');starts={r['call_id']:r for r in rows if r['kind']=='collection-call-enter' and r.get('frame')==root['frame']};clocks=[r for r in rows if r['kind']=='collection-call-exit' and r.get('call_id') in starts and starts[r['call_id']]['callee']=='java/util/Calendar.getTime()Ljava/util/Date;'];assert len(clocks)==1 and clocks[0]['result']==f['observed']
            from datetime import datetime,timezone
            instant=datetime.strptime(c['response']['date'],'%Y-%m-%dT%H:%M:%S.%f%z');delta=instant.astimezone(timezone.utc)-datetime(1970,1,1,tzinfo=timezone.utc);assert delta.days*86400000+delta.seconds*1000+instant.microsecond//1000==f['observed']['date_epoch_ms'];expected=[]
        else:expected=source_model.oracle(q,c,q['path'],{'orders':rows})
        truth.append({'case':c['case'],'message':c['message'],'path':q['path'],'expected':sorted(expected,key=str)})
    save(d/'independent-truth.json',{'basis':'Original business bytecode, concrete original HTTP decoder fields/object versions or original Calendar call, independent ISO conversion. No TF propagation or baseline labels.','targets':truth})
    g=old.Reconstruction(d/'build',cap,['orders']);pred=[]
    for t in truth:
        a=g.query(t['message'],t['path'],'orders',boundary=old.BOUNDARY);want={tuple(v) for v in t['expected']};actual={__import__('normalize_orders_origins').source_coordinate('orders',s,rows) for s in a['sources']};status=('correct' if actual==want else 'wrong') if a['known'] else 'unknown';pred.append({**t,'status':status,'answer':a})
    result={'targets':len(pred),'known_exact':sum(p['status']=='correct' for p in pred),'unknown':sum(p['status']=='unknown' for p in pred),'wrong':sum(p['status']=='wrong' for p in pred),'evidence_invalid':0,'oracle_unavailable':0,'N/A_requests':0,'predictions':pred};save(d/'evaluation.json',result);save(d/'execution-audit.json',g.local_queries['orders']);assert not result['wrong'];return {k:v for k,v in result.items() if k!='predictions'}

def run(out,base,development=False):
    out.mkdir(parents=True,exist_ok=False);qs=load(HERE/'orders-end-to-end-protocol-20261021.json')['queries'];setup=out/'setup';setup.mkdir();spec=old.spec_for('original',setup,base,1,'768m');spec.pop('networks',None);save(setup/'compose.json',spec);dep=old.CachedDeployment(argparse.Namespace(project='tf2-async-dependencies-'+secrets.token_hex(5),ready_timeout=240),setup,setup/'compose.json');state={'status':'failed','project':dep.args.project};progress=[]
    if development:qs=[q for q in qs if q['path']=='/customer/username']
    templates=TEMPLATES[:1] if development else TEMPLATES
    modes=('full',) if development else ('full','selective')
    try:
        dep.start();inputs=out/'inputs';inputs.mkdir();prepared=[];trace=secrets.token_hex(16)
        for i,template in enumerate(templates):
            item=old.prepare({**template,'expected_target':True},'group-'+str(i),inputs/('group-'+str(i)),'http://127.0.0.1:18580','http://127.0.0.1:18581');span=secrets.token_hex(8);item[-1].update(message=trace+'/'+span,traceparent='00-'+trace+'-'+span+'-01');prepared.append(item);save(inputs/('group-'+str(i))/'frozen-contract.json',item[-1])
        save(out/'input-protocol.json',{'templates':templates,'development':development,'identity':'New legal IDs, same actual data/requests/messages between all declared configurations. Original six input shapes retained. Clock-generated date varies.','queries':qs,'source_evidence':'Enabled identically: raw HTTP bytes are independent oracle/diagnostic facts, never automatic known origins. No performance claim.'});dep.compose('stop','-t','20','orders',timeout=40)
        for mode in modes:
            for q in qs:
                d=out/(mode+'-'+q['id']);d.mkdir();p=plan_response(load(base/'orders/model.json'),q['entry'],q['target'],q['path'],execution_kernel=True,application_calls=True);p['source_evidence']=True;p=__import__('plan_async_dependencies').attach_async_dependencies(p);old.query_build(d/'build',base,q,p);save(d/'configuration.json',{'query':q,'mode':mode,'driver_sha256':sha(Path(__file__)),'plan':p});cap=d/'capture';cap.mkdir();active=copy.deepcopy(spec);active['services']['orders']['volumes']=[v for v in active['services']['orders'].get('volumes',[]) if ':/tf2/app.jar:' not in v];old.observed(active,'orders','orders',cap,d/'build');active['services']['orders']['entrypoint'][2]+=' --port=80';opts=active['services']['orders']['environment'];opts['JAVA_OPTS']=opts['JAVA_OPTS'].replace('-Dservice.mode=selective','-Dservice.mode='+mode);save(cap/'compose.json',active)
                dep.out=cap;dep.compose('exec','-T','orders-db','mongo','data','--quiet','--eval','db.dropDatabase()');dep.file=cap/'compose.json';dep.compose('up','-d','--no-deps','--force-recreate','--pull','never','orders',timeout=180);ready(dep);cases=requests(cap,prepared);dep.compose('stop','-t','20','orders',timeout=40);dep.diagnostics();save(cap/'run.json',{'status':'business-completed','roles':['orders'],'cases':cases,'mode':mode});old.verify_build(d/'build');ev=evaluate(d,q);progress.append({'query':q['id'],'mode':mode,**ev});save(out/'results.json',{'complete':len(progress)==len(modes)*len(qs),'development':development,'results':progress,'new_performance':False});print(progress[-1],flush=True)
        state['status']='completed'
    finally:
        dep.diagnostics();result=dep.compose('down','--volumes','--remove-orphans',timeout=120,check=False);state['cleanup_returncode']=result.returncode;save(out/'cleanup.json',state)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--base-build',type=Path,required=True);p.add_argument('--development',action='store_true');a=p.parse_args();run(a.out.resolve(),a.base_build.resolve(),a.development)
