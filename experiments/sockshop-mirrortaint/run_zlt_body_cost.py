"""Two preselected tasks, one semantic candidate; experiment drivers only.

Calibration and timing never modify the candidate or choose a different plan.
The Orders task uses the existing service-plan entry point, as in its original
common-task protocol. Mall uses the unified query route and guarded body cut.
"""
import argparse,copy,json,os,random,resource,subprocess,sys,time
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save,sha

FINAL=ROOT/'artifacts/zlt-completion-slice-20261031/final-candidate-01'
BASE=FINAL/'historical/frozen-base'
MALL=FINAL/'mall'
COMMIT='7e4ad0b900a64871259a5fac008968128cc5ec28'
JVM='-Xms32m -Xmx256m -XX:ParallelGCThreads=1 -XX:CICompilerCount=2 -Djava.security.egd=file:/dev/urandom -Dspring.zipkin.enabled=false'


def verify():
    freeze=load(FINAL/'historical/algorithm-freeze.json')
    for name,digest in freeze['sources'].items():assert sha(Path(name))==digest,name
    assert sha(BASE/'distributed-observer.jar')==load(FINAL/'final-protocol-before-business.json')['agent_sha256']
    return freeze


def prepare(home):
    from plan_service_observations import plan_service
    from plan_distributed_fields import augment
    from plan_date_projection import attach_date_projection
    from run_response_binding_revision import query_build,verify_build
    import mirrortaint_instances as mt
    home.mkdir(parents=True,exist_ok=False);freeze=verify()
    old=load(ROOT/'artifacts/desktop-portable-build/orders/plan.json')
    q={'role':'orders','entry':old['entry'],'target':old['target'],'path':'/total'}
    model=load(BASE/'orders/model.json');plan=attach_date_projection(augment(model,plan_service(model,q['entry'],q['target'])),model)
    assert plan['profile']=='mapped-reduction'
    query_build(home/'orders-build',BASE,q,plan);verify_build(home/'orders-build')
    save(home/'orders-query.json',q)
    mt.build(home/'orders-mt-adapter',ROOT/'artifacts/external-tools/mirrortaint/mirrorTaint.jar',home/'orders-build')
    jobs=[];rng=random.Random(31102643)
    for repeat in range(1,6):
        for task in ('orders','mall'):
            modes=['original','full','selective','mirrortaint'];rng.shuffle(modes)
            jobs.extend({'round':repeat,'task':task,'mode':mode}for mode in modes)
    protocol={'algorithm':COMMIT,'reference':'c1a4e5c','agent_sha256':sha(BASE/'distributed-observer.jar'),
        'core_sources':freeze['sources'],'tasks':{'orders':{'query':q,'profile':plan['profile'],
        'source':'Actual Carts response/write quantity and unitPrice fields, original fixed task; not DB history',
        'planner':'Existing plan_service then augment; selected before any calibration or timed result, not legacy saved plan bytes'},
        'mall':{'path':'/data/expiresIn','source':'Actual AuthService.getAccessToken call return field, unchanged boundary',
        'plan_sha256':sha(MALL/'planning-first/mall-swarm-3/002-plan.json')}},
        'jobs':jobs,'warmup_seconds':30,'measure_seconds':60,'rate':2,'concurrency':2,'sampler_seconds':2,
        'JVM':JVM,'business_limits':'1CPU/768MiB each JVM; databases and queue limits fixed within task',
        'gate':'ZLT15, Mall98, Account40 and historical answers/states/signatures before any timed workload',
        'same_dependencies_within_task':True,'MT':'Fixed native propagation, separately sealed adapters; only formally included after independent task and dependency calibration',
        'body_off':'One short selective control, same Agent/plan, real runtime flag; not a formal 5-round arm',
        'locality_off':'Full capture, precision ablation only; not a same-answer cheap configuration',
        'offline':'One normal pass, required internal certificate checks retained; fresh-exec, raw-fact oracle index, scoring/export separated',
        'no_timed_work_during_development':True,'drivers':{str(Path(__file__).relative_to(ROOT)):sha(Path(__file__))}}
    save(home/'protocol-before-calibration.json',protocol)
    save(home/'plan-hashes.json',{str(p.relative_to(home/'orders-build')):sha(p)for p in(home/'orders-build').glob('*/plan.json')})
    print('Prepared two fixed tasks',COMMIT,flush=True)


