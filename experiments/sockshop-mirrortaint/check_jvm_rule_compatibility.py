"""Old/new interpreters in separate processes, identical complete old captures."""
import argparse,json,subprocess,sys
from pathlib import Path

def worker(plan,capture,out,reference):
    if reference:sys.path.insert(0,str(reference))
    from infer_execution_kernel import infer_execution
    result=infer_execution(json.loads(plan.read_text()),[json.loads(s)for s in capture.read_text().splitlines()])
    out.write_text(json.dumps(result,sort_keys=True,separators=(',',':')))

def run(out):
    from run_planned_service import ROOT,HERE,load,save,sha
    out.mkdir(parents=True,exist_ok=False);reference=out/'baseline-python';reference.mkdir()
    protocol=load(ROOT/'artifacts/jvm-rule-evidence-20261110/protocol-before-change.json')
    for path in protocol['baseline_sources']:
        relative=str(Path(path).relative_to(ROOT))
        data=subprocess.check_output(['git','show',protocol['main']+':'+relative],cwd=ROOT)
        (reference/Path(path).name).write_bytes(data)
    old=ROOT/'artifacts/unrelated-work-scaling-20261109';jobs=[]
    for mode in ('full','selective'):
        for tier in ('low','medium','high'):
            jobs.append((tier+'-'+mode,old/'controlled-build-04'/tier/'plan.json',old/'pilot-controlled-04'/(tier+'-'+mode)/'capture/events.jsonl'))
        jobs.append(('mall-'+mode,old/'mall-plan.json',old/'formal'/('01-mall-2-'+mode)/'capture/events.jsonl'))
    reports=[]
    for name,plan,capture in jobs:
        for version in ('old','new'):
            cmd=[sys.executable,str(Path(__file__).resolve()),'--worker','--plan',str(plan),'--capture',str(capture),'--out',str(out/(name+'-'+version+'.json'))]
            if version=='old':cmd+=['--reference',str(reference)]
            subprocess.run(cmd,check=True)
        a=load(out/(name+'-old.json'));b=load(out/(name+'-new.json'));assert a==b,name
        reports.append({'task':name,'capture_sha256':sha(capture),'targets':len(a['answers']),'known':sum(v['known']for v in a['answers']),'entire_result_equal':True})
    save(out/'results.json',{'complete_captures':reports,'scope':'Old online executions, fresh offline replay; no new Agent deployment or same-execution omission license.'})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--worker',action='store_true');p.add_argument('--plan',type=Path);p.add_argument('--capture',type=Path);p.add_argument('--reference',type=Path);a=p.parse_args()
    if a.worker:worker(a.plan,a.capture,a.out,a.reference)
    else:run(a.out.resolve())
