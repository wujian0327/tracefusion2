"""Untimed full interpreter-state/selection replay, separate from timings."""
import argparse,importlib.util,json
from pathlib import Path
from run_planned_service import ROOT,load,save,sha


def run(out):
    out.mkdir(parents=True,exist_ok=False);h=ROOT/'artifacts/ruoyi-zlt-refinement-20261103';base=ROOT/'artifacts/target-closure-revision-20261103'
    import infer_application_execution as indexed
    spec=importlib.util.spec_from_file_location('reference_application',h/'reference-core/infer_application_execution.py');old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
    plan=load(base/'final-candidate-02/zlt/planning-first/ZLT-MP-4/000-plan.json');receipts=[]
    for i in range(1,6):
        for mode in('full','selective'):
            path=base/('common-cost-01/round-%02d-zlt-user-%s/capture/events.jsonl'%(i,mode));before=sha(path);rows=[json.loads(x)for x in path.open()]
            a=old.infer_application(plan,rows);b=indexed.infer_application(plan,rows)
            assert a==b,'Full origins/selectors/versions/status/root evidence differs'
            assert len(a['answers'])==270 and all(r['known']for r in a['answers'])and before==sha(path)
            dest=out/('%02d-%s.json'%(i,mode));save(dest,a)
            receipts.append({'round':i,'mode':mode,'answers':270,'capture_sha256':before,'full_result_sha256':sha(dest),'selection_evidence_equal':True});save(out/'progress.json',receipts)
    save(out/'summary.json',{'passed':True,'not_timed':True,'receipts':receipts,'source':'Full actual interpreter answers including selectors and complete root audits, not only public graph query origins.'})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.out.resolve())