def install_mall():
    import run_frozen_locality_cost as runner
    runner.BASE=BASE;runner.MALL=MALL;runner.COMMIT=COMMIT;runner.verify=verify
    return runner


def install_orders(home=None):
    import run_sockshop_cost as cost
    import calibrate_mirrortaint_total as calibration
    if getattr(calibration,'_zlt_cost_home',None) is not None:
        assert calibration._zlt_cost_home==home
        return cost,calibration
    calibration._zlt_cost_home=home
    cost.JVM=calibration.JVM=JVM
    # Keep the same original JAR/image within all arms. Memory limits for data
    # services are fixed here rather than altered after seeing measurements.
    original=calibration.spec_for
    def spec(*args,**kwargs):
        cfg=original(*args,**kwargs)
        for name,s in cfg['services'].items():
            if name.endswith('-db'):s['mem_limit']='384m'
            if name=='rabbitmq':s['mem_limit']='384m'
        return cfg
    calibration.spec_for=spec
    if home is not None:
        original_common=calibration.common_spec
        def common(mode,dest,build,bundle,*args,**kwargs):
            cfg=original_common(mode,dest,build,bundle,*args,**kwargs)
            if mode=='mirrortaint':
                for role in ('orders','carts'):
                    s=cfg['services'][role]
                    s['volumes'].append(str(home/'orders-library-witness/library-witness.jar')+':/tf2/library-witness.jar:ro')
                    s['environment']['JAVA_OPTS']='-javaagent:/tf2/library-witness.jar -Dnative.library.events=/tf2/capture/native-library.jsonl '+s['environment']['JAVA_OPTS']
            return cfg
        calibration.common_spec=common
    return cost,calibration


