#!/usr/bin/env python3
"""One frozen core and precomputed routing; fresh original-JAR capability acceptance.

Collectors and predictions do not determine oracle selection. Native baseline
files supply frozen business inputs only. Known and unknown are both retained.
"""
import argparse,copy,json,secrets,time,traceback,os
from pathlib import Path
from collections import defaultdict
from run_planned_service import ROOT,HERE,load,save,sha
import run_response_binding_revision as old
import run_execution_kernel_pilot as loops
import run_sockshop_model_revision as model
from audit_baseline_capabilities import native_location,response_value

HOME=ROOT/'artifacts/date-effects-capability-20261021/final-capability'
BASELINE=ROOT/'artifacts/baseline-capability-20261020'
QUERIES=load(HERE/'capability-comparison-62-20261020.json')['queries']
GROUPS=defaultdict(list)
for _q in QUERIES:GROUPS[_q['entry']].append(_q)

def previous(q):return native_location(BASELINE,GROUPS[q['entry']])[0]
def plan(q):return load(HOME/'frozen-plans'/(q['id']+'.json'))
def check():
    f=load(HOME/'algorithm-freeze.json')
    for p,h in f['sources'].items():assert sha(ROOT/p)==h,p
    assert sha(HERE/'execution-kernel-protocol-20261020.json')=='87c40107282aaccb8e049fc5ffe37bb1e66deacfeabd0f015a08544bc1972fae'

def mode_config(spec,name,role,cap,build,mode):
    old.observed(spec,name,role,cap,build)
    cfg=spec['services'][name];cfg['environment']['JAVA_OPTS']=cfg['environment']['JAVA_OPTS'].replace('-Dservice.mode=selective','-Dservice.mode='+mode)

def capture_train(d,base,q,mode):
    cap=d/'capture';cap.mkdir();role=q['role'];prior=previous(q);frozen=load(prior/'run.json')['cases']
    config=load(ROOT/'artifacts/trainticket-cost-preparation-20261016/inputs/inputs.json')
    config['ticketinfo']={'image':load(ROOT/'artifacts/real-path-expansion-preflight-20261015/images.json')['ticketinfo']['digests'][0]}
    roles=list(old.ROLES)+(['ticketinfo'] if role=='ticketinfo' else []) if role in ('basic','ticketinfo') else [role]
    internal={**old.ROLES,'ticketinfo':15681};ports={r:int(os.environ.get('TF2_CAPABILITY_PORT','18820'))+i for i,r in enumerate(roles)}
    mongo=next(k for k,v in load(ROOT/'artifacts/desktop-inputs/images-lock.json').items() if 'trainticket/ts-station-mongo' in v['services'])
    spec={'services':{},'volumes':{}}
    for r in roles:
        name='ts-'+r+'-service';spec['services'][name]={'image':config[r]['image'],'restart':'no','ports':[f'127.0.0.1:{ports[r]}:{internal[r]}'],'dns_search':['.'],'mem_limit':'768m','cpus':1}
        if r not in ('basic','ticketinfo'):
            db='ts-'+r+'-mongo';v=r+'-data';spec['volumes'][v]={};spec['services'][db]={'image':mongo,'restart':'no','volumes':[v+':/data/db'],'mem_limit':'384m','cpus':1};spec['services'][name]['depends_on']=[db]
    mode_config(spec,'ts-'+role+'-service',role,cap,d/'build',mode);save(cap/'compose.json',spec)
    dep=old.Deployment(argparse.Namespace(project='tf2-final-'+secrets.token_hex(5)),cap,cap/'compose.json');run={'status':'failed','roles':[role],'project':dep.args.project,'mode':mode,'cases':[]}
    try:
        save(cap/'images.json',{v['image']:json.loads(dep.command(['docker','image','inspect',v['image']]).stdout)[0] for v in spec['services'].values()})
        dep.compose('up','-d','--pull','never',timeout=180);client=old.Client(cap);deadline=time.monotonic()+240
        while time.monotonic()<deadline:
            try:
                for r in roles:client.request('GET',f'http://127.0.0.1:{ports[r]}/api/v1/{r}service/'+({'train':'trains/','price':'prices/'}.get(r,''))+'welcome',label='readiness')
                break
            except Exception:time.sleep(2)
        else:raise ValueError('Readiness timeout')
        if role in ('basic','ticketinfo'):
            for r in ('station','train','route','price'):
                bd=cap/('db-'+r);bd.mkdir();old.database(dep,r,load(prior/('db-'+r)/'database-input.json'),bd)
        audits=[]
        for c in frozen:
            cd=cap/c['case'];cd.mkdir();cl=old.Client(cd);message=old.context(cl,secrets.token_hex(16))
            if role not in ('basic','ticketinfo'):old.database(dep,role,c['database_documents'],cd)
            method=q['http'].split(' ',1)[0];body=c.get('request_body',c.get('body'));path=c['request_path']
            response,status=old.request_raw(cl,method,f'http://127.0.0.1:{ports[role]}'+path,body)
            actual={**c,'message':message,'response':response,'http_status':status,'request_body':body}
            assert status==c['http_status'] and response_value(actual)==response_value(c),(c['case'],response,c['response'])
            run['cases'].append(actual);save(cd/'contract-result.json',actual);audits.append({'case':c['case'],'same_request_database_response':True})
        dep.compose('stop','-t','20','ts-'+role+'-service',timeout=40);old.verify_build(d/'build');run['status']='business-completed';save(d/'input-audit.json',{'baseline':str(prior),'sha256':sha(prior/'run.json'),'checks':audits})
    finally:old.cleanup(dep,run,cap)

