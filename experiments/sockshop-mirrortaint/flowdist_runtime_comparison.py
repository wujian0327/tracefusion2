#!/usr/bin/env python3
"""Same newOrder workload and common observer: plain, FlowDist, TraceFusion.

Pilot costs describe the deployed configurations, not a fully qualified ranking.
Keep runtime, whole-JVM RSS and allocation distinct from offline reconstruction.
"""
import argparse
import hashlib
import json
from pathlib import Path
import secrets
import shutil
import statistics
import time

from flowdist_full_order import CachedDeployment
from host import HERE, ROOT, prepare, submit
from sockshop import save, check_spec
import flowdist_preflight as tool


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def events(path):
    rows=[json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if [r['seq'] for r in rows]!=list(range(1,len(rows)+1)) or any(r['kind']=='problem' for r in rows):
        raise ValueError('Observer failure or sequence gap: '+str(path))
    return rows


def stats(values):
    data=sorted(values)
    if not data:raise ValueError('Missing measured samples')
    return {'mean':statistics.mean(data),'median':statistics.median(data),
        'p95':data[max(0,(len(data)*95+99)//100-1)],'min':min(data),'max':max(data)}


def configuration(args,mode,out):
    spec=json.loads((ROOT/'scenarios/sockshop/compose.json').read_text());check_spec(spec)
    spec['networks']={'default':{'ipam':{'config':[{'subnet':args.subnet}]}}}
    for role,port,internal in (('front-end',18580,8079),('carts',18581,80),('orders',18582,80)):
        spec['services'][role]['ports']=[f'127.0.0.1:{port}:{internal}']
    spec['services']['rabbitmq']['environment']={'RABBITMQ_SERVER_ADDITIONAL_ERL_ARGS':'+S 2:2 +A 8'}
    boundary=args.boundary.resolve();shutil.copyfile(boundary,out/'observer.jar')
    meta=json.loads((boundary.parent/'result.json').read_text())
    if digest(boundary)!=meta['agent_sha256']:raise ValueError('Observer build digest mismatch')
    manifest=json.loads((args.apps/'manifest.json').read_text())
    for role,original in (('orders',args.orders),('shipping',args.shipping)):
        if digest(original)!=manifest['apps'][role]['original_sha256']:raise ValueError('Original business JAR differs')
        jar=args.apps/(role+'-flowdist.jar') if mode=='flowdist' else original
        if mode=='flowdist' and digest(jar)!=manifest['apps'][role]['adapted_sha256']:raise ValueError('FlowDist build changed')
        shutil.copyfile(jar,out/(role+'.jar'))
        runtime=out/'runtime'/role;(runtime/'test1').mkdir(parents=True);runtime.chmod(0o777);(runtime/'test1').chmod(0o777)
        cost=out/'cost-events'/role;cost.mkdir(parents=True);cost.chmod(0o777)
        cfg=spec['services'][role]
        cfg.setdefault('volumes',[]).extend([str(out/(role+'.jar'))+':/tf2/app.jar:ro',
            str(runtime)+':/tf2/output:rw',str(out/'observer.jar')+':/tf2/observer.jar:ro',str(cost)+':/tf2/cost:rw'])
        cfg['entrypoint']=['sh','-c','cd /tf2/output && exec java $$JAVA_OPTS -jar /tf2/app.jar --port=80']
        if mode=='flowdist':
            model=manifest.get('branch_models',{}).get(role,{})
            if not model.get('author_method_instrumentation'):raise ValueError('Full original method event instrumentation required')
            for key,name in (('mapping','entitystmt.out.branch'),('statements','stmtids.out')):
                path=Path(model[key])
                if digest(path)!=model[key+'_sha256']:raise ValueError('Branch model digest mismatch')
                shutil.copyfile(path,runtime/name)
            cfg['environment']['JAVA_OPTS']+=' -Dflowdist.method.instrumented=true -Dflowdist.http.peer=http://shipping/shipping -Dflowdist.audit=/tf2/output/spring-events.jsonl'
        if mode=='tracefusion':
            if role=='orders':
                agent=args.tracefusion.resolve();meta=json.loads((agent.parent/'result.json').read_text())
                if digest(agent)!=meta['agent_sha256']:raise ValueError('TraceFusion build digest mismatch')
                shutil.copyfile(agent,out/'tracefusion-agent.jar')
                capture=out/'tracefusion-events';capture.mkdir();capture.chmod(0o777)
                cfg['volumes'].extend([str(out/'tracefusion-agent.jar')+':/tf2/tracefusion-agent.jar:ro',str(capture)+':/tf2/tf-events:rw'])
                cfg['environment']['JAVA_OPTS']+=' -javaagent:/tf2/tracefusion-agent.jar -Dtracefusion.service.output=/tf2/tf-events'
            else:
                capture=out/'boundary-events'/role;capture.mkdir(parents=True);capture.chmod(0o777)
                cfg['volumes'].append(str(capture)+':/tf2/boundary:rw')
                cfg['environment']['JAVA_OPTS']+=' -javaagent:/tf2/observer.jar -Dtracefusion.boundary.mode=tracefusion -Dtracefusion.boundary.output=/tf2/boundary'
        cfg['environment']['JAVA_OPTS']+=' -javaagent:/tf2/observer.jar=cost -Dtracefusion.cost.output=/tf2/cost'
    for cfg in spec['services'].values():cfg['restart']='no'
    return spec


def run_mode(args,mode,out):
    out.mkdir(parents=True,exist_ok=False)
    spec=configuration(args,mode,out);file=out/'compose.preflight.json';save(file,spec)
    project='tf2-fd-cost-'+secrets.token_hex(5)
    options=argparse.Namespace(project=project,ready_timeout=args.ready_timeout)
    deployment=CachedDeployment(options,out,file)
    for command in (['docker','ps','--all','--quiet'],['docker','network','ls','--quiet'],['docker','volume','ls','--quiet']):
        if deployment.command(command+['--filter','label=com.docker.compose.project='+project]).stdout.strip():
            raise ValueError('Fresh Docker project required')
    result={'mode':mode,'project':project,'status':'failed','cases':[],'samples':[],
        'accuracy_eligible':False,'performance_eligible':False}
    registry=json.loads((HERE/'cases.json').read_text())
    save(out/'cases.json',registry)
    try:
        deployment.start()
        phases=[('accuracy',registry['cases']),('warmup',[registry['cases'][0]]*args.warmup),
            ('measurement',[registry['cases'][0]]*args.repetitions)]
        for phase,cases in phases:
            for index,case in enumerate(cases):
                name=case['id'] if phase=='accuracy' else phase+'-'+str(index)
                folder=out/name
                fixture=prepare(case,name,folder,'http://127.0.0.1:18580','http://127.0.0.1:18581')
                before={role:len(events(out/'cost-events'/role/'events.jsonl')) for role in ('orders','shipping')}
                business=submit(fixture,'http://127.0.0.1:18582',folder)
                business.update(method='newOrder',phase=phase,trace_id=fixture[-1]['trace_id_requested'])
                result['cases'].append(business)
                save(out/'progress.json',{'cases':result['cases']})
                if not business['business_passed']:raise ValueError('Business workload failed: '+name)
                if phase!='measurement':continue
                sample={'case':name,'http_ms':(business['end_monotonic_ns']-business['start_monotonic_ns'])/1e6,'services':{}}
                for role,method in (('orders','newOrder'),('shipping','postShipping')):
                    new=events(out/'cost-events'/role/'events.jsonl')[before[role]:]
                    hits=[r for r in new if r['kind']=='exit' and r['parent']==0 and '.'+method+'(' in r['method']]
                    if len(hits)!=1:raise ValueError('Missing/duplicate cost event: '+name+'/'+role)
                    row=hits[0]
                    if any(row[k]<0 for k in ('process_allocated_bytes','thread_allocated_bytes')):
                        raise ValueError('Invalid allocation counter delta: '+name+'/'+role)
                    sample['services'][role]={'controller_ms':row['runtime_ns']/1e6,
                        'process_allocated_KiB':row['process_allocated_bytes']/1024,
                        'thread_allocated_KiB':row['thread_allocated_bytes']/1024,'jvm_rss_KiB':row['rss_kb'],
                        'observer_sequence':row['seq']}
                result['samples'].append(sample)
                print(mode,name,'passed',flush=True)
        for role in ('orders','shipping'):deployment.compose('stop','-t','30',role,timeout=45)
        result['status']='business-and-common-observer-passed'
        result['cost']={role:{key:stats([s['services'][role][key] for s in result['samples']])
            for key in ('controller_ms','process_allocated_KiB','thread_allocated_KiB','jvm_rss_KiB')}
            for role in ('orders','shipping')}
        result['cost']['client_http_ms']=stats([s['http_ms'] for s in result['samples']])
    finally:
        deployment.diagnostics();deployment.compose('down','--volumes','--remove-orphans',check=False,timeout=90)
        save(out/'result.json',result)
    return result


def run(args):
    tool.verify_repository(args.repo.resolve());out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    protocol={'target':'original newOrder with Shipping async HTTP; also report nested postShipping costs',
        'warmup':args.warmup,'repetitions':args.repetitions,'serial':True,'deployment_rounds':1,
        'accuracy_cases':7,'observer_sha256':digest(args.boundary),'tracefusion_agent_sha256':digest(args.tracefusion),
        'flowdist_build_manifest_sha256':digest(args.apps/'manifest.json'),
        'rss_definition':'whole service JVM VmRSS sampled after each controller call; KiB',
        'allocation_definition':'process-wide and current-thread allocation counter deltas, separately; KiB',
        'offline_analysis_included':False,'static_preprocessing_included':False,
        'original_jars':{role:digest(path) for role,path in (('orders',args.orders),('shipping',args.shipping))}}
    save(out/'protocol.json',protocol)
    reports={}
    for mode in args.modes:reports[mode]=run_mode(args,mode,out/mode)
    locks=[json.loads((out/m/'compose.lock.json').read_text()) for m in reports]
    images={s:c['image'] for s,c in locks[0]['services'].items()}
    if any({s:c['image'] for s,c in lock['services'].items()}!=images for lock in locks):raise ValueError('Different business images')
    report={'kind':'sockshop-flowdist-tracefusion-cost-pilot','protocol':protocol,'runs':reports,
        'same_business_images':True,'images':images,'accuracy_results_available':False,
        'accuracy_eligible':False,'performance_eligible':False,
        'limitations':['One deployment per mode in fixed order; no stable ranking or confidence claim.',
        'FlowDist uses full original method events, branch probes and disclosed HTTP/lambda/runtime adaptations.',
        'TraceFusion observes Orders DTO/RPC/stream data and Shipping boundary fields; tracing scopes differ.',
        'Offline query/reconstruction and static preprocessing are excluded and must be measured separately.',
        'Allocation includes background activity; RSS is whole-process resident memory, not per-call retained memory.',
        'Business oracle checks are not information-flow accuracy; field/path predictions require separate evaluation.']}
    if 'plain' in reports:
        for mode in reports:
            if mode=='plain':continue
            for role in ('orders','shipping'):
                base=reports['plain']['cost'][role];cost=reports[mode]['cost'][role]
                cost['controller_overhead_percent']=100*(cost['controller_ms']['mean']/base['controller_ms']['mean']-1)
                cost['rss_delta_KiB']=cost['jvm_rss_KiB']['mean']-base['jvm_rss_KiB']['mean']
    save(out/'comparison.json',report)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for flag in ('repo','apps','orders','shipping','boundary','tracefusion','out'):p.add_argument('--'+flag,type=Path,required=True)
    p.add_argument('--modes',nargs='+',choices=('plain','flowdist','tracefusion'),default=['plain','flowdist','tracefusion'])
    p.add_argument('--warmup',type=int,default=5);p.add_argument('--repetitions',type=int,default=20)
    p.add_argument('--ready-timeout',type=int,default=180);p.add_argument('--subnet',default='10.254.243.0/24')
    args=p.parse_args()
    if args.warmup<0 or args.repetitions<1 or len(set(args.modes))!=len(args.modes):p.error('Invalid workload or duplicate modes')
    run(args)
