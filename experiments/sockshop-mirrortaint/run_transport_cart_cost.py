#!/usr/bin/env python3
"""Five-round Cart observation ablation, after complete capability acceptance.

All configurations use the same frozen collector, formats and required checks.
Vary optional proof direction and target response-field observation separately.
"""
import argparse,copy,json,random,subprocess,sys,time
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save,sha
from plan_capability_policy import choose,specialize_transport
import run_response_binding_revision as binding
import run_bound_query_cost as bound
from run_isolated_cost import install,JVM

ARMS={'original':('original',True,True),'full':('full',True,True),'scope':('selective',True,False),'fields':('selective',False,True),'combined':('selective',True,True)}


def check(root):
    c=load(root/'config.json')
    assert sha(root/'config.json')==load(root/'protocol-freeze.json')['config_sha256']
    assert sha(root/'templates.json')==c['templates_sha256']
    for p,h in c['sources'].items():assert sha(Path(p))==h,p
    for arm in ARMS:binding.verify_build(root/'builds'/arm)
    return c


def prepare(root,capability):
    root.mkdir(parents=True,exist_ok=False);(root/'logs').mkdir();(root/'builds').mkdir();base=capability/'frozen-base';q=bound.query('cart');p,policy=choose(load(base/'carts/model.json'),q);assert p['profile']=='execution-dependency'and p['source_evidence']
    for arm,(_,scope,fields)in ARMS.items():
        plan=copy.deepcopy(p);specialize_transport(plan,scope=scope,fields=fields);binding.query_build(root/'builds'/arm,base,q,plan)
    (root/'cart-build').symlink_to(root/'builds/combined',target_is_directory=True)
    sources=load(capability/'algorithm-freeze.json')['sources'];sources={**sources,**{str(HERE/n):sha(HERE/n)for n in ['run_transport_cart_cost.py','run_bound_query_cost.py','run_isolated_cost.py','run_sockshop_cost.py','run_frozen_capability_acceptance.py','audit_cost_request_records.py','measure_offline_memory.py','measure_isolated_planning.py','measure_static_planning.py']}}
    order=[];rng=random.Random(231023)
    for i in range(1,6):
        arms=list(ARMS);rng.shuffle(arms);order.extend({'name':f'round-{i:02d}-{j:02d}-{a}','arm':a,'mode':ARMS[a][0]}for j,a in enumerate(arms,1))
    config={'algorithm_commit':load(capability/'algorithm-freeze.json')['commit'],'capability':str(capability),'capability_gate':'capability-audit/audit.json must pass428/431 state preservation before any trial','query':q,'jvm':JVM,'warmup_seconds':30,'measurement_seconds':60,'rate':2,'concurrency':2,'sample_interval':2,'rounds':5,'arms':ARMS,'order':order,'seed':231023,'sources':sources,'source_evidence':True,'format_compression':False,'scope':'Cart only; all25 deployments new. No external baseline cost ranking. Paired deployment ratios, not pooled request independence.'}
    save(root/'templates.json',bound.templates('cart'));config.update(templates_sha256=sha(root/'templates.json'),experiment_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip())
    save(root/'config.json',config);save(root/'protocol-freeze.json',{'config_sha256':sha(root/'config.json'),'no_trials_yet':True});save(root/'run-status.json',{'status':'prepared','no_trials_yet':True})
    print({'prepared':str(root),'deployments':25},flush=True)


def gate(root):
    c=check(root);a=load(Path(c['capability'])/'capability-audit/audit.json');assert a['all_passed']and a['parent_431_state_preservation_passed'];return c


def calibrate(root):
    gate(root);install();out=root/'calibration';out.mkdir();results={}
    for arm in ('full','scope','fields','combined'):
        mode=ARMS[arm][0];d=out/arm;results[arm]=bound.trial_run(d,root/'builds'/arm,'cart',mode,load(root/'templates.json'),3,6,2,2,2)['offline']['summary']
    assert all(r['queries']==r['exact']and not r['unknown']for r in results.values());save(root/'calibration-audit.json',{'all_passed':True,'arms':results,'not_formal_cost_samples':True})


