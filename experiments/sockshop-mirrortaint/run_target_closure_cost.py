"""Frozen closure experiment: existing four tasks, one normal offline pass.

Uses the prior corrected Mall/Orders workload implementations. New ZLT workload
uses the same original six pagination templates. No source or model selection
depends on a cost result. Metric thresholds were sealed before core edits.
"""
import argparse
import copy
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
import os
from pathlib import Path
import random
import resource
import secrets
import shutil
import subprocess
import sys
import time
import traceback
from run_planned_service import ROOT,HERE,load,save,sha

FINAL=ROOT/'artifacts/target-closure-revision-20261103/final-candidate-02'
BASE=FINAL/'historical/frozen-base'
MALL=FINAL/'mall'
COMMIT=None


def verify():
    f=load(FINAL/'historical/algorithm-freeze.json')
    for p,h in f['sources'].items():assert sha(Path(p))==h,p
    assert sha(HERE/'build_distributed_plans.py')==f['builder_sha256']
    assert sha(BASE/'distributed-observer.jar')==load(FINAL/'final-protocol-before-business.json')['agent_sha256']
    return f


def legacy():
    import run_zlt_body_cost as previous
    previous.FINAL=FINAL;previous.BASE=BASE;previous.MALL=MALL
    previous.COMMIT=verify()['commit'];previous.verify=verify
    # Its subprocess launch sites now enter THIS frozen experiment wrapper;
    # both wrapper and unchanged helper hashes are recorded in the protocol.
    previous.__file__=str(Path(__file__).resolve())
    previous.fresh=fresh
    return previous


def prepare(home):
    previous=legacy();previous.prepare(home)
    protocol=load(home/'protocol-before-calibration.json')
    witness=home/'orders-library-witness';witness.mkdir()
    prior=ROOT/'artifacts/zlt-body-cost-20261031/orders-library-witness/library-witness.jar'
    shutil.copyfile(prior,witness/'library-witness.jar')
    protocol['unchanged_Orders_mapper_witness']={'original':str(prior),'sha256':sha(prior)}
    protocol['reference']='7e4ad0b900a64871259a5fac008968128cc5ec28'
    protocol['metric_protocol_before_core']=load(FINAL.parent/'development-protocol-before-change.json')
    protocol['unchanged_helpers']={'run_zlt_body_cost.py':sha(HERE/'run_zlt_body_cost.py'),
                                  'run_frozen_locality_cost.py':sha(HERE/'run_frozen_locality_cost.py')}
    for task,api in [('zlt-client','ZLT-MP-1'),('zlt-user','ZLT-MP-4')]:
        q=next(q for q in load(FINAL/'zlt/task-seal.json')['entries']if q['id']==api)
        protocol['tasks'][task]={'api':api,'query':q,'source':q['oracle']['source'],
           'plan_sha256':sha(FINAL/'zlt/planning-first'/api/'000-plan.json'),
           'input':'Cycle original six page/limit templates, including empty pages; actual targets remain in denominator. No new pagination contract.',
           'MT_adapter':'Original isolated B2.2 and unchanged native JAR; formal inclusion only after new per-JVM calibration.'}
    rng=random.Random(20261103);jobs=[]
    for repeat in range(1,6):
        for task in ('mall','zlt-client','zlt-user','orders'):
            modes=['original','full','selective','mirrortaint'];rng.shuffle(modes)
            jobs.extend(dict(round=repeat,task=task,mode=mode)for mode in modes)
    protocol.update(jobs=jobs,deployments_planned=80,
        majority_unit='Four preselected query tasks, not requests. Rejected/not-common-correct tasks remain in coverage and cannot be wins.',
        strata={'unified_execution':['mall','zlt-client','zlt-user'],'existing_specialized':['orders']},
        primary_criterion='Both complete-batch protocol bytes and normal offline CPU lower; online business CPU and p95 median ratios <=1.05 and every paired round ratio <=1.10. Report individual metrics even if this joint criterion fails.',
        independent_ablation='Short selective projection on/off, same Agent/plan/body policy and checks; event/byte/node/allocation counts, no speed inference from short windows.',
        memory='Current exec /proc/self/status VmHWM; original ru_maxrss retained only as a diagnostic, not used as exec memory.',
        external_gate='New-app first matrix completed unchanged before formal costs; per-task original/TF/MT business, source and target calibration required.')
    protocol['business_comparison']={'Mall':'Mask freshly issued token/refreshToken; verify expiresIn against original 86400-second configuration and each request duration before normalizing clock rounding. Retain keys/types, code/message/tokenHead and exact login-log insert count. Per-JVM target/source value equality remains exact.',
        'ZLT':'Full JSON equality per original page/limit template across original and instrumented arms. Physical source truth is scored separately, never by these equal values.',
        'Orders':'Existing frozen original common-task calibration and independent total/source rules; generated IDs are not cross-JVM matched.'}
    save(home/'protocol-before-calibration.json',protocol)


