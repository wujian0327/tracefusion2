#!/usr/bin/env python3
"""New live Cart closure ablation and separate cross-service price costs.

The shared indexed reconstructor and event format are identical in all arms.
Never resumes or replaces a failed formal deployment.
"""
import argparse,copy,json,random,subprocess,sys,time,os
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save,sha
import run_bound_query_cost as bound
import run_train_cost as price
import run_response_binding_revision as binding
import run_train_multisource as calibration
from run_isolated_cost import install,JVM,OLD_COST
from plan_capability_policy import choose
import build_distributed_plans as builder

ARMS={'original':('original',True),'full':('full',True),'selective_without_closure':('selective',False),'selective':('selective',True)}


def check(root,gate=True):
    c=load(root/'config.json');assert sha(root/'config.json')==load(root/'protocol-freeze.json')['config_sha256']
    assert sha(root/'templates.json')==c['templates_sha256']
    assert sha(root/'price-inputs.json')==c['price_inputs_sha256']
    assert sha(ROOT/'artifacts/desktop-inputs/images-lock.json')==c['image_lock_sha256']
    for p,h in c['sources'].items():assert sha(Path(p))==h,p
    for arm in ARMS:binding.verify_build(root/'builds'/arm)
    binding.verify_build(root/'price-build')
    if gate:
        r=Path(c['capability']);a=load(r/'capability-audit/audit.json');b=load(r/'regression29-audit/audit.json');assert a['all_passed']and a['parent_431_state_preservation_passed']and b['all_passed']
    return c


def prepare(root,capability):
    root.mkdir(parents=True,exist_ok=False);(root/'logs').mkdir();(root/'builds').mkdir();base=capability/'frozen-base';q=bound.query('cart');p=choose(load(base/'carts/model.json'),q)[0]
    for arm,(_,enabled)in ARMS.items():
        plan=copy.deepcopy(p);plan['execution_observation_closure']['enabled']=enabled;binding.query_build(root/'builds'/arm,base,q,plan)
    (root/'cart-build').symlink_to(root/'builds/selective',target_is_directory=True)
    previous=load(OLD_COST/'price-build/build.json');builder.build(root/'price-build',{r:{**v['query_config'],'source_evidence':True}for r,v in previous['inputs'].items()})
    sources=load(capability/'algorithm-freeze.json')['sources'];names=['run_execution_closure_cost.py','run_bound_query_cost.py','run_train_cost.py','run_sockshop_cost.py','run_isolated_cost.py','run_response_binding_revision.py','run_train_multisource.py','measure_offline_memory.py','measure_isolated_planning.py','measure_static_planning.py','audit_execution_closure_cost.py','audit_cost_request_records.py']
    names+=['run_frozen_capability_acceptance.py','run_sockshop_model_revision.py','run_execution_kernel_pilot.py','audit_train_multisource.py','audit_cost_population.py','audit_baseline_capabilities.py','normalize_orders_origins.py','run_distributed_paths.py','audit_jackson_isolation.py','audit_application_call_revision.py']
    sources={**sources,**{str(HERE/n):sha(HERE/n)for n in names},str(ROOT/'scripts/sockshop.py'):sha(ROOT/'scripts/sockshop.py')};order=[];rng=random.Random(231026)
    for i in range(1,6):
        arms=list(ARMS);rng.shuffle(arms);order.extend({'name':f'round-{i:02d}-{j:02d}-{a}','arm':a,'mode':ARMS[a][0]}for j,a in enumerate(arms,1))
    save(root/'templates.json',bound.templates('cart'))
    save(root/'price-inputs.json',load(Path(load(OLD_COST/'cost-price/config.json')['inputs'])))
    c={'algorithm_commit':load(capability/'algorithm-freeze.json')['commit'],'capability':str(capability),'sources':sources,'jvm':JVM,'rounds':5,'warmup':30,'seconds':60,'rate':2,'concurrency':2,'sample_interval':2,'seed':231026,'cart_order':order,'cart_arms':ARMS,'source_evidence':True,'format_compression':False,'shared_alias_index':True,'scope':'Cart original/full/selective without closure/selective with closure:20 independent deployments. Cross-service collection price path:15 separate deployments; not generic-kernel slicing evidence. All online deployments sequential after 62+29 capability gates. No maximum throughput or external baseline ranking.','templates_sha256':sha(root/'templates.json')}
    c.update(price_inputs_sha256=sha(root/'price-inputs.json'),image_lock_sha256=sha(ROOT/'artifacts/desktop-inputs/images-lock.json'))
    save(root/'config.json',c);save(root/'protocol-freeze.json',{'config_sha256':sha(root/'config.json'),'formal_trials_started':False});save(root/'run-status.json',{'status':'prepared'});print({'prepared':True,'formal_deployments':35},flush=True)


