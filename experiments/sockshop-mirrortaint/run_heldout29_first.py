#!/usr/bin/env python3
"""First evaluation of the original 29 sealed fields, without core changes.

The experiment's independent projections never call reconstruction or native
taint to construct truth. Runtime decisions do not select query strategies.
"""
import argparse,copy,json,secrets,time,traceback,sys,hashlib,base64
from pathlib import Path
from collections import defaultdict,Counter
from urllib.parse import urlparse
from run_planned_service import ROOT,HERE,load,save,sha
import run_frozen_capability_acceptance as tf
import run_response_binding_revision as old
import run_mirror_extra_capabilities as extra
import run_mirror_read_capabilities as reads
import run_mirror_sock_capabilities as sock
from build_mirror_capability import configure as original_native_configure
from run_mirror_capability_probe import read_events,native_answer
from run_quota_capability_acceptance import qualified_options

SEAL=HERE/'execution-kernel-protocol-20261020.json'
SEAL_SHA='87c40107282aaccb8e049fc5ffe37bb1e66deacfeabd0f015a08544bc1972fae'
ORIGINAL_TF_ORACLE=tf.independent
ORIGINAL_OBSERVED=old.observed
ORIGINAL_SPEC=old.spec_for


def check(root):
    assert sha(SEAL)==SEAL_SHA
    for p,h in load(root/'algorithm-freeze.json')['sources'].items():assert sha(Path(p))==h,p
    protocol=load(root/'protocol-before-first.json')
    for p,h in protocol['experiment_sources'].items():assert sha(ROOT/p)==h,p


def native_configure(spec,dest,base,bundle,q):
    original_native_configure(spec,dest,base,bundle,q)
    name=q['role'] if q['application']=='sockshop' else 'ts-'+q['role']+'-service'
    cfg=spec['services'][name]
    cfg['volumes'].append(str(bundle/'runtime-witness.jar')+':/tf2/runtime-witness.jar:ro')
    # Registered before native transformers, so the witness hashes original
    # mapper definition bytes rather than MT's rewritten method bodies.
    opts=cfg['environment']['JAVA_OPTS']
    cfg['environment']['JAVA_OPTS']='-javaagent:/tf2/runtime-witness.jar -Dnative.library.events=/tf2/capture/native-library.jsonl '+opts+' -XX:ParallelGCThreads=1 -XX:CICompilerCount=2'


def observed(spec,name,role,cap,build):
    ORIGINAL_OBSERVED(spec,name,role,cap,build)
    e=spec['services'][name]['environment'];e['JAVA_OPTS']=qualified_options(e['JAVA_OPTS'])


def original_spec(*args,**kwargs):
    spec=ORIGINAL_SPEC(*args,**kwargs)
    for cfg in spec['services'].values():
        e=cfg.get('environment',{})
        if '-javaagent:' in e.get('JAVA_OPTS',''):e['JAVA_OPTS']=qualified_options(e['JAVA_OPTS'])
    return spec


def independent_tf(q,c,path,rows):
    if q['role']=='basic' and path=='/data/percent':
        # Reviewed original TravelResult default plus the sole setPercent(1).
        assert c['response']['data']['percent'] in (0,1)
        return []
    if q['role']=='orders' and path in ('/id','/customerId'):
        if path=='/id':raise ValueError('Generated Mongo ID has no independently audited generator/field coordinate; do not infer an empty origin')
        facts=[r for r in rows['orders'] if r['kind']=='http-source-fact' and r.get('parent_message')==c['message'] and urlparse(r.get('uri','')).path=='/customers/'+c['fixture']['customer_id']]
        assert len(facts)==1
        fact=facts[0];raw=base64.b64decode(fact['raw_base64']);assert fact['document_complete'] and hashlib.sha256(raw).hexdigest()==fact['raw_sha256']
        doc=json.loads(raw);href=doc['_links']['self']['href'];assert href.rstrip('/').rsplit('/',1)[-1]==c['response']['customerId']
        fs=[f for f in fact['fields'] if f['path']=='/_links/self/href']
        if len(fs)!=1:raise ValueError('Actual self-link raw value present, but independent decoded Link.href instance coordinate unavailable')
        return [old.source_coord('orders',fact,fs[0])]
    return ORIGINAL_TF_ORACLE(q,c,path,rows)


