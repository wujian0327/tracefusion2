"""Existing protocol perturbations; this does not certify JDK native effects."""
import argparse,copy,json
from pathlib import Path
from run_planned_service import load,save
from run_public_control_semantics import checked
from analysis_status import failure_status


def run(home,out):
    out.mkdir(parents=True,exist_ok=False);plan=load(home/'plan.json');checks=[]
    faults=['missing-start','duplicate-start','wrong-start-id','wrong-start-pc','missing-completion','duplicate-completion','wrong-receiver','wrong-completion-id','missing-parent-frame','wrong-parent-frame','missing-defaults','duplicate-defaults','wrong-default-version','wrong-default-object','missing-child-write','duplicate-child-write','wrong-write-version','wrong-reference-object']
    for mode in ['full','static','selective']:
        original=[json.loads(l)for l in(home/mode/'events.jsonl').read_text().splitlines()]
        for fault in faults:
            rows=copy.deepcopy(original)
            start=next(r for r in rows if r['kind']=='execution-constructor-enter'and '$Child.<init>'in r['callee']);id_=start['constructor_id']
            end=next(r for r in rows if r['kind']=='execution-constructed'and r['constructor_id']==id_)
            parent=next(r for r in rows if r['kind']=='enter'and '$Parent.<init>'in r['method'])
            defaults=next(r for r in rows if r['kind']=='execution-defaults'and r['constructor_id']==id_)
            write=next(r for r in rows if r['kind']=='write'and r.get('site','').startswith('ConstructorScopeFixture$Child.<init>'))
            if fault=='missing-start':rows.remove(start)
            elif fault=='duplicate-start':rows.insert(rows.index(start),copy.deepcopy(start))
            elif fault=='wrong-start-id':start['constructor_id']+=999
            elif fault=='wrong-start-pc':start['pc']+=999
            elif fault=='missing-completion':rows.remove(end)
            elif fault=='duplicate-completion':rows.insert(rows.index(end),copy.deepcopy(end))
            elif fault=='wrong-receiver':end['receiver']['object']='wrong'
            elif fault=='wrong-completion-id':end['constructor_id']+=999
            elif fault=='missing-parent-frame':rows.remove(parent)
            elif fault=='wrong-parent-frame':parent['parent']='wrong'
            elif fault=='missing-defaults':rows.remove(defaults)
            elif fault=='duplicate-defaults':rows.insert(rows.index(defaults),copy.deepcopy(defaults))
            elif fault=='wrong-default-version':defaults['fields'][0]['version']=1
            elif fault=='wrong-default-object':defaults['object']='wrong'
            elif fault=='missing-child-write':rows.remove(write)
            elif fault=='duplicate-child-write':rows.insert(rows.index(write),copy.deepcopy(write))
            elif fault=='wrong-write-version':write['version']=0
            elif fault=='wrong-reference-object':write['observed']['object']='wrong'
            for seq,r in enumerate(rows,1):r['seq']=seq
            try:
                checked(plan,rows);state='accepted';error=None
            except (ValueError,AssertionError,KeyError)as e:state=failure_status(e);error=str(e)
            checks.append({'mode':mode,'fault':fault,'state':state,'passed':state=='evidence_invalid','error':error})
    save(out/'results.json',{'checks':checks,'gate':all(c['passed']for c in checks)})
    print(json.dumps({'checks':len(checks),'gate':all(c['passed']for c in checks),'failed':[c for c in checks if not c['passed']]}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.home.resolve(),a.out.resolve())