def zlt_spec(home,out,task,mode,projection_off=False):
    api='ZLT-MP-1'if task=='zlt-client'else'ZLT-MP-4'
    q=next(q for q in load(FINAL/'zlt/task-seal.json')['entries']if q['id']==api)
    reference=FINAL/'zlt/runs'/api/'full'
    cfg=copy.deepcopy(load(reference/'compose.json'))
    for role,s in cfg['services'].items():
        if role in ('zlt-user','zlt-uaa'):
            s['command']=[('-Xmx256m'if a.startswith('-Xmx')else a)for a in s['command']
                          if not a.startswith(('-javaagent:','-Dservice.','-Dinstance.','-Dcapability.','-Dtaint.','-Dnative.library.'))]
            s['volumes']=[v for v in s['volumes']if not v.split(':')[1].startswith('/tf2/')]
        # Pin the actual image ID, even if a prior compose used a human tag.
        image=json.loads(subprocess.check_output(['docker','image','inspect',s['image']],text=True))[0]
        s['image']=image['Id']
    cap=out/'capture';cap.mkdir();cap.chmod(0o777)
    role=q['role'];options=[];mounts={}
    if mode in ('full','selective'):
        plan=FINAL/'zlt/planning-first'/api/'000-plan.json'
        mounts={BASE/'distributed-observer.jar':'/tf2/observer.jar',plan:'/tf2/plan.json'}
        options=['-javaagent:/tf2/observer.jar','-Dservice.plan=/tf2/plan.json',
                 '-Dservice.events=/tf2/capture/events.jsonl','-Dservice.mode='+mode]
        if projection_off:options.append('-Dservice.target.observation=false')
    elif mode=='mirrortaint':
        prior=ROOT/'artifacts/offline-zlt-revision-20261031/final-zlt-MT-isolated-01/runs'/api/'mirrortaint'
        reference_cfg=load(prior/'compose.json')['services'][role]
        for v in reference_cfg['volumes']:
            parts=v.split(':')
            if len(parts)>1 and parts[1].startswith('/tf2/')and parts[1]!='/tf2/capture':
                mounts[Path(parts[0])]=parts[1]
        options=[a for a in reference_cfg['command']if a.startswith(('-javaagent:','-Dnative.library.','-Dtaint.','-Dcapability.','-Dinstance.','-Duser.home='))]
    if mode!='original':
        cfg['services'][role]['volumes'] += [str(p)+':'+dest+':ro'for p,dest in mounts.items()]+[str(cap)+':/tf2/capture:rw']
        command=cfg['services'][role]['command'];at=command.index('-jar');command[at:at]=options
    cfg['services']['load-client']={'image':'sha256:16b80569968fb112fee59fdbaeda7a5fe9b3d534ba1cf212f33afe1d1089fe75','entrypoint':['/bin/sh','-c','while true; do sleep 60; done'],
                                      'cpus':1,'mem_limit':'128m','dns_search':['.']}
    save(out/'tool-binaries.json',{'task':task,'mode':mode,'files':{str(p):sha(p)for p in mounts},'projection_off':projection_off,
         'native_propagation_changed':False,'MT_adapter_changed':False})
    return cfg,q


