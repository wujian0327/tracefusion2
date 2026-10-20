#!/usr/bin/env python3
"""Original-JAR finite-model revision; independent literal business projections.

No TF propagation/graph join is called by oracle(). Core and experiment code are
hashed separately. First held-out runs require an immutable algorithm freeze.
"""
import argparse
import base64
import copy
import hashlib
import json
from pathlib import Path
import traceback
from urllib.parse import urlparse
import run_response_binding_revision as old
from run_planned_service import HERE,ROOT,load,save,sha
from plan_response_binding import plan_response

HOME=ROOT/'artifacts/sockshop-model-revision-20261020'
SEAL=HERE/'sockshop-model-heldout-20261020.json'
OLD_ORACLE=old.oracle


def oracle(q,c,path,rows):
    role=q['role']
    if q['application']!='sockshop':return OLD_ORACLE(q,c,path,rows)
    if role=='orders':
        # Original newOrder passes the actual Customer/Address/Card content
        # into the output order, preserving these nested object references.
        part,name=path.split('/')[1:3]
        lookup={'customer':('customers','customer_id','Customer'),'address':('addresses','address_id','Address'),'card':('cards','card_id','Card')}
        if part not in lookup or len(path.split('/'))!=3:raise ValueError('No reviewed non-list Orders projection: '+path)
        route,key,typ=lookup[part];uri='/'+route+'/'+c['fixture'][key]
        facts=[r for r in rows[role] if r['kind']=='http-source-fact' and r.get('parent_message')==c['message'] and urlparse(r.get('uri','')).path==uri]
        if len(facts)!=1:raise ValueError('Raw source call absent/ambiguous: '+uri)
        r=facts[0];raw=base64.b64decode(r['raw_base64']);document=json.loads(raw)
        if not r['document_complete'] or hashlib.sha256(raw).hexdigest()!=r['raw_sha256']:raise ValueError('Raw document incomplete or changed')
        fields=[f for f in r['fields'] if f['path']=='/'+name and f['field']=='works/weave/socks/orders/entities/'+typ+'.'+name]
        if len(fields)!=1:raise ValueError('Decoded source coordinate absent/ambiguous')
        f=fields[0];value=f['observed'].get('value')
        if name=='id':
            # ResourceSupport.getId is @JsonIgnore. The original default
            # Jackson converter drops this name before unwrapping content.
            # The independent no-Agent probe reproduces null with raw id present.
            # The ignored wire id is not a data origin of the default null.
            if value is not None or f['version']!=0 or 'id' not in document:raise ValueError('Reviewed ignored-id/default contract differs')
        elif document.get(name)!=value:raise ValueError('Original raw scalar projection differs')
        outputs=[f for r in rows[role] if r['kind']=='http-json' and r['phase']=='write' and r['direction']=='response' and r['message']==c['message'] for f in r['fields'] if f['path']==path]
        if len(outputs)!=1 or any(outputs[0][k]!=f[k] for k in ('owner','field','version')):raise ValueError('Original nested reference/version projection differs')
        if name=='id':return []
        return [old.source_coord(role,r,f)]
    if role=='carts':
        # Original getItems = get(customer).contents(). Original get selects
        # findByCustomerId(...).stream().findFirst(), or the separate create path.
        # Prepared cases all have a persisted Cart, including empty item lists.
        returns=[r for r in rows[role] if r['kind']=='binding-return' and r.get('message')==c['message']]
        if len(returns)!=1:raise ValueError('Cart root return absent/ambiguous')
        sources=[r for r in rows[role] if r['kind']=='binding-source' and r['frame']==returns[0]['frame'] and r['callee']=='works/weave/socks/cart/repositories/CartRepository.findByCustomerId(Ljava/lang/String;)Ljava/util/List;']
        if len(sources)!=1:raise ValueError('Cart repository call absent/repeated; cannot substitute a same-valued invocation')
        relative='/0'+('/items' if '.getItems(' in q['entry'] else '')+path
        matches=[f for f in sources[0]['fields'] if f['path']==relative]
        if len(matches)!=1:raise ValueError('Independent Cart first-record/element projection absent: '+relative)
        f=matches[0]
        if '.getItems(' in q['entry']:
            index=int(path.split('/')[1]);actual=c['response'][index]
            expected=c['fixture']['expected_items'].get(actual['itemId'])
            if not expected or any(actual[k]!=expected[k] for k in ('quantity','unitPrice')):raise ValueError('Independent legal Cart fixture differs')
        elif path=='/customerId' and c['response']['customerId']!=c['fixture']['customer_id']:raise ValueError('Cart customer differs from legal fixture')
        return [old.source_coord(role,sources[0],f)]
    raise ValueError('No reviewed independent projection for '+q['id'])