def run(root):
    c=gate(root);assert load(root/'calibration-audit.json')['all_passed'];install();home=root/'deployments';home.mkdir();save(root/'run-status.json',{'status':'running'});bound.cost.environment(root)
    try:
        for job in c['order']:
            check(root);d=home/job['name'];build=root/'builds'/job['arm'];save(root/'logs'/(job['name']+'-start.json'),{**job,'plan_sha256':sha(build/'carts/plan.json')})
            bound.trial_run(d,build,'cart',job['mode'],load(root/'templates.json'),c['warmup_seconds'],c['measurement_seconds'],c['rate'],c['concurrency'],c['sample_interval'])
            save(d/'arm-configuration.json',{**job,'build':str(build),'plan_sha256':sha(build/'carts/plan.json')});done=sum((home/j['name']/'metrics.json').exists()for j in c['order']);save(root/'progress.json',{'completed':done,'total':len(c['order']),'last':job})
        save(root/'run-status.json',{'status':'passed'})
    except BaseException as e:save(root/'run-status.json',{'status':'failed','error':str(e)});raise


def memory(root):
    c=gate(root);assert load(root/'run-status.json')['status']=='passed';out=root/'offline-memory-replays';out.mkdir();results={};unchanged={}
    for job in c['order']:
        if job['mode']=='original':continue
        original=root/'deployments'/job['name'];dest=out/job['name'];(dest/'capture/carts').mkdir(parents=True)
        for rel in ('capture/carts/events.jsonl','capture/run.json'):(dest/rel).symlink_to(original/rel)
        for rel in ('capture/carts/events.jsonl','capture/run.json','metrics.json','offline.json','field-results.json'):unchanged[str(original/rel)]=sha(original/rel)
        cmd=[sys.executable,str(HERE/'measure_offline_memory.py'),'worker','--out',str(dest),'--build',str(root/'builds'/job['arm']),'--kind','cart'];save(dest/'command.json',cmd)
        with (dest/'worker.log').open('w')as log:subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=600)
        a=load(original/'offline.json');b=load(dest/'offline.json');assert a['summary']==b['summary']and a['populations']==b['populations'];results[job['name']]=load(dest/'memory.json');save(out/'progress.json',{'completed':len(results),'total':20})
    assert all(sha(Path(p))==h for p,h in unchanged.items());save(root/'offline-memory-audit.json',{'all_passed':True,'originals_unchanged':True,'guarded_original_sha256':unchanged,'measurements':results,'scope':'20 fresh-exec same-evidence VmHWM replays after online completion; retain original wall/CPU.'})


def planning(root):
    import os
    import measure_static_planning as meters
    gate(root);out=root/'static-planning';out.mkdir();cpu=min(os.sched_getaffinity(0));results=[]
    for i in range(1,6):
        d=out/f'round-{i:02d}';d.mkdir();cmd=['taskset','-c',str(cpu),sys.executable,str(HERE/'measure_isolated_planning.py'),'worker','--root',str(root),'--out',str(d),'--kind','cart'];peak=0;start=time.monotonic()
        with (d/'worker.log').open('w')as log:
            p=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT)
            while p.poll()is None:peak=max(peak,meters.tree_rss(p.pid));time.sleep(.015)
        assert p.returncode==0;v=load(d/'worker.json');v.update(subprocess_wall_seconds=time.monotonic()-start,process_tree_sampled_peak_rss_bytes=peak);results.append(v)
    save(out/'results.json',{'all_passed':True,'cpu':cpu,'cache_flushed':False,'sampled_RSS_includes_shared_pages_repeated':True,'measurements':results})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--stage',choices=('prepare','calibrate','run','memory','planning'),required=True);p.add_argument('--capability',type=Path);a=p.parse_args();r=a.root.resolve()
    if a.stage=='prepare':prepare(r,a.capability.resolve())
    else:{'calibrate':calibrate,'run':run,'memory':memory,'planning':planning}[a.stage](r)