def calibrate(root):
    check(root);install();out=root/'calibration';out.mkdir();results={}
    for arm in ARMS:
        if arm=='original':continue
        results[arm]=bound.trial_run(out/arm,root/'builds'/arm,'cart',ARMS[arm][0],load(root/'templates.json'),3,6,2,2,2)['offline']['summary']
    inputs=root/'price-inputs.json';p=out/'price';calibration.freeze(p,root/'price-build',inputs,161019)
    for mode in('full','selective'):calibration.capture(p,root/'price-build',inputs,mode);calibration.evaluate(p,root/'price-build',mode)
    from audit_train_multisource import audit
    audit(p,root/'price-build');results['price']=load(p/'independent-audit.json');save(root/'calibration-audit.json',{'all_passed':True,'results':results})
    args=argparse.Namespace(out=root/'cost-price',build=root/'price-build',inputs=inputs,calibration=p,rounds=5,warmup=30.,seconds=60.,rate=2.,concurrency=2,sample_interval=2.,seed=231027,offline_timeout=600.)
    price.freeze(args,args.out)


def run(root):
    c=check(root);assert load(root/'calibration-audit.json')['all_passed'];install();home=root/'cart-deployments';home.mkdir();save(root/'run-status.json',{'status':'running'});bound.cost.environment(root)
    try:
        for job in c['cart_order']:
            check(root);save(root/'logs'/('cart-'+job['name']+'-start.json'),job);d=home/job['name'];bound.trial_run(d,root/'builds'/job['arm'],'cart',job['mode'],load(root/'templates.json'),c['warmup'],c['seconds'],c['rate'],c['concurrency'],c['sample_interval']);save(d/'arm-configuration.json',job);save(root/'progress.json',{'cart_completed':sum((home/j['name']/'metrics.json').exists()for j in c['cart_order']),'cart_total':20,'last':job})
        ph=root/'cost-price';pc=load(ph/'config.json');args=argparse.Namespace(**{k:Path(v)if k in('out','build','inputs','calibration')else v for k,v in pc.items()});save(ph/'run-status.json',{'status':'running'})
        for name,mode in pc['order']:
            check(root);price.trial_run(args,ph/name,mode,ph);save(root/'progress.json',{'cart_completed':20,'price_completed':sum((ph/n/'metrics.json').exists()for n,_ in pc['order']),'price_total':15,'last':name})
        save(ph/'run-status.json',{'status':'passed'});save(root/'run-status.json',{'status':'passed'})
    except BaseException as error:save(root/'run-status.json',{'status':'failed','error':str(error)});raise