def zlt_trial(home,name,task,mode,warm,measure,projection_off=False,sample=True):
    from sockshop import Deployment
    from run_sockshop_cost import Sampler
    verify();out=home/name;out.mkdir(parents=True,exist_ok=False)
    cfg,q=zlt_spec(home,out,task,mode,projection_off);save(out/'compose.json',cfg)
    dep=Deployment(argparse.Namespace(project='tf2-target-cost-'+secrets.token_hex(5)),out,out/'compose.json')
    role=q['role'];port=8000 if role=='zlt-uaa'else 7000
    outcome={'task':task,'mode':mode,'state':'environment_failed'}
    def request(label,i):
        template=q['inputs'][i%len(q['inputs'])];digest=hashlib.sha256((name+'|'+label+'|'+str(i)).encode()).hexdigest()
        message=digest[:32]+'/'+digest[32:48];start=time.monotonic_ns()
        p=dep.compose('exec','-T','load-client','curl','--noproxy','*','-sS','--max-time','20','-w','\n%{http_code}\n%{time_total}',
          '-H','traceparent: 00-'+digest[:32]+'-'+digest[32:48]+'-01','http://'+role+':'+str(port)+template['path'],check=False)
        end=time.monotonic_ns();raw,status,timing=p.stdout.rsplit('\n',2)
        try:value=json.loads(raw)
        except ValueError:value=raw
        passed=p.returncode==0 and int(status)==200 and isinstance(value,dict)and isinstance(value.get('data'),list)
        return {'case':label+'-%05d'%i,'template':template['case'],'request_path':template['path'],'message':message,
                'http_status':int(status),'response':value,'start_ns':start,'end_ns':end,'http_seconds':float(timing),'business_passed':passed}
    def phase(label,seconds):
        start=time.monotonic_ns();pending=[]
        with ThreadPoolExecutor(max_workers=2)as pool:
            for i in range(round(seconds*2)):
                delay=start/1e9+i/2-time.monotonic()
                if delay>0:time.sleep(delay)
                pending.append(pool.submit(request,label,i))
            delay=start/1e9+seconds-time.monotonic()
            if delay>0:time.sleep(delay)
            rows=[future.result()for future in pending]
        return {'start_ns':start,'end_ns':time.monotonic_ns(),'requests':rows}
    try:
        dep.compose('up','-d','mysql','redis','redis2','redis3','nacos','--pull','never',timeout=180)
        deadline=time.monotonic()+180
        while time.monotonic()<deadline:
            check=dep.compose('exec','-T','mysql','mysql','-uroot','-ptf2-portability-fixture-only','-e','SELECT COUNT(*) FROM `user-center`.sys_user;',check=False)
            if check.returncode==0:break
            time.sleep(2)
        else:raise RuntimeError('ZLT original SQL not ready')
        result=dep.compose('exec','-T','redis','redis-cli','-a','tf2-portability-fixture-only','--cluster','create',
            'redis:6379','redis2:6380','redis3:6381','--cluster-replicas','0','--cluster-yes',check=False,timeout=90)
        (out/'redis-cluster-create.log').write_text((result.stdout or'')+(result.stderr or''))
        assert result.returncode==0
        deadline=time.monotonic()+120
        while time.monotonic()<deadline:
            probe=dep.compose('exec','-T','nacos','curl','-fsS','--max-time','5','http://127.0.0.1:8848/nacos/v1/ns/operator/metrics',check=False)
            if probe.returncode==0:break
            time.sleep(2)
        else:raise RuntimeError('ZLT Nacos not ready')
        dep.compose('up','-d','--pull','never',timeout=180)
        deadline=time.monotonic()+200
        while time.monotonic()<deadline:
            logs={r:dep.compose('logs','--no-color',r,check=False).stdout for r in ('zlt-user','zlt-uaa')}
            if any('APPLICATION FAILED TO START'in s or'Application run failed'in s for s in logs.values()):raise RuntimeError('ZLT startup failed')
            if all('Started 'in s for s in logs.values()):break
            time.sleep(3)
        else:raise RuntimeError('ZLT readiness timeout')
        containers={r:dep.compose('ps','-q',r).stdout.strip()for r in cfg['services']if r!='load-client'}
        if sample:
            with Sampler(containers,2,out/'resources.jsonl',observed_roles=('zlt-user','zlt-uaa'))as sampler:
                a=phase(name+'-warmup',warm);save(out/'warmup.json',a)
                b=phase(name+'-measure',measure);save(out/'measure.json',b)
            save(out/'resource-summary.json',sampler.summary(b['start_ns'],b['end_ns']))
        else:
            a=phase(name+'-warmup',warm);save(out/'warmup.json',a)
            b=phase(name+'-measure',measure);save(out/'measure.json',b)
        cases=a['requests']+b['requests']
        outcome.update(state='captured',requests=len(cases),business_passed=sum(r['business_passed']for r in cases))
        database='oauth-center'if task=='zlt-client'else'user-center';table=q['oracle']['sql_table']
        r=dep.compose('exec','-T','mysql','mysql','-uroot','-ptf2-portability-fixture-only','--batch','-e','SELECT * FROM `'+database+'`.`'+table+'` ORDER BY id;',check=False)
        (out/'independent-database.tsv').write_text((r.stdout or'')+(r.stderr or''))
    except Exception as error:outcome['error']=str(error);(out/'failure.log').write_text(traceback.format_exc())
    finally:
        try:dep.compose('stop','-t','30','zlt-user','zlt-uaa',check=False,timeout=120);dep.diagnostics()
        finally:outcome['cleanup_returncode']=dep.compose('down','--volumes','--remove-orphans',check=False,timeout=120).returncode;save(out/'result.json',outcome)
    verify();assert outcome['state']=='captured'and outcome['requests']==outcome['business_passed']and outcome['cleanup_returncode']==0,outcome
    if mode!='original':fresh(home,out,task,mode)
    print(name,outcome,flush=True)


