#!/usr/bin/env python3
"""Bounded response-binding revision: original applications, no performance claim.

Business-specific input generation and manually reviewed oracle projections live
here, never in the planner, agent or reconstruction. Every target leaf is counted
from the actual client response, including targets whose evidence is missing.
"""
import argparse
import base64
import copy
import json
from pathlib import Path
import random
import secrets
import shutil
import subprocess
import time
import traceback
import uuid
from zipfile import ZipFile
from run_planned_service import ROOT,HERE,load,save,sha
from build_distributed_plans import build
from plan_response_binding import plan_response
from run_distributed_paths import observed,cleanup
from run_sockshop_cost import spec_for
from flowdist_full_order import CachedDeployment
from sockshop import Deployment,Client
from host import prepare,submit
from infer_distributed_fields import Reconstruction

HOME=ROOT/'artifacts/response-binding-revision-20261019'
FIRST=ROOT/'artifacts/query-coverage-first-20261019'
BOUNDARY=[{'kind':'binding-source'},{'kind':'argument'},{'kind':'http-json','direction':'response','phase':'read'}]
ROLES={'station':12345,'train':14567,'route':11178,'price':16579,'basic':15680}


def queries(stage):
    if stage=='development':
        pool=load(FIRST/'pool.json');return [q for q in pool['candidates'] if q['id'] in pool['selected_ids']]
    seal=load(HOME/'algorithm-freeze.json')
    path=HERE/'response-binding-heldout-20261019.json'
    if sha(path)!=seal['heldout_sha256']:raise ValueError('Holdout seal differs')
    # A source-hash mismatch stops holdout before attempting any query.
    for file,value in seal['sources'].items():
        if sha(ROOT/file)!=value:raise ValueError('Frozen revision changed: '+file)
    current=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    if subprocess.run(['git','merge-base','--is-ancestor',seal['commit'],current],cwd=ROOT).returncode:raise ValueError('Frozen commit absent')
    return load(path)['queries']


def plan_all(out,base,stage):
    out.mkdir(parents=True,exist_ok=False);result=[]
    for q in queries(stage):
        dest=out/q['id'];dest.mkdir();save(dest/'query.json',q)
        try:
            plan=plan_response(load(base/q['role']/'model.json'),q['entry'],q['target'],q['path'])
            # Existing, pinned library contract, not a new business-specific rule.
            if q['role']=='basic':
                plan['json_conversion_methods']=['edu/fudan/common/util/JsonUtils.conveterObject(Ljava/lang/Object;Ljava/lang/Class;)Ljava/lang/Object;']
                plan['json_conversion_contract']='Existing reviewed default Jackson relative-JSON conversion contract; original implementation pinned.'
            save(dest/'plan.json',plan)
            result.append({'id':q['id'],'application':q['application'],'role':q['role'],'status':'accepted','profile':plan['profile'],'classification':plan['response_binding']['classification']})
        except ValueError as e:
            (dest/'rejection.txt').write_text(traceback.format_exc());result.append({'id':q['id'],'application':q['application'],'role':q['role'],'status':'rejected','reason':str(e)})
        save(out/'planning.json',result)
    save(out/'stage.json',{'stage':stage,'base_build':str(base),'base_sha256':sha(base/'build.json'),'query_count':len(result),'accepted':sum(r['status']=='accepted' for r in result),'cost_experiments':False})
    print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)


def query_build(dest,base,q,plan):
    dest.mkdir();manifest=copy.deepcopy(load(base/'build.json'))
    for f in ('distributed-observer.jar','tools'):(dest/f).symlink_to(base/f,target_is_directory=(f=='tools'))
    for role in manifest['inputs']:
        rd=dest/role;rd.mkdir()
        for file in ('original.jar','model.json','app'):(rd/file).symlink_to(base/role/file,target_is_directory=file=='app')
        p=copy.deepcopy(plan if role==q['role'] else load(base/role/'plan.json'))
        p['collection_elements']=True
        save(rd/'plan.json',p)
        manifest['inputs'][role]['plan_sha256']=sha(rd/'plan.json');manifest['inputs'][role]['profile']=p['profile']
        if role==q['role']:manifest['inputs'][role]['query_config']={'jar':str(base/role/'original.jar'),'entry':q['entry'],'targets':[q['target']],'response_path':q['path']}
    manifest['runtime_driver_sha256']=sha(Path(__file__));save(dest/'build.json',manifest)


