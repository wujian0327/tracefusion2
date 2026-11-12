"""Fail closed on typed field corruption and real reference identity loss."""
import argparse,copy,json
from pathlib import Path
from run_planned_service import load,save
from run_public_control_semantics import checked
from analysis_status import failure_status


def run(home,out):
    out.mkdir(parents=True,exist_ok=False);checks=[]
    for mode in ('full','static','selective'):
        for fault in ('primitive-id','missing-type','wrong-descriptor','lost-source','wrong-version','reference-source-id','reference-write-id','reference-missing-id','unknown-version','unversioned-primitive'):
            field='boxed'if fault.startswith('reference')else'big';plan=load(home/(field+'-plan.json'));rows=[json.loads(l)for l in(home/(field+'-'+mode)/'events.jsonl').read_text().splitlines()];wanted='evidence_invalid'
            read=next(r for r in rows if r['kind']=='read'and r['field']=='PrimitiveObservationFixture$Datum.'+field)
            if fault=='primitive-id':read['observed']['object']='fake-box'
            elif fault=='missing-type':read['observed'].pop('primitive')
            elif fault=='wrong-descriptor':read['descriptor']='J'
            elif fault=='wrong-version':next(r for r in rows if r['kind']=='write'and r['field'].endswith('.big'))['version']=0
            elif fault=='lost-source':
                src=next(r for r in rows if r['kind']=='binding-source');src['fields']=[f for f in src['fields']if not f['field'].endswith('.big')];wanted='unknown'
            elif fault=='reference-source-id':read['observed']['object']='other-real-wrapper'
            elif fault=='reference-write-id':next(r for r in rows if r['kind']=='write'and r['field']=='PrimitiveObservationFixture$Out.boxed')['observed']['object']='other-real-wrapper'
            elif fault=='reference-missing-id':read['observed'].pop('object')
            elif fault=='unknown-version':rows[0]['field_value_version']=2
            elif fault=='unversioned-primitive':rows[0].pop('field_value_version')
            try:
                p=checked(plan,rows);state='known'if p['answers'][0]['known']else'unknown';error=None
            except (ValueError,KeyError,AssertionError)as e:state=failure_status(e);error=str(e)
            checks.append({'mode':mode,'fault':fault,'expected':wanted,'state':state,'passed':state==wanted,'error':error})
    save(out/'results.json',{'checks':checks,'gate':all(c['passed']for c in checks)});assert all(c['passed']for c in checks),checks

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.home,a.out)