def selected(stage):
    if stage=='previous22':return load(HERE/'response-binding-heldout-20261019.json')['queries']
    if stage=='cart-development':return [q for q in old.queries('development') if q['id'] in {'sockshop-carts-get-customerId','sockshop-carts-getItems-each-quantity','sockshop-carts-getItems-each-unitPrice'}]
    freeze=load(HOME/'algorithm-freeze.json')
    if sha(SEAL)!=freeze['heldout_sha256']:raise ValueError('Holdout seal changed')
    for p,h in freeze['sources'].items():
        if sha(ROOT/p)!=h:raise ValueError('Frozen core changed: '+p)
    return load(SEAL)['queries']


def plan(out,base,stage,application=None):
    out.mkdir(parents=True,exist_ok=False);result=[]
    for q in selected(stage):
        if application and q['application']!=application:continue
        d=out/q['id'];d.mkdir();save(d/'query.json',q)
        try:
            p=plan_response(load(base/q['role']/'model.json'),q['entry'],q['target'],q['path'],read_forward_contracts=True)
            p['source_evidence']=True
            if q['role']=='basic':p['json_conversion_methods']=['edu/fudan/common/util/JsonUtils.conveterObject(Ljava/lang/Object;Ljava/lang/Class;)Ljava/lang/Object;']
            save(d/'plan.json',p);result.append({'id':q['id'],'application':q['application'],'entry':q['entry'],'role':q['role'],'status':'accepted','profile':p['profile'],'caveats':p.get('planning_caveats')})
        except ValueError as e:
            (d/'rejection.txt').write_text(traceback.format_exc());result.append({'id':q['id'],'application':q['application'],'entry':q['entry'],'role':q['role'],'status':'rejected','reason':str(e)})
        save(out/'planning.json',result)
    save(out/'stage.json',{'stage':stage,'base_build':str(base),'driver_sha256':sha(Path(__file__)),'queries':len(result),'accepted':sum(r['status']=='accepted' for r in result),'performance':False})
    print({'stage':stage,'application':application,'queries':len(result),'accepted':sum(r['status']=='accepted' for r in result)},flush=True)


def capture(out,base):
    old.oracle=oracle;reports=[]
    for at,r in enumerate(load(out/'planning.json')):
        if r['status']!='accepted':continue
        d=out/r['id'];q=load(d/'query.json');runtime=d/'capture'
        if runtime.exists():raise ValueError('First evidence immutable; use another named attempt: '+str(runtime))
        old.query_build(d/'build',base,q,load(d/'plan.json'));runtime.mkdir();old.verify_build(d/'build')
        try:
            if q['application']=='sockshop':old.capture_sock(runtime,d/'build',q,20261020+at)
            else:old.capture_train(runtime,d/'build',q,20261020+at)
        except Exception:(runtime/'capture-error.txt').write_text(traceback.format_exc())
        if (runtime/'run.json').exists():report=old.evaluate(runtime,d/'build',q)
        else:report={'id':q['id'],'deployment_failed':True,'error':(runtime/'capture-error.txt').read_text()}
        reports.append(report);save(out/'runtime-summary.json',reports)
        print({k:v for k,v in report.items() if k!='predictions'},flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('plan','capture','evaluate'));p.add_argument('--out',type=Path,required=True);p.add_argument('--base',type=Path,required=True);p.add_argument('--stage',choices=('previous22','cart-development','heldout'),default='previous22');p.add_argument('--application',choices=('sockshop','trainticket'));a=p.parse_args()
    if a.action=='plan':plan(a.out.resolve(),a.base.resolve(),a.stage,a.application)
    elif a.action=='capture':capture(a.out.resolve(),a.base.resolve())
    else:
        old.oracle=oracle;reports=[]
        for r in load(a.out/'planning.json'):
            if r['status']=='accepted':
                d=a.out/r['id'];reports.append(old.evaluate(d/'capture',d/'build',load(d/'query.json')))
        save(a.out/'runtime-summary.json',reports)
