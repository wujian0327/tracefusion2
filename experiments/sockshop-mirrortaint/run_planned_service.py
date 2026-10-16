#!/usr/bin/env python3
"""Build and compare automatic/full observation on the unmodified Sock Shop Orders service."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import random
import secrets
import shutil
import subprocess
import threading
from zipfile import ZipFile,ZIP_DEFLATED
from run_query_planner import JARS,command
from experiment_environment import java8_target
from plan_service_observations import plan_service
from infer_planned_service import infer_service
from host import HERE,ROOT,prepare,submit
from flowdist_full_order import CachedDeployment


def load(p):return json.loads(p.read_text())
def save(p,v):p.write_text(json.dumps(v,indent=2,ensure_ascii=False)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def build(out,jar,entry,target):
    out.mkdir(parents=True,exist_ok=False);(out/'tools').mkdir();(out/'app').mkdir()
    cp=':'.join(map(str,JARS));src=[HERE/n for n in ('QueryObservationAgent.java','QueryBytecodeModel.java','PlannedServiceAgent.java','CollectionServiceHooks.java','SpringTransportAgent.java','W3CTraceContext.java')]
    _,compiler_target=java8_target()
    command(['javac',*compiler_target,'-cp',cp,'-d',str(out/'tools'),*map(str,src)],out/'compile.log')
    with ZipFile(jar) as z:
        for n in z.namelist():
            if n.startswith('BOOT-INF/classes/') and n.endswith('.class'):
                dest=out/'app'/n[len('BOOT-INF/classes/'):];dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(z.read(n))
    command(['java','-cp',str(out/'tools')+':'+cp,'QueryBytecodeModel',str(out/'app'),str(out/'model.json')],out/'model.log')
    model=load(out/'model.json');p=plan_service(model,entry,target);save(out/'plan.json',p)
    agent=out/'planned-observer.jar'
    with ZipFile(agent,'w',ZIP_DEFLATED) as z:
        z.writestr('META-INF/MANIFEST.MF','Manifest-Version: 1.0\nPremain-Class: PlannedServiceAgent\n\n')
        for f in (out/'tools').glob('PlannedServiceAgent*.class'):z.write(f,f.name)
        for prefix in ('CollectionServiceHooks','SpringTransportAgent','W3CTraceContext'):
            for f in (out/'tools').glob(prefix+'*.class'):z.write(f,f.name)
        for dep in JARS:
            with ZipFile(dep) as dz:
                for n in dz.namelist():
                    if n.endswith('.class') and n.startswith(('org/objectweb/asm/','com/fasterxml/jackson/')):z.writestr(n,dz.read(n))
    shutil.copyfile(jar,out/'original.jar')
    save(out/'build.json',{'original_jar':str(jar),'original_jar_sha256':sha(jar),'agent_sha256':sha(agent),
        'plan_sha256':sha(out/'plan.json'),'model_sha256':sha(out/'model.json'),'sources':{str(f):sha(f) for f in src+[HERE/'plan_service_observations.py',HERE/'infer_planned_service.py',HERE/'query_observation_planner.py']},
        'dependencies':{str(f):sha(f) for f in JARS},'entry':entry,'target':target})
    print('Generated plan:',p['target'],p['mapper_fields'],flush=True)


def freeze(out,b,seed,secondary=None):
    out.mkdir(parents=True,exist_ok=False)
    cases=load(HERE/'cases.json')['cases'];rng=random.Random(seed)
    for i in range(10):cases.append({'id':'heldout-'+str(i),'items':[{'key':str(j),'quantity':rng.randint(1,3),'unitPrice':rng.choice([0.,1.25,2.5,5.])} for j in range(rng.randint(0,4))],'expected_target':True})
    save(out/'cases.json',cases)
    save(out/'freeze.json',{'build_sha256':sha(b/'build.json'),'cases_sha256':sha(out/'cases.json'),'seed':seed,
        'secondary_build':str(secondary) if secondary else None,'secondary_build_sha256':sha(secondary/'build.json') if secondary else None,
        'note':'Additional inputs generated after model/plan/code freeze; independently authored blind benchmark not claimed.'})


def check_frozen(out,b):
    frozen=load(out/'freeze.json');info=load(b/'build.json')
    if sha(b/'build.json')!=frozen['build_sha256'] or sha(out/'cases.json')!=frozen['cases_sha256']:raise ValueError('Frozen inputs changed')
    for f,wanted in {**info['sources'],**info['dependencies']}.items():
        if sha(Path(f))!=wanted:raise ValueError('Frozen source/dependency changed: '+f)
    for f,key in [('plan.json','plan_sha256'),('model.json','model_sha256'),('original.jar','original_jar_sha256'),('planned-observer.jar','agent_sha256')]:
        if sha(b/f)!=info[key]:raise ValueError('Frozen build changed')
    if frozen.get('secondary_build'):
        other=Path(frozen['secondary_build']);secondary=load(other/'build.json')
        if sha(other/'build.json')!=frozen['secondary_build_sha256']:raise ValueError('Secondary frozen build changed')
        for f,key in [('plan.json','plan_sha256'),('model.json','model_sha256'),('original.jar','original_jar_sha256'),('planned-observer.jar','agent_sha256')]:
            if sha(other/f)!=secondary[key]:raise ValueError('Secondary build changed')


def run(out,b,mode):
    check_frozen(out,b);dest=out/mode;dest.mkdir(exist_ok=False);capture=dest/'capture';capture.mkdir();capture.chmod(0o777)
    spec=load(ROOT/'scenarios/sockshop/compose.json')
    spec['networks']={'default':{'ipam':{'config':[{'subnet':'10.254.250.0/24'}]}}}
    for cfg in spec['services'].values():cfg['restart']='no'
    for role,port in [('front-end',18580),('carts',18581),('orders',18582)]:spec['services'][role]['ports']=['127.0.0.1:'+str(port)+(':'+str(8079 if role=='front-end' else 80))]
    spec['services']['rabbitmq']['environment']={'RABBITMQ_SERVER_ADDITIONAL_ERL_ARGS':'+S 2:2 +A 8'}
    cfg=spec['services']['orders'];cfg.setdefault('volumes',[]).extend([str(b/'original.jar')+':/tf2/app.jar:ro',str(b/'planned-observer.jar')+':/tf2/observer.jar:ro',str(b/'plan.json')+':/tf2/plan.json:ro',str(capture)+':/tf2/capture:rw'])
    cfg['entrypoint']=['sh','-c','exec java $$JAVA_OPTS -jar /tf2/app.jar --port=80']
    cfg['environment']['JAVA_OPTS']+=' -javaagent:/tf2/observer.jar -Dservice.plan=/tf2/plan.json -Dservice.events=/tf2/capture/events.jsonl -Dservice.mode='+mode
    secondary=load(out/'freeze.json').get('secondary_build')
    if secondary:
        other=Path(secondary);sc=dest/'shipping-capture';sc.mkdir();sc.chmod(0o777);cfg=spec['services']['shipping'];cfg['ports']=['127.0.0.1:18583:80']
        cfg.setdefault('volumes',[]).extend([str(other/'original.jar')+':/tf2/app.jar:ro',str(other/'planned-observer.jar')+':/tf2/observer.jar:ro',str(other/'plan.json')+':/tf2/plan.json:ro',str(sc)+':/tf2/capture:rw'])
        cfg['entrypoint']=['sh','-c','exec java $$JAVA_OPTS -jar /tf2/app.jar --port=80']
        cfg['environment']['JAVA_OPTS']+=' -javaagent:/tf2/observer.jar -Dservice.plan=/tf2/plan.json -Dservice.events=/tf2/capture/events.jsonl -Dservice.mode='+mode
    save(dest/'compose.json',spec);project='tf2-planned-'+secrets.token_hex(5)
    dep=CachedDeployment(argparse.Namespace(project=project,ready_timeout=180),dest,dest/'compose.json')
    for cmd in (['docker','ps','-aq'],['docker','network','ls','-q'],['docker','volume','ls','-q']):
        if dep.command(cmd+['--filter','label=com.docker.compose.project='+project]).stdout.strip():raise ValueError('Fresh project required')
    result={'project':project,'mode':mode,'status':'failed','cases':[],'performance_eligible':False}
    def remember(r):
        result['cases'].append(r);save(dest/'progress.json',result)
        if not r['business_passed']:raise ValueError('Business request failed: '+str(r))
    try:
        dep.start()
        for case in load(out/'cases.json'):
            path=dest/case['id'];remember(submit(prepare(case,case['id'],path,'http://127.0.0.1:18580','http://127.0.0.1:18581'),'http://127.0.0.1:18582',path))
        base=load(out/'cases.json')[0];prepared=[]
        for i in range(8):prepared.append(prepare(base,'parallel-'+str(i),dest/('parallel-'+str(i)),'http://127.0.0.1:18580','http://127.0.0.1:18581',shared=True))
        barrier=threading.Barrier(8)
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures=[pool.submit(submit,p,'http://127.0.0.1:18582',dest/('parallel-'+str(i)),barrier) for i,p in enumerate(prepared)]
            for f in futures:remember(f.result())
        if secondary:
            from sockshop import Client
            # Independent source field and sibling field contain equal values in
            # two requests; identity/field coordinates must still stay distinct.
            direct=[]
            for i,name in enumerate(['same','same','changed','','中文名字']):
                d=dest/('shipping-direct-'+str(i));d.mkdir();client=Client(d);client.headers={'X-B3-TraceId':secrets.token_hex(8),'X-B3-SpanId':secrets.token_hex(8),'X-B3-Sampled':'1'}
                payload={'id':'same' if i<2 else 'direct-'+str(i),'name':name};response=client.request('POST','http://127.0.0.1:18583/shipping',payload,'shipping-target')
                if response!=payload:raise ValueError('Independent Shipping API oracle differs')
                direct.append({'trace_id':client.headers['X-B3-TraceId'],'input':payload,'response':response})
            save(dest/'shipping-direct.json',direct)
        dep.compose('stop','-t','20','orders',timeout=35)
        if secondary:dep.compose('stop','-t','20','shipping',timeout=35)
        result['status']='business-passed';print(mode,len(result['cases']),'business calls passed',flush=True)
    finally:
        dep.diagnostics();dep.compose('down','--volumes','--remove-orphans',timeout=90,check=False);save(dest/'result.json',result)


def evaluate(out,b):
    check_frozen(out,b);p=load(b/'plan.json');reports={};norm={}
    for mode in ('full','selective'):
        dest=out/mode;run_info=load(dest/'result.json');require(run_info['status']=='business-passed','Business run failed')
        r=infer_service(p,dest/'capture/events.jsonl');raw=[json.loads(l) for l in (dest/'capture/events.jsonl').read_text().splitlines()]
        entries={v['frame']:v for v in raw if v['kind']=='enter'};bytrace={a['trace_id']:a for a in r['answers']};no={a['trace_id'] for a in r['rejected_roots']}
        require(len(bytrace)==len(r['answers']) and None not in bytrace,'Root trace labels missing or duplicate')
        exact=0;tp=fp=fn=0;normalized={}
        for c in run_info['cases']:
            case=c['case'];contract=load(dest/case/'query-contract.json');trace=contract['trace_id_requested']
            if not contract['expected_target']:
                require(trace in no and trace not in bytrace,'No-target request misclassified');continue
            require(trace in bytrace,'Missing registered query');a=bytrace[trace];calc=entries[a['basis']['producer']];inputs=calc['inputs']
            expected_items=load(dest/case/'fixture.json')['expected_items'];require(len(inputs)==len(expected_items),'Observed member coverage differs from business oracle')
            # Identity grounding comes from actual input objects, while expected
            # dependency roles come from the separately frozen business contract.
            expected={(v['object'],p['mapper_owner']+'.'+name,next(f['version'] for f in v['fields'] if f['field']==p['mapper_owner']+'.'+name)) for v in inputs for name in ('quantity','unitPrice')}
            actual={tuple(v) for v in a['sources']};tp+=len(expected&actual);fp+=len(actual-expected);fn+=len(expected-actual)
            is_exact=actual==expected and a['version']==1;exact+=is_exact;require(is_exact,'Independent field-origin oracle differs')
            owner_to_index={v['object']:i for i,v in enumerate(inputs)}
            normalized[case]={'sources':sorted([owner_to_index[o],f,v] for o,f,v in actual),'target_field':a['field'],'target_version':a['version']}
        require(len(r['answers'])==sum(c['expected_target'] for c in run_info['cases']),'Unexpected/duplicate query')
        active=set();peak=0
        for row in raw:
            if row['kind']=='enter' and row['method']==p['entry']:active.add(row['frame']);peak=max(peak,len(active))
            elif row['kind'] in ('exit','abort'):active.discard(row['frame'])
        r.update(queries=len(r['answers']),exact=exact,tp=tp,fp=fp,fn=fn,precision=tp/(tp+fp),recall=tp/(tp+fn),f1=2*tp/(2*tp+fp+fn),peak_overlapping_roots=peak,business_calls=len(run_info['cases']))
        save(dest/'inference.json',r);reports[mode]={k:v for k,v in r.items() if k not in ('answers','rejected_roots')};norm[mode]=normalized
    require(norm['full']==norm['selective'],'Full/selected query answers differ')
    save(out/'comparison.json',{'results':reports,'normalized_answers_identical':True,'plan':p,'performance_eligible':False,
        'scope':'Real unmodified Spring Orders controller; producer-entry object field-version origins, not automatic HTTP/DB/cross-service reconstruction.'})
    if load(out/'freeze.json').get('secondary_build'):
        other=Path(load(out/'freeze.json')['secondary_build']);sp=load(other/'plan.json');sr={}
        for mode in ('full','selective'):
            d=out/mode;r=infer_service(sp,d/'shipping-capture/events.jsonl');raw=[json.loads(l) for l in (d/'shipping-capture/events.jsonl').read_text().splitlines()];en={v['frame']:v for v in raw if v['kind']=='enter'}
            # 24 successful Orders submissions each invoke Shipping once, plus
            # the separately checked direct HTTP requests.
            expected_count=len(load(d/'inference.json')['answers'])+len(load(d/'shipping-direct.json'))
            require(len(r['answers'])==expected_count and not r['rejected_roots'],'Shipping query coverage differs')
            for a in r['answers']:
                e=en[a['root_frame']];name=next(f for f in e['input_fields'] if f['field'].rsplit('.',1)[1]=='name')
                require(a['sources']==[[e['input_object'],sp['target'],name['version']]] and a['owner']==e['input_object'] and a['version']==name['version'],'Shipping field-instance oracle differs')
            direct_ids={v['trace_id'] for v in load(d/'shipping-direct.json')};require(direct_ids<={a['trace_id'] for a in r['answers']},'Direct shipping inputs missing')
            r.update(queries=len(r['answers']),exact=len(r['answers']),tp=len(r['answers']),fp=0,fn=0,precision=1.,recall=1.,f1=1.)
            save(d/'shipping-inference.json',r);sr[mode]={k:v for k,v in r.items() if k not in ('answers','rejected_roots')}
        first_classes={f.name:sha(f) for f in (b/'tools').glob('PlannedServiceAgent*.class')}
        other_classes={f.name:sha(f) for f in (other/'tools').glob('PlannedServiceAgent*.class')}
        save(out/'shipping-comparison.json',{'results':sr,'plan':sp,'same_collector_bytecode':first_classes==other_classes,
             'scope':'Shipping postShipping input Shipment.name to same returned object field; HTTP/AMQP provenance is not reconstructed.'})
    print(json.dumps(reports,indent=2),flush=True)


from query_observation_planner import require
if __name__=='__main__':
    a=argparse.ArgumentParser(description=__doc__);a.add_argument('stage',choices=('build','freeze','run','evaluate'));a.add_argument('--out',type=Path,required=True);a.add_argument('--build',type=Path);a.add_argument('--jar',type=Path);a.add_argument('--entry');a.add_argument('--target',default='CustomerOrder.total');a.add_argument('--mode',choices=('full','selective'));a.add_argument('--seed',type=int,default=151026);a.add_argument('--secondary-build',type=Path);args=a.parse_args();out=args.out.resolve()
    if args.stage=='build':build(out,args.jar.resolve(),args.entry,args.target)
    elif args.stage=='freeze':freeze(out,args.build.resolve(),args.seed,args.secondary_build.resolve() if args.secondary_build else None)
    elif args.stage=='run':run(out,args.build.resolve(),args.mode)
    else:evaluate(out,args.build.resolve())
