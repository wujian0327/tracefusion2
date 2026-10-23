#!/usr/bin/env python3
"""Paired offline-only replays with exact graph/answer preservation gates."""
import argparse,importlib.util,os,random,subprocess,sys,time
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save,sha


def reference(path):
    spec=importlib.util.spec_from_file_location('infer_distributed_fields',path);module=importlib.util.module_from_spec(spec);sys.modules['infer_distributed_fields']=module;spec.loader.exec_module(module);return module


def prepare(root):
    root.mkdir(parents=True,exist_ok=False);(root/'logs').mkdir();ref=root/'reference';ref.mkdir()
    rel='experiments/sockshop-mirrortaint/infer_distributed_fields.py'
    (ref/'infer_distributed_fields.py').write_bytes(subprocess.check_output(['git','show','e78cc04:'+rel],cwd=ROOT))
    cost=ROOT/'artifacts/transport-cart-cost-v3-20261023';assert load(cost/'pipeline-complete.json')['all_passed']
    cfg=load(cost/'config.json');jobs=[];rng=random.Random(231024)
    for item in cfg['order']:
        if item['mode']=='original':continue
        variants=['reference','indexed'];rng.shuffle(variants)
        for v in variants:jobs.append({'trial':item['name'],'arm':item['arm'],'variant':v,'source':str(cost/'deployments'/item['name']),'build':str(cost/'builds'/item['arm'])})
    save(root/'protocol.json',{'source_cost':str(cost),'source_cost_audit_sha256':sha(cost/'cost-audit.json'),'reference_commit':'e78cc04','reference_module':str(ref/'infer_distributed_fields.py'),'reference_sha256':sha(ref/'infer_distributed_fields.py'),'indexed_sha256':sha(HERE/'infer_distributed_fields.py'),'driver_sha256':sha(Path(__file__)),'jobs':jobs,'cpu':min(os.sched_getaffinity(0)),'seed':231024,'fresh_exec':True,'raw_capture_and_original_metrics_unchanged':True,'scope':'20 existing independently deployed datasets, both reconstructors on each. Pair by original deployment; no new online costs and no pseudo-independent requests. Cache contains all candidates, not first-match aliases.'})


def worker(root,index):
    protocol=load(root/'protocol.json');job=protocol['jobs'][index];source=Path(job['source']);dest=root/'replays'/(f'{index:02d}-'+job['trial']+'-'+job['variant']);(dest/'capture/carts').mkdir(parents=True)
    for rel in ('capture/carts/events.jsonl','capture/run.json'):(dest/rel).symlink_to(source/rel)
    if job['variant']=='reference':reference(Path(protocol['reference_module']))
    from measure_offline_memory import worker as measure
    measure(argparse.Namespace(out=dest,build=Path(job['build']),kind='cart'))
    for filename in ('answers.json','field-results.json','field-graph.json'):
        assert load(dest/filename)==load(source/filename),('Graph/answer changed',job,filename)
    save(dest/'identity-audit.json',{'all_passed':True,'original':str(source),'graph_and_all_answers_exactly_equal':True,'raw_events_sha256':sha(source/'capture/carts/events.jsonl')})


def run(root):
    p=load(root/'protocol.json');assert sha(HERE/'infer_distributed_fields.py')==p['indexed_sha256']and sha(Path(__file__))==p['driver_sha256'];guarded={}
    for job in p['jobs']:
        source=Path(job['source'])
        for f in ('capture/carts/events.jsonl','capture/run.json','metrics.json','offline.json','answers.json','field-results.json','field-graph.json'):guarded[str(source/f)]=sha(source/f)
    for i,job in enumerate(p['jobs']):
        assert sha(HERE/'infer_distributed_fields.py')==p['indexed_sha256']
        cmd=['taskset','-c',str(p['cpu']),sys.executable,str(Path(__file__).resolve()),'worker','--root',str(root),'--index',str(i)]
        with (root/'logs'/f'{i:02d}.log').open('w')as log:subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True,env={**os.environ,'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1'})
        save(root/'progress.json',{'completed':i+1,'total':len(p['jobs']),'last':job});print(i+1,job['variant'],job['trial'],'passed',flush=True)
    assert all(sha(Path(f))==h for f,h in guarded.items());save(root/'benchmark-complete.json',{'all_passed':True,'jobs':40,'raw_originals_unchanged':True,'original_sha256':guarded})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=('prepare','run','worker'));p.add_argument('--root',type=Path,required=True);p.add_argument('--index',type=int);a=p.parse_args();root=a.root.resolve()
    if a.stage=='worker':worker(root,a.index)
    else:{'prepare':prepare,'run':run}[a.stage](root)
