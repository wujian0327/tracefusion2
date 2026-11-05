"""Perturb complete derived copies; no original capture is edited."""
import argparse,copy,json
from pathlib import Path
from run_planned_service import load,save,sha
from infer_distributed_fields import Reconstruction

def run(home,out):
    out.mkdir(parents=True,exist_ok=False);checks=[];hashes={}
    for mode in ('full','selective'):
        base=home/'final-C1';q='ruoyi-2';p=base/'runs'/q/mode/'capture/events.jsonl';hashes[str(p)]=sha(p)
        rows=[json.loads(x)for x in p.read_text().splitlines()]
        chosen=next(r for r in load(home/'audit-final-03/instances.json')if r['query']==q and r['mode']==mode and r['state']=='known_correct')
        source_seq=chosen['expected'][0][2];message=next(r for r in load(base/'runs'/q/mode/'result.json')['cases']if r['case']==chosen['case'])['message']
        faults=('missing-source-fields','ambiguous-source-field','wrong-source-call','wrong-source-pc','missing-before-step','duplicate-step-reference','transparent-before','sticky-invalid')
        for fault in faults:
            changed=copy.deepcopy(rows);source=next(r for r in changed if r['seq']==source_seq)
            dispatch=next(r for r in changed if r['kind']=='execution-direct-dispatch'and r.get('before_only')and r['frame']==next(r for r in changed if r['kind']=='binding-return'and r['message']==message)['frame'])
            if fault=='missing-source-fields':source['fields']=[]
            elif fault=='ambiguous-source-field':source['fields'].append(copy.deepcopy(next(f for f in source['fields']if f['owner']==chosen['target_coordinate']['owner']and f['field']==chosen['target_coordinate']['field'])))
            elif fault=='wrong-source-call':source['source_call_id']=-100
            elif fault=='wrong-source-pc':source['source_pc']+=100
            elif fault=='missing-before-step':next(r for r in changed if r['seq']==dispatch['before_steps'][-1])['kind']='diagnostic-missing-before'
            elif fault=='duplicate-step-reference':dispatch['before_steps'].append(dispatch['before_steps'][-1])
            elif fault=='transparent-before':dispatch['empty_chain']=True
            else:next(r for r in changed if r['kind']=='metrics')['capture_invalid']=True
            d=out/mode/fault;(d/'build/role').mkdir(parents=True);(d/'capture/role').mkdir(parents=True)
            (d/'build/role/plan.json').write_bytes((base/'plans'/q/'plan.json').read_bytes());(d/'capture/role/events.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n'for r in changed))
            try:
                graph=Reconstruction(d/'build',d/'capture',['role']);answer=graph.query(message,chosen['path'],'role',boundary=[{'kind':'binding-source'},{'kind':'argument'}]);assert not answer['known'],fault;state='unknown'
            except ValueError as e:state='rejected';reason=str(e)
            checks.append({'mode':mode,'fault':fault,'state':state,'reason':reason if state=='rejected'else None,'affected_originally_known_target':chosen['path']})
    for n,v in hashes.items():assert sha(Path(n))==v
    save(out/'checks.json',{'checks':checks,'original_hashes_unchanged':hashes});print(checks)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.home.resolve(),a.out.resolve())