def zlt_offline(home,trial,out,task,mode):
    from audit_zlt_foundation_revision import fields_equal,ancestor
    import external_transfer_oracle as oracle
    out.mkdir(parents=True,exist_ok=False);start=time.perf_counter();cpu=time.process_time();times={};t=start
    q=load(home/'protocol-before-calibration.json')['tasks'][task]['query'];role=q['role'];leaf=q['return_targets'][0]['path'].split('/')[-1]
    cases=load(trial/'warmup.json')['requests']+load(trial/'measure.json')['requests']
    if mode=='mirrortaint':
        from native_source_protocol import validate as validate_native
        from run_mirror_capability_probe import read_events,native_answer
        view=out/'native-view';view.mkdir();(view/'role').symlink_to((trial/'capture').resolve(),target_is_directory=True)
        rows=read_events(view,'role');times['decode_complete_capture']=time.perf_counter()-t
        t=time.perf_counter();validate_native(rows);times['required_source_protocol']=time.perf_counter()-t
        wire=oracle.raw(trial/'capture/instances.jsonl');graph=None
    else:
        from infer_distributed_fields import Reconstruction
        rows=oracle.raw(trial/'capture/events.jsonl');oracle.require_complete_raw_capture(rows);times['decode_complete_capture']=time.perf_counter()-t
        build=out/'build'/role;build.mkdir(parents=True);(build/'plan.json').write_bytes((FINAL/'zlt/planning-first'/q['id']/'000-plan.json').read_bytes())
        cap=out/'capture'/role;cap.mkdir(parents=True);(cap/'events.jsonl').symlink_to((trial/'capture/events.jsonl').resolve())
        t=time.perf_counter();graph=Reconstruction(out/'build',out/'capture',[role],decoded_rows={role:rows});times['reconstruction_with_required_certificates']=time.perf_counter()-t
        wire=[]
    # Raw indices contain no graph edges or decoded labels. Truth is the
    # original copy rule plus actual source/target owner-field-version equality.
    t=time.perf_counter()
    raw_returns={};raw_sources={};wire_by_message={};frames={};starts={};ends={}
    for r in rows:
        if r['kind']=='enter':frames[r['frame']]=r
        if r['kind'] in ('source-call-enter','collection-call-enter'):
            starts.setdefault((r['kind'],r.get('source_call_id',r.get('call_id'))),[]).append(r)
        if r['kind'] in ('source-call-exit','collection-call-exit'):
            ends.setdefault((r['kind'],r.get('source_call_id',r.get('call_id'))),[]).append(r)
        if r['kind']=='binding-return':raw_returns.setdefault(r.get('message'),[]).append(r)
        elif r['kind']=='binding-source':raw_sources.setdefault((r.get('frame'),r.get('callee')),[]).append(r)
        elif r['kind']=='target':raw_returns.setdefault(r['context'].get('message'),[]).append(r)
        elif r['kind']=='source':raw_sources.setdefault((r.get('root'),r.get('call')),[]).append(r)
    for r in wire:
        if r['kind']=='http-json'and r.get('direction')=='response'and r.get('phase')=='write':wire_by_message.setdefault(r.get('message'),[]).extend(r['fields'])
    sources_by_root={}
    if mode!='mirrortaint':
        # Every raw source occurrence is paired exactly once. Indexing retains
        # all ambiguous candidates; no first-match or trace-only assignment.
        from query_observation_planner import require
        root_frames={r['frame']for group in raw_returns.values()for r in group}
        owners={}
        def owning_roots(frame,seen=frozenset()):
            if frame in owners:return owners[frame]
            require(frame not in seen,'Raw Frame ancestry cycle')
            found={frame}if frame in root_frames else set()
            if frame in frames:
                parent=frames[frame].get('parent')
                if parent is not None:found.update(owning_roots(parent,seen|{frame}))
            owners[frame]=found;return found
        for (frame,callee),group in raw_sources.items():
            if callee!=q['oracle']['source']:continue
            roots=owning_roots(frame)
            require(len(roots)==1,'Source has missing/ambiguous returned root')
            root=next(iter(roots))
            for s in group:
                cid=s.get('source_call_id');require(cid is not None,'Missing source invocation')
                observed=s.get('source_scope')=='observation-only-call';prefix='source-call-'if observed else'collection-call-'
                aa=starts.get((prefix+'enter',cid),[]);bb=ends.get((prefix+'exit',cid),[])
                require(len(aa)==len(bb)==1,'Source completion missing/ambiguous');a,b=aa[0],bb[0]
                method=a['caller_method']if observed else a['method']
                require(a['seq']<s['seq']<b['seq'] and s['frame']==a['frame']==b['frame']and s['callee']==a['callee'],'Source interval/parent differs')
                require(s.get('source_caller_method')==method and s.get('source_pc')==a['pc'],'Source caller/PC differs')
                if observed:require(s.get('source_observation_frame')==a['observation_frame']==b['observation_frame'],'Source observation scope differs')
                sources_by_root.setdefault(root,[]).append(s)
    times['independent_raw_fact_index_and_pairing']=time.perf_counter()-t
    answers=[];t=time.perf_counter()
    for c in cases:
        for i,item in enumerate(c['response']['data']):
            path='/data/'+str(i)+'/'+leaf
            a=native_answer(rows,c['message'],path)if mode=='mirrortaint'else graph.query(c['message'],path,role,boundary=[{'kind':'binding-source'},{'kind':'argument'}])
            answers.append((c,i,path,a))
    times['native_tag_decode'if mode=='mirrortaint'else'query']=time.perf_counter()-t
    t=time.perf_counter();save(out/'answers.json',[{'case':c['case'],'path':p,'answer':a}for c,_,p,a in answers]);times['export']=time.perf_counter()-t
    t=time.perf_counter();scores=[]
    for c,i,path,a in answers:
        targets=raw_returns.get(c['message'],[]);assert len(targets)==1;target=targets[0]
        if mode=='mirrortaint':
            sources=raw_sources.get((target['root'],q['oracle']['source']),[]);assert len(sources)==1;source=sources[0]
            f=fields_equal(source['fields'],wire_by_message[c['message']],'/'+str(i)+'/'+leaf,path)
            assert f['value']==c['response']['data'][i][leaf]
            want={(source['call'],source['ordinal'],f['path'],f['owner'],f['field'],f['version'])}
            got=set(map(tuple,a['sources']));known=a['state']=='known'
        else:
            # Both exposed ZLT source callers are interpreted in this frozen
            # candidate; require the exact enclosing root source occurrence.
            sources=sources_by_root.get(target['frame'],[])
            assert len(sources)==1;source=sources[0]
            f=fields_equal(source['fields'],target['fields'],'/'+str(i)+'/'+leaf,path)
            assert f['observed']['value']==c['response']['data'][i][leaf]
            want={(source['callee'],source['frame'],source['seq'],f['path'],f['owner'],f['field'],f['version'])}
            got={(s.get('callee'),s.get('root_frame'),s['seq'],s.get('path'),s['owner'],s['field'],s['version'])for s in a['sources']};known=a['known']
        assert known and got==want and c['business_passed'],(c['case'],path,a,want)
        scores.append({'case':c['case'],'path':path,'known':True,'exact':True,'expected':sorted(want,key=str),'actual':sorted(got,key=str)})
    times['independent_score_raw_index']=time.perf_counter()-t;save(out/'scores.json',scores)
    core=times.get('reconstruction_with_required_certificates',0)+times.get('query',0)+times.get('native_tag_decode',0)
    save(out/'summary.json',{'targets':len(scores),'correct':len(scores),'positive':len(scores),'N/A_requests':sum(not c['response']['data']for c in cases),
        'core_seconds':core,'phases_seconds':times,'wall_seconds':time.perf_counter()-start,'cpu_seconds':time.process_time()-cpu,
        'raw_fact_oracle_only':True,'duplicate_external_certificate_validation':False})