def independent_native(q,c,path,rows,target):
    if q['role']=='basic' and path=='/data/percent':
        assert c['response']['data']['percent'] in (0,1);return set()
    if q['role']=='orders' and path in ('/id','/customerId'):
        raise ValueError('Generated ID or HATEOAS self-link requires independently audited physical source coordinate; no same-name/value inference')
    if q['role']=='orders':return sock.independent(q,c,path,rows,target)
    if q['role'] in ('basic','ticketinfo') or '{start}' in q['http']:return extra.independent(q,c,path,rows,target)
    return reads.independently_expected(q,c,path,rows,target)


def score_native(dest,qs):
    cap=dest/'capture';rows=read_events(cap,qs[0]['role']);cases=load(cap/'run.json')['cases'];result=[]
    for q in qs:
        targets=[];na=0
        for c in cases:
            leaves=old.leaves(c['response'],q['path']) if 200<=c['http_status']<300 else [];na+=not bool(leaves)
            for path,value in leaves:
                a=native_answer(rows,c['message'],path);t={'query':q['id'],'case':c['case'],'path':path,'client_value':value,'answer':a}
                try:
                    rs=[r for r in rows if r['kind']=='target' and r['context'].get('message')==c['message']];assert len(rs)==1
                    wire=[f for f in rs[0].get('wire_fields',[]) if f['path']==path]
                    assert len(wire)==1 and wire[0]['observed'].get('value')==value,'Serialized target/client mismatch'
                    expected=independent_native(q,c,path,rows,rs[0]);actual={tuple(v) for v in a.get('sources',[])}
                    t.update(expected=sorted(expected,key=str),actual=sorted(actual,key=str),state=('known_correct' if actual==expected else 'known_wrong') if a['state']=='known' else a['state'],tp=len(actual&expected) if a['state']=='known' else 0,fp=len(actual-expected) if a['state']=='known' else 0,fn=len(expected-actual) if a['state']=='known' else len(expected))
                except Exception as e:t.update(state='known_unchecked' if a['state']=='known' else a['state'],oracle_error=str(e))
                targets.append(t)
        result.append({'query':q['id'],'mode':'mirrortaint','requests':len(cases),'N/A_requests':na,'targets':len(targets),'states':dict(Counter(t['state'] for t in targets)),'oracle_unavailable':sum('oracle_error'in t for t in targets),'tp':sum(t.get('tp',0) for t in targets),'fp':sum(t.get('fp',0) for t in targets),'fn':sum(t.get('fn',0) for t in targets),'predictions':targets})
    save(dest/'evaluation.json',result)
    witness=cap/qs[0]['role']/'native-library.jsonl'
    observed_rows=[json.loads(s) for s in witness.read_text().splitlines()]
    expected='c9d931c46efbc313108215ad320a7fa1b1c25bd82af5f4ae781b46f4d1d99e59' if qs[0]['application']=='sockshop' else '1a33365556ca88668006a549208e136c5c20c965b7cdc8406a106ac8f5bae7f3'
    assert observed_rows and all(r['sha256']==expected and 'BOOT-INF/lib/jackson-databind-' in r['source'] for r in observed_rows),observed_rows
    save(dest/'native-library-audit.json',{'passed':True,'original_mapper_sha256':expected,'definitions':observed_rows,'native_propagation_changed':False})
    return [{k:v for k,v in r.items() if k!='predictions'} for r in result]


