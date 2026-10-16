#!/usr/bin/env python3
"""Independent low-rate Train Ticket deployments; all outputs and failures kept."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
import datetime as dt
import json
from pathlib import Path
import random
import resource
import secrets
import shutil
import statistics
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

from run_planned_service import ROOT,HERE,load,save,sha
from run_train_multisource import ROLES,check as check_calibration
from run_distributed_paths import observed
from run_sockshop_cost import Sampler,percentiles,environment
from sockshop import Client,Deployment

JVM='-Xms32m -Xmx256m -Djava.security.egd=file:/dev/urandom -Dspring.zipkin.enabled=false'
CORE_FILES=['run_train_cost.py','run_sockshop_cost.py','run_train_multisource.py',
            'infer_distributed_fields.py','infer_collection_service.py','audit_train_multisource.py','audit_cost_population.py']


def sources():
    return {str(HERE/n):sha(HERE/n) for n in CORE_FILES}


def spec_for(mode,dest,build,inputs):
    config=load(inputs);services={};volumes={}
    mongo=next(k for k,v in load(ROOT/'artifacts/desktop-inputs/images-lock.json').items() if 'trainticket/ts-station-mongo' in v['services'])
    for i,(role,port) in enumerate(ROLES.items()):
        name='ts-'+role+'-service'
        cfg={'image':config[role]['image'],'platform':'linux/amd64','restart':'no','ports':['127.0.0.1:'+str(18700+i)+':'+str(port)],'dns_search':['.'],'mem_limit':'768m','cpus':1}
        services[name]=cfg
        if role!='basic':
            db='ts-'+role+'-mongo';volume=role+'-data';volumes[volume]={}
            services[db]={'image':mongo,'platform':'linux/amd64','restart':'no','volumes':[volume+':/data/db'],'dns_search':['.'],'mem_limit':'384m','cpus':1}
            cfg['depends_on']=[db]
    spec={'services':services,'volumes':volumes}
    for role in ROLES:
        name='ts-'+role+'-service';cfg=services[name]
        if mode!='original':
            observed(spec,name,role,dest,build)
            cfg['environment']['JAVA_OPTS']=JVM+' -javaagent:/tf2/observer.jar -Dservice.plan=/tf2/plan.json -Dservice.events=/tf2/capture/events.jsonl -Dservice.mode='+mode
        else:
            cfg['volumes']=[str(build/role/'original.jar')+':/tf2/app.jar:ro']
            cfg['entrypoint']=['sh','-c','exec java $$JAVA_OPTS -jar /tf2/app.jar']
            cfg['environment']={'JAVA_OPTS':JVM}
    return spec


def log_position(dest):
    return {r:{'events':sum(1 for _ in (dest/r/'events.jsonl').open('rb')),'bytes':(dest/r/'events.jsonl').stat().st_size} if (dest/r/'events.jsonl').exists() else {'events':0,'bytes':0} for r in ROLES}


def business_matches(template,status,response):
    return status==200 and isinstance(response,dict) and response.get('status')==template['expected_status'] and response.get('data',{}).get('prices')==template['expected_prices']


def request_one(dest,template,index,start,rate,trace,label):
    name=f'{label}-{index:05d}';out=dest/name;client=Client(out);span=secrets.token_hex(8);message=trace+'/'+span
    scheduled=start+round(index/rate*1e9)
    request=urllib.request.Request('http://127.0.0.1:18704/api/v1/basicservice/basic/travel',data=json.dumps(template['body']).encode(),method='POST',headers={'Content-Type':'application/json','traceparent':'00-'+trace+'-'+span+'-01','tracestate':'research=cost'})
    status=None;response=None;error=None;began=time.monotonic_ns()
    try:
        try:
            with client.opener.open(request,timeout=20) as r:status,raw=r.status,r.read()
        except urllib.error.HTTPError as r:status,raw=r.code,r.read()
    except Exception as e:error=str(e)
    ended=time.monotonic_ns()
    if error is None:
        try:response=json.loads(raw)
        except (ValueError,UnicodeDecodeError) as e:error=str(e)
    passed=error is None and business_matches(template,status,response)
    result={**template,'template_case':template['case'],'case':name,'message':message,'target_available':True,'response':response,'http_status':status,'error':error,'business_passed':passed,'scheduled_ns':scheduled,'online_start_ns':began,'online_end_ns':ended}
    save(out/'contract-result.json',result)
    return result


def phase(dest,templates,label,seconds,rate,concurrency):
    n=round(seconds*rate);trace=secrets.token_hex(16)
    for i in range(n):(dest/f'{label}-{i:05d}').mkdir()
    start=time.monotonic_ns();results=[]
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        pending=[]
        for i in range(n):
            delay=(start+round(i/rate*1e9)-time.monotonic_ns())/1e9
            if delay>0:time.sleep(delay)
            pending.append(pool.submit(request_one,dest,templates[i%len(templates)],i,start,rate,trace,label))
        remaining=(start+round(seconds*1e9)-time.monotonic_ns())/1e9
        if remaining>0:time.sleep(remaining)
        for f in pending:results.append(f.result())
    return {'start_ns':start,'scheduled_end_ns':start+round(seconds*1e9),'drain_end_ns':time.monotonic_ns(),'requests':results}


def score_answers(records,answers,rows):
    # Oracle is invoked only after the independent inference/answer export.
    predicted={(r['case'],r['key']):r['answer'] for r in answers};queries=[]
    rpcs={}
    for r in rows['basic']:
        if r['kind']=='http-rpc-enter':rpcs.setdefault(r.get('parent_message'),[]).append(r)
    for c in records:
        calls=rpcs.get(c['message'],[])
        requests={r:[x for x in calls if 'ts-'+r+'-service:' in x['uri']] for r in ('route','price')}
        if any(len(v)!=1 for v in requests.values()):raise ValueError('Source RPC instances ambiguous')
        for key,rate in [('economyClass','basicPriceRate'),('confortClass','firstClassPriceRate')]:
            answer=predicted[(c['case'],key)];actual={(s['service'],s['message'],s['path']) for s in answer['sources']};expected=set()
            if not c['fallback']:
                expected.add(('price',requests['price'][0]['message'],'/data/'+rate))
                expected.update(('route',requests['route'][0]['message'],'/data/distances/'+str(i)) for i in c['distance_indices'])
            queries.append({'case':c['case'],'phase':c['case'].split('-')[0],'key':key,'known':answer['known'],'exact':answer['known'] and actual==expected,'tp':len(actual&expected),'fp':len(actual-expected),'fn':len(expected-actual),'expected':sorted(expected),'actual':sorted(actual)})
    def totals(qs):return {'queries':len(qs),'exact':sum(q['exact'] for q in qs),'unknown':sum(not q['known'] for q in qs),**{k:sum(q[k] for q in qs) for k in ('tp','fp','fn')}}
    return {'queries':queries,'summary':totals(queries),'populations':{label:totals([q for q in queries if q['phase']==label]) for label in ('warmup','steady')}}


def offline(trial,build):
    from infer_distributed_fields import Reconstruction
    dest=trial/'trainticket';records=load(dest/'run.json')['cases'];phases={}
    started=time.monotonic_ns();t=time.perf_counter();rows={r:[json.loads(s) for s in (dest/r/'events.jsonl').read_text().splitlines()] for r in ROLES};phases['decode_json_seconds']=time.perf_counter()-t
    t=time.perf_counter();g=Reconstruction(build,dest,list(ROLES),decoded_rows=rows);phases['validate_graph_reconstruct_seconds']=time.perf_counter()-t
    t=time.perf_counter();answers=[]
    for c in records:
        for key in ('economyClass','confortClass'):
            answer=g.query(c['message'],'/data/prices/'+key,'basic',boundary=[{'service':r,'kind':'http-json','phase':'write','direction':'response'} for r in ('route','price')])
            answers.append({'case':c['case'],'key':key,'answer':answer})
    phases['target_origin_restore_seconds']=time.perf_counter()-t
    t=time.perf_counter();save(dest/'answers.json',answers);phases['answer_export_seconds']=time.perf_counter()-t;ready=time.monotonic_ns()
    t=time.perf_counter();score=score_answers(records,answers,rows);phases['oracle_score_seconds']=time.perf_counter()-t
    t=time.perf_counter();save(dest/'field-results.json',score);save(dest/'field-graph.json',g.export());phases['evidence_export_seconds']=time.perf_counter()-t
    verified=time.monotonic_ns();usage=resource.getrusage(resource.RUSAGE_SELF)
    result={'summary':score['summary'],'populations':score['populations'],'phases':phases,'core_seconds':phases['validate_graph_reconstruct_seconds']+phases['target_origin_restore_seconds'],'restore_score_export_seconds':(verified-started)/1e9,'process_cpu_seconds':usage.ru_utime+usage.ru_stime,'peak_rss_bytes':usage.ru_maxrss*1024,'answers_ready_ns':ready,'scored_evidence_ready_ns':verified,'background_unknown':dict(Counter(n.get('field','unknown') for n in g.nodes.values() if n.get('unknown')))}
    save(trial/'offline.json',result)
    s=score['summary']
    if s['exact']!=s['queries'] or s['unknown'] or s['fp'] or s['fn']:raise ValueError('Provenance correctness failed; predictions and unknowns retained')


def validate_gate(calibration,build,inputs):
    check_calibration(calibration,build,inputs)
    audit=load(calibration/'independent-audit.json')
    if not audit['all_passed']:raise ValueError('Common correctness calibration not independently admitted')
    if audit['auditor_sha256']!=sha(HERE/'audit_train_multisource.py'):raise ValueError('Calibration auditor changed')
    for mode in ('full','selective'):
        s=load(calibration/mode/'evaluation.json')
        if s['exact']!=38 or s['queries']!=38 or s['fp'] or s['fn'] or s['unknown']:raise ValueError('Full calibration required')
    return audit


def freeze(args,out):
    validate_gate(args.calibration,args.build,args.inputs)
    out.mkdir(parents=True,exist_ok=False);(out/'logs').mkdir();templates=[c for c in load(args.calibration/'cases.json') if c['expected_http_status']==200]
    save(out/'templates.json',templates);shutil.copyfile(args.calibration/'database-fixtures.json',out/'database-fixtures.json')
    rng=random.Random(args.seed);order=[]
    for i in range(args.rounds):
        modes=['original','full','selective'];rng.shuffle(modes)
        order.extend((f'round-{i+1:02d}-{j+1:02d}-{mode}',mode) for j,mode in enumerate(modes))
    config={k:str(v) if isinstance(v,Path) else v for k,v in vars(args).items()}
    config.update(order=order,jvm=JVM,template_count=len(templates),source_sha256=sources(),build_sha256=sha(args.build/'build.json'),inputs_sha256=sha(args.inputs),templates_sha256=sha(out/'templates.json'),fixtures_sha256=sha(out/'database-fixtures.json'),calibration_audit_sha256=sha(args.calibration/'independent-audit.json'),calibration_evidence_sha256={str(p):sha(p) for p in sorted(args.calibration.rglob('*')) if p.is_file()},image_lock_sha256=sha(ROOT/'artifacts/desktop-inputs/images-lock.json'),modes=['original','full','selective'],measurement_unit='POST Basic /basic/travel, two prices target entries',excluded_template='missing-train: no target; kept in calibration only')
    save(out/'config.json',config);environment(out)
    snapshot=out/'sources'
    for filename in sources():
        p=Path(filename);d=snapshot/p.relative_to(ROOT);d.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,d)
    save(out/'run-status.json',{'status':'frozen'})


def check_run(out,args):
    c=load(out/'config.json');validate_gate(args.calibration,args.build,args.inputs)
    for filename,h in c['source_sha256'].items():
        if sha(Path(filename))!=h:raise ValueError('Frozen cost source changed: '+filename)
    for filename,h in c['calibration_evidence_sha256'].items():
        if sha(Path(filename))!=h:raise ValueError('Sealed calibration changed: '+filename)
    for p,k in [(args.build/'build.json','build_sha256'),(args.inputs,'inputs_sha256'),(out/'templates.json','templates_sha256'),(out/'database-fixtures.json','fixtures_sha256'),(args.calibration/'independent-audit.json','calibration_audit_sha256'),(ROOT/'artifacts/desktop-inputs/images-lock.json','image_lock_sha256')]:
        if sha(p)!=c[k]:raise ValueError('Frozen experiment input changed: '+str(p))
    return c


def trial_run(args,trial,mode,run_root):
    check_run(run_root,args);trial.mkdir();dest=trial/'trainticket';dest.mkdir();spec=spec_for(mode,dest,args.build,args.inputs);save(dest/'compose.json',spec)
    dep=Deployment(argparse.Namespace(project='tf2-train-cost-'+secrets.token_hex(5)),dest,dest/'compose.json');result={'status':'failed','project':dep.args.project,'mode':mode,'cases':[]};save(dest/'run.json',result)
    try:
        images={}
        for cfg in spec['services'].values():
            if cfg['image'] in images:continue
            info=json.loads(dep.command(['docker','image','inspect',cfg['image']]).stdout)[0]
            if cfg['image'] not in info['RepoDigests']:raise ValueError('Image not pinned')
            images[cfg['image']]={'id':info['Id'],'digests':info['RepoDigests']}
        save(dest/'images.json',images);dep.compose('up','-d','--pull','never',timeout=180)
        inspected=json.loads(dep.command(['docker','inspect',*dep.compose('ps','-q').stdout.split()]).stdout);save(dest/'containers.json',inspected)
        containers={i['Config']['Labels']['com.docker.compose.service']:i['Id'] for i in inspected}
        for i in inspected:
            role=i['Config']['Labels']['com.docker.compose.service'];want=384 if role.endswith('-mongo') else 768
            if i['HostConfig']['Memory']!=want*2**20 or i['HostConfig']['NanoCpus']!=10**9:raise ValueError('Actual resource limits differ')
        client=Client(dest);deadline=time.monotonic()+240
        while time.monotonic()<deadline:
            try:
                for i,r in enumerate(ROLES):client.request('GET','http://127.0.0.1:'+str(18700+i)+'/api/v1/'+r+'service/'+{'train':'trains/','price':'prices/'}.get(r,'')+'welcome',label='readiness')
                break
            except Exception:time.sleep(2)
        else:raise ValueError('Service readiness timeout')
        save(dest/'jvm-versions.json',{r:dep.compose('exec','-T','ts-'+r+'-service','java','-version').stdout for r in ROLES})
        db=load(run_root/'database-fixtures.json');facts={}
        for r,collections in db.items():
            for collection,docs in collections.items():
                script='db.'+collection+'.deleteMany({});db.'+collection+'.insertMany(('+json.dumps(docs)+').map(function(d){if(d._id && d._id.uuid_legacy_base64)d._id=BinData(3,d._id.uuid_legacy_base64);return d;}));'
                dep.compose('exec','-T','ts-'+r+'-mongo','mongo','ts','--quiet','--eval',script)
                facts[r]=dep.compose('exec','-T','ts-'+r+'-mongo','mongo','ts','--quiet','--eval','JSON.stringify(db.'+collection+'.find({}).toArray())').stdout
        save(dest/'independent-database.json',facts);templates=load(run_root/'templates.json')
        warm=phase(dest,templates,'warmup',args.warmup,args.rate,args.concurrency);save(trial/'warmup.json',warm)
        if not all(r['business_passed'] for r in warm['requests']):raise ValueError('Warmup business correctness failed')
        before=log_position(dest)
        business_roles=['ts-'+r+'-service' for r in ROLES]
        with Sampler(containers,args.sample_interval,trial/'resources.jsonl',observed_roles=business_roles) as sampler:
            steady=phase(dest,templates,'steady',args.seconds,args.rate,args.concurrency)
        after=log_position(dest);save(trial/'steady.json',steady);save(trial/'capture-window.json',{'before':before,'after':after,'start_ns':steady['start_ns'],'scheduled_end_ns':steady['scheduled_end_ns'],'drain_end_ns':steady['drain_end_ns']})
        result['cases']=warm['requests']+steady['requests'];result['status']='business-passed' if all(r['business_passed'] for r in result['cases']) else 'business-failed';save(dest/'run.json',result)
        if result['status']!='business-passed':raise ValueError('Steady business correctness failed')
        resources=sampler.summary(steady['start_ns'],steady['scheduled_end_ns']);shutdown=time.monotonic_ns()
        dep.compose('stop','-t','20',*business_roles,timeout=70);closed=time.monotonic_ns()
        off=None
        if mode!='original':
            command=[sys.executable,str(Path(__file__).resolve()),'offline','--out',str(trial),'--build',str(args.build)]
            started=time.monotonic_ns();p=subprocess.run(command,capture_output=True,text=True,timeout=args.offline_timeout);(trial/'offline.log').write_text(p.stdout+p.stderr);save(trial/'offline-command.json',{'command':command,'returncode':p.returncode})
            if p.returncode:raise ValueError('Offline correctness failed')
            off=load(trial/'offline.json');off['subprocess_wall_seconds']=(time.monotonic_ns()-started)/1e9
        records=steady['requests'];window=[r for r in records if r['online_end_ns']<=steady['scheduled_end_ns']];latency=[(r['online_end_ns']-r['online_start_ns'])/1e6 for r in records]
        timeline={'steady_start_ns':steady['start_ns'],'steady_end_ns':steady['scheduled_end_ns'],'drain_end_ns':steady['drain_end_ns'],'shutdown_started_ns':shutdown,'capture_closed_upper_bound_ns':closed,'target_creation_ns':None,'raw_evidence_first_available_ns':None,'answers_ready_ns':None if off is None else off['answers_ready_ns'],'scored_evidence_ready_ns':None if off is None else off['scored_evidence_ready_ns']};save(trial/'result-timeline.json',timeline)
        readiness=[]
        if off:
            for r in records:readiness.append({'case':r['case'],'response_complete_ns':r['online_end_ns'],'capture_closed_upper_bound_ns':closed,'answers_ready_ns':off['answers_ready_ns'],'completion_to_raw_capture_upper_bound_seconds':(closed-r['online_end_ns'])/1e9,'completion_to_answer_seconds':(off['answers_ready_ns']-r['online_end_ns'])/1e9,'completion_to_scored_evidence_seconds':(off['scored_evidence_ready_ns']-r['online_end_ns'])/1e9})
        save(trial/'answer-readiness.json',readiness)
        console=dep.compose('logs','--no-color',timeout=90).stdout;(trial/'container-console.log').write_text(console)
        metrics={'mode':mode,'status':'passed','steady_requests':len(records),'error_rate':0,'http_status_counts':dict(Counter(str(r['http_status']) for r in records)),'offered_rate_rps':args.rate,'throughput_rps':len(window)/args.seconds,'drained_throughput_rps':len(records)/((steady['drain_end_ns']-steady['start_ns'])/1e9),'online_latency_ms':percentiles(latency),'scheduled_to_response_ms':percentiles([(r['online_end_ns']-r['scheduled_ns'])/1e6 for r in records]),'max_dispatch_lag_ms':max((r['online_start_ns']-r['scheduled_ns'])/1e6 for r in records),'resources':resources,'steady_capture':{r:{k:after[r][k]-before[r][k] for k in ('events','bytes')} for r in ROLES},'total_capture':log_position(dest),'container_console_bytes':len(console.encode()),'offline':off,'completion_to_batch_answers_seconds':percentiles([r['completion_to_answer_seconds'] for r in readiness]) if readiness else None,'completion_to_raw_capture_upper_bound_seconds':percentiles([r['completion_to_raw_capture_upper_bound_seconds'] for r in readiness]) if readiness else None,'provenance_status':'N/A: original has no provenance' if off is None else 'passed'}
        check_run(run_root,args);save(trial/'metrics.json',metrics);print(trial.name,'passed',flush=True);return metrics
    except BaseException as e:save(trial/'failure.json',{'error':str(e),'mode':mode});raise
    finally:
        dep.diagnostics();p=dep.compose('down','--volumes','--remove-orphans',timeout=120,check=False);save(trial/'cleanup.json',{'returncode':p.returncode,'project':dep.args.project})
        if p.returncode:raise ValueError('Cleanup failed')


def run(args):
    c=check_run(args.out,args);save(args.out/'run-status.json',{'status':'running'})
    try:
        for name,mode in c['order']:
            trial=args.out/name
            if trial.exists():raise ValueError('Output exists; never overwrite or silently resume a deployment')
            trial_run(args,trial,mode,args.out)
            finished=sum((args.out/n/'metrics.json').exists() for n,_ in c['order'])
            save(args.out/'progress.json',{'last_completed':name,'finished':finished,'total':len(c['order'])})
            if finished%3==0:
                block={m:load(args.out/n/'metrics.json') for n,m in c['order'] if n.startswith(name[:8])}
                save(args.out/'logs'/('round-'+name.split('-')[1]+'.json'),{'round':int(name.split('-')[1]),'all_three_passed':True,'results':block})
        save(args.out/'run-status.json',{'status':'passed'})
    except BaseException as e:save(args.out/'run-status.json',{'status':'failed','error':str(e)});raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('stage',choices=('freeze','run','offline'));p.add_argument('--out',type=Path,required=True);p.add_argument('--build',type=Path,required=True);p.add_argument('--inputs',type=Path);p.add_argument('--calibration',type=Path);p.add_argument('--rounds',type=int,default=5);p.add_argument('--warmup',type=float,default=30);p.add_argument('--seconds',type=float,default=60);p.add_argument('--rate',type=float,default=2);p.add_argument('--concurrency',type=int,default=2);p.add_argument('--sample-interval',type=float,default=2);p.add_argument('--offline-timeout',type=float,default=180);p.add_argument('--seed',type=int,default=161207);a=p.parse_args()
    for key in ('out','build','inputs','calibration'):
        if getattr(a,key) is not None:setattr(a,key,getattr(a,key).resolve())
    if a.stage=='offline':offline(a.out,a.build)
    elif a.stage=='freeze':
        if min(a.warmup,a.seconds,a.rate,a.concurrency,a.sample_interval,a.rounds)<=0 or a.seconds<3*a.sample_interval:raise ValueError('Positive protocol and >=3 sampling intervals required')
        freeze(a,a.out)
    else:
        c=load(a.out/'config.json')
        for k in ('inputs','calibration','rounds','warmup','seconds','rate','concurrency','sample_interval','offline_timeout','seed'):setattr(a,k,Path(c[k]) if k in ('inputs','calibration') else c[k])
        run(a)