def mall_offline(home,trial,out,mode):
    if mode=='mirrortaint':
        from run_mirror_capability_probe import read_events,native_answer
        import external_transfer_oracle as oracle
        out.mkdir(parents=True,exist_ok=False);start=time.perf_counter();cpu=time.process_time();times={};view=out/'view';view.mkdir();(view/'role').symlink_to((trial/'capture').resolve(),target_is_directory=True)
        t=time.perf_counter();rows=read_events(view,'role');times['decode_complete_capture']=time.perf_counter()-t
        cases=load(trial/'warmup.json')['requests']+load(trial/'measure.json')['requests'];t=time.perf_counter()
        answers=[(c,native_answer(rows,c['message'],'/data/expiresIn'))for c in cases];times['native_tag_decode']=time.perf_counter()-t
        t=time.perf_counter();save(out/'answers.json',[{'case':c['case'],'answer':a}for c,a in answers]);times['export']=time.perf_counter()-t
        t=time.perf_counter();scored=[]
        for c,a in answers:
            roots=[r for r in rows if r['kind']=='target'and r['context'].get('message')==c['message']];assert len(roots)==1
            want={tuple(v)for v in oracle.native_expected(rows,roots[0]['root'],{'kind':'rpc-field','api':'mall-swarm-3','rpc_owner':'AuthService'},'/data/expiresIn')}
            got={tuple(v)for v in a.get('sources',[])}
            assert c['business_passed']and a['state']=='known'and want and want==got
            scored.append({'case':c['case'],'known':True,'exact':True,'expected':sorted(want,key=str),'actual':sorted(got,key=str)})
        times['independent_score']=time.perf_counter()-t;save(out/'scores.json',scored)
        save(out/'summary.json',{'targets':len(scored),'correct':len(scored),'positive':len(scored),'phases_seconds':times,
            'core_seconds':times['native_tag_decode'],'wall_seconds':time.perf_counter()-start,'cpu_seconds':time.process_time()-cpu,
            'VmHWM_KiB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'raw_fact_oracle_only':True})
        return
    from infer_distributed_fields import Reconstruction
    import external_transfer_oracle as oracle
    out.mkdir(parents=True,exist_ok=False);start=time.perf_counter();cpu=time.process_time();times={};t=start
    rows=oracle.raw(trial/'capture/events.jsonl');oracle.require_complete_raw_capture(rows);times['decode_complete_capture']=time.perf_counter()-t
    b=out/'build/mall-admin';b.mkdir(parents=True);(b/'plan.json').write_bytes((MALL/'planning-first/mall-swarm-3/002-plan.json').read_bytes())
    cap=out/'capture/mall-admin';cap.mkdir(parents=True);(cap/'events.jsonl').symlink_to((trial/'capture/events.jsonl').resolve())
    t=time.perf_counter();g=Reconstruction(out/'build',out/'capture',['mall-admin'],decoded_rows={'mall-admin':rows});times['reconstruction_with_required_certificates']=time.perf_counter()-t
    cases=load(trial/'warmup.json')['requests']+load(trial/'measure.json')['requests'];answers=[];t=time.perf_counter()
    for c in cases:answers.append((c,g.query(c['message'],'/data/expiresIn','mall-admin',boundary=[{'kind':'binding-source'},{'kind':'argument'},{'kind':'http-json','direction':'response','phase':'read'}])))
    times['query']=time.perf_counter()-t;t=time.perf_counter();save(out/'answers.json',[{'case':c['case'],'answer':a}for c,a in answers]);times['export']=time.perf_counter()-t
    t=time.perf_counter();index=oracle.RawFactIndex(rows);scored=[]
    for c,a in answers:
        returns=index.returns.get(c['message'],[]);assert len(returns)==1
        want={tuple(v)for v in oracle.tf_expected(rows,returns[0],{'kind':'rpc-field','api':'mall-swarm-3','rpc_owner':'AuthService'},'/data/expiresIn',raw_index=index)}
        got={(s.get('callee'),s.get('root_frame'),s['seq'],s.get('path'),s['owner'],s['field'],s['version'])for s in a['sources']}
        assert want and a['known'] and got==want and c['business_passed']
        assert a['target']['observed']['value']==c['response']['data']['expiresIn']
        scored.append({'case':c['case'],'known':True,'exact':True,'expected':sorted(want,key=str),'actual':sorted(got,key=str)})
    times['independent_score_raw_index']=time.perf_counter()-t;save(out/'scores.json',scored)
    save(out/'summary.json',{'targets':len(scored),'correct':len(scored),'positive':len(scored),'phases_seconds':times,
        'core_seconds':times['reconstruction_with_required_certificates']+times['query'],
        'wall_seconds':time.perf_counter()-start,'cpu_seconds':time.process_time()-cpu,'VmHWM_KiB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        'raw_fact_oracle_only':True,'duplicate_external_certificate_validation':False})


def offline_worker(home,trial,out,task,mode):
    verify()
    if task=='mall':return mall_offline(home,trial,out,mode)
    import mirrortaint_instances as mt
    out.mkdir(parents=True,exist_ok=False)
    report=mt.evaluate(trial,home/'orders-build','mirrortaint'if mode=='mirrortaint'else'tracefusion',result_out=out)
    s=load(out/'offline.json');assert report['summary']['queries']==report['summary']['exact']and not report['summary']['unknown']
    phases=s['phases_seconds'];save(out/'summary.json',{'targets':report['summary']['queries'],'correct':report['summary']['exact'],
        'positive':sum(bool(q['expected_source_keys'])for q in report['queries']),
        'core_seconds':phases['graph_reconstruction']+phases['query_or_native_origin_restore'],'phases_seconds':phases,
        'VmHWM_KiB':s['peak_rss_bytes']/1024})


def fresh(home,trial,task,mode,out=None):
    out=out or trial/'offline-single-pass';before=resource.getrusage(resource.RUSAGE_CHILDREN);start=time.perf_counter()
    with(out.parent/(out.name+'.log')).open('w')as f:
        subprocess.run([sys.executable,__file__,'offline','--home',str(home),'--trial',str(trial),'--out',str(out),'--task',task,'--mode',mode],stdout=f,stderr=subprocess.STDOUT,check=True)
    after=resource.getrusage(resource.RUSAGE_CHILDREN);s=load(out/'summary.json');s.update(process_wall_seconds=time.perf_counter()-start,
        process_cpu_seconds=after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime)
    save(out/'process.json',s);return s


def trial(home,name,task,mode,warm,measure,body_off=False):
    verify()
    if task=='mall':
        runner=install_mall()
        old_spec=runner.spec
        if body_off:
            def spec(out,policy):
                cfg=old_spec(out,policy);cfg['services']['admin']['command'].insert(1,'-Dservice.body.observation=false');return cfg
            runner.spec=spec
        try:result=runner.trial(home,name,mode,warm,measure)
        finally:runner.spec=old_spec
        assert result['state']=='captured'and result['requests']==result['business_passed']and result['cleanup_returncode']==0
        if mode!='original':fresh(home,home/name,task,mode)
    else:
        cost,_=install_orders(home)
        args=argparse.Namespace(observation_policy=mode if mode in('full','selective')else'selective',query_scope='total',
            mt_bundle=home/'orders-mt-adapter',cpus=1,memory='768m',correctness=ROOT/'artifacts/desktop-portable-acceptance',
            warmup=warm,seconds=measure,rate=2,concurrency=2,sample_interval=2,allow_errors=False,offline_timeout=300,
            offline_program=Path(__file__).resolve())
        cost.trial_run(args,home/name,'tracefusion'if mode in('full','selective')else mode,home/'orders-build')
    verify()


def calibrate(home):
    verify();_,runner=install_orders(home)
    for mode in('full','selective','mirrortaint'):
        args=argparse.Namespace(out=home/('cal-orders-'+mode),build=home/'orders-build',bundle=home/'orders-mt-adapter',
            correctness=ROOT/'artifacts/desktop-portable-acceptance',mode='mirrortaint'if mode=='mirrortaint'else'tracefusion',observation_policy=mode if mode!='mirrortaint'else'selective')
        if (args.out/'calibration.json').exists():assert load(args.out/'calibration.json')['passed']
        else:runner.run(args)
        assert load(args.out/'calibration.json')['passed']
    import run_sockshop_cost as cost
    class BusinessOnlySampler:
        """No resource cost measurements in short correctness calibration."""
        def __init__(self,containers,interval,path,**kwargs):self.path=path
        def __enter__(self):
            save(self.path.parent/'resource-calibration-scope.json',{'resource_sampling':False,'scope':'Business/source/target correctness only; incidental request timestamps not performance results'})
            return self
        def __exit__(self,*args):pass
        def summary(self,*args):return {}
    original_sampler=cost.Sampler;cost.Sampler=BusinessOnlySampler
    try:
        prior=home/'cal-orders-original/sockshop/run.json'
        if prior.exists():
            r=load(prior);assert r['status']=='business-passed'and len(r['cases'])==24 and all(c['business_passed']for c in r['cases'])
            save(prior.parent.parent/'business-calibration-receipt.json',{'business_requests':24,'all_passed':True,'raw_run_sha256':sha(prior),
                'sampling_failure_preserved':True,'note':'Existing requests completed before the short resource-window error. Accept business facts only, do not certify missing resource measurements or overwrite failure.'})
        else:trial(home,'cal-orders-original','orders','original',4,8)
    # Mall original/TF/MT use identical input, source return boundary and wire
    # target; scoring always derives physical coordinates in that same JVM.
        for mode in('original','full','selective','mirrortaint'):
            trial(home,'cal-mall-'+mode,'mall',mode,4,8)
        trial(home,'cal-mall-selective-without-body-cut','mall','selective',4,8,body_off=True)
    finally:cost.Sampler=original_sampler
    save(home/'calibration-business-and-source.json',{'passed':True,'Orders':'24-task original common calibration per instrumented arm including parallel trace/span protection',
        'Mall':'24 requests per arm; source coordinates and target bound in own JVM; additional selective no-cut control',
        'dependency_calibration':'Required separate receipt before formal run; export success alone is not dependency equivalence'})


def formal(home):
    protocol=load(home/'protocol-before-calibration.json');assert load(home/'calibration-business-and-source.json')['passed']
    assert load(home/'dependency-calibration.json')['passed']
    assert load(home/'capability-gates.json')['passed']
    save(home/'environment-before-formal.json',{'docker_ps':subprocess.check_output(['docker','ps','--format','{{.Names}}'],text=True).splitlines(),
        'uname':subprocess.check_output(['uname','-a'],text=True).strip(),'cpuinfo':Path('/proc/cpuinfo').read_text(),'affinity':sorted(os.sched_getaffinity(0))})
    for job in protocol['jobs']:
        name='round-%02d-%s-%s'%(job['round'],job['task'],job['mode'])
        assert not(home/name).exists(),'Refuse to overwrite '+name
        print('START',name,flush=True);trial(home,name,job['task'],job['mode'],30,60)
        save(home/'formal-progress.json',{'latest':job,'latest_completed':name});print('COMPLETE',name,flush=True)
    save(home/'formal-complete.json',{'complete':True,'deployments':40,'algorithm':COMMIT});verify()


def planning_worker(home,out,task):
    out.mkdir(parents=True,exist_ok=False);start=time.perf_counter();cpu=time.process_time()
    if task=='mall':
        from plan_capability_policy import choose
        p,_=choose(load(MALL/'metadata/mall-admin/model.json'),load(MALL/'planning-first/mall-swarm-3/002.json')['query'],deployment=load(MALL/'deployment-environment.json'))
        expected=load(MALL/'planning-first/mall-swarm-3/002-plan.json')
    else:
        from plan_service_observations import plan_service
        from plan_distributed_fields import augment
        from plan_date_projection import attach_date_projection
        q=load(home/'orders-query.json');model=load(BASE/'orders/model.json');p=attach_date_projection(augment(model,plan_service(model,q['entry'],q['target'])),model)
        p['collection_elements']=True;expected=load(home/'orders-build/orders/plan.json')
    elapsed=time.perf_counter()-start;used=time.process_time()-cpu;assert p==expected
    save(out/'result.json',{'task':task,'plan_equals_deployment':True,'wall_seconds':elapsed,'cpu_seconds':used,'VmHWM_KiB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss})


def planning(home):
    out=home/'static-planning';out.mkdir(exist_ok=False);cpu=min(os.sched_getaffinity(0));rows=[]
    for task in('orders','mall'):
        for repeat in range(5):
            dest=out/('%s-%02d'%(task,repeat));before=resource.getrusage(resource.RUSAGE_CHILDREN);start=time.perf_counter()
            with(out/(dest.name+'.log')).open('w')as f:
                subprocess.run(['taskset','-c',str(cpu),sys.executable,__file__,'planning-worker','--home',str(home),'--out',str(dest),'--task',task],stdout=f,stderr=subprocess.STDOUT,check=True)
            after=resource.getrusage(resource.RUSAGE_CHILDREN);s=load(dest/'result.json');s.update(repeat=repeat,process_wall_seconds=time.perf_counter()-start,process_cpu_seconds=after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime);rows.append(s)
    save(out/'summary.json',{'logical_cpu':cpu,'fresh_exec':True,'OS_cache_not_cleared':True,'scope':'Prebuilt model load and planning, excluding JAR/model extraction, JDK probe, Agent compilation and service startup','rows':rows})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['prepare','calibrate','formal','offline','planning','planning-worker']);p.add_argument('--home',type=Path);p.add_argument('--out',type=Path);p.add_argument('--trial',type=Path);p.add_argument('--build',type=Path);p.add_argument('--task',choices=['orders','mall']);p.add_argument('--mode');p.add_argument('--query-scope');p.add_argument('--allow-errors',action='store_true');a=p.parse_args()
    # The existing Orders timed driver invokes this child with its documented
    # CLI. Its --out means trial directory; build is the sealed orders-build.
    if a.stage=='offline'and a.home is None:
        home=a.build.resolve().parent;trialpath=a.out.resolve();out=trialpath/'offline-single-pass'
        offline_worker(home,trialpath,out,'orders',a.mode)
        summary=load(out/'summary.json');summary['process_cpu_seconds']=time.process_time();save(out/'summary.json',summary)
        s=load(out/'offline.json');s['process_cpu_seconds']=summary['process_cpu_seconds'];save(trialpath/'offline.json',s)
    elif a.stage=='offline':offline_worker(a.home.resolve(),a.trial.resolve(),a.out.resolve(),a.task,a.mode)
    elif a.stage=='planning-worker':planning_worker(a.home.resolve(),a.out.resolve(),a.task)
    else:globals()[a.stage](a.home.resolve())
