"""Corrupt method evidence without changing original truth or raw captures."""
import argparse,copy,json
from pathlib import Path
from run_planned_service import load,save
from run_public_control_semantics import checked
from analysis_status import failure_status


def run(home,out):
    out.mkdir(parents=True,exist_ok=False);checks=[];plan=load(home/'plan.json')
    for mode in ('full','static','selective'):
        original=[json.loads(l)for l in(home/mode/'events.jsonl').read_text().splitlines()]
        for fault in ('missing-descriptor','argument-count','primitive-as-ref','ref-as-primitive','bad-range','return-as-ref','wrong-return-bits','void-as-null','constructor-descriptor','constructor-receiver','missing-version','unknown-version','lambda-capture-kind','lambda-capture-desc'):
            rows=copy.deepcopy(original);enter=next(r for r in rows if r['kind']=='enter'and r['method'].endswith('.mixed(ZBCSIJFDLjava/lang/Integer;Ljava/lang/Long;Ljava/lang/Object;)I'));end=next(r for r in rows if r['kind']=='exit'and r['frame']==enter['frame'])
            if fault=='missing-descriptor':enter.pop('method_descriptor')
            elif fault=='argument-count':enter['args'].pop()
            elif fault=='primitive-as-ref':enter['args'][4]={'object':'box','value':1000000}
            elif fault=='ref-as-primitive':enter['args'][8]={'object':None,'primitive':'I','value':1000000}
            elif fault=='bad-range':enter['args'][1]['value']=1000
            elif fault=='return-as-ref':end['result']={'object':'box','value':1000000}
            elif fault=='wrong-return-bits':next(r for r in rows if r['kind']=='exit'and r['result'].get('primitive')=='D')['result']['bits']='0'
            elif fault=='void-as-null':next(r for r in rows if r['kind']=='exit'and r['result'].get('void'))['result'].pop('void')
            elif fault=='constructor-descriptor':next(r for r in rows if r['kind']=='execution-constructor-enter')['method_descriptor']='()V'
            elif fault=='constructor-receiver':next(r for r in rows if r['kind']=='execution-constructed')['receiver']={'object':None,'value':None}
            elif fault=='missing-version':rows[0].pop('method_value_version')
            elif fault=='unknown-version':rows[0]['method_value_version']=2
            elif fault=='lambda-capture-kind':next(r for r in rows if r['kind']=='execution-lambda')['captures'][0]={'object':'box','value':1000000}
            elif fault=='lambda-capture-desc':next(r for r in rows if r['kind']=='execution-lambda')['method_descriptor']='(Ljava/lang/Integer;)Ljava/util/function/Predicate;'
            try:checked(plan,rows);state='accepted';error=None
            except (ValueError,KeyError,AssertionError)as e:state=failure_status(e);error=str(e)
            checks.append({'mode':mode,'fault':fault,'state':state,'passed':state=='evidence_invalid','error':error})
    save(out/'results.json',{'checks':checks,'gate':all(c['passed']for c in checks)});assert all(c['passed']for c in checks),checks

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.home,a.out)
