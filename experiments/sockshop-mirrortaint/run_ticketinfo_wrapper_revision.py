#!/usr/bin/env python3
"""Original TicketInfo requests, raw RPC-read instance oracle, full before selective."""
import argparse,json,secrets,time,traceback
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save,sha
import run_response_binding_revision as old
from plan_response_binding import plan_response

BASELINE=ROOT/'artifacts/baseline-capability-20261020/extra-entries-calibrated07/trainticket-ticketinfo-queryForTravel-data-trainType-id/capture/run.json'
BOUNDARY=[{'kind':'http-json','phase':'read','direction':'response'}]

def capture(dest,base,q,mode):
    dest.mkdir();p=plan_response(load(base/'ticketinfo/model.json'),q['entry'],q['target'],q['path'],execution_kernel=True,application_calls=True)
    old.query_build(dest/'build',base,q,p);cap=dest/'capture';cap.mkdir()
    cfg=load(ROOT/'artifacts/trainticket-cost-preparation-20261016/inputs/inputs.json');cfg['ticketinfo']={'image':load(ROOT/'artifacts/real-path-expansion-preflight-20261015/images.json')['ticketinfo']['digests'][0]}
    roles=list(old.ROLES)+['ticketinfo'];ports={r:18740+i for i,r in enumerate(roles)};internal={**old.ROLES,'ticketinfo':15681}
    mongo=next(k for k,v in load(ROOT/'artifacts/desktop-inputs/images-lock.json').items() if 'trainticket/ts-station-mongo' in v['services']);spec={'services':{},'volumes':{}}
    for role in roles:
        name='ts-'+role+'-service';spec['services'][name]={'image':cfg[role]['image'],'restart':'no','ports':['127.0.0.1:'+str(ports[role])+':'+str(internal[role])],'mem_limit':'768m','cpus':1,'dns_search':['.']}
        if role not in ('basic','ticketinfo'):
            db='ts-'+role+'-mongo';v=role+'-data';spec['volumes'][v]={};spec['services'][db]={'image':mongo,'restart':'no','volumes':[v+':/data/db'],'mem_limit':'384m','cpus':1};spec['services'][name]['depends_on']=[db]
    old.observed(spec,'ts-ticketinfo-service','ticketinfo',cap,dest/'build');opts=spec['services']['ts-ticketinfo-service']['environment'];opts['JAVA_OPTS']=opts['JAVA_OPTS'].replace('-Dservice.mode=selective','-Dservice.mode='+mode)
    save(cap/'compose.json',spec);save(dest/'configuration.json',{'query':q,'mode':mode,'plan':p,'driver_sha256':sha(Path(__file__)),'original_baseline':str(BASELINE),'baseline_sha256':sha(BASELINE)})
    dep=old.Deployment(argparse.Namespace(project='tf2-ticket-wrapper-'+secrets.token_hex(5)),cap,cap/'compose.json');run={'status':'failed','roles':roles,'cases':[],'project':dep.args.project}
    try:
        dep.compose('up','-d','--pull','never',timeout=180);client=old.Client(cap);deadline=time.monotonic()+240
        while time.monotonic()<deadline:
            try:
                for r in roles:client.request('GET','http://127.0.0.1:'+str(ports[r])+'/api/v1/'+r+'service/'+({'train':'trains/','price':'prices/'}.get(r,''))+'welcome',label='readiness')
                break
            except Exception:time.sleep(2)
        else:raise ValueError('Original TicketInfo readiness timeout')
        from run_train_multisource import freeze
        temp=cap/'travel-inputs';freeze(temp,base,ROOT/'artifacts/trainticket-cost-preparation-20261016/inputs/inputs.json',20261020)
        for r,coll in load(temp/'database-fixtures.json').items():
            rd=cap/('db-'+r);rd.mkdir();old.database(dep,r,list(coll.values())[0],rd)
        frozen_cases=load(temp/'cases.json')[:8];baseline=load(BASELINE)['cases'];assert len(frozen_cases)==len(baseline)==8
        trace=secrets.token_hex(16)
        for c,previous in zip(frozen_cases,baseline):
            cd=cap/c['case'];cd.mkdir();cl=old.Client(cd);message=old.context(cl,trace);method,path=q['http'].split(' ',1)
            assert c['body']==previous['request_body'] and c['case']==previous['case']
            response,status=old.request_raw(cl,method,'http://127.0.0.1:'+str(ports['ticketinfo'])+path,c['body'])
            actual_body={k:v for k,v in response.items() if k!='timestamp'} if status>=400 and isinstance(response,dict) else response
            previous_body={k:v for k,v in previous['response'].items() if k!='timestamp'} if status>=400 and isinstance(previous['response'],dict) else previous['response']
            assert status==previous['http_status'] and actual_body==previous_body,(c['case'],status,response,previous['response'])
            result={**c,'message':message,'response':response,'http_status':status,'request_path':path,'request_body':c['body']};save(cd/'contract-result.json',result);run['cases'].append(result)
        dep.compose('stop','-t','20','ts-ticketinfo-service',timeout=40);run['status']='business-completed'
    finally:old.cleanup(dep,run,cap)
    return evaluate(dest,q)