def family(rows,root):
    ids={root['frame']}
    for _ in range(100):
        more={r['frame'] for r in rows if r['kind']=='enter' and r.get('parent') in ids}
        if more<=ids:return ids
        ids.update(more)
    raise ValueError('Oracle call nesting budget')

def independent(q,c,path,rows):
    role=q['role'];rs=rows[role]
    if role=='orders':
        if path=='/date':
            from datetime import datetime,timezone
            root=next(r for r in rs if r['kind']=='binding-return' and r.get('message')==c['message']);f=next(f for f in root['fields'] if f['path']==path)
            starts={r['call_id']:r for r in rs if r['kind']=='collection-call-enter' and r.get('frame')==root['frame']}
            clocks=[r for r in rs if r['kind']=='collection-call-exit' and r.get('call_id') in starts and starts[r['call_id']]['callee']=='java/util/Calendar.getTime()Ljava/util/Date;'];assert len(clocks)==1 and clocks[0]['result']==f['observed']
            instant=datetime.strptime(c['response']['date'],'%Y-%m-%dT%H:%M:%S.%f%z');assert round(instant.timestamp()*1000)==f['observed']['date_epoch_ms'];return []
        return model.oracle(q,c,path,rows)
    if role=='ticketinfo':
        reads=[r for r in rs if r['kind']=='http-json' and r.get('phase')=='read' and r.get('direction')=='response' and r.get('parent_message')==c['message']];assert len(reads)==1
        f=next(f for f in reads[0]['fields'] if f['path']==path);return [old.source_coord(role,reads[0],f)]
    if role in ('station','route') and any(s in q['http'] for s in ('namelist','idlist','{start}')):return loops.independent(q,c,path,rs)
    if role!='carts':return old.oracle(q,c,path,rows)
    root=next(r for r in rs if r['kind']=='binding-return' and r.get('message')==c['message']);frames=family(rs,root)
    sources=[r for r in rs if r['kind']=='binding-source' and r.get('frame') in frames and '.findByCustomerId(' in r.get('callee','')]
    if '.addToCart(' in q['entry']:
        if not c['fixture']['expected_items']:
            arg=next(r for r in rs if r['kind']=='binding-input' and r['frame']==root['frame'] and r.get('argument')==1);fs=[f for f in arg['fields'] if f['path']==path]
            if len(fs)!=1:raise ValueError('Entry argument source coordinate not available for new Item')
            return [old.source_coord(role,arg,fs[0])]
        assert len(sources)>=4,len(sources);source=sources[3 if path=='/quantity' else 2]
    else:assert len(sources)==1,len(sources);source=sources[0]
    if '.getItems(' in q['entry']:relative='/0/items'+path
    elif path=='/customerId':relative='/0/customerId'
    else:
        item=c.get('request_body',{}).get('itemId') if '.addToCart(' in q['entry'] else c['request_path'].rsplit('/',1)[-1]
        ids=[f for f in source['fields'] if f['path'].endswith('/itemId') and f['observed']['value']==item];assert len(ids)==1
        relative=ids[0]['path'].rsplit('/',1)[0]+path
    fs=[f for f in source['fields'] if f['path']==relative];assert len(fs)==1
    return [old.source_coord(role,source,fs[0])]

