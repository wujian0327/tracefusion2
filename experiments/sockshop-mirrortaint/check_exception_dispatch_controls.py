"""Mutate new runtime evidence; preserve originals and literal expectations."""
import argparse,copy,json
from pathlib import Path
from run_planned_service import load,save
from run_public_control_semantics import checked
from analysis_status import failure_status


def run(home,out):
    out.mkdir(parents=True,exist_ok=False);plan=load(home/'plan.json');reports=[]
    for mode in ('full','static','selective'):
        original=[json.loads(l)for l in(home/mode/'events.jsonl').read_text().splitlines()]
        for fault in ('missing-witness','wrong-object','wrong-type','wrong-hash','broken-chain','wrong-catch-order','other-loader','reused-class-id','unknown-version','legacy-custom'):
            rows=copy.deepcopy(original);event=next(r for r in rows if r['kind']=='collection-catch'and r['exception'].endswith('$Leaf'));f=event['exception_dispatch'];wanted='evidence_invalid'
            if fault=='missing-witness':del event['exception_dispatch']
            elif fault=='wrong-object':f['exception']['object']='bad'
            elif fault=='wrong-type':f['actual_type']='ExceptionDispatchFixture$Other'
            elif fault=='wrong-hash':f['hierarchy'][0]['class_sha256']='0'*64
            elif fault=='broken-chain':f['hierarchy'][0]['super']='absent'
            elif fault=='wrong-catch-order':f['targets']=[None]*len(f['targets'])
            elif fault=='other-loader':f['hierarchy'][0]['loader']='other-loader';wanted='analysis_limited'
            elif fault=='reused-class-id':f['hierarchy'][0]['id']=f['caller']['id']
            elif fault=='unknown-version':next(r for r in rows if r['kind']=='start')['exception_dispatch_version']=2
            elif fault=='legacy-custom':
                next(r for r in rows if r['kind']=='start').pop('exception_dispatch_version')
                for r in rows:r.pop('exception_dispatch',None)
                wanted='analysis_limited'
            try:checked(plan,rows);state='accepted';error=None
            except (ValueError,KeyError,AssertionError)as e:state=failure_status(e);error=str(e)
            reports.append({'mode':mode,'fault':fault,'expected':wanted,'state':state,'passed':state==wanted,'error':error})
    save(out/'results.json',{'checks':reports,'gate':all(x['passed']for x in reports)})
    assert all(x['passed']for x in reports),reports

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.home,a.out)