def offline_worker(home,trial,out,task,mode):
    verify()
    # Constant-time accounting on the ONE ordinary graph construction. No
    # second reconstruction/audit is charged or hidden in this normal flow.
    work=[];core_cpu={'reconstruction':0.0,'query':0.0,'native_decode':0.0}
    if mode!='mirrortaint':
        import infer_distributed_fields as module
        original=module.Reconstruction;attribute='Reconstruction'
        class CountedReconstruction(original):
            def __init__(self,*args,**kwargs):
                begin=time.process_time()
                super().__init__(*args,**kwargs)
                core_cpu['reconstruction']+=time.process_time()-begin
                work.append({'nodes':len(self.nodes),'edge_lists':len(self.edges)})
            def query(self,*args,**kwargs):
                begin=time.process_time()
                try:return super().query(*args,**kwargs)
                finally:core_cpu['query']+=time.process_time()-begin
        replacement=CountedReconstruction
    else:
        # A native decode does not load the TF engine just for accounting.
        if task=='orders':import mirrortaint_instances as module;attribute='native_predictions'
        else:import run_mirror_capability_probe as module;attribute='native_answer'
        original=getattr(module,attribute)
        def measured_native(*args,**kwargs):
            begin=time.process_time()
            try:return original(*args,**kwargs)
            finally:core_cpu['native_decode']+=time.process_time()-begin
        replacement=measured_native
    setattr(module,attribute,replacement)
    try:
        if task.startswith('zlt-'):zlt_offline(home,trial,out,task,mode)
        else:legacy().offline_worker(home,trial,out,task,mode)
    finally:setattr(module,attribute,original)
    fields=dict(line.split(':',1)for line in Path('/proc/self/status').read_text().splitlines()if':'in line)
    summary=load(out/'summary.json');summary['resource_ru_maxrss_KiB']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    summary['VmHWM_KiB']=int(fields['VmHWM'].split()[0]);summary['memory_scope']='current exec /proc/self/status VmHWM'
    summary['graph_work_counts']=work
    summary['core_cpu_seconds']=sum(core_cpu.values());summary['core_cpu_phases_seconds']=core_cpu
    summary['CPU_scope']='Normal process CPU separately measured by parent; core counters exclude independent scoring/export and are not profiler times.'
    save(out/'summary.json',summary)