def prepare(root):
    seal=load(SEAL);qs=seal['unexamined_candidates'];assert len(qs)==29
    groups=defaultdict(list)
    for q in qs:groups[q['entry']].append(q)
    known_entries={q['entry'] for q in load(HERE/'capability-comparison-62-20261020.json')['queries']}
    assert set(groups)<=known_entries
    sources=['run_heldout29_first.py','build_native_mirror_bundle.py','NativeLibraryWitness.java','run_frozen_capability_acceptance.py','run_mirror_extra_capabilities.py','run_mirror_read_capabilities.py','run_mirror_sock_capabilities.py','build_mirror_capability.py','run_matched_orders_capabilities.py','run_response_binding_revision.py','run_sockshop_model_revision.py','run_train_multisource.py','run_quota_capability_acceptance.py']
    p={'algorithm_commit':'76d2050de6634c52db6583832aefa1e6892454c9','seal_sha256':SEAL_SHA,'queries':qs,'query_count':29,'entry_count':len(groups),'novelty':'All are previously untested fields at previously used entries, not new entries or third-party blind queries. Inputs reuse frozen six-case repository/Orders or eight-case travel structures.','selection':'All remaining candidates; no replacements after planning.','order':'Freeze truth and driver; commit protocol; plan all queries; native capture by entry then full and selective per accepted query. Refused TF queries remain in inventory and native evaluation.','runtime':{'TF':'32/256 MiB heap, GC threads1, compiler threads2','MirrorTaint':'32/512 MiB heap (historical qualified preset), GC threads1, compiler threads2','target_limit':'1 CPU /768MiB','cost_claim':False},'independent_truth':{'repository':'Literal original repository return/list order and declared physical field/element coordinates; route filter selected source index determined from original predicate and actual documents. UUID serialization projection is checked separately from identity.','basic_percent':'Original default0 or literal setPercent(1), no declared input-field data source; selection evidence excluded.','basic_train':'Actual Train RPC response.data physical field, original JsonUtils default conversion.','ticketinfo':'Actual incoming Basic RPC response leaf at identical relative JSON path, including explicit null.','orders_nested':'Original Customer/Address/Card references, actual raw HTTP decode facts, field identity/version, ignored id yields default null. Empty associations produce no elements.','orders_customerId':'Original Future customer Resource.getId().getHref() then parseId. Require actual self-link and decoded physical Link.href coordinate; absent coordinate is oracle unavailable.','orders_id':'Mongo-generated ID lacks independently audited generator/field source coordinate in this protocol: oracle unavailable, never presumed empty.'},'failure_policy':'First outcomes immutable. Core changes forbidden; experiment/evaluation defects retain initial records and separate corrected evaluation. Missing targets N/A, literal null is a target; unknown, analysis_limited, invalid, known_unchecked distinct.','baseline_packaging':'Native author JAR and fixed v09 adapter unchanged; relocate only exporter private Jackson. Read-only witness installed first to record original business mapper definitions. Historical368 mask is not silently replaced by this new configuration.','experiment_sources':{str((HERE/n).relative_to(ROOT)):sha(HERE/n) for n in sources},'baseline_bundle_sha256':sha(root/'native-bundle/build.json')}
    assert not (root/'protocol-before-first.json').exists();save(root/'protocol-before-first.json',p)
    save(HERE/'heldout29-protocol-20261023.json',p)
    print({'prepared':True,'queries':len(qs),'entries':len(groups)},flush=True)


def plan_all(root):
    from plan_capability_policy import choose
    check(root);out=root/'frozen-plans';out.mkdir();result=[]
    for q in load(root/'protocol-before-first.json')['queries']:
        r={'query':q}
        try:
            p,policy=choose(load(root/'frozen-base'/q['role']/'model.json'),q);save(out/(q['id']+'.json'),p);r.update(accepted=True,policy=policy,plan_sha256=sha(out/(q['id']+'.json')),profile=p['profile'])
        except Exception as e:r.update(accepted=False,rejection=str(e),exception_type=type(e).__name__)
        result.append(r)
    save(out/'planning.json',result);print({'planning_accepted':sum(r['accepted']for r in result),'planning_rejected':sum(not r['accepted']for r in result)},flush=True)