def verify_build(build):
    m=load(build/'build.json')
    for file,value in {**m['sources'],**m['dependencies']}.items():
        if sha(Path(file))!=value:raise ValueError('Observer/inference source changed: '+file)
    if sha(build/'distributed-observer.jar')!=m['agent_sha256']:raise ValueError('Observer changed')
    for role,v in m['inputs'].items():
        for file,key in [('original.jar','original_jar_sha256'),('model.json','model_sha256'),('plan.json','plan_sha256')]:
            if sha(build/role/file)!=v[key]:raise ValueError('Frozen application/plan changed')


def reuse_forward_captures(out,base,previous):
    """Only unchanged forward plans/compiled observer classes may reuse captures.

    Raw evidence stays immutable. Re-evaluation uses the new frozen offline
    implementation and records the actual original collector artifact separately.
    """
    def classes(jar):
        import hashlib
        with ZipFile(jar) as z:return {n:hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist() if n.endswith('.class')}
    reports=[]
    for q in load(out/'planning.json'):
        if q['status']!='accepted':continue
        dest=out/q['id'];old=previous/q['id'];plan=load(dest/'plan.json')
        if plan['profile']!='response-forward':continue
        assert sha(dest/'plan.json')==sha(old/'plan.json'),'Changed plan cannot reuse capture'
        assert classes(base/'distributed-observer.jar')==classes(old/'build/distributed-observer.jar'),'Changed runtime observer cannot reuse capture'
        query=load(dest/'query.json');query_build(dest/'build',base,query,plan);runtime=dest/'capture';runtime.mkdir()
        for file in (old/'capture').iterdir():
            if file.name in ('evaluation.json','evaluation-first-development-driver.json','evaluation-v0-201-filter-error.json','field-graph.json','reconstruction-error.txt'):continue
            (runtime/file.name).symlink_to(file.resolve(),target_is_directory=file.is_dir())
        save(runtime/'reuse.json',{'original_capture':str((old/'capture').resolve()),'original_build_sha256':sha(old/'build/build.json'),
             'original_observer_jar_sha256':sha(old/'build/distributed-observer.jar'),'new_observer_jar_sha256':sha(base/'distributed-observer.jar'),
             'all_compiled_observer_class_hashes_identical':True,'target_plan_hash_identical':True,
             'purpose':'Re-evaluate unchanged forward evidence under revised offline implementation; no invented new deployment.'})
        reports.append(evaluate(runtime,dest/'build',query))
    save(out/'runtime-summary.json',reports)


def context(client,trace):
    span=secrets.token_hex(8);client.headers={'traceparent':'00-'+trace+'-'+span+'-01','tracestate':'research=response-binding'};return trace+'/'+span


def mongo_fixture(role,index,rng):
    """Six groups: 2 records, equal-valued fields, 1 record, empty, 3 records,
    repeated equal values; input identities differ even when leaf values match."""
    n=[2,2,1,0,3,2][index%6];token=str(rng.getrandbits(40));docs=[]
    for j in range(n):
        same=index%6 in (1,5);v=7 if same else index*10+j+1
        if role=='station':d={'_id':'S-'+token+'-'+str(j),'name':'SAME' if same else 'N-'+token+'-'+str(j),'stayTime':v,'_class':'fdse.microservice.entity.Station'}
        elif role=='train':d={'_id':'T-'+token+'-'+str(j),'economyClass':v,'confortClass':v,'averageSpeed':100+v,'_class':'train.entity.TrainType'}
        elif role=='route':d={'_id':'R-'+token+'-'+str(j),'stations':['S0','S1','S2'],'distances':[v,v,v] if same else [v,v+10,v+20],'startStationId':'S0','terminalStationId':'S2','_class':'route.entity.Route'}
        else:
            ident=uuid.UUID(int=rng.getrandbits(128));raw=ident.bytes
            d={'_id':{'uuid_legacy_base64':base64.b64encode(raw[:8][::-1]+raw[8:][::-1]).decode()},'routeId':'R-'+token+'-'+str(j),'trainType':'T-'+token+'-'+str(j),'basicPriceRate':float(v),'firstClassPriceRate':float(v),'_class':'price.entity.PriceConfig'}
        docs.append(d)
    return docs


