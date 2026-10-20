#!/usr/bin/env python3
"""Separate original-JAR Cart/read-model and Train/return-binding cost tasks.

Uses the existing low-rate sampler, nearest-rank percentiles, independent
deployments and subprocess offline measurement. Oracle projections are fixed
original-code projections; no inference edges decide their expected sources.
"""
import argparse,copy,json,random,resource,secrets,statistics,subprocess,sys,time,urllib.request,urllib.error
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from collections import Counter
from run_planned_service import ROOT,HERE,load,save,sha
import run_response_binding_revision as old
import run_sockshop_model_revision as model
import run_sockshop_cost as cost
from run_distributed_paths import observed
from infer_distributed_fields import Reconstruction

JVM=cost.JVM


def driver_sources():
    return {str(p):sha(p) for p in (Path(__file__).resolve(),HERE/'run_response_binding_revision.py',HERE/'run_sockshop_model_revision.py',HERE/'run_sockshop_cost.py',ROOT/'scripts/sockshop.py')}


def query(kind):
    file='sockshop-model-heldout-20261020.json' if kind=='cart' else 'response-binding-heldout-20261019.json'
    ident='sockshop-carts-getItems-each-itemId' if kind=='cart' else 'trainticket-train-retrieve-data-economyClass'
    return next(q for q in load(HERE/file)['queries'] if q['id']==ident)


def templates(kind):
    if kind=='cart':
        return [{'case':f'template-{i}','customer_id':f'{i+100:024x}',
                 'items':[{'itemId':f'same-item-{j}','quantity':i%3+1,'unitPrice':2.5} for j in range(1+i%2)]} for i in range(6)]
    rng=random.Random(201020)
    return [{'case':f'template-{i}','document':old.mongo_fixture('train',i,rng)[0]} for i in (0,1,2,4,5)]


def prepare(out,base,kind,raw=False):
    q=query(kind);p=old.plan_response(load(base/q['role']/'model.json'),q['entry'],q['target'],q['path'],read_forward_contracts=True)
    if raw:p['source_evidence']=True
    old.query_build(out,base,q,p)


def spec_for(kind,mode,dest,build):
    if kind=='cart':
        spec=cost.spec_for('tracefusion' if mode!='original' else 'original',dest,build,1,'768m')
        spec['services']={k:v for k,v in spec['services'].items() if k in ('carts','carts-db')}
        spec['services']['carts']['ports']=['127.0.0.1:19691:80'];spec['networks']={'default':{'ipam':{'config':[{'subnet':'10.254.245.0/24'}]}}}
        spec['services']['carts-db'].update(mem_limit='384m')
        if mode!='original':spec['services']['carts']['environment']['JAVA_OPTS']=JVM+' -javaagent:/tf2/observer.jar -Dservice.plan=/tf2/plan.json -Dservice.events=/tf2/capture/events.jsonl -Dservice.mode='+mode
        return spec,'carts',['carts'],'http://127.0.0.1:19691'
    cfg=load(ROOT/'artifacts/trainticket-cost-preparation-20261016/inputs/inputs.json')['train']
    mongo=next(k for k,v in load(ROOT/'artifacts/desktop-inputs/images-lock.json').items() if 'trainticket/ts-station-mongo' in v['services'])
    spec={'services':{'ts-train-service':{'image':cfg['image'],'ports':['127.0.0.1:19692:14567'],'restart':'no','mem_limit':'768m','cpus':1,'dns_search':['.'],'depends_on':['ts-train-mongo']},'ts-train-mongo':{'image':mongo,'restart':'no','mem_limit':'384m','cpus':1,'volumes':['train-data:/data/db']}},'volumes':{'train-data':{}}}
    svc=spec['services']['ts-train-service']
    if mode!='original':observed(spec,'ts-train-service','train',dest,build)
    else:svc.update(volumes=[str(build/'train/original.jar')+':/tf2/app.jar:ro'],entrypoint=['sh','-c','exec java $$JAVA_OPTS -jar /tf2/app.jar'])
    svc.setdefault('environment',{})['JAVA_OPTS']=JVM+(' -javaagent:/tf2/observer.jar -Dservice.plan=/tf2/plan.json -Dservice.events=/tf2/capture/events.jsonl -Dservice.mode='+mode if mode!='original' else '')
    return spec,'train',['ts-train-service'],'http://127.0.0.1:19692'


