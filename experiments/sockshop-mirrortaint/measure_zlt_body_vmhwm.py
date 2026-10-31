"""Correct current-exec VmHWM; retain earlier ru_maxrss and valid timings."""
import argparse,json,resource,subprocess,sys,time
from pathlib import Path
from run_planned_service import ROOT,load,save,sha
from run_zlt_body_cost import offline_worker


def worker(home,trial,out,task,mode):
    offline_worker(home,trial,out,task,mode)
    fields={line.split(':',1)[0]:line.split(':',1)[1].strip()for line in Path('/proc/self/status').read_text().splitlines()if ':'in line}
    current=int(fields['VmHWM'].split()[0]);summary=load(out/'summary.json')
    summary.update(current_exec_VmHWM_KiB=current,resource_ru_maxrss_KiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        reason='Linux rusage may retain the fork/pre-exec image peak; /proc/self/status VmHWM is the current exec image high-water mark. Memory-only repeat, no original timing overwritten.')
    save(out/'memory.json',summary)


def run(home):
    out=home/'current-exec-memory';out.mkdir(exist_ok=False);results=[]
    jobs=[j for j in load(home/'protocol-before-calibration.json')['jobs']if j['mode']!='original']
    save(out/'protocol-before-runs.json',{'jobs':jobs,'driver_sha256':sha(Path(__file__)),'same_complete_capture':True,'profiler':False,
        'timing_policy':'Preserve all valid original wall/CPU values; repeat only to obtain current-exec VmHWM and compare complete source signatures.'})
    for job in jobs:
        name='round-%02d-%s-%s'%(job['round'],job['task'],job['mode']);trial=home/name;dest=out/name
        with(out/(name+'.log')).open('w')as f:
            subprocess.run([sys.executable,__file__,'worker','--home',str(home),'--trial',str(trial),'--out',str(dest),'--task',job['task'],'--mode',job['mode']],stdout=f,stderr=subprocess.STDOUT,check=True)
        s=load(dest/'memory.json');assert s['correct']==s['targets']==180
        if job['task']=='mall':
            before=load(trial/'offline-single-pass/scores.json');after=load(dest/'scores.json')
            assert before==after
        else:
            before=load(trial/'offline-single-pass/sockshop/field-results.json');after=load(dest/'sockshop/field-results.json')
            assert before==after
        s.update(**job,trial=name,answers_and_physical_source_signatures_identical=True);results.append(s)
        save(out/'progress.json',{'complete':False,'results':results});print(name,s['current_exec_VmHWM_KiB'],s['resource_ru_maxrss_KiB'],flush=True)
    save(out/'summary.json',{'complete':True,'measurements':results,'original_online_and_offline_timings_preserved':True})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['worker','run']);p.add_argument('--home',type=Path,required=True);p.add_argument('--out',type=Path);p.add_argument('--trial',type=Path);p.add_argument('--task');p.add_argument('--mode');a=p.parse_args()
    if a.stage=='run':run(a.home.resolve())
    else:worker(a.home.resolve(),a.trial.resolve(),a.out.resolve(),a.task,a.mode)