COLLECTION={'station':'station','train':'trainType','route':'routes','price':'price_config'}


def database(dep,role,docs,dest):
    collection=COLLECTION[role]
    script='db.'+collection+'.deleteMany({}); var docs=('+json.dumps(docs)+').map(function(d){if(d._id && d._id.uuid_legacy_base64)d._id=BinData(3,d._id.uuid_legacy_base64);return d;}); if(docs.length)db.'+collection+'.insertMany(docs);'
    dep.compose('exec','-T','ts-'+role+'-mongo','mongo','ts','--quiet','--eval',script)
    audit=dep.compose('exec','-T','ts-'+role+'-mongo','mongo','ts','--quiet','--eval','JSON.stringify(db.'+collection+'.find({}).toArray())').stdout
    (dest/'independent-database.txt').write_text(audit);save(dest/'database-input.json',docs)


def request_raw(client,method,url,body=None):
    try:response=client.request(method,url,body,label='target-query')
    except RuntimeError:
        if not client.events:raise
        response=client.events[-1]['response']
    return response,client.events[-1]['status']


def capture_train(dest,build,q,seed):
    rng=random.Random(seed);role=q['role'];config=load(ROOT/'artifacts/trainticket-cost-preparation-20261016/inputs/inputs.json')
    roles=list(ROLES) if role=='basic' else [role]
    mongo=next(k for k,v in load(ROOT/'artifacts/desktop-inputs/images-lock.json').items() if 'trainticket/ts-station-mongo' in v['services'])
    services={};volumes={};ports={}
    for i,r in enumerate(roles):
        name='ts-'+r+'-service';ports[r]=18720+i
        services[name]={'image':config[r]['image'],'restart':'no','ports':['127.0.0.1:'+str(ports[r])+':'+str(ROLES[r])],'dns_search':['.'],'mem_limit':'768m','cpus':1}
        if r!='basic':
            volume=r+'-data';volumes[volume]={};db='ts-'+r+'-mongo';services[db]={'image':mongo,'restart':'no','volumes':[volume+':/data/db'],'mem_limit':'384m','cpus':1};services[name]['depends_on']=[db]
    spec={'services':services,'volumes':volumes}
    for r in roles:observed(spec,'ts-'+r+'-service',r,dest,build)
    save(dest/'compose.json',spec);dep=Deployment(argparse.Namespace(project='tf2-binding-'+secrets.token_hex(5)),dest,dest/'compose.json');result={'status':'failed','project':dep.args.project,'cases':[],'roles':roles}
    try:
        images={}
        for cfg in services.values():
            if cfg['image'] not in images:
                info=json.loads(dep.command(['docker','image','inspect',cfg['image']]).stdout)[0]
                if cfg['image'] not in info.get('RepoDigests',[]):raise ValueError('Image not pinned')
                images[cfg['image']]={'id':info['Id'],'digests':info['RepoDigests']}
        save(dest/'images.json',images);dep.compose('up','-d','--pull','never',timeout=180)
        client=Client(dest);deadline=time.monotonic()+240
        while time.monotonic()<deadline:
            try:
                for r in roles:client.request('GET','http://127.0.0.1:'+str(ports[r])+'/api/v1/'+r+'service/'+({'train':'trains/','price':'prices/'}.get(r,''))+'welcome',label='readiness')
                break
            except Exception:time.sleep(2)
        else:raise ValueError('Readiness timeout')
        trace=secrets.token_hex(16)
        if role=='basic':
            # Existing independent real multi-source fixture generator, newly
            # generated seed; retain one missing-target and real fallback cases.
            from run_train_multisource import freeze
            temp=dest/'basic-inputs';freeze(temp,build,ROOT/'artifacts/trainticket-cost-preparation-20261016/inputs/inputs.json',seed)
            db=load(temp/'database-fixtures.json')
            for r,collections in db.items():
                rd=dest/('db-'+r);rd.mkdir();database(dep,r,list(collections.values())[0],rd)
            cases=load(temp/'cases.json')[:8]
        else:cases=[{'case':'group-'+str(i),'index':i} for i in range(6)]
        for c in cases:
            cd=dest/c['case'];cd.mkdir();cl=Client(cd);message=context(cl,trace)
            if role=='basic':method='POST';path='/api/v1/basicservice/basic/travel';body=c['body'];docs=[]
            else:
                docs=mongo_fixture(role,c['index'],rng);database(dep,role,docs,cd);body=None;method,path=q['http'].split(' ',1)
                substitutions={'id':docs[0]['_id'] if docs and isinstance(docs[0]['_id'],str) else 'MISSING',
                   'route':docs[0].get('routeId','MISSING') if docs else 'MISSING','train':docs[0].get('trainType','MISSING') if docs else 'MISSING'}
                for k,v in substitutions.items():path=path.replace('{'+k+'}',v)
                if '{' in path:raise ValueError('No preregistered request generator for '+q['http'])
            response,status=request_raw(cl,method,'http://127.0.0.1:'+str(ports[role])+path,body)
            r={**c,'message':message,'response':response,'http_status':status,'request_path':path,'database_documents':docs}
            # Business check independent of TF: query methods preserve stored
            # objects/list order. Missing-entity branches may return no data.
            if role!='basic' and status==200:
                data=response.get('data') if isinstance(response,dict) else response
                if isinstance(data,list) and len(data)!=len(docs):raise ValueError('Business list cardinality differs from database')
                actual=data if isinstance(data,list) else [data] if isinstance(data,dict) else []
                for at,item in enumerate(actual):
                    if at>=len(docs):raise ValueError('Business object absent from database fixtures')
                    expected=docs[at]
                    for key,value in expected.items():
                        if key=='_class' or key=='_id' and not isinstance(value,str):continue
                        field='id' if key=='_id' else key
                        if item.get(field)!=value:raise ValueError('Business field differs from independent database: '+field)
            if role=='basic' and status!=c['expected_http_status']:raise ValueError('Basic business HTTP status differs')
            save(cd/'contract-result.json',r);result['cases'].append(r)
        for r in roles:dep.compose('stop','-t','20','ts-'+r+'-service',timeout=40)
        verify_build(build);result['status']='business-completed'
    finally:cleanup(dep,result,dest)