def evaluate(d,q):
    cap=d/'capture';run=load(cap/'run.json');role=q['role'];rows={role:[json.loads(s) for s in (cap/role/'events.jsonl').read_text().splitlines()]};error=None;limited=False;g=None
    try:g=old.Reconstruction(d/'build',cap,[role])
    except old.AnalysisLimit as e:error=str(e);limited=True
    except Exception as e:error=str(e);(d/'reconstruction-error.txt').write_text(traceback.format_exc())
    predictions=[];na=0
    for c in run['cases']:
        leaves=old.leaves(c['response'],q['path']) if 200<=c['http_status']<300 else [];na+=not bool(leaves)
        for path,value in leaves:
            t={'query':q['id'],'case':c['case'],'path':path,'client_value':value,'message':c['message']};expected=None
            try:expected=set(independent(q,c,path,rows));t['expected']=sorted(expected,key=str)
            except Exception as e:t['oracle_error']=str(e)
            if error:t.update(state='analysis_limited' if limited else 'evidence_invalid',error=error)
            else:
                try:
                    a=g.query(c['message'],path,role,boundary=old.BOUNDARY);t['answer']=a
                    if path!='/date' or role!='orders':assert a['target']['observed'].get('value')==value
                    if role=='orders':
                        from normalize_orders_origins import source_coordinate
                        actual={source_coordinate(role,s,rows[role]) for s in a['sources']}
                    else:actual={old.predicted_coord(s) for s in a['sources']}
                    t['actual']=sorted(actual,key=str);t['state']=('known_correct' if actual==expected else 'known_wrong') if a['known'] and expected is not None else 'known_unchecked' if a['known'] else 'unknown'
                    if expected is not None:t.update(tp=len(actual&expected) if a['known'] else 0,fp=len(actual-expected) if a['known'] else 0,fn=len(expected-actual) if a['known'] else len(expected))
                except Exception as e:t.update(state='evidence_invalid',error=str(e))
            predictions.append(t)
    from collections import Counter
    result={'query':q['id'],'mode':run['mode'],'requests':len(run['cases']),'targets':len(predictions),'states':dict(Counter(t['state'] for t in predictions)),'N/A_requests':na,'oracle_unavailable':sum('oracle_error' in t for t in predictions),'tp':sum(t.get('tp',0) for t in predictions),'fp':sum(t.get('fp',0) for t in predictions),'fn':sum(t.get('fn',0) for t in predictions),'predictions':predictions}
    if g:save(d/'execution-audit.json',g.local_queries.get(role,{}))
    save(d/'independent-truth.json',{'basis':'Reviewed original business projections, raw source calls and physical instance coordinates, not TF propagation or baseline labels','targets':[{k:v for k,v in t.items() if k in ('query','case','path','expected','oracle_error')} for t in predictions]});save(d/'evaluation.json',result)
    return {k:v for k,v in result.items() if k!='predictions'}