def fresh(home,trial,task,mode,out=None):
    out=out or trial/'offline-single-pass';before=resource.getrusage(resource.RUSAGE_CHILDREN);start=time.perf_counter()
    with(out.parent/(out.name+'.log')).open('w')as log:
        subprocess.run([sys.executable,__file__,'offline','--home',str(home),'--trial',str(trial),'--out',str(out),'--task',task,'--mode',mode],stdout=log,stderr=subprocess.STDOUT,check=True)
    after=resource.getrusage(resource.RUSAGE_CHILDREN);summary=load(out/'summary.json')
    summary.update(process_wall_seconds=time.perf_counter()-start,process_cpu_seconds=after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime)
    save(out/'process.json',summary);return summary


def trial(home,name,task,mode,warm,measure,projection_off=False,sample=True):
    if task.startswith('zlt-'):return zlt_trial(home,name,task,mode,warm,measure,projection_off,sample)
    old=legacy()
    if not sample:
        import run_sockshop_cost as cost
        original=cost.Sampler
        class BusinessOnlySampler:
            def __init__(self,containers,interval,path,**kwargs):self.path=path
            def __enter__(self):
                save(self.path.parent/'resource-calibration-scope.json',{'resource_sampling':False,'short_correctness_only':True});return self
            def __exit__(self,*args):pass
            def summary(self,*args):return {}
        cost.Sampler=BusinessOnlySampler
        try:return trial(home,name,task,mode,warm,measure,projection_off,True)
        finally:cost.Sampler=original
    if task=='mall'and projection_off:
        runner=old.install_mall();original=runner.spec
        def spec(out,policy):
            cfg=original(out,policy);cfg['services']['admin']['command'].insert(1,'-Dservice.target.observation=false');return cfg
        runner.spec=spec
        try:return old.trial(home,name,task,mode,warm,measure)
        finally:runner.spec=original
    if task=='orders'and mode!='original':
        real_run=subprocess.run
        def measured_run(command,*args,**kwargs):
            is_offline=isinstance(command,list)and len(command)>2 and command[0]==sys.executable and command[1]==str(Path(__file__).resolve())and command[2]=='offline'
            if not is_offline:return real_run(command,*args,**kwargs)
            before=resource.getrusage(resource.RUSAGE_CHILDREN);start=time.perf_counter()
            result=real_run(command,*args,**kwargs)
            after=resource.getrusage(resource.RUSAGE_CHILDREN)
            save(home/name/'offline-exec-resource-receipt.json',{'returncode':result.returncode,
                'cpu_seconds':after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime,
                'wall_seconds':time.perf_counter()-start,'scope':'Exactly one waited fresh offline child; no Docker or cleanup subprocess included.'})
            return result
        subprocess.run=measured_run
        try:result=old.trial(home,name,task,mode,warm,measure)
        finally:subprocess.run=real_run
        receipt=load(home/name/'offline-exec-resource-receipt.json');assert receipt['returncode']==0
        p=home/name/'offline-single-pass/summary.json';summary=load(p)
        summary['process_cpu_seconds']=receipt['cpu_seconds'];summary['process_wall_seconds']=receipt['wall_seconds'];save(p,summary)
        return result
    return old.trial(home,name,task,mode,warm,measure)


def planning_worker(home,out,task):
    if not task.startswith('zlt-'):legacy().planning_worker(home,out,task)
    else:
        out.mkdir(parents=True,exist_ok=False);start=time.perf_counter();cpu=time.process_time()
        from plan_capability_policy import choose
        q=load(home/'protocol-before-calibration.json')['tasks'][task]['query']
        model=load(FINAL/'zlt/metadata'/q['role']/'model.json')
        plan,_=choose(model,{'entry':q['entry'],**q['return_targets'][0],'source_calls':[q['oracle']['source']]})
        expected=load(FINAL/'zlt/planning-first'/q['id']/'000-plan.json');assert plan==expected
        save(out/'result.json',{'task':task,'plan_equals_deployment':True,'wall_seconds':time.perf_counter()-start,'cpu_seconds':time.process_time()-cpu})
    result=load(out/'result.json');fields=dict(line.split(':',1)for line in Path('/proc/self/status').read_text().splitlines()if':'in line)
    result['VmHWM_KiB']=int(fields['VmHWM'].split()[0]);result['memory_scope']='current exec /proc/self/status'
    save(out/'result.json',result)


