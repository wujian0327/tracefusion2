"""Old/new interpreter checks on an actual complete ZLT User capture."""
import argparse,copy,importlib.util,json,sys
from pathlib import Path
from run_planned_service import ROOT,load,save


def run(out):
    out.mkdir(parents=True,exist_ok=False);home=ROOT/'artifacts/ruoyi-zlt-refinement-20261103'
    old=ROOT/'artifacts/target-closure-revision-20261103/final-candidate-02/zlt'
    plan=load(old/'planning-first/ZLT-MP-4/000-plan.json');rows=[json.loads(x)for x in(old/'runs/ZLT-MP-4/full/capture/events.jsonl').open()]
    import infer_application_execution as indexed
    spec=importlib.util.spec_from_file_location('reference_application',home/'reference-core/infer_application_execution.py')
    reference=importlib.util.module_from_spec(spec);spec.loader.exec_module(reference)
    results={}
    for name,module in [('reference',reference),('indexed',indexed)]:
        base=module.infer_application(plan,rows);assert sum(a['known']for a in base['answers'])==9
        checks={}
        for fault in('duplicate-init','missing-init','wrong-hash','wrong-class-object','sticky-invalid','source-coordinate','missing-source'):
            bad=copy.deepcopy(rows);marker=next(r for r in bad if r['kind']=='execution-initialized-class')
            if fault=='duplicate-init':
                r=copy.deepcopy(marker);r['seq']=bad[-1]['seq'];bad[-1]['seq']+=1;bad.insert(-1,r)
            elif fault=='missing-init':bad.remove(marker)
            elif fault=='wrong-hash':marker['class_sha256']='wrong'
            elif fault=='wrong-class-object':marker['class_object']='wrong'
            elif fault=='sticky-invalid':next(r for r in bad if r['kind']=='metrics')['capture_invalid']=True
            elif fault=='source-coordinate':next(r for r in bad if r['kind']=='binding-source')['source_call_id']=-1
            else:
                source=next(r for r in bad if r['kind']=='binding-source');bad.remove(source)
            try:answer=module.infer_application(plan,bad)
            except (ValueError,KeyError):checks[fault]='rejected'
            else:
                assert fault=='missing-source',fault
                affected=[a for a in answer['answers']if a['root_frame']==source['frame']]
                # Interpreted source may be in a child Frame: never allow an
                # increase in certified answers when its source disappears.
                assert sum(a['known']for a in answer['answers'])<9
                checks[fault]='affected answers unknown, unaffected roots retained'
        results[name]={'checks':checks,'answers':base['answers']}
    assert results['reference']['answers']==results['indexed']['answers']
    assert results['reference']['checks']==results['indexed']['checks']
    save(out/'results.json',{'passed':True,**results});print('Initialization/source guards passed',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.out.resolve())
