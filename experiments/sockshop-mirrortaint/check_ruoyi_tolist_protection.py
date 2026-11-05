"""Perturb complete dictionary copies; originals remain immutable."""
import argparse,copy,json
from pathlib import Path
from run_planned_service import load,save,sha
from infer_distributed_fields import Reconstruction

def run(home,out):
 out.mkdir(parents=True,exist_ok=False);checks=[];hashes={}
 for mode in('full','selective'):
  raw=home/'final-C1/runs/ruoyi-3'/mode/'capture/events.jsonl';hashes[str(raw)]=sha(raw);rows=[json.loads(s)for s in raw.read_text().splitlines()]
  chosen=next(r for r in load(home/'dictionary-final-score/instances.json')if r['mode']==mode and r['state']=='known_correct');seq=chosen['expected'][0][2];message=load(home/'final-C1/runs/ruoyi-3'/mode/'result.json')['cases'][chosen['case']]['message']
  for fault in('missing-cache','duplicate-cache','wrong-cache-call','wrong-target-class','wrong-member-identity','certificate-ineligible','missing-certificate','missing-source','ambiguous-source','wrong-source-call','wrong-source-version','sticky-invalid'):
   changed=copy.deepcopy(rows);source=next(r for r in changed if r['seq']==seq)
   source_owners={r['owner']for r in changed if r['seq']in source['json_tree_proofs']and r['class']=='com/alibaba/fastjson2/JSONArray'}
   calls=[r for r in changed if r['kind']=='collection-call-enter'and '.toList('in r['callee']and r.get('receiver',{}).get('object')in source_owners and r['seq']>seq]
   assert len(calls)==1,'Actual source container must identify a unique subsequent typed-list invocation'
   end=next(r for r in changed if r['kind']=='collection-call-exit'and r['call_id']==calls[0]['call_id']);proof=end['json_list_copy'];assert proof['valid'];hit=next(r for r in changed if r['seq']==proof['cache_seq'])
   if fault=='missing-cache':hit['kind']='diagnostic-missing-cache'
   elif fault=='duplicate-cache':changed.insert(changed.index(hit),copy.deepcopy(hit))
   elif fault=='wrong-cache-call':hit['call_id']=-1
   elif fault=='wrong-target-class':hit['target_class']='wrong'
   elif fault=='wrong-member-identity':proof['members'][0]=copy.deepcopy(proof['members'][1])
   elif fault=='certificate-ineligible':proof['valid']=False
   elif fault=='missing-certificate':end.pop('json_list_copy')
   elif fault=='missing-source':source['fields']=[]
   elif fault=='ambiguous-source':source['fields'].append(copy.deepcopy(next(f for f in source['fields']if f['owner']==chosen['target_coordinate']['owner']and f['field']==chosen['target_coordinate']['field'])))
   elif fault=='wrong-source-call':source['source_call_id']=-1
   elif fault=='wrong-source-version':next(f for f in source['fields']if f['owner']==chosen['target_coordinate']['owner']and f['field']==chosen['target_coordinate']['field'])['version']+=1
   else:next(r for r in changed if r['kind']=='metrics')['capture_invalid']=True
   d=out/mode/fault;(d/'build/role').mkdir(parents=True);(d/'capture/role').mkdir(parents=True);(d/'build/role/plan.json').write_bytes((home/'final-C1/plans/ruoyi-3/plan.json').read_bytes());(d/'capture/role/events.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n'for r in changed))
   try:
    graph=Reconstruction(d/'build',d/'capture',['role']);answer=graph.query(message,chosen['path'],'role',boundary=[{'kind':'binding-source'},{'kind':'argument'}]);assert not answer['known'],fault;state='unknown';reason=None
   except ValueError as e:state='rejected';reason=str(e)
   checks.append({'mode':mode,'fault':fault,'state':state,'reason':reason})
 assert all(sha(Path(p))==h for p,h in hashes.items());save(out/'checks.json',{'checks':checks,'original_hashes_unchanged':hashes});print(checks)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.home.resolve(),a.out.resolve())
