#!/usr/bin/env python3
"""CPU-pinned fresh-process static planning; no business execution or Agent compile."""
import argparse,json,os,random,resource,subprocess,sys,time
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile
from run_planned_service import load,save,sha,HERE
from run_query_planner import JARS
from plan_response_binding import plan_response
from plan_distributed_fields import augment,copy_plan
from plan_service_observations import plan_service
from plan_collection_service import plan_collection
from run_bound_query_cost import query


def worker(out,base,kind):
    started=time.perf_counter();phase={};result={};roles=['carts'] if kind=='cart' else ['train'] if kind=='train' else list(load(base/'build.json')['inputs'])
    for role in roles:
        d=out/role;d.mkdir();app=d/'app';app.mkdir();jar=base/role/'original.jar';cfg=load(base/'build.json')['inputs'][role]['query_config'];t=time.perf_counter()
        with ZipFile(jar) as z:
            for n in z.namelist():
                if n.startswith('BOOT-INF/classes/') and n.endswith('.class'):
                    f=app/n[len('BOOT-INF/classes/'):];f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(z.read(n))
            missing={target.rsplit('.',1)[0].replace('.','/')+'.class' for target in cfg.get('targets',[]) if not (app/(target.rsplit('.',1)[0].replace('.','/')+'.class')).exists()}
            for n in z.namelist():
                if missing and n.startswith('BOOT-INF/lib/') and n.endswith('.jar'):
                    with ZipFile(BytesIO(z.read(n))) as lib:
                        for requested in list(missing):
                            if requested in lib.namelist():
                                f=app/requested;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(lib.read(requested));missing.remove(requested)
        extract=time.perf_counter()-t;t=time.perf_counter()
        cmd=['java','-cp',str(base/'tools')+':'+':'.join(map(str,JARS)),'QueryBytecodeModel',str(app),str(d/'model.json')]
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=90);(d/'model.log').write_text(p.stdout+p.stderr)
        if p.returncode:raise ValueError('Bytecode model failed')
        bytecode=time.perf_counter()-t;t=time.perf_counter();m=load(d/'model.json');decode=time.perf_counter()-t;t=time.perf_counter()
        if kind!='price':
            q=query(kind);plan=plan_response(m,q['entry'],q['target'],q['path'],read_forward_contracts=True)
        else:
            local=None
            if cfg.get('entry'):
                if cfg.get('profile')=='collection-computation':local=plan_collection(m,cfg['entry'],cfg['targets'][0])
                else:
                    try:local=plan_service(m,cfg['entry'],cfg['targets'][0])
                    except ValueError:local=copy_plan(m,cfg['entry'],cfg['targets'][0])
            plan=augment(m,local);plan['collection_elements']=True
            if cfg.get('json_conversion_methods'):
                plan['json_conversion_methods']=cfg['json_conversion_methods']
                plan['json_conversion_contract']=load(base/role/'plan.json')['json_conversion_contract']
        # query_build enables element coordinates on every role in this task.
        if kind!='price':plan['collection_elements']=True
        planning=time.perf_counter()-t;t=time.perf_counter();save(d/'plan.json',plan);export=time.perf_counter()-t
        # Exact plan equivalence protects this timing from benchmarking a shortcut.
        if plan!=load(base/role/'plan.json'):raise ValueError('Benchmarked plan differs from deployed plan: '+role)
        phase[role]={'extract_seconds':extract,'bytecode_model_seconds':bytecode,'model_json_decode_seconds':decode,'plan_analysis_seconds':planning,'plan_export_seconds':export,'model_bytes':(d/'model.json').stat().st_size,'plan_bytes':(d/'plan.json').stat().st_size}
    usage=resource.getrusage(resource.RUSAGE_SELF);child=resource.getrusage(resource.RUSAGE_CHILDREN)
    save(out/'worker.json',{'kind':kind,'wall_seconds':time.perf_counter()-started,'cpu_seconds':usage.ru_utime+usage.ru_stime+child.ru_utime+child.ru_stime,'python_peak_rss_bytes':usage.ru_maxrss*1024,'largest_child_peak_rss_bytes':child.ru_maxrss*1024,'phases':phase,'plans_equal_deployed':True,'affinity':sorted(os.sched_getaffinity(0))})


def tree_rss(pid):
    total=0;todo=[pid];seen=set()
    while todo:
        p=todo.pop()
        if p in seen:continue
        seen.add(p)
        try:
            status=Path(f'/proc/{p}/status').read_text();total+=next(int(l.split()[1])*1024 for l in status.splitlines() if l.startswith('VmRSS:'))
            # Children may be created by any JVM thread.
            for task in Path(f'/proc/{p}/task').iterdir():todo.extend(map(int,(task/'children').read_text().split()))
        except (FileNotFoundError,ProcessLookupError,StopIteration):pass
    return total


def run(args):
    args.out.mkdir();affinity=sorted(os.sched_getaffinity(0));cpu=affinity[0];jobs=[(r,k) for r in range(1,args.rounds+1) for k in ('cart','train','price')];random.Random(201020).shuffle(jobs);results=[]
    config={'order':jobs,'single_cpu':cpu,'allowed_cpus':affinity,'fresh_worker_each_repeat':True,'cache':'OS page cache not flushed; process-cold, not disk-cold','rss':'15ms samples of summed process-tree RSS; shared pages may be counted more than once','agent_compile_excluded':True,'image_startup_excluded':True,'source_sha256':sha(Path(__file__))};save(args.out/'config.json',config)
    for repeat,kind in jobs:
        d=args.out/(f'round-{repeat:02d}-'+kind);d.mkdir();base=getattr(args,kind+'_build')
        env={**os.environ,'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1'}
        cmd=[sys.executable,str(Path(__file__).resolve()),'worker','--out',str(d),'--base',str(base),'--kind',kind]
        def pin():os.sched_setaffinity(0,{cpu})
        peak=0;samples=0;started=time.monotonic_ns()
        with (d/'worker.log').open('w') as log:
            p=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,env=env,preexec_fn=pin)
            while p.poll() is None:peak=max(peak,tree_rss(p.pid));samples+=1;time.sleep(.015)
        if p.returncode:raise ValueError('Static planning failed: '+str(d))
        result=load(d/'worker.json');result.update(repeat=repeat,subprocess_wall_seconds=(time.monotonic_ns()-started)/1e9,process_tree_sampled_peak_rss_bytes=peak,rss_samples=samples)
        save(d/'measurement.json',result);results.append(result);save(args.out/'results.json',{'all_passed':True,'scope':'Static planning only, full/selective share one plan','measurements':results});print(kind,repeat,'passed',flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('stage',choices=('run','worker'));p.add_argument('--out',type=Path,required=True);p.add_argument('--base',type=Path);p.add_argument('--kind',choices=('cart','train','price'));p.add_argument('--cart-build',type=Path);p.add_argument('--train-build',type=Path);p.add_argument('--price-build',type=Path);p.add_argument('--rounds',type=int,default=5);a=p.parse_args()
    for key in ('out','base','cart_build','train_build','price_build'):
        if getattr(a,key) is not None:setattr(a,key,getattr(a,key).resolve())
    if a.stage=='worker':worker(a.out,a.base,a.kind)
    else:run(a)