def capture_sock(dest,build,q,seed):
    spec=spec_for('tracefusion',dest,build,1,'768m')
    save(dest/'compose.json',spec);dep=CachedDeployment(argparse.Namespace(project='tf2-binding-'+secrets.token_hex(5),ready_timeout=180),dest,dest/'compose.json');result={'status':'failed','project':dep.args.project,'roles':['orders','carts','shipping'],'cases':[]}
    try:
        dep.start();trace=secrets.token_hex(16)
        templates=[{'items':[{'key':'a','quantity':1,'unitPrice':1.25}]},
            {'items':[{'key':'a','quantity':2,'unitPrice':2.5},{'key':'b','quantity':2,'unitPrice':2.5}]},
            {'items':[]},{'items':[{'key':'a','quantity':3,'unitPrice':0.}]},
            {'items':[{'key':'a','quantity':1,'unitPrice':5.}],'patch':{'key':'a','quantity':2,'unitPrice':5.}},
            {'items':[{'key':'a','quantity':1,'unitPrice':1.25}]}]
        for i,c in enumerate(templates):
            c={**c,'expected_target':True};name='group-'+str(i);cd=dest/name
            prepared=prepare(c,name,cd,'http://127.0.0.1:18580','http://127.0.0.1:18581');message=context(prepared[1],trace)
            if q['role']=='orders':
                b=submit(prepared,'http://127.0.0.1:18582',cd)
                if not b['business_passed']:raise ValueError('Orders business check failed: '+str(b))
                response=load(cd/'order-response.json');status=b['http_status']
            else:
                method,path=q['http'].split(' ',1);path=path.replace('{customerId}',prepared[2]['customer_id'])
                if '{' in path:raise ValueError('No generator for '+path)
                response,status=request_raw(prepared[1],method,'http://127.0.0.1:18581'+path)
                if status!=200:raise ValueError('Cart request failed')
            r={'case':name,'message':message,'http_status':status,'response':response,'fixture':prepared[2]};save(cd/'contract-result.json',r);result['cases'].append(r)
        for r in result['roles']:dep.compose('stop','-t','20',r,timeout=40)
        verify_build(build);result['status']='business-completed'
    finally:cleanup(dep,result,dest)