def install(root):
    check(root);tf.HOME=root;old.observed=observed;old.spec_for=original_spec;tf.independent=independent_tf
    extra.configure=native_configure


def run_train(root):
    install(root);base=root/'frozen-base';bundle=root/'native-bundle';out=root/'train-first';out.mkdir();results=[];groups=defaultdict(list)
    for q in load(root/'protocol-before-first.json')['queries']:
        if q['application']=='trainticket':groups[q['entry']].append(q)
    for entry,qs in groups.items():
        check(root);q=qs[0];nd=out/('native-'+q['id']);nd.mkdir();cap=nd/'capture'
        try:
            if q['role'] in ('basic','ticketinfo') or '{start}'in q['http']:extra.capture(cap,base,bundle,q)
            else:
                cap.mkdir()
                def conf(spec,name,role,capt,bld):
                    observed(spec,name,role,capt,bld)
                    if role==q['role']:native_configure(spec,capt,base,bundle,q)
                old.observed=conf
                try:old.capture_train(cap,base,q,20261020)
                finally:old.observed=observed
            results.extend(score_native(nd,qs))
        except Exception as e:
            r={'mode':'mirrortaint','queries':[v['id']for v in qs],'failure':str(e)};save(nd/'failure.json',{**r,'traceback':traceback.format_exc()});results.append(r)
        save(out/'results.json',{'complete':False,'results':results});print({'native_entry':entry,'result':results[-1]},flush=True)
        if not (cap/'run.json').exists() or load(cap/'run.json')['status']!='business-completed':continue
        for mode in ('full','selective'):
            for q in qs:
                check(root);d=out/(mode+'-'+q['id']);d.mkdir()
                if not(root/'frozen-plans'/(q['id']+'.json')).exists():
                    r={'query':q['id'],'mode':mode,'planning_rejected':True};save(d/'planning-rejection.json',r)
                else:
                    old.query_build(d/'build',base,q,tf.plan(q));tf.previous=lambda query,source=cap:source
                    try:tf.capture_train(d,base,q,mode);r=tf.evaluate(d,q)
                    except Exception as e:r={'query':q['id'],'mode':mode,'failure':str(e)};save(d/'failure.json',{**r,'traceback':traceback.format_exc()})
                results.append(r);save(out/'results.json',{'complete':False,'results':results});print(r,flush=True)
    save(out/'results.json',{'complete':True,'results':results})