def train(out,base,only=None):
    out.mkdir(parents=True,exist_ok=False);results=[]
    for mode in ('full','selective'):
        for q in QUERIES:
            if q['application']!='trainticket' or only and only not in q['id'] or os.environ.get('TF2_CAPABILITY_ROLES') and q['role'] not in os.environ['TF2_CAPABILITY_ROLES'].split(','):continue
            check();d=out/(mode+'-'+q['id']);d.mkdir()
            if not (HOME/'frozen-plans'/(q['id']+'.json')).exists():
                reason=next(r for r in load(HOME/'frozen-plans/planning.json') if r['query']['id']==q['id'])
                r={'query':q['id'],'mode':mode,'planning_rejected':True,'reason':reason['rejection']};save(d/'planning-rejection.json',r);results.append(r);save(out/'results.json',{'complete':False,'results':results});print(r,flush=True);continue
            old.query_build(d/'build',base,q,plan(q));save(d/'configuration.json',{'query':q,'mode':mode,'preplanned':str(HOME/'frozen-plans'/(q['id']+'.json'))})
            try:capture_train(d,base,q,mode);r=evaluate(d,q)
            except Exception as e:r={'query':q['id'],'mode':mode,'failure':str(e)};save(d/'failure.json',{'error':str(e),'traceback':traceback.format_exc()})
            results.append(r);save(out/'results.json',{'complete':False,'results':results});print(r,flush=True)
    save(out/'results.json',{'complete':True,'results':results})


# Sock Shop workers have independent ports/projects from the Train worker.
def seed_carts(dep,cases,dest):
    import hashlib
    script=['db.cart.deleteMany({});db.item.deleteMany({});']
    for c in cases:
        f=c['fixture'];items=f['fixture_read_items'];refs=[]
        for item in items:
            ident=item['id'];doc={'_class':'works.weave.socks.cart.entities.Item',**{k:item[k] for k in ('itemId','quantity','unitPrice')}}
            script.append('db.item.insert(Object.assign('+json.dumps(doc)+',{_id:ObjectId('+json.dumps(ident)+')}));');refs.append('DBRef("item",ObjectId('+json.dumps(ident)+'))')
        cid=hashlib.sha256(f['customer_id'].encode()).hexdigest()[:24]
        script.append('db.cart.insert({_id:ObjectId('+json.dumps(cid)+'),_class:"works.weave.socks.cart.entities.Cart",customerId:'+json.dumps(f['customer_id'])+',items:['+','.join(refs)+']});')
    text='\n'.join(script);(dest/'database-input.js').write_text(text);dep.compose('exec','-T','carts-db','mongo','data','--quiet','--eval',text)
    result=dep.compose('exec','-T','carts-db','mongo','data','--quiet','--eval','db.getCollectionNames().forEach(function(c){print(c); printjson(db.getCollection(c).find().toArray());})');(dest/'independent-database.txt').write_text(result.stdout)