def planning(home):
    out=home/'static-planning';out.mkdir(exist_ok=False);cpu=min(os.sched_getaffinity(0));rows=[]
    for task in('orders','mall','zlt-client','zlt-user'):
        for repeat in range(5):
            dest=out/('%s-%02d'%(task,repeat));before=resource.getrusage(resource.RUSAGE_CHILDREN);start=time.perf_counter()
            with(out/(dest.name+'.log')).open('w')as log:
                subprocess.run(['taskset','-c',str(cpu),sys.executable,__file__,'planning-worker','--home',str(home),'--out',str(dest),'--task',task],stdout=log,stderr=subprocess.STDOUT,check=True)
            after=resource.getrusage(resource.RUSAGE_CHILDREN);r=load(dest/'result.json');r.update(repeat=repeat,process_wall_seconds=time.perf_counter()-start,
                process_cpu_seconds=after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime);rows.append(r)
    save(out/'summary.json',{'logical_cpu':cpu,'fresh_exec':True,'OS_cache_not_cleared':True,
        'scope':'Frozen model load and planning. Excludes original JAR/model extraction, first dependency inventory, runtime probe, Agent compile and startup.','rows':rows})


def calibrate(home):
    verify();old=legacy();_,runner=old.install_orders(home)
    for mode in('full','selective','mirrortaint'):
        args=argparse.Namespace(out=home/('cal-orders-'+mode),build=home/'orders-build',bundle=home/'orders-mt-adapter',
            correctness=ROOT/'artifacts/desktop-portable-acceptance',mode='mirrortaint'if mode=='mirrortaint'else'tracefusion',
            observation_policy=mode if mode!='mirrortaint'else'selective')
        runner.run(args);assert load(args.out/'calibration.json')['passed']
    trial(home,'cal-orders-original','orders','original',4,8,sample=False)
    for task in ('mall','zlt-client','zlt-user'):
        for mode in('original','full','selective','mirrortaint'):
            trial(home,'cal-'+task+'-'+mode,task,mode,4,8,sample=False)
        trial(home,'cal-'+task+'-selective-without-value-projection',task,'selective',4,8,projection_off=True,sample=False)
    compare_business(home)
    save(home/'calibration-business-and-source.json',{'passed':True,'short_windows_are_not_cost_results':True,
         'Orders':'Original common calibration including parallel trace/span guards; three instrumented arms and separate original.',
         'other_tasks':'Original plus TF full/selective and fixed MT; six original input templates cycle, all actual positive targets independently scored in their own JVM.',
         'projection_ablation':'New real captures, same Agent/plan/body guards, runtime value projection disabled only; no shortened certificate protocol.'})


def compare_business(home):
    receipts=[]
    def cases(name):return load(home/name/'warmup.json')['requests']+load(home/name/'measure.json')['requests']
    def normalized(task,case):
        result=copy.deepcopy(case['response'])
        if task=='mall':
            for key in('token','refreshToken'):
                assert isinstance(result['data'][key],str)and result['data'][key]
                result['data'][key]='<fresh-token-string>'
            ttl=result['data']['expiresIn'];assert type(ttl)is int and 86400-math.ceil(case['http_seconds'])-1<=ttl<=86400
            result['data']['expiresIn']='<clock-rounded-86400-second-validity>'
        return result
    for task in('mall','zlt-client','zlt-user'):
        original=cases('cal-'+task+'-original')
        for mode in('original','full','selective','mirrortaint','selective-without-value-projection'):
            name='cal-'+task+'-'+mode;actual=cases(name);assert len(original)==len(actual)==24
            assert all(normalized(task,a)==normalized(task,b)for a,b in zip(original,actual)),(task,mode)
            item={'task':task,'mode':mode,'requests':24,'normalized_business_equal':True}
            if task=='mall':
                lines=(home/name/'database-after.txt').read_text().splitlines();at=lines.index('login_log_count');assert int(lines[at+1])==24
                item['login_log_rows']=24
            receipts.append(item)
    config=ROOT/'artifacts/portability-first-20261028/upstream/mall-swarm/mall-auth/src/main/java/com/macro/mall/auth/config/Oauth2ServerConfig.java'
    assert '.accessTokenValiditySeconds(3600*24)'in config.read_text()
    save(home/'business-comparison-detail.json',{'passed':True,'records':receipts,'values_are_not_instance_source_oracle':True,
        'public_original_TTL_configuration':{'source':str(config),'sha256':sha(config),'seconds':86400},
        'clock_normalization_only':'Independent per-JVM source/target expiresIn is still exact; token values never serve as cross-JVM instance IDs.'})