def run_orders(root):
    from run_matched_orders_capabilities import ready,requests
    install(root);base=root/'frozen-base';bundle=root/'native-bundle';out=root/'orders-first';out.mkdir();prep=out/'setup';prep.mkdir();spec=old.spec_for('original',prep,base,1,'768m');spec.pop('networks',None);save(prep/'compose.json',spec)
    qs=[q for q in load(root/'protocol-before-first.json')['queries']if q['role']=='orders'];prior=tf.previous(qs[0]);frozen=load(prior/'run.json')['cases']
    save(out/'frozen-business-inputs-before-runtime.json',{'cases':frozen,'historical_input_capture':str(prior),'sha256':sha(prior/'run.json')})
    dep=old.CachedDeployment(argparse.Namespace(project='tf2-held29-orders-'+secrets.token_hex(4),ready_timeout=240),prep,prep/'compose.json');results=[]
    try:
        dep.start();script=['db.customers.deleteMany({});db.addresses.deleteMany({});db.cards.deleteMany({});']
        for c in frozen:
            f=c['fixture'];doc={k:c['response']['customer'][k] for k in ('firstName','lastName','username')};doc.update(password='unavailable-fixture-only',salt='unavailable-fixture-only',addresses=[],cards=[])
            for col,value,ident in [('customers',doc,f['customer_id']),('addresses',f['address'],f['address_id']),('cards',f['card'],f['card_id'])]:script.append('db.'+col+'.insert(Object.assign('+json.dumps(value)+',{_id:ObjectId('+json.dumps(ident)+')}));')
        text='\n'.join(script);(out/'user-database-input.js').write_text(text);dep.compose('exec','-T','user-db','mongo','users','--quiet','--eval',text);tf.seed_carts(dep,frozen,out)
        prepared=[];trace=secrets.token_hex(16)
        for c in frozen:
            cd=out/('prepared-'+c['case']);cd.mkdir();cl=old.Client(cd);f=c['fixture'];assert cl.request('GET','http://127.0.0.1:18581/carts/'+f['customer_id']+'/items',label='independent-input-check')==f['fixture_read_items']
            span=secrets.token_hex(8);prepared.append(({'expected_target':True},cl,copy.deepcopy(f),copy.deepcopy(c['request_body']),{'case':c['case'],'message':trace+'/'+span,'traceparent':'00-'+trace+'-'+span+'-01'}))
        dep.compose('stop','-t','20','orders',timeout=40)
        jobs=[('mirrortaint',qs[0])]+[(mode,q)for mode in ('full','selective')for q in qs]
        for mode,q in jobs:
            check(root);d=out/('native' if mode=='mirrortaint'else mode+'-'+q['id']);d.mkdir()
            if mode!='mirrortaint'and not(root/'frozen-plans'/(q['id']+'.json')).exists():
                r={'query':q['id'],'mode':mode,'planning_rejected':True};results.append(r);save(d/'planning-rejection.json',r);continue
            cap=d/'capture';cap.mkdir();active=copy.deepcopy(spec);active['services']['orders']['volumes']=[v for v in active['services']['orders'].get('volumes',[])if ':/tf2/app.jar:'not in v]
            if mode=='mirrortaint':native_configure(active,cap,base,bundle,q)
            else:old.query_build(d/'build',base,q,tf.plan(q));tf.mode_config(active,'orders','orders',cap,d/'build',mode);active['services']['orders']['entrypoint'][2]+=' --port=80'
            save(cap/'compose.json',active);dep.out=cap;dep.compose('exec','-T','orders-db','mongo','data','--quiet','--eval','db.dropDatabase()');dep.file=cap/'compose.json'
            try:
                dep.compose('up','-d','--no-deps','--force-recreate','--pull','never','orders',timeout=180);ready(dep);cases=requests(cap,prepared);dep.compose('stop','-t','20','orders',timeout=40);dep.diagnostics()
                for c,previous in zip(cases,frozen):
                    assert c['request_body']==previous['request_body']and c['fixture']==previous['fixture']and c['http_status']==previous['http_status']
                    assert all(c['response'][k]==previous['response'][k]for k in ('customer','address','card','items','total','customerId'))
                    assert isinstance(c['response']['id'],str)and c['response']['id']
                save(cap/'run.json',{'status':'business-completed','roles':['orders'],'mode':mode,'cases':cases});save(d/'input-audit.json',{'passed':True,'requests_sources_business_values_equal':True,'generated_order_id_and_clock_allowed_to_vary':True})
                if mode=='mirrortaint':rs=score_native(d,qs);results.extend(rs);r={'mode':mode,'summaries':rs}
                else:old.verify_build(d/'build');r=tf.evaluate(d,q);results.append(r)
            except Exception as e:
                dep.compose('stop','-t','20','orders',timeout=40,check=False);r={'query':q['id'],'mode':mode,'failure':str(e)};save(d/'failure.json',{**r,'traceback':traceback.format_exc()});results.append(r)
            save(out/'results.json',{'complete':False,'results':results});print(r,flush=True)
    finally:
        dep.diagnostics();cleanup=dep.compose('down','--volumes','--remove-orphans',timeout=120,check=False);save(out/'cleanup.json',{'cleanup_returncode':cleanup.returncode})
    save(out/'results.json',{'complete':True,'results':results})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--stage',choices=('prepare','plan','train','orders'),required=True);a=p.parse_args();r=a.root.resolve()
    {'prepare':prepare,'plan':plan_all,'train':run_train,'orders':run_orders}[a.stage](r)