def leaves(value,pattern,path=''):
    """Concrete targets from client JSON, not from collected evidence."""
    parts=pattern[1:].split('/') if isinstance(pattern,str) else pattern
    if not parts:return [(path,value)]
    part=parts[0];rest=parts[1:]
    if isinstance(value,list):
        indexes=range(len(value)) if part=='*' else [int(part)] if part.isdecimal() and int(part)<len(value) else []
        return [p for i in indexes for p in leaves(value[i],rest,path+'/'+str(i))]
    if isinstance(value,dict):
        key=part.replace('~1','/').replace('~0','~')
        if key in value:return leaves(value[key],rest,path+'/'+part)
    return []


def source_coord(role,row,f):
    return (role,row.get('message'),row.get('frame'),row['seq'],f['owner'],f['field'],f['version'],f['path'])


def predicted_coord(s):return (s['service'],s.get('message'),s.get('root_frame',s.get('frame')),s['seq'],s['owner'],s['field'],s['version'],s.get('path'))


def oracle(q,c,path,rows):
    """Independent original-method projections, not TF edges or aliases.

    Repo methods return their original entity/list (javap reviewed). Match raw
    repository return fields by list position and declared schema field. RPC
    passthrough projections are manually specified by original controller code.
    Scalar status writes are literal constants in the original Basic method.
    """
    role=q['role'];message=c['message'];return_frames={r['frame'] for r in rows[role] if r['kind']=='binding-return' and r.get('message')==message}
    root=[r for r in rows[role] if r['kind']=='enter' and r['method']==q['entry'] and r['frame'] in return_frames]
    if len(root)!=1:raise ValueError('Independent root-call witness absent/ambiguous')
    frame=root[0]['frame']
    if role=='basic' and q['target'].endswith('TravelResult.status'):return []
    if role=='station' and '.queryById(' in q['entry']:
        # Reviewed original offsets 0..31: one repository read then getName;
        # offsets 35..57: missing ID is copied directly from argument zero.
        if not c['database_documents']:
            assert c['response']['status']==0 and c['response']['data']==c['request_path'].rsplit('/',1)[-1]
            arg=root[0]['args'][0]
            return [(role,None,None,root[0]['seq'],arg['object'],'@argument:0',0,None)]
        candidates=[source_coord(role,r,f) for r in rows[role] if r['kind']=='binding-source' and r['frame']==frame
                    for f in r['fields'] if f['path']=='/name' and f['field']=='fdse/microservice/entity/Station.name']
        if len(candidates)==1:return candidates
        raise ValueError('Independent Station getName projection absent/ambiguous')
    if role in ('station','train','route','price'):
        # For the read/list methods in this protocol, Response.data wraps the
        # repository result without reordering or remapping its members.
        relative=path.removeprefix('/data')
        candidates=[]
        returns=[r for r in rows[role] if r['kind']=='binding-source' and r.get('frame')==frame]
        if role=='train' and '.retrieve(' in q['entry']:
            # Original offsets5 and31 call findById twice. Only the SECOND
            # invocation is returned; never select a same-valued first object.
            if len(returns)!=2:raise ValueError('Independent Train two-read contract differs')
            returns=returns[1:]
        for r in returns:
                for f in r['fields']:
                    if f['path']==relative:
                        declared=q['target'].rsplit('.',1);declared=declared[0].replace('.','/')+'.'+declared[1]
                        if f.get('schema_field',f['field'])!=declared:raise ValueError('Source field differs from independently declared business field')
                        if f['field'].startswith('@list:') and f['field']!='@list:'+path.rsplit('/',1)[-1]:raise ValueError('Source list slot differs')
                        candidates.append(source_coord(role,r,f))
        if len(candidates)==1:return candidates
        raise ValueError('Independent repository-return target projection absent/ambiguous: '+relative)
    if role=='orders':
        if path.startswith('/customer/addresses/'):
            uri='/customers/'+c['fixture']['customer_id']+'/addresses';relative=path.removeprefix('/customer/addresses')
        elif path.startswith('/customer/'):
            uri='/customers/'+c['fixture']['customer_id'];relative=path.removeprefix('/customer')
        elif path.startswith('/address/'):
            uri='/addresses/'+c['fixture']['address_id'];relative=path.removeprefix('/address')
        elif path.startswith('/card/'):
            uri='/cards/'+c['fixture']['card_id'];relative=path.removeprefix('/card')
        else:raise ValueError('No independently reviewed projection: '+path)
        candidates=[]
        for r in rows[role]:
            if r['kind']=='http-json' and r['phase']=='read' and r['direction']=='response' and r.get('parent_message')==message and uri in r.get('uri',''):
                for f in r['fields']:
                    if f['path']==relative:candidates.append(source_coord(role,r,f))
        if len(candidates)==1:return candidates
        raise ValueError('Independent upstream response projection absent/ambiguous: '+uri+' '+relative)
    if role=='basic':
        # Original queryTrainType helper decodes Train response.data. The core
        # is free to answer unknown; the oracle still names the actual RPC leaf.
        candidates=[]
        for r in rows[role]:
            if r['kind']=='http-json' and r['phase']=='read' and r['direction']=='response' and r.get('parent_message')==message and 'ts-train-service:' in r.get('uri',''):
                for f in r['fields']:
                    if f['path']=='/data/'+path.rsplit('/',1)[-1]:candidates.append(source_coord(role,r,f))
        if len(candidates)==1:return candidates
        raise ValueError('Independent train RPC projection absent/ambiguous')
    # Cart DAO helper is not an admitted repository-return contract. Its origin
    # is not invented at root return; retain a separate oracle-unavailable flag.
    raise ValueError('Cart helper source path requires independent DAO witness; not asserted from equal values')