def position(dest,role):
    f=dest/role/'events.jsonl'
    return {'events':sum(1 for _ in f.open('rb')),'bytes':f.stat().st_size} if f.exists() else {'events':0,'bytes':0}


def setup(kind,dep,dest,endpoint,ts):
    client=old.Client(dest);deadline=time.monotonic()+240
    while time.monotonic()<deadline:
        try:client.request('GET',endpoint+('/health' if kind=='cart' else '/api/v1/trainservice/trains/welcome'),label='readiness');break
        except Exception:time.sleep(2)
    else:raise ValueError('Readiness failed')
    if kind=='cart':
        for t in ts:
            for item in t['items']:client.request('POST',endpoint+'/carts/'+t['customer_id']+'/items',item,label='legal-fixture-setup')
            actual=client.request('GET',endpoint+'/carts/'+t['customer_id']+'/items',label='fixture-audit')
            if [{k:i[k] for k in ('itemId','quantity','unitPrice')} for i in actual]!=t['items']:raise ValueError('Independent Cart input differs')
        facts=dep.compose('exec','-T','carts-db','mongo','data','--quiet','--eval','JSON.stringify(db.getCollectionNames().map(function(n){return {name:n,rows:db.getCollection(n).find({}).toArray()};}))').stdout
        (dest/'independent-database.txt').write_text(facts)
    else:old.database(dep,'train',[t['document'] for t in ts],dest)


def request(kind,dest,endpoint,t,index,label,start,rate,trace):
    name=f'{label}-{index:05d}';cd=dest/name;cd.mkdir();client=old.Client(cd);message=old.context(client,trace)
    if kind=='cart':path='/carts/'+t['customer_id']+'/items';docs=[]
    else:path='/api/v1/trainservice/trains/'+t['document']['_id'];docs=[t['document']]
    req=urllib.request.Request(endpoint+path,method='GET',headers={'Content-Type':'application/json',**client.headers})
    began=time.monotonic_ns();response=None;status=None;error=None
    try:
        try:
            with client.opener.open(req,timeout=20) as r:status,raw=r.status,r.read()
        except urllib.error.HTTPError as r:status,raw=r.code,r.read()
    except Exception as e:error=str(e)
    ended=time.monotonic_ns()
    # HTTP timer ends before JSON decode, oracle checks, or client evidence I/O.
    if error is None:
        try:response=json.loads(raw)
        except (ValueError,UnicodeDecodeError) as e:error=str(e)
    passed=status==200 and error is None
    if passed and kind=='cart':passed=[{k:i[k] for k in ('itemId','quantity','unitPrice')} for i in response]==t['items']
    if passed and kind!='cart':passed=all(response.get('data',{}).get('id' if k=='_id' else k)==v for k,v in docs[0].items() if k!='_class')
    c={'case':name,'template_case':t['case'],'message':message,'http_status':status,'response':response,'request_path':path,'database_documents':docs,'fixture':{'expected_items':{i['itemId']:i for i in t.get('items',[])},'customer_id':t.get('customer_id')},'error':error,'business_passed':passed,'scheduled_ns':start+round(index/rate*1e9),'online_start_ns':began,'online_end_ns':ended}
    save(cd/'contract-result.json',c);return c


def phase(kind,dest,endpoint,ts,label,seconds,rate,concurrency):
    start=time.monotonic_ns();trace=secrets.token_hex(16);pending=[]
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        for i in range(round(seconds*rate)):
            delay=(start+round(i/rate*1e9)-time.monotonic_ns())/1e9
            if delay>0:time.sleep(delay)
            pending.append(pool.submit(request,kind,dest,endpoint,ts[i%len(ts)],i,label,start,rate,trace))
        remaining=(start+round(seconds*1e9)-time.monotonic_ns())/1e9
        if remaining>0:time.sleep(remaining)
        records=[f.result() for f in pending]
    return {'start_ns':start,'scheduled_end_ns':start+round(seconds*1e9),'drain_end_ns':time.monotonic_ns(),'requests':records}