def memory(root):
    c=check(root);assert load(root/'run-status.json')['status']=='passed';out=root/'offline-memory-replays';out.mkdir();jobs=[]
    jobs.extend(('cart',j['name'],j['mode'],root/'builds'/j['arm'],root/'cart-deployments'/j['name'])for j in c['cart_order']if j['mode']!='original')
    jobs.extend(('price',name,mode,root/'price-build',root/'cost-price'/name)for name,mode in load(root/'cost-price/config.json')['order']if mode!='original');random.Random(231028).shuffle(jobs);records={};guarded={}
    for kind,name,mode,build,original in jobs:
        dest=out/kind/name;dest.mkdir(parents=True);app='trainticket'if kind=='price'else'capture';cap=dest/app;cap.mkdir();roles=list(bound.old.ROLES)if kind=='price'else['carts']
        for role in roles:(cap/role).mkdir();(cap/role/'events.jsonl').symlink_to(original/app/role/'events.jsonl')
        (cap/'run.json').symlink_to(original/app/'run.json')
        for p in [original/'metrics.json',original/'offline.json',original/app/'run.json',*[original/app/r/'events.jsonl'for r in roles]]:guarded[str(p)]=sha(p)
        cmd=[sys.executable,str(HERE/'measure_offline_memory.py'),'worker','--out',str(dest),'--build',str(build),'--kind',kind]
        save(dest/'command.json',cmd)
        with(dest/'worker.log').open('w')as log:subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=600)
        before=load(original/'offline.json');after=load(dest/'offline.json');assert before['summary']==after['summary']and before['populations']==after['populations'];records[kind+'/'+name]=load(dest/'memory.json');save(out/'progress.json',{'completed':len(records),'total':25})
    assert all(sha(Path(p))==h for p,h in guarded.items());save(root/'offline-memory-audit.json',{'all_passed':True,'originals_unchanged':True,'guarded_sha256':guarded,'measurements':records})


def planning(root):
    import measure_static_planning as meters
    check(root);out=root/'static-planning';out.mkdir();cpu=min(os.sched_getaffinity(0));records=[]
    for kind in('cart','price'):
        for repeat in range(1,6):
            d=out/(kind+f'-{repeat:02d}');d.mkdir();cmd=['taskset','-c',str(cpu),sys.executable,str(HERE/'measure_isolated_planning.py'),'worker','--root',str(root),'--out',str(d),'--kind',kind];peak=0;start=time.monotonic()
            with(d/'worker.log').open('w')as log:
                process=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,env={**os.environ,'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1'})
                while process.poll()is None:peak=max(peak,meters.tree_rss(process.pid));time.sleep(.015)
            assert process.returncode==0;record=load(d/'worker.json');record.update(kind=kind,repeat=repeat,subprocess_wall_seconds=time.monotonic()-start,process_tree_sampled_peak_rss_bytes=peak);records.append(record)
    save(out/'results.json',{'all_passed':True,'cpu':cpu,'OS_cache_flushed':False,'measurements':records})


def scale(root):
    check(root);install();out=root/'input-scale';out.mkdir();records=[]
    # Records/offline scale only: short captures are not latency estimates.
    for count in(1,4,16):
        templates=[{'case':'scale','customer_id':f'{500+count:024x}','items':[{'itemId':f'scale-item-{i}','quantity':1,'unitPrice':2.5}for i in range(count)]}]
        save(out/('inputs-'+str(count)+'.json'),templates)
        for arm in('full','selective_without_closure','selective'):
            d=out/(f'n-{count:02d}-'+arm);m=bound.trial_run(d,root/'builds'/arm,'cart',ARMS[arm][0],templates,3,6,2,2,2);records.append({'items':count,'arm':arm,'directory':str(d),'summary':m['offline']['summary']})
    save(out/'results.json',{'all_passed':True,'not_formal_latency_samples':True,'results':records})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',required=True,type=Path);p.add_argument('--capability',type=Path);p.add_argument('--stage',choices=('prepare','calibrate','run','memory','planning','scale'),required=True);a=p.parse_args();root=a.root.resolve()
    if a.stage=='prepare':prepare(root,a.capability.resolve())
    else:{'calibrate':calibrate,'run':run,'memory':memory,'planning':planning,'scale':scale}[a.stage](root)
