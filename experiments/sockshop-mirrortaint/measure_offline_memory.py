#!/usr/bin/env python3
"""Fresh-exec VmHWM on existing evidence; fork-inherited rusage is retained.

No business deployment is rerun. Exports go to a separate replay directory;
original captures, answers and timings are never overwritten.
"""
import argparse,json,os,random,resource,runpy,subprocess,sys,time
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save,sha


def worker(args):
    script=HERE/('run_train_cost.py' if args.kind=='price' else 'run_bound_query_cost.py')
    sys.argv=[str(script),'offline','--out',str(args.out),'--build',str(args.build)]
    if args.kind!='price':sys.argv+=['--kind',args.kind]
    before=time.monotonic_ns();runpy.run_path(str(script),run_name='__main__');ended=time.monotonic_ns()
    status=Path('/proc/self/status').read_text();hwm=next(int(l.split()[1])*1024 for l in status.splitlines() if l.startswith('VmHWM:'))
    usage=resource.getrusage(resource.RUSAGE_SELF)
    save(args.out/'memory.json',{'vmhwm_bytes':hwm,'launch_inclusive_rusage_maxrss_bytes':usage.ru_maxrss*1024,'replay_wall_seconds':(ended-before)/1e9,'cpu_seconds':usage.ru_utime+usage.ru_stime,'status_after_export':status,'measurement':'VmHWM of this exec image after core/query/oracle/evidence export','affinity':sorted(os.sched_getaffinity(0))})


def run(root):
    mapping=load(root/'formal-run-map.json');out=root/'offline-memory-replays';out.mkdir();jobs=[]
    for kind,folder in mapping.items():
        home=root/folder;assert load(home/'run-status.json')['status']=='passed';cfg=load(home/'config.json')
        jobs.extend((kind,name,mode,str(Path(cfg['build']))) for name,mode in cfg['order'] if mode!='original')
    random.Random(201021).shuffle(jobs);save(out/'protocol.json',{'order':jobs,'scope':'Existing captured evidence, separate fresh exec per deployment, no overlapping application experiment','meter':'Linux /proc/self/status VmHWM; ru_maxrss can retain fork launch footprint','original_timings_unchanged':True,'source_sha256':sha(Path(__file__))})
    results={};guarded={}
    for kind,name,mode,build in jobs:
        original=root/mapping[kind]/name;dest=out/kind/name;dest.mkdir(parents=True);app='trainticket' if kind=='price' else 'capture';capture=dest/app;capture.mkdir()
        run=load(original/app/'run.json');roles=run['roles'] if 'roles' in run else list(load(Path(build)/'build.json')['inputs'])
        for r in roles:
            (capture/r).mkdir();(capture/r/'events.jsonl').symlink_to((original/app/r/'events.jsonl').resolve())
        (capture/'run.json').symlink_to((original/app/'run.json').resolve())
        # Preserve whole originals, including exported predictions, before replay.
        inputs=[original/'metrics.json',original/'offline.json',original/app/'run.json',original/(app+'/field-results.json' if kind=='price' else 'field-results.json'),*[original/app/r/'events.jsonl' for r in roles]]
        export_root=original/app if kind=='price' else original
        inputs.extend(p for p in (export_root/'answers.json',export_root/'field-graph.json') if p.exists())
        for p in inputs:guarded[str(p)]=sha(p)
        command=[sys.executable,str(Path(__file__).resolve()),'worker','--out',str(dest),'--build',build,'--kind',kind]
        save(dest/'command.json',command)
        with (dest/'worker.log').open('w') as log:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=600)
        memory=load(dest/'memory.json');old=load(original/'offline.json');new=load(dest/'offline.json')
        assert new['summary']==old['summary'] and new['populations']==old['populations'],'Replay answers differ'
        key=kind+'/'+name;results[key]={'kind':kind,'trial':name,'mode':mode,'summary':new['summary'],'vmhwm_bytes':memory['vmhwm_bytes'],'original_launch_rusage_bytes':old['peak_rss_bytes'],'replay_launch_rusage_bytes':memory['launch_inclusive_rusage_maxrss_bytes'],'measurement_file':str(dest/'memory.json')}
        save(out/'progress.json',{'completed':len(results),'total':len(jobs),'last':key});print(key,'passed',flush=True)
    assert all(sha(Path(p))==h for p,h in guarded.items()),'Original evidence/timing changed'
    save(root/'offline-memory-audit.json',{'all_passed':True,'measurements':results,'original_file_sha256':guarded,'originals_unchanged':True,'replay_count':len(results),'scope':'VmHWM is a separate post-experiment replay on identical frozen evidence; original wall/CPU measurements retained. ru_maxrss includes inherited launch footprint on this host.'})

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('stage',choices=('run','worker'));p.add_argument('--root',type=Path);p.add_argument('--out',type=Path);p.add_argument('--build',type=Path);p.add_argument('--kind',choices=('cart','train','price'));a=p.parse_args()
    for k in ('root','out','build'):
        if getattr(a,k) is not None:setattr(a,k,getattr(a,k).resolve())
    if a.stage=='worker':worker(a)
    else:run(a.root)