def offline(trial,build,kind):
    dest=trial/'capture';q=query(kind);role=q['role'];cases=load(dest/'run.json')['cases'];phases={};started=time.monotonic_ns()
    t=time.perf_counter();rows=[json.loads(l) for l in (dest/role/'events.jsonl').read_text().splitlines()];phases['decode_json_seconds']=time.perf_counter()-t
    t=time.perf_counter();g=Reconstruction(build,dest,[role],decoded_rows={role:rows});phases['validate_graph_reconstruct_seconds']=time.perf_counter()-t
    t=time.perf_counter();answers=[]
    for c in cases:
        for path,value in old.leaves(c['response'],q['path']):
            answer=g.query(c['message'],path,role,boundary=old.BOUNDARY)
            if answer['target']['observed'].get('value')!=value:raise ValueError('Collected target differs from actual client JSON')
            answers.append({'case':c['case'],'path':path,'answer':answer})
    phases['target_origin_restore_seconds']=time.perf_counter()-t
    t=time.perf_counter();save(trial/'answers.json',answers);phases['answer_export_seconds']=time.perf_counter()-t;ready=time.monotonic_ns()
    t=time.perf_counter();bycase={c['case']:c for c in cases};scored=[]
    for a in answers:
        c=bycase[a['case']];expected=set(model.oracle(q,c,a['path'],{role:rows}));answer=a['answer'];actual={old.predicted_coord(s) for s in answer['sources']}
        scored.append({'case':c['case'],'phase':c['case'].split('-')[0],'path':a['path'],'known':answer['known'],'exact':answer['known'] and expected==actual,'tp':len(expected&actual),'fp':len(actual-expected),'fn':len(expected-actual),'expected':sorted(expected,key=str),'actual':sorted(actual,key=str)})
    phases['oracle_score_seconds']=time.perf_counter()-t
    def total(rs):return {'queries':len(rs),'exact':sum(r['exact'] for r in rs),'unknown':sum(not r['known'] for r in rs),**{k:sum(r[k] for r in rs) for k in ('tp','fp','fn')}}
    summary=total(scored)
    t=time.perf_counter();save(trial/'field-results.json',{'summary':summary,'queries':scored});save(trial/'field-graph.json',g.export());phases['evidence_export_seconds']=time.perf_counter()-t
    usage=resource.getrusage(resource.RUSAGE_SELF);result={'summary':summary,'populations':{p:total([r for r in scored if r['phase']==p]) for p in ('warmup','steady')},'phases':phases,'core_seconds':phases['validate_graph_reconstruct_seconds']+phases['target_origin_restore_seconds'],'restore_score_export_seconds':(time.monotonic_ns()-started)/1e9,'process_cpu_seconds':usage.ru_utime+usage.ru_stime,'peak_rss_bytes':usage.ru_maxrss*1024,'answers_ready_ns':ready,'scored_evidence_ready_ns':time.monotonic_ns(),'raw_http_source_facts':sum(r['kind']=='http-source-fact' for r in rows),'events':len(rows)}
    save(trial/'offline.json',result)
    if not summary['queries'] or summary['exact']!=summary['queries'] or summary['fp'] or summary['fn'] or summary['unknown']:raise ValueError('Independent instance provenance check failed: '+str(summary))


