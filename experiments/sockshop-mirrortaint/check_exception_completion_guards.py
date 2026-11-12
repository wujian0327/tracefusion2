"""Guard necessity and evidence integrity; derived copies never replace raw logs."""
import argparse,copy,json
from pathlib import Path
from run_planned_service import load,save
from run_public_control_semantics import checked
from analysis_status import failure_status


def run(home,out):
    out.mkdir(parents=True,exist_ok=False);plan=load(home/'plan.json');reports=[]
    faults={k:'unknown'for k in ['missing-condition','duplicate-condition','condition-version-gap','missing-null-guard','missing-index-guard','missing-needed-data']}
    faults.update({k:'correct-known'for k in ['missing-ignored-payload','missing-stored-payload-on-bounds']})
    faults.update({k:'evidence_invalid'for k in ['source-call','source-PC','source-caller','missing-branch','duplicate-branch','wrong-branch-result','wrong-branch-PC','wrong-branch-frame','missing-callee-abort','duplicate-callee-abort','wrong-parent','wrong-original-exception','missing-catch','wrong-catch-object','wrong-array-exception','sticky']})
    for mode in ['full','static','selective']:
        original=[json.loads(l)for l in(home/mode/'events.jsonl').read_text().splitlines()];truth=load(home/mode/'truth-before-prediction.json')
        for fault,wanted in faults.items():
            scenario,n=(1,0)if fault=='missing-ignored-payload'else(8,1)if fault in('missing-stored-payload-on-bounds','missing-index-guard','wrong-array-exception')else(4,0)if fault=='missing-null-guard'else(0,1)
            t=next(t for t in truth if t['scenario']==scenario and t['input']==n);rows=copy.deepcopy(original)
            root=next(r['frame']for r in rows if r['kind']=='binding-return'and r['message']==t['message'])
            role='11.value'if fault in('missing-ignored-payload','missing-needed-data')else'11.nullable'if fault=='missing-stored-payload-on-bounds'else'30.nullable'if fault=='missing-null-guard'else'20.value'
            fact=next(r for r in t['raw']if r['role']==role);token=fact['token'];source=next(r for r in rows if r['seq']==token[1]);field=source['fields'][token[2]]
            if fault.startswith('missing-')and fault in('missing-condition','missing-null-guard','missing-index-guard','missing-ignored-payload','missing-stored-payload-on-bounds','missing-needed-data'):source['fields'].pop(token[2])
            elif fault=='duplicate-condition':source['fields'].append(copy.deepcopy(field))
            elif fault=='condition-version-gap':field['version']+=99
            elif fault=='source-call':source['source_call_id']=-1
            elif fault=='source-PC':source['source_pc']+=999
            elif fault=='source-caller':source['source_caller_method']='bad'
            elif fault=='sticky':next(r for r in rows if r['kind']=='metrics')['capture_invalid']=True
            elif fault=='wrong-array-exception':next(r for r in rows if r['kind']=='execution-array-throw'and r['seq']>source['seq'])['exception_type']='java.lang.NullPointerException'
            else:
                begin=next(r for r in rows if r['kind']=='enter'and r.get('parent')==root and '.writeThenThrow('in r['method'])
                aborted=next(r for r in rows if r['kind']=='abort'and r.get('frame')==begin['frame'])
                branch=next(r for r in rows if r['kind']=='branch'and r.get('frame')==begin['frame'])
                caught=next(r for r in rows if r['kind']=='collection-catch'and r['frame']==root)
                failure=next(r for r in rows if r['kind']=='collection-call-throw'and r['frame']==root)
                if fault=='missing-branch':rows.remove(branch)
                elif fault=='duplicate-branch':rows.insert(rows.index(branch),copy.deepcopy(branch))
                elif fault=='wrong-branch-result':branch['taken']=not branch['taken']
                elif fault=='wrong-branch-PC':branch['site']=branch['site'].rsplit('@',1)[0]+'@9999'
                elif fault=='wrong-branch-frame':branch['frame']='bad'
                elif fault=='missing-callee-abort':rows.remove(aborted)
                elif fault=='duplicate-callee-abort':rows.insert(rows.index(aborted),copy.deepcopy(aborted))
                elif fault=='wrong-parent':begin['parent']='bad'
                elif fault=='wrong-original-exception':failure['exception']['object']='bad'
                elif fault=='missing-catch':rows.remove(caught)
                elif fault=='wrong-catch-object':caught['observed']['object']='bad'
            for i,r in enumerate(rows,1):r['seq']=i
            try:
                p=checked(plan,rows);a=next(a for a in p['answers']if a['root_frame']==root and a['path']=='/value')
                state='unknown'if not a['known']else'correct-known'if set(map(tuple,a['origins']))==set(map(tuple,t['origins']))and set(map(tuple,a['selectors']))==set(map(tuple,t['selectors']))else'incorrect-known'
                error=None
            except (ValueError,KeyError,AssertionError)as e:state=failure_status(e);error=str(e)
            reports.append({'mode':mode,'fault':fault,'scenario':scenario,'input':n,'expected':wanted,'state':state,'passed':state==wanted,'error':error})
    save(out/'results.json',{'checks':reports,'gate':all(c['passed']for c in reports)})
    print(json.dumps({'checks':len(reports),'gate':all(c['passed']for c in reports),'failed':[c for c in reports if not c['passed']]}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.home.resolve(),a.out.resolve())