def carts(out,base):
    import run_matched_cart_capabilities as cart
    out.mkdir(parents=True,exist_ok=False);prep=out/'setup';prep.mkdir();spec=old.spec_for('original',prep,base,1,'768m');spec['services']={k:v for k,v in spec['services'].items() if k in ('carts','carts-db')};spec.pop('networks',None);spec['services']['carts']['ports']=['127.0.0.1:19693:80'];save(prep/'compose.json',spec)
    dep=old.Deployment(argparse.Namespace(project='tf2-final-cart-'+secrets.token_hex(5)),prep,prep/'compose.json');results=[];state={'status':'failed'}
    try:
        dep.compose('up','-d','--pull','never',timeout=180);cart.ready(prep);dep.compose('stop','-t','20','carts',timeout=40)
        for mode in ('full','selective'):
            for q in QUERIES:
                if q['role']!='carts':continue
                check();d=out/(mode+'-'+q['id']);d.mkdir();old.query_build(d/'build',base,q,plan(q));cap=d/'capture';cap.mkdir();prior=previous(q);frozen=load(prior/'run.json')['cases'];seed_carts(dep,frozen,d)
                active=copy.deepcopy(spec);active['services']['carts']['volumes']=[v for v in active['services']['carts'].get('volumes',[]) if ':/tf2/app.jar:' not in v];mode_config(active,'carts','carts',cap,d/'build',mode);active['services']['carts']['entrypoint'][2]+=' --port=80';save(cap/'compose.json',active);dep.file=cap/'compose.json';dep.out=cap
                try:
                    dep.compose('up','-d','--no-deps','--force-recreate','--pull','never','carts',timeout=180);cart.ready(cap);cases=cart.requests(cap,[copy.deepcopy(c['fixture']) for c in frozen],q,secrets.token_hex(16));dep.compose('stop','-t','20','carts',timeout=40);dep.diagnostics();audits=[]
                    for c,oldcase in zip(cases,frozen):
                        assert c['request_path']==oldcase['request_path'] and c.get('request_body')==oldcase.get('request_body') and c['http_status']==oldcase['http_status']
                        assert old.leaves(c['response'],q['path'])==old.leaves(oldcase['response'],q['path'])
                        # Database-generated id on an ADD result is outside the selected target.
                        def comparable(v):
                            if isinstance(v,list):return [comparable(x) for x in v]
                            if isinstance(v,dict):return {k:comparable(x) for k,x in v.items() if k not in ('timestamp',) and not (k=='id' and '.addToCart(' in q['entry'])}
                            return v
                        assert comparable(c['response'])==comparable(oldcase['response'])
                        audits.append({'case':c['case'],'same_request_persisted_item_ids_values_and_target':True})
                    save(cap/'run.json',{'status':'business-completed','mode':mode,'roles':['carts'],'cases':cases});old.verify_build(d/'build');save(d/'input-audit.json',{'baseline':str(prior),'baseline_sha256':sha(prior/'run.json'),'checks':audits,'unobserved_root_cart_id':'Deterministic fixture id, no query targets or sources use the private root Cart.id','generated_ADD_result_id':'Outside all selected target paths'});r=evaluate(d,q)
                except Exception as e:
                    dep.compose('stop','-t','20','carts',timeout=40,check=False);r={'query':q['id'],'mode':mode,'failure':str(e)};save(d/'failure.json',{'error':str(e),'traceback':traceback.format_exc()})
                results.append(r);save(out/'results.json',{'complete':False,'results':results});print(r,flush=True)
        state['status']='completed'
    finally:
        dep.diagnostics();cleanup=dep.compose('down','--volumes','--remove-orphans',timeout=120,check=False);save(out/'cleanup.json',{**state,'cleanup_returncode':cleanup.returncode})
    save(out/'results.json',{'complete':True,'results':results})