def trial_run(trial,build,kind,mode,ts,warmup,seconds,rate,concurrency,interval):
    old.verify_build(build);trial.mkdir();dest=trial/'capture';dest.mkdir();spec,role,business,endpoint=spec_for(kind,mode,dest,build);save(dest/'compose.json',spec)
    dep=old.Deployment(argparse.Namespace(project='tf2-bound-cost-'+secrets.token_hex(5)),dest,dest/'compose.json');run={'status':'failed','project':dep.args.project,'roles':[role],'cases':[]};save(dest/'run.json',run)
    try:
        images={}
        for cfg in spec['services'].values():
            info=json.loads(dep.command(['docker','image','inspect',cfg['image']]).stdout)[0]
            if cfg['image'] not in info['RepoDigests']:raise ValueError('Unpinned image')
            images[cfg['image']]={'id':info['Id'],'digests':info['RepoDigests']}
        save(dest/'images.json',images);dep.compose('up','-d','--pull','never',timeout=180)
        inspected=json.loads(dep.command(['docker','inspect',*dep.compose('ps','-q').stdout.split()]).stdout);save(dest/'containers.json',inspected)
        containers={i['Config']['Labels']['com.docker.compose.service']:i['Id'] for i in inspected}
        for i in inspected:
            name=i['Config']['Labels']['com.docker.compose.service'];memory=768 if name in business else 384
            if i['HostConfig']['Memory']!=memory*2**20 or i['HostConfig']['NanoCpus']!=10**9:raise ValueError('Resource limits differ')
        setup(kind,dep,dest,endpoint,ts);save(dest/'jvm-versions.json',{r:dep.compose('exec','-T',r,'java','-version').stdout for r in business})
        warm=phase(kind,dest,endpoint,ts,'warmup',warmup,rate,concurrency);save(trial/'warmup.json',warm)
        if not all(c['business_passed'] for c in warm['requests']):raise ValueError('Warmup business failure')
        before=position(dest,role)
        with cost.Sampler(containers,interval,trial/'resources.jsonl',observed_roles=business) as sampler:steady=phase(kind,dest,endpoint,ts,'steady',seconds,rate,concurrency)
        after=position(dest,role);save(trial/'steady.json',steady);save(trial/'capture-window.json',{'before':before,'after':after,'start_ns':steady['start_ns'],'scheduled_end_ns':steady['scheduled_end_ns'],'drain_end_ns':steady['drain_end_ns']})
        run['cases']=warm['requests']+steady['requests']
        if not all(c['business_passed'] for c in run['cases']):raise ValueError('Steady business failure')
        run['status']='business-completed';save(dest/'run.json',run);resources=sampler.summary(steady['start_ns'],steady['scheduled_end_ns'])
        stop_started=time.monotonic_ns();dep.compose('stop','-t','20',*business,timeout=60);closed=time.monotonic_ns();off=None
        if mode!='original':
            cmd=[sys.executable,str(Path(__file__).resolve()),'offline','--out',str(trial),'--build',str(build),'--kind',kind]
            began=time.monotonic_ns();p=subprocess.run(cmd,capture_output=True,text=True,timeout=240);(trial/'offline.log').write_text(p.stdout+p.stderr);save(trial/'offline-command.json',{'command':cmd,'returncode':p.returncode})
            if p.returncode:raise ValueError('Offline correctness failed')
            off=load(trial/'offline.json');off['subprocess_wall_seconds']=(time.monotonic_ns()-began)/1e9
        records=steady['requests'];readiness=[]
        if off:
            readiness=[{'case':r['case'],'response_complete_ns':r['online_end_ns'],'capture_closed_upper_bound_ns':closed,'answers_ready_ns':off['answers_ready_ns'],'completion_to_raw_capture_upper_bound_seconds':(closed-r['online_end_ns'])/1e9,'completion_to_answer_seconds':(off['answers_ready_ns']-r['online_end_ns'])/1e9} for r in records]
        save(trial/'answer-readiness.json',readiness);console=dep.compose('logs','--no-color',timeout=90).stdout;(trial/'container-console.log').write_text(console)
        metrics={'kind':kind,'mode':mode,'status':'passed','steady_requests':len(records),'error_rate':0,'offered_rate_rps':rate,'throughput_rps':sum(r['online_end_ns']<=steady['scheduled_end_ns'] for r in records)/seconds,'online_latency_ms':cost.percentiles([(r['online_end_ns']-r['online_start_ns'])/1e6 for r in records]),'scheduled_to_response_ms':cost.percentiles([(r['online_end_ns']-r['scheduled_ns'])/1e6 for r in records]),'max_dispatch_lag_ms':max((r['online_start_ns']-r['scheduled_ns'])/1e6 for r in records),'resources':resources,'steady_capture':{role:{k:after[k]-before[k] for k in before}},'total_capture':{role:position(dest,role)},'container_console_bytes':len(console.encode()),'offline':off,'completion_to_batch_answers_seconds':cost.percentiles([r['completion_to_answer_seconds'] for r in readiness]) if readiness else None,'completion_to_raw_capture_upper_bound_seconds':cost.percentiles([r['completion_to_raw_capture_upper_bound_seconds'] for r in readiness]) if readiness else None,'provenance_status':'N/A: original has no provenance' if off is None else 'passed','capture_shutdown_started_ns':stop_started,'capture_closed_upper_bound_ns':closed}
        old.verify_build(build);save(trial/'metrics.json',metrics);print(trial.name,'passed',flush=True);return metrics
    except BaseException as e:save(trial/'failure.json',{'error':str(e)});raise
    finally:
        dep.diagnostics();p=dep.compose('down','--volumes','--remove-orphans',timeout=120,check=False);save(trial/'cleanup.json',{'project':dep.args.project,'returncode':p.returncode})
        if p.returncode:raise ValueError('Cleanup failed')


