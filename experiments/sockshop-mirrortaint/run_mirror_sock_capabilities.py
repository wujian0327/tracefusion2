#!/usr/bin/env python3
"""All five sealed Sock Shop entries, including TF-refused Cart methods."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import secrets
import traceback
from run_planned_service import ROOT,HERE,load,save,sha
import run_response_binding_revision as old
from build_mirror_capability import configure
from run_mirror_capability_probe import native_answer,read_events


def capture(dest,base,bundle,q):
    dest.mkdir();spec=old.spec_for('tracefusion',dest,base,1,'768m');configure(spec,dest,base,bundle,q);save(dest/'compose.json',spec)
    dep=old.CachedDeployment(argparse.Namespace(project='tf2-mt-sockcap-'+secrets.token_hex(5),ready_timeout=240),dest,dest/'compose.json')
    run={'status':'failed','project':dep.args.project,'roles':['orders','carts','shipping'],'cases':[]}
    templates=[{'items':[{'key':'a','quantity':1,'unitPrice':1.25}]},
        {'items':[{'key':'a','quantity':2,'unitPrice':2.5},{'key':'b','quantity':2,'unitPrice':2.5}]},
        {'items':[]},{'items':[{'key':'a','quantity':3,'unitPrice':0.}]},
        {'items':[{'key':'a','quantity':1,'unitPrice':5.}],'patch':{'key':'a','quantity':2,'unitPrice':5.}},
        {'items':[{'key':'a','quantity':1,'unitPrice':1.25}]}]
    save(dest/'input-protocol.json',{'templates':templates,'queries_entry':q['entry'],'post_body':'Select existing first itemId, or new item for empty fixture; quantity=2, unitPrice=4.75. Original existing-item branch increments by literal one, ignoring posted quantity/price for returned value.','get_missing':'Preserve no-target response for empty item fixture; do not replace.'})
    try:
        dep.start();trace=secrets.token_hex(16)
        for i,c in enumerate(templates):
            name='group-'+str(i);cd=dest/name
            prepared=old.prepare({**c,'expected_target':True},name,cd,'http://127.0.0.1:18580','http://127.0.0.1:18581');message=old.context(prepared[1],trace)
            fixture=prepared[2];body=None
            if q['role']=='orders':
                b=old.submit(prepared,'http://127.0.0.1:18582',cd);assert b['business_passed'];response=load(cd/'order-response.json');status=b['http_status'];path='/orders'
            else:
                method,path=q['http'].split(' ',1);path=path.replace('{customerId}',fixture['customer_id'])
                item=next(iter(fixture['expected_items']), 'missing-item-'+name);path=path.replace('{itemId}',item)
                if method=='POST':body={'itemId':item,'quantity':2,'unitPrice':4.75}
                response,status=old.request_raw(prepared[1],method,'http://127.0.0.1:18581'+path,body)
                if status not in (200,201) and not (not fixture['expected_items'] and '{itemId}' in q['http']):raise ValueError('Unexpected Cart status '+str(status))
            case={'case':name,'message':message,'http_status':status,'response':response,'fixture':fixture,'request_path':path,'request_body':body}
            save(cd/'contract-result.json',case);run['cases'].append(case)
        for r in run['roles']:dep.compose('stop','-t','20',r,timeout=40)
        run['status']='business-completed'
    finally:old.cleanup(dep,run,dest)


def origin(r,f):return (r['call'],r['ordinal'],f['path'],f.get('owner'),f.get('field'),f.get('version'))


def independent(q,c,path,rows,target):
    sources=[r for r in rows if r['kind']=='source' and r['root']==target['root']]
    field=path.rsplit('/',1)[-1]
    if q['role']=='orders':
        if field=='id':return set()  # default Resource decoding ignores wire id; pinned no-Agent probe.
        if path=='/date':
            # Original newOrder offsets554/557 Calendar.getInstance/getTime,
            # passed into CustomerOrder.<init> at562. No declared entry/repo/
            # RPC field is a data operand of this clock value. This is an empty
            # PROJECTION onto the sealed field boundary, not "time is constant".
            return set()
        leaf=next(f for f in target['fields'] if f['path']==path)
        # Original CustomerOrder constructor preserves actual nested references.
        candidates=[origin(r,f) for r in sources if not r['call'].startswith('@argument') for f in r['fields']
                    if all(f.get(k)==leaf.get(k) for k in ('owner','field','version')) and f['path'].endswith('/'+field)]
        if len(candidates)!=1:raise ValueError('Original nested source object absent/ambiguous')
        return set(candidates)
    repo=[r for r in sources if not r['call'].startswith('@argument')]
    if '.addToCart(' in q['entry']:
        if not c['fixture']['expected_items']:
            rs=[r for r in sources if r['call']=='@argument:1'];assert len(rs)==1
            fs=[f for f in rs[0]['fields'] if f['path']=='/'+field];assert len(fs)==1
            assert c['response'][field]==c['request_body'][field]
            return {origin(rs[0],fs[0])}
        # hasItem performs two supplier reads (selection and logging), then
        # two separate FoundItem.get invocations at original offsets53,56.
        # Constructor copies itemId/unitPrice from first, quantity from second +1.
        if len(repo)<4:raise ValueError('Original repeated FoundItem reads absent')
        r=repo[3 if field=='quantity' else 2]
        item_id=c['request_body']['itemId'];matches=[]
        for f in r['fields']:
            if f['path'].endswith('/itemId') and f['value']==item_id:
                prefix=f['path'].rsplit('/',1)[0]
                matches.extend(v for v in r['fields'] if v['path']==prefix+'/'+field)
        assert len(matches)==1
        f=matches[0];expected=f['value']+1 if field=='quantity' else f['value'];assert c['response'][field]==expected
        return {origin(r,f)}
    assert len(repo)==1,'Original read entry expected one repository call'
    r=repo[0]
    if '.getItems(' in q['entry']:relative='/0/items'+path
    elif path=='/customerId':relative='/0/customerId'
    else:
        selected=c['request_path'].rsplit('/',1)[-1]
        ids=[f for f in r['fields'] if f['path'].endswith('/itemId') and f['value']==selected]
        assert len(ids)==1;relative=ids[0]['path'].rsplit('/',1)[0]+path
    fs=[f for f in r['fields'] if f['path']==relative];assert len(fs)==1
    return {origin(r,fs[0])}


def evaluate(dest,qs):
    rows=read_events(dest,qs[0]['role']);run=load(dest/'run.json');result=[]
    for q in qs:
        targets=[];na=0
        for c in run['cases']:
            leaves=old.leaves(c['response'],q['path']) if c['http_status'] in (200,201) else []
            if not leaves:na+=1
            for path,value in leaves:
                p={'query':q['id'],'case':c['case'],'message':c['message'],'path':path,'client_value':value};answer=native_answer(rows,c['message'],path);p['answer']=answer
                try:
                    ts=[r for r in rows if r['kind']=='target' and r['context'].get('message')==c['message']];assert len(ts)==1
                    leaf=next(f for f in ts[0]['fields'] if f['path']==path)
                    check_value=value
                    if q['id']=='sockshop-orders-newOrder-date':
                        from datetime import datetime
                        check_value=round(datetime.strptime(value,'%Y-%m-%dT%H:%M:%S.%f%z').timestamp()*1000)
                    assert leaf['value']==check_value
                    expected=independent(q,c,path,rows,ts[0]);p['expected']=[list(v) for v in expected];actual={tuple(v) for v in answer.get('sources',[])}
                    p['state']=('known_correct' if actual==expected else 'known_wrong') if answer['state']=='known' else answer['state']
                    p.update(tp=len(actual&expected) if answer['state']=='known' else 0,fp=len(actual-expected) if answer['state']=='known' else 0,fn=len(expected-actual) if answer['state']=='known' else len(expected))
                except (AssertionError,ValueError,StopIteration) as e:p.update(state='oracle_unavailable',oracle_error=str(e))
                targets.append(p)
        result.append({'id':q['id'],'requests':len(run['cases']),'N/A_requests':na,'targets':targets})
    save(dest.parent/'native-evaluation.json',result);return result


def run(out,base,bundle):
    out.mkdir(parents=True,exist_ok=True);groups=defaultdict(list)
    for q in load(HERE/'capability-comparison-62-20261020.json')['queries']:
        if q['application']=='sockshop':groups[q['entry']].append(q)
    progress=[]
    for entry,qs in groups.items():
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
