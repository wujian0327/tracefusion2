#!/usr/bin/env python3
"""Fresh all-62 acceptance with fixed JVM worker limits and no receipt replacement."""
import argparse,copy,os,secrets,shutil,signal,subprocess,sys,time
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save,sha
import run_frozen_capability_acceptance as driver

PARENT=ROOT/'artifacts/orders-availability-20261021'
FLAGS=' -XX:ParallelGCThreads=1 -XX:CICompilerCount=2'
def qualified_options(options):
    # The legacy pair uses spec_for's cost preset (64m/G1), whereas the common
    # observed() helper uses 32m/default GC. Normalize every observed service to
    # the declared acceptance preset; this does not alter native backends.
    tokens=[t for t in options.split()if not t.startswith(('-Xms','-Xmx','-XX:ParallelGCThreads=','-XX:CICompilerCount='))and t!='-XX:+UseG1GC']
    return '-Xms32m -Xmx256m '+' '.join(tokens)+FLAGS

def install(root):
    driver.HOME=root
    observed=driver.old.observed;spec_for=driver.old.spec_for
    def configure(spec,name,role,cap,build):
        observed(spec,name,role,cap,build);spec['services'][name]['environment']['JAVA_OPTS']=qualified_options(spec['services'][name]['environment']['JAVA_OPTS'])
    def specs(*args,**kwargs):
        result=spec_for(*args,**kwargs)
        for config in result['services'].values():
            env=config.get('environment',{});opts=env.get('JAVA_OPTS','')
            if '-javaagent:'in opts:env['JAVA_OPTS']=qualified_options(opts)
        return result
    driver.old.observed=configure;driver.old.spec_for=specs
    driver.check()

def prepare(root):
    root.mkdir(parents=True,exist_ok=False);base=PARENT/'buffered-core';previous=driver.HOME
    freeze=load(previous/'algorithm-freeze.json');actual=load(base/'algorithm-freeze.json')
    freeze.update(commit=actual['algorithm_commit'],sources=actual['sources'],base_build=str(root/'frozen-base'),experiment_protocol_sha256=sha(HERE/'quota-capability-protocol-20261021.json'),experiment_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),runtime_policy={'ParallelGCThreads':1,'CICompilerCount':2,'applies_to':'Every observed target JVM, full and selective; native backends unchanged','gc_logging':False},pair_driver_sha256=sha(HERE/'run_cart_reread_baseline_pair.py'))
    (root/'frozen-base').symlink_to(base/'frozen-base',target_is_directory=True);(root/'source-snapshot').symlink_to(base/'source-snapshot',target_is_directory=True);shutil.copytree(base/'frozen-plans',root/'frozen-plans');freeze['planning_sha256']=sha(root/'frozen-plans/planning.json');save(root/'algorithm-freeze.json',freeze)
    (root/'drivers').mkdir();(root/'logs').mkdir()
    for name in ('run_quota_capability_acceptance.py','run_frozen_capability_acceptance.py','run_cart_reread_baseline_pair.py'):
        dest=root/'drivers'/('cart-pair-library-driver-at-launch.py'if name=='run_cart_reread_baseline_pair.py'else name);dest.write_bytes((HERE/name).read_bytes())
    for target,source in [('date-controls',PARENT/'semantic-controls/date'),('received-controls',PARENT/'semantic-controls/received-mutations'),('legacy-collection-controls',PARENT/'legacy-collection-controls')]:
        (root/target).symlink_to(source,target_is_directory=True)
    save(root/'protocol-before-business.json',load(HERE/'quota-capability-protocol-20261021.json'))

def worker(root,name,pair_destination=None):
    install(root);base=root/'frozen-base'
    if name=='orders':driver.orders(root/'all62-orders-serial',base)
    elif name=='cart':driver.carts(root/'all62-cart',base)
    elif name=='pair':
        import run_cart_reread_baseline_pair as pair
        destination=pair_destination or root/'cart-create-pair';query=next(q for q in driver.QUERIES if q['id']=='sockshop-carts-get-customerId');pair.plan_response=lambda *args,**kwargs:copy.deepcopy(driver.plan(query));pair.run(destination,base)
        save(destination/'launch-metadata.json',{'actual_customerId':'56e8f576709b70d0ace01fb0','driver_at_launch_sha256':sha(root/'drivers/cart-pair-library-driver-at-launch.py'),'original_declared_input_already_correct':True})
    else:
        roles,port={'reads':('station,train,price','18820'),'route':('route','18920'),'travel':('basic,ticketinfo','19020')}[name];os.environ.update(TF2_CAPABILITY_ROLES=roles,TF2_CAPABILITY_PORT=port);driver.train(root/('all62-'+name),base)

def run(root):
    jobs=[]
    # Orders remains isolated. An error is retained and does not select a repeat.
    worker(root,'orders')
    try:
        for name in ('reads','route','travel','cart','pair'):
            log=(root/'logs'/(name+'.log')).open('w');cmd=[sys.executable,str(Path(__file__).resolve()),'--root',str(root),'--worker',name];process=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);jobs.append((name,process,log));print({'started':name,'pid':process.pid},flush=True)
        while any(process.poll()is None for _,process,_ in jobs):save(root/'worker-status.json',{'workers':{name:p.poll()for name,p,_ in jobs}});time.sleep(5)
        codes={name:p.returncode for name,p,_ in jobs};save(root/'worker-status.json',{'complete':True,'workers':codes});assert not any(codes.values()),codes
    finally:
        for _,process,_ in jobs:
            if process.poll()is None:os.killpg(process.pid,signal.SIGINT)
        for _,process,log in jobs:
            if process.poll()is None:process.wait(timeout=180)
            log.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--prepare',action='store_true');p.add_argument('--worker',choices=('orders','reads','route','travel','cart','pair'));p.add_argument('--pair-destination',type=Path);a=p.parse_args();root=a.root.resolve()
    if a.prepare:prepare(root)
    elif a.worker:worker(root,a.worker,a.pair_destination.resolve()if a.pair_destination else None)
    else:run(root)