def evaluate(dest,q):
    cap=dest/'capture';rows=[json.loads(s) for s in (cap/'ticketinfo/events.jsonl').read_text().splitlines()];run=load(cap/'run.json');truth=[]
    # The original root directly returns exchange(...).getBody(). The oracle
    # selects its one actual HTTP response read by original call extent and
    # parent request, then projects actual decoded map coordinates. No TF replay.
    for c in run['cases']:
        for path,value in old.leaves(c['response'],q['path']) if c['http_status']==200 else []:
            read=[r for r in rows if r['kind']=='http-json' and r.get('phase')=='read' and r.get('direction')=='response' and r.get('parent_message')==c['message']];assert len(read)==1
            fs=[f for f in read[0]['fields'] if f['path']==path];assert len(fs)==1 and fs[0]['observed']['value']==value
            f=fs[0];truth.append({'case':c['case'],'message':c['message'],'path':path,'value':value,'expected':('ticketinfo',read[0]['seq'],path,f['owner'],f['field'],f['version'],read[0]['message'])})
    save(dest/'independent-truth.json',{'driver_sha256':sha(Path(__file__)),'targets':truth,'basis':'Original direct-return bytecode, actual parent-request/RPC message and decoded physical field coordinates. No TF propagation or graph queried.'})
    graph=old.Reconstruction(dest/'build',cap,['ticketinfo']);predictions=[]
    for t in truth:
        a=graph.query(t['message'],t['path'],'ticketinfo',boundary=BOUNDARY);actual={(s['service'],s['seq'],s['path'],s['owner'],s['field'],s['version'],s['message']) for s in a['sources']};want={tuple(t['expected'])}
        status=('correct' if actual==want else 'wrong') if a['known'] else 'unknown'
        predictions.append({**t,'status':status,'answer':a,'tp':len(actual&want) if a['known'] else 0,'fp':len(actual-want) if a['known'] else 0,'fn':len(want-actual) if a['known'] else len(want)})
    result={'query':q['id'],'requests':len(run['cases']),'targets':len(truth),'correct':sum(t['status']=='correct' for t in predictions),'unknown':sum(t['status']=='unknown' for t in predictions),'wrong':sum(t['status']=='wrong' for t in predictions),'N/A_requests':sum(not old.leaves(c['response'],q['path']) for c in run['cases']),'tp':sum(t['tp'] for t in predictions),'fp':sum(t['fp'] for t in predictions),'fn':sum(t['fn'] for t in predictions),'predictions':predictions};save(dest/'evaluation.json',result);return {k:v for k,v in result.items() if k!='predictions'}

def run(out,base,modes):
    out.mkdir(parents=True,exist_ok=False);progress=[]
    qs=load(HERE/'ticketinfo-wrapper-protocol-20261020.json')['queries']
    for mode in modes:
        for q in qs:
            d=out/(mode+'-'+q['id'])
            try:r={'mode':mode,**capture(d,base,q,mode)}
            except Exception as e:
                save(out/'failure.json',{'directory':str(d),'error':str(e),'traceback':traceback.format_exc()});raise
            progress.append(r);save(out/'results.json',{'complete':len(progress)==len(qs)*len(modes),'results':progress});print(r,flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--base-build',type=Path,required=True);p.add_argument('--modes',nargs='+',default=['full','selective']);a=p.parse_args();run(a.out.resolve(),a.base_build.resolve(),a.modes)