def orders(out,base,only=None,modes=('full','selective')):
    from run_matched_orders_capabilities import ready,requests
    # setup may have been started for a read-only schema preflight; no capture
    # or query has run here before this driver freezes its original inputs.
    out.mkdir(parents=True,exist_ok=False);prep=out/'setup';prep.mkdir();spec=old.spec_for('original',prep,base,1,'768m');spec.pop('networks',None);save(prep/'compose.json',spec)
    dep=old.CachedDeployment(argparse.Namespace(project='tf2-final-orders-'+secrets.token_hex(5),ready_timeout=240),prep,prep/'compose.json');results=[];state={'status':'failed'}
    qs=[q for q in QUERIES if q['role']=='orders' and (only is None or q['id']==only)];prior=previous(qs[0]);frozen=load(prior/'run.json')['cases']
    save(out/'input-protocol-before-queries.json',{'baseline':str(prior),'sha256':sha(prior/'run.json'),'cases':frozen,'data_preparation':'Restore original user/address/card IDs, public fields, empty association lists and Cart item IDs/values. Private authentication fields unused by GET use inert fixture strings. Original source boundary is actual HTTP response, not database history. Generated order ID and wall clock are independent per request.','queries':[q['id'] for q in qs],'driver_sha256':sha(Path(__file__))})
    try:
        dep.start();script=['db.customers.deleteMany({});db.addresses.deleteMany({});db.cards.deleteMany({});']
        for c in frozen:
            f=c['fixture'];customer=c['response']['customer'];doc={k:customer[k] for k in ('firstName','lastName','username')};doc.update(password='unavailable-fixture-only',salt='unavailable-fixture-only',addresses=[],cards=[])
            for col,value,ident in [('customers',doc,f['customer_id']),('addresses',f['address'],f['address_id']),('cards',f['card'],f['card_id'])]:script.append('db.'+col+'.insert(Object.assign('+json.dumps(value)+',{_id:ObjectId('+json.dumps(ident)+')}));')
        text='\n'.join(script);(out/'user-database-input.js').write_text(text);dep.compose('exec','-T','user-db','mongo','users','--quiet','--eval',text);seed_carts(dep,frozen,out)
        prepared=[];trace=secrets.token_hex(16)
        for c in frozen:
            cd=out/('prepared-'+c['case']);cd.mkdir();cl=old.Client(cd);f=c['fixture']
            actual=cl.request('GET','http://127.0.0.1:18581/carts/'+f['customer_id']+'/items',label='independent-input-check');assert actual==f['fixture_read_items'],(actual,f['fixture_read_items'])
            span=secrets.token_hex(8);prepared.append(({'expected_target':True},cl,copy.deepcopy(f),copy.deepcopy(c['request_body']),{'case':c['case'],'message':trace+'/'+span,'traceparent':'00-'+trace+'-'+span+'-01'}))
        dep.compose('stop','-t','20','orders',timeout=40)
        for mode in modes:
            for q in qs:
                check();d=out/(mode+'-'+q['id']);d.mkdir();old.query_build(d/'build',base,q,plan(q));cap=d/'capture';cap.mkdir();active=copy.deepcopy(spec);active['services']['orders']['volumes']=[v for v in active['services']['orders'].get('volumes',[]) if ':/tf2/app.jar:' not in v];mode_config(active,'orders','orders',cap,d/'build',mode);active['services']['orders']['entrypoint'][2]+=' --port=80';save(cap/'compose.json',active)
                dep.out=cap;dep.compose('exec','-T','orders-db','mongo','data','--quiet','--eval','db.dropDatabase()');dep.file=cap/'compose.json'
                try:
                    dep.compose('up','-d','--no-deps','--force-recreate','--pull','never','orders',timeout=180);ready(dep);cases=requests(cap,prepared);dep.compose('stop','-t','20','orders',timeout=40);dep.diagnostics();audits=[]
                    for c,oldcase in zip(cases,frozen):
                        assert c['request_body']==oldcase['request_body'] and c['fixture']==oldcase['fixture'] and c['http_status']==oldcase['http_status']
                        # Independent environment clock is not expected to repeat.
                        if q['path']!='/date':assert old.leaves(c['response'],q['path'])==old.leaves(oldcase['response'],q['path'])
                        assert all(c['response'][k]==oldcase['response'][k] for k in ('customer','address','card','items','total'))
                        audits.append({'case':c['case'],'same_request_actual_source_business_values':True,'environment_clock_new':True})
                    save(cap/'run.json',{'status':'business-completed','roles':['orders'],'mode':mode,'cases':cases});old.verify_build(d/'build');save(d/'input-audit.json',{'baseline':str(prior),'sha256':sha(prior/'run.json'),'checks':audits});r=evaluate(d,q)
                except Exception as e:
                    dep.compose('stop','-t','20','orders',timeout=40,check=False);r={'query':q['id'],'mode':mode,'failure':str(e)};save(d/'failure.json',{'error':str(e),'traceback':traceback.format_exc()})
                results.append(r);save(out/'results.json',{'complete':False,'results':results});print(r,flush=True)
        state['status']='completed'
    finally:
        dep.diagnostics();cleanup=dep.compose('down','--volumes','--remove-orphans',timeout=120,check=False);save(out/'cleanup.json',{**state,'cleanup_returncode':cleanup.returncode})
    save(out/'results.json',{'complete':True,'results':results})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--base-build',type=Path,required=True);p.add_argument('--only');a=p.parse_args();train(a.out.resolve(),a.base_build.resolve(),a.only)