def dependencies(home):
    import audit_zlt_body_cost as audit
    audit.BASE=BASE;audit.MALL=MALL;audit.COMMIT=verify()['commit'];audit.verify=verify
    audit.dependencies(home)
    result=load(home/'dependency-calibration.json');more=[]
    for task,role in [('zlt-client','zlt-uaa'),('zlt-user','zlt-user')]:
        jar=FINAL/'zlt/business-jars'/(role+'.jar');entry,digest=audit.mapper_hash(jar)
        path=home/('cal-'+task+'-mirrortaint/capture/native-library.jsonl')
        records=[json.loads(line)for line in path.read_text().splitlines()]
        assert len(records)==1 and records[0]['sha256']==digest,(task,records,digest)
        for mode in('full','selective','mirrortaint'):
            summary=load(home/('cal-'+task+'-'+mode)/'offline-single-pass/summary.json')
            assert summary['targets']==summary['correct']and summary['positive']==summary['correct']and summary['correct']>0
        more.append({'task':task,'original_jar_sha256':sha(jar),'original_mapper':entry,'original_sha256':digest,
            'actual_witness':records[0],'witness_file_sha256':sha(path)})
    result['ZLT_mapper_witnesses']=more;result['ZLT_MT_adapter']='Existing isolated B2.2; native propagation unchanged; no new Class model or exporter code.'
    save(home/'dependency-calibration.json',result)


def formal(home):
    protocol=load(home/'protocol-before-calibration.json')
    for name in ('capability-gates.json','dependency-calibration.json','calibration-business-and-source.json','external-first-complete.json'):
        assert load(home/name)['passed'],name
    verify();save(home/'environment-before-formal.json',{'docker_ps':subprocess.check_output(['docker','ps','--format','{{.Names}}'],text=True).splitlines(),
       'uname':subprocess.check_output(['uname','-a'],text=True).strip(),'cpuinfo':Path('/proc/cpuinfo').read_text(),'affinity':sorted(os.sched_getaffinity(0))})
    driver_files=('run_target_closure_cost.py','run_zlt_body_cost.py','run_frozen_locality_cost.py','run_sockshop_cost.py',
        'calibrate_mirrortaint_total.py','mirrortaint_instances.py','external_transfer_oracle.py',
        'run_mirror_capability_probe.py','audit_zlt_foundation_revision.py','native_source_protocol.py')
    lock={str(HERE/name):sha(HERE/name)for name in driver_files}
    assert not(home/'driver-lock-before-formal.json').exists()
    save(home/'driver-lock-before-formal.json',{'files':lock,'protocol_sha256':sha(home/'protocol-before-calibration.json'),
        'cost_primary_fixed_before_core':sha(FINAL.parent/'development-protocol-before-change.json')})
    results=[]
    for job in protocol['jobs']:
        for p,h in lock.items():assert sha(Path(p))==h,p
        name='round-%02d-%s-%s'%(job['round'],job['task'],job['mode']);assert not(home/name).exists()
        print('START',name,flush=True)
        try:trial(home,name,job['task'],job['mode'],30,60);result={**job,'trial':name,'completed':True}
        except Exception as error:result={**job,'trial':name,'completed':False,'error':str(error)}
        results.append(result);save(home/'formal-progress.json',{'complete':False,'results':results});print('END',result,flush=True)
        for p,h in lock.items():assert sha(Path(p))==h,p
    save(home/'formal-complete.json',{'complete':True,'results':results,'all_trials_passed':all(r['completed']for r in results),'algorithm':verify()['commit']})


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['prepare','trial','calibrate','dependencies','formal','offline','planning-worker','planning'])
    parser.add_argument('--home',type=Path);parser.add_argument('--trial',type=Path);parser.add_argument('--out',type=Path);parser.add_argument('--build',type=Path)
    parser.add_argument('--task',choices=['mall','orders','zlt-client','zlt-user']);parser.add_argument('--mode');parser.add_argument('--name')
    parser.add_argument('--warmup',type=int,default=4);parser.add_argument('--measure',type=int,default=8)
    parser.add_argument('--projection-off',action='store_true');parser.add_argument('--no-sample',action='store_true')
    parser.add_argument('--query-scope');parser.add_argument('--allow-errors',action='store_true');args=parser.parse_args()
    if args.stage=='offline'and args.home is None:
        home=args.build.resolve().parent;trial_path=args.out.resolve();out=trial_path/'offline-single-pass'
        offline_worker(home,trial_path,out,'orders',args.mode)
        summary=load(out/'summary.json');summary['process_cpu_seconds']=time.process_time();save(out/'summary.json',summary)
        s=load(out/'offline.json');s['process_cpu_seconds']=summary['process_cpu_seconds'];save(trial_path/'offline.json',s)
    elif args.stage=='offline':offline_worker(args.home.resolve(),args.trial.resolve(),args.out.resolve(),args.task,args.mode)
    elif args.stage=='prepare':prepare(args.home.resolve())
    elif args.stage=='formal':formal(args.home.resolve())
    elif args.stage=='calibrate':calibrate(args.home.resolve())
    elif args.stage=='dependencies':dependencies(args.home.resolve())
    elif args.stage=='trial':trial(args.home.resolve(),args.name,args.task,args.mode,args.warmup,args.measure,args.projection_off,not args.no_sample)
    elif args.stage=='planning-worker':planning_worker(args.home.resolve(),args.out.resolve(),args.task)
    else:planning(args.home.resolve())