def evaluate(dest,build,q):
    run=load(dest/'run.json');raw={}
    for role in run['roles']:
        p=dest/role/'events.jsonl';raw[role]=[json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []
    invalid=None;graph=None
    try:
        if run['status']!='business-completed' or run.get('cleanup_returncode'):raise ValueError('Incomplete business deployment')
        graph=Reconstruction(build,dest,run['roles'])
    except Exception as e:invalid=str(e);(dest/'reconstruction-error.txt').write_text(traceback.format_exc())
    result={'id':q['id'],'application':q['application'],'requests':len(run['cases']),'target_instances':0,'known':0,'unknown':0,'N/A_requests':0,'evidence_invalid':0,'oracle_unavailable':0,'known_oracle_checked':0,'exact':0,'tp':0,'fp':0,'fn':0,'invalid_reason':invalid,'predictions':[]}
    for c in run['cases']:
        if q['role'] in COLLECTION and 200<=c['http_status']<300:
            data=c['response'].get('data') if isinstance(c['response'],dict) else c['response']
            actual=data if isinstance(data,list) else [data] if isinstance(data,dict) else []
            docs=c['database_documents']
            for at,item in enumerate(actual):
                if at>=len(docs):raise ValueError('Independent business audit: result cardinality differs')
                for k,v in docs[at].items():
                    if k=='_class' or k=='_id' and not isinstance(v,str):continue
                    if item.get('id' if k=='_id' else k)!=v:raise ValueError('Independent business audit: database field projection differs')
            if q['role']=='station' and '.queryById(' in q['entry'] and docs:
                if c['response']['status']!=1 or c['response']['data']!=docs[0]['name']:raise ValueError('Independent Station getName business projection differs')
        if q['role']=='basic' and c['http_status']==200:
            if c['response'].get('data',{}).get('status')!=(c['expected_status']==1):raise ValueError('Independent Basic literal-status branch oracle differs')
        targets=leaves(c['response'],q['path']) if 200<=c['http_status']<300 else []
        if not targets:result['N/A_requests']+=1
        for path,value in targets:
            result['target_instances']+=1;item={'case':c['case'],'message':c['message'],'path':path,'client_value':value};expected=None
            try:expected=oracle(q,c,path,raw);item['expected']=expected
            except ValueError as e:item['oracle_error']=str(e);result['oracle_unavailable']+=1
            if invalid:result['evidence_invalid']+=1;item['status']='evidence-invalid'
            else:
                try:
                    answer=graph.query(c['message'],path,q['role'],boundary=BOUNDARY);item['answer']=answer
                    if answer['target']['observed'].get('value')!=value:raise ValueError('Collected target differs from actual client JSON')
                    item['unknown_reasons']=sorted({n['unknown'] for n in graph.nodes.values() if n.get('unknown') and n.get('root_frame') in {r['frame'] for r in raw[q['role']] if r['kind']=='binding-return' and r.get('message')==c['message']}})
                    item['status']='known' if answer['known'] else 'unknown';result[item['status']]+=1
                    if answer['known'] and expected is not None:
                        wanted=set(expected);actual={predicted_coord(s) for s in answer['sources']};result['known_oracle_checked']+=1;result['exact']+=int(wanted==actual)
                        result['tp']+=len(wanted&actual);result['fp']+=len(actual-wanted);result['fn']+=len(wanted-actual);item['actual']=sorted(actual,key=str)
                except ValueError as e:result['evidence_invalid']+=1;item.update(status='evidence-invalid',error=str(e))
            result['predictions'].append(item)
    if graph:save(dest/'field-graph.json',graph.export())
    save(dest/'evaluation.json',result);return result


def capture_all(out,base,only=None):
    planning=load(out/'planning.json');reports=[]
    for index,row in enumerate(planning):
        if row['status']!='accepted' or only and row['id']!=only:continue
        dest=out/row['id'];q=load(dest/'query.json');runtime=dest/'capture'
        if runtime.exists():
            if (runtime/'evaluation.json').exists():reports.append(load(runtime/'evaluation.json'));continue
            raise ValueError('Incomplete capture retained; use a new attempt directory: '+str(runtime))
        query_build(dest/'build',base,q,load(dest/'plan.json'));runtime.mkdir();verify_build(dest/'build')
        try:
            if q['application']=='sockshop':capture_sock(runtime,dest/'build',q,191019+index)
            else:capture_train(runtime,dest/'build',q,191019+index)
        except Exception:
            (runtime/'capture-error.txt').write_text(traceback.format_exc());print(row['id'],'capture failed; evidence retained',flush=True)
        if (runtime/'run.json').exists():reports.append(evaluate(runtime,dest/'build',q))
        else:reports.append({'id':q['id'],'status':'deployment-failed','error':(runtime/'capture-error.txt').read_text()})
        save(out/'runtime-summary.json',reports);print({k:v for k,v in reports[-1].items() if k!='predictions'},flush=True)
    save(out/'runtime-summary.json',reports)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('plan','capture','evaluate','reuse-forward'));p.add_argument('--stage',choices=('development','heldout'),default='development');p.add_argument('--out',type=Path,required=True);p.add_argument('--base',type=Path,required=True);p.add_argument('--only');p.add_argument('--previous',type=Path);a=p.parse_args();out=a.out.resolve();base=a.base.resolve()
    if a.action=='plan':plan_all(out,base,a.stage)
    elif a.action=='reuse-forward':
        assert a.stage=='development' and a.previous;reuse_forward_captures(out,base,a.previous.resolve())
    elif a.action=='capture':capture_all(out,base,a.only)
    else:
        reports=[]
        for r in load(out/'planning.json'):
            if r['status']=='accepted' and (out/r['id']/'capture/run.json').exists():reports.append(evaluate(out/r['id']/'capture',out/r['id']/'build',load(out/r['id']/'query.json')))
        save(out/'runtime-summary.json',reports)
