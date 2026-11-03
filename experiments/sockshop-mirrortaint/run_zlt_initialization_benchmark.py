"""Complete old captures, capture-local lookup A/B, no online measurement."""
import argparse,copy,hashlib,importlib.util,json,os,random,resource,subprocess,sys,time
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save,sha
HOME=ROOT/'artifacts/ruoyi-zlt-refinement-20261103'
OLD=ROOT/'artifacts/target-closure-revision-20261103/common-cost-01'


def worker(trial,out,mode,engine):
    # Other normal reconstruction, certificate and scoring code is SHARED.
    # The reference arm loads the exact 1308589 application interpreter.
    lock=load(HOME/'offline-benchmark-lock.json')
    for p,h in lock['sources'].items():assert sha(Path(p))==h,p
    if engine=='reference':
        path=HOME/'reference-core/infer_application_execution.py'
        assert sha(path)==lock['reference_application_sha256']
        spec=importlib.util.spec_from_file_location('infer_application_execution',path)
        module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    import run_target_closure_cost as common
    # Replace only the prior experiment driver's source-lock checker. Actual
    # reconstruction's plan/hash/completion/effect checks stay unchanged.
    common.verify=lambda:lock
    common.offline_worker(OLD,trial,out,'zlt-user',mode)


def run(out):
    out.mkdir(parents=True,exist_ok=False);rng=random.Random(20261103);jobs=[]
    source_names=load(HOME/'protocol-before-change.json')['reference_sources']
    sources={p:sha(Path(p))for p in source_names}
    for n in('plan_map_wrapper.py','infer_map_wrapper.py','map-wrapper-contracts-20261103.json',Path(__file__).name):sources[str(HERE/n)]=sha(HERE/n)
    save(HOME/'offline-benchmark-lock.json',{'sources':sources,'reference_application_sha256':sha(HOME/'reference-core/infer_application_execution.py'),
      'commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
      'scope':'Shared candidate normal flow, exact old application interpreter versus indexed application interpreter. No source/plan/event filtering or online changes.'})
    cpu=min(os.sched_getaffinity(0));rows=[]
    for i in range(1,6):
        for mode in('full','selective','mirrortaint'):
            engines=['reference','indexed'];rng.shuffle(engines)
            for engine in engines:jobs.append({'round':i,'mode':mode,'engine':engine})
    save(out/'protocol-before-timing.json',{'jobs':jobs,'logical_cpu':cpu,'capture_family':'Original five formal ZLT User complete captures, all 180 requests and 270 targets per capture.','fresh_exec':True,'profiler':False})
    for job in jobs:
        trial=OLD/('round-%02d-zlt-user-%s'%(job['round'],job['mode']));dest=out/('%02d-%s-%s'%(job['round'],job['mode'],job['engine']))
        files=sorted((trial/'capture').glob('*.jsonl'));before={str(p):sha(p)for p in files}
        t=time.perf_counter();a=resource.getrusage(resource.RUSAGE_CHILDREN)
        with dest.with_suffix('.log').open('w')as log:
            p=subprocess.run(['taskset','-c',str(cpu),sys.executable,__file__,'worker','--trial',str(trial),'--out',str(dest),'--mode',job['mode'],'--engine',job['engine']],stdout=log,stderr=subprocess.STDOUT)
        b=resource.getrusage(resource.RUSAGE_CHILDREN);wall=time.perf_counter()-t
        assert p.returncode==0,(job,p.returncode)
        assert before=={str(p):sha(p)for p in files}
        s=load(dest/'summary.json');assert s['targets']==s['correct']==270
        rows.append({**job,'wall_seconds':wall,'CPU_seconds':b.ru_utime+b.ru_stime-a.ru_utime-a.ru_stime,
            'VmHWM_KiB':s['VmHWM_KiB'],'phases_seconds':s['phases_seconds'],'core_CPU':s['core_cpu_seconds'],
            'capture_hashes':before,'answers_sha256':sha(dest/'answers.json')})
        save(out/'progress.json',{'complete':False,'rows':rows});print(job,round(wall,3),flush=True)
    for i in range(1,6):
        for mode in('full','selective','mirrortaint'):
            a=out/('%02d-%s-reference'%(i,mode));b=out/('%02d-%s-indexed'%(i,mode))
            assert load(a/'answers.json')==load(b/'answers.json'),'Status/source/selection evidence changed'
            assert load(a/'scores.json')==load(b/'scores.json'),'Independent raw-source coordinates changed'
    save(out/'summary.json',{'complete':True,'all_answers_sources_selections_equal':True,'all_complete_capture_hashes_unchanged':True,'rows':rows})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['run','worker']);p.add_argument('--out',type=Path,required=True);p.add_argument('--trial',type=Path);p.add_argument('--mode');p.add_argument('--engine');a=p.parse_args()
    if a.stage=='run':run(a.out.resolve())
    else:worker(a.trial.resolve(),a.out.resolve(),a.mode,a.engine)
