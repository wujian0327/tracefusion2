"""Faults in derived copies; original captures are never modified."""
import argparse,copy,json
from pathlib import Path
from run_planned_service import save,load
from run_public_control_semantics import checked
from analysis_status import failure_status


def run(home,out):
    out.mkdir(parents=True,exist_ok=False);plan=load(home/'plan.json');reports=[]
    expected={k:'unknown'for k in ('missing-condition','ambiguous-condition','condition-version-gap')}
    expected.update({k:'evidence_invalid'for k in ('source-call','source-PC','source-caller','branch-missing','branch-duplicate','branch-result','branch-Frame','branch-PC','parent-call','link-object','link-version','link-write-missing','sticky')})
    for mode in ('full','static','selective'):
        rows=[json.loads(x)for x in(home/mode/'events.jsonl').read_text().splitlines()]
        t=next(t for t in load(home/mode/'truth-before-prediction.json')if t['scenario']==1 and t['input']==0)
        root=next(r['frame']for r in rows if r['kind']=='binding-return'and r['message']==t['message'])
        for fault,wanted in expected.items():
            altered=copy.deepcopy(rows);token=t['selectors'][0]
            source=next(r for r in altered if r['seq']==token[1]);field=source['fields'][token[2]]
            read=next(r for r in altered if r['kind']=='read'and r['frame']==root and r['owner']==field['owner']and r['field']==field['field']and r['seq']>source['seq'])
            branch=next(r for r in altered if r['kind']=='branch'and r['frame']==root and r['seq']>read['seq'])
            link=next(r for r in altered if r['kind']=='write'and r.get('field')=='CallWriteFootprintFixture$Holder.child'and r['frame']==root and source['seq']<r['seq']<branch['seq'])
            if fault=='missing-condition':source['fields'].pop(token[2])
            elif fault=='ambiguous-condition':source['fields'].append(copy.deepcopy(field))
            elif fault=='condition-version-gap':field['version']+=100
            elif fault=='source-call':source['source_call_id']=-999
            elif fault=='source-PC':source['source_pc']+=999
            elif fault=='source-caller':source['source_caller_method']='bad'
            elif fault=='branch-missing':altered.remove(branch)
            elif fault=='branch-duplicate':altered.insert(altered.index(branch),copy.deepcopy(branch))
            elif fault=='branch-result':branch['taken']=not branch['taken']
            elif fault=='branch-Frame':branch['frame']='bad'
            elif fault=='branch-PC':branch['site']=branch['site'].rsplit('@',1)[0]+'@9999'
            elif fault=='parent-call':next(r for r in altered if r['kind']=='enter'and r.get('parent')and r['seq']>source['seq'])['parent']='bad'
            elif fault=='link-object':link['observed']['object']='bad'
            elif fault=='link-version':link['version']=0
            elif fault=='link-write-missing':altered.remove(link)
            elif fault=='sticky':next(r for r in altered if r['kind']=='metrics')['capture_invalid']=True
            for seq,r in enumerate(altered,1):r['seq']=seq
            try:
                prediction=checked(plan,altered)
                answer=next(a for a in prediction['answers']if a['root_frame']==root and a['path']=='/value')
                state='incorrect_known'if answer['known']else'unknown';error=None
            except (ValueError,KeyError,AssertionError)as e:state=failure_status(e);error=str(e)
            reports.append({'mode':mode,'fault':fault,'expected':wanted,'state':state,'passed':wanted==state,'error':error})
    save(out/'results.json',{'checks':reports,'gate':all(r['passed']for r in reports)})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.home.resolve(),a.out.resolve())
