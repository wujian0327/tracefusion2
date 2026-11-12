"""Same full execution, old/new offline selection semantics, no new deployment."""
import argparse,json,subprocess,sys,tarfile,io
from pathlib import Path


def worker(plan,capture,out,reference):
    if reference:sys.path.insert(0,str(reference))
    from infer_execution_kernel import infer_execution
    from analysis_status import failure_status
    try:
        result=infer_execution(json.loads(plan.read_text()),[json.loads(x)for x in capture.read_text().splitlines()])
        answer={'status':'completed','result':result}
    except (ValueError,KeyError,AssertionError)as e:answer={'status':failure_status(e),'error':str(e)}
    out.write_text(json.dumps(answer,ensure_ascii=False,sort_keys=True))


def run(out):
    from run_planned_service import ROOT,HERE,sha,save,load
    out.mkdir(parents=True,exist_ok=False);reference=out/'reference';reference.mkdir()
    data=subprocess.check_output(['git','archive','f68115e','experiments/sockshop-mirrortaint'],cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(data))as tar:tar.extractall(reference,filter='data')
    reference=reference/'experiments/sockshop-mirrortaint'
    old=ROOT/'artifacts/galette-compatibility-selection-20261111';jobs=[]
    for cohort in ('selection-controls-02','direct-selection-controls-02'):
        for mode in ('full','static','selective'):
            jobs.append((cohort+'-'+mode,old/cohort/'plan.json',old/cohort/mode/'events.jsonl','independent literal expectations retained'))
    remove=ROOT/'artifacts/ruoyi-removeif-20261105/controls-04'
    for mode in ('full','selective'):
        jobs.append(('removeIf-control-'+mode,remove/'plan.json',remove/mode/'events.jsonl','old explicit-data oracle; selection incomplete'))
    ruoyi=ROOT/'artifacts/ruoyi-tolist-20261105/final-C1'
    for q in ('ruoyi-1','ruoyi-2','ruoyi-3'):
        for mode in ('full','selective'):
            jobs.append((q+'-'+mode,ruoyi/'plans'/q/'plan.json',ruoyi/'runs'/q/mode/'capture/events.jsonl','old explicit-data oracle; selection incomplete'))
    save(out/'jobs-before-replay.json',[{'name':n,'plan':str(p),'capture':str(c),'plan_sha256':sha(p),'capture_sha256':sha(c),'selection_oracle':oracle}for n,p,c,oracle in jobs])
    reports=[]
    for name,plan,capture,oracle in jobs:
        for version in ('old','new'):
            cmd=[sys.executable,str(Path(__file__).resolve()),'--worker','--plan',str(plan),'--capture',str(capture),'--out',str(out/(name+'-'+version+'.json'))]
            if version=='old':cmd+=['--reference',str(reference)]
            with(out/(name+'-'+version+'.log')).open('w')as f:subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,check=True)
        a,b=[load(out/(name+'-'+v+'.json'))for v in ('old','new')]
        changes=[]
        if a['status']==b['status']=='completed':
            before=a['result']['answers'];after=b['result']['answers'];assert len(before)==len(after)
            def key(r):return tuple(r.get(k)for k in ('root_frame','path','owner','field','version'))
            assert len({key(r)for r in before})==len(before) and {key(r)for r in before}=={key(r)for r in after}
            after={key(r):r for r in after}
            for x in before:
                y=after[key(x)];diff={k:{'old':x[k],'new':y[k]}for k in ('known','origins','selectors')if x[k]!=y[k]}
                if diff:changes.append({'coordinate':list(key(x)),'changes':diff})
            report={'targets':len(before),'old_known':sum(x['known']for x in before),'new_known':sum(x['known']for x in after.values()),'versions_equal':True,'explicit_data_changes':sum('origins'in x['changes']for x in changes),'known_changes':sum('known'in x['changes']for x in changes),'selector_changes':sum('selectors'in x['changes']for x in changes),'root_audits_equal':a['result']['roots']==b['result']['roots']}
        else:report={'old_error':a.get('error'),'new_error':b.get('error')}
        save(out/(name+'-changes.json'),changes)
        reports.append({'task':name,'old_status':a['status'],'new_status':b['status'],'capture_sha256':sha(capture),'selection_oracle':oracle,**report})
        print(name,a['status'],b['status'],report,flush=True)
    save(out/'results.json',{'captures':reports,'scope':'Complete old captures, new offline semantics only. No independent old business selector oracle invented.','new_Agent_deployment':False})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--worker',action='store_true');p.add_argument('--plan',type=Path);p.add_argument('--capture',type=Path);p.add_argument('--reference',type=Path);a=p.parse_args()
    if a.worker:worker(a.plan,a.capture,a.out,a.reference)
    else:run(a.out.resolve())