def freeze(args):
    args.out.mkdir();ts=templates(args.kind);save(args.out/'templates.json',ts);order=[];rng=random.Random(args.seed)
    for i in range(args.rounds):
        modes=['original','full','selective'];rng.shuffle(modes);order.extend((f'round-{i+1:02d}-{j+1:02d}-{m}',m) for j,m in enumerate(modes))
    cfg={k:str(v) if isinstance(v,Path) else v for k,v in vars(args).items()};cfg.update(order=order,query=query(args.kind),jvm=JVM,latency_scope='HTTP open through complete response-body read; JSON decoding, business checks and client evidence writes excluded',build_sha256=sha(args.build/'build.json'),templates_sha256=sha(args.out/'templates.json'),driver_sha256=sha(Path(__file__)),source_sha256=driver_sources(),image_lock_sha256=sha(ROOT/'artifacts/desktop-inputs/images-lock.json'))
    save(args.out/'config.json',cfg);cost.environment(args.out);save(args.out/'run-status.json',{'status':'frozen'})


def run(args):
    c=load(args.out/'config.json');save(args.out/'run-status.json',{'status':'running'})
    try:
        for name,mode in c['order']:
            if driver_sources()!=c['source_sha256'] or sha(args.build/'build.json')!=c['build_sha256'] or sha(args.out/'templates.json')!=c['templates_sha256'] or sha(ROOT/'artifacts/desktop-inputs/images-lock.json')!=c['image_lock_sha256']:raise ValueError('Frozen input/driver changed')
            trial_run(args.out/name,args.build,c['kind'],mode,load(args.out/'templates.json'),c['warmup'],c['seconds'],c['rate'],c['concurrency'],c['sample_interval'])
            save(args.out/'progress.json',{'completed':sum((args.out/n/'metrics.json').exists() for n,_ in c['order']),'total':len(c['order']),'last':name})
            if sum((args.out/n/'metrics.json').exists() for n,_ in c['order'])%3==0:
                log=args.out/'logs';log.mkdir(exist_ok=True);save(log/(name[:8]+'.json'),{'round':name[:8],'all_three_passed':True,'results':{m:load(args.out/n/'metrics.json') for n,m in c['order'] if n[:8]==name[:8]}})
        save(args.out/'run-status.json',{'status':'passed'})
    except BaseException as e:save(args.out/'run-status.json',{'status':'failed','error':str(e)});raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('stage',choices=('prepare','freeze','run','offline'));p.add_argument('--out',type=Path,required=True);p.add_argument('--build',type=Path,required=True);p.add_argument('--kind',choices=('cart','train'),required=True);p.add_argument('--raw',action='store_true');p.add_argument('--rounds',type=int,default=5);p.add_argument('--warmup',type=float,default=30);p.add_argument('--seconds',type=float,default=60);p.add_argument('--rate',type=float,default=2);p.add_argument('--concurrency',type=int,default=2);p.add_argument('--sample-interval',type=float,default=2);p.add_argument('--seed',type=int,default=201020);a=p.parse_args();a.out=a.out.resolve();a.build=a.build.resolve()
    if a.stage=='prepare':prepare(a.out,a.build,a.kind,a.raw)
    elif a.stage=='freeze':
        if min(a.rounds,a.warmup,a.seconds,a.rate,a.concurrency,a.sample_interval)<=0 or a.seconds<3*a.sample_interval:raise ValueError('Invalid measurement protocol')
        freeze(a)
    elif a.stage=='offline':offline(a.out,a.build,a.kind)
    else:run(a)
