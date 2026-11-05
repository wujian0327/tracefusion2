"""Check the model's existing-member dependencies independently of final DTO queries."""
import argparse,copy,json
from collections import defaultdict
from pathlib import Path
from run_planned_service import load,save
from execution_dependency_state import State,Frame,Value,Container
from infer_json_list_copy import transfer

def run(home,out):
 out.mkdir(parents=True,exist_ok=False);checks=[];plan=load(home/'plan.json')
 for mode in('full','selective'):
  rows=[json.loads(s)for s in(home/mode/'events.jsonl').read_text().splitlines()];index=defaultdict(list)
  for r in rows:
   if r['kind']=='json-list-class':index[(r['kind'],r['class'])].append(r)
   elif r['kind']=='json-list-initialized':index[(r['kind'],r['seq'])].append(r)
   elif r['kind']=='json-list-cache':index[(r['kind'],r['call_id'])].append(r)
  end=next(r for r in rows if r.get('json_list_copy',{}).get('valid'));call=next(r for r in rows if r['kind']=='collection-call-enter'and r['call_id']==end['call_id']);root=next(r for r in rows if r['kind']=='enter'and r['frame']==call['frame']);owner=call['receiver']['object']
  for unknown in (False,True):
   state=State(Frame(root['frame']));members=[Value(v,frozenset({('member',i)}),frozenset({('choice',i)}),unknown and i==0)for i,v in enumerate(call['collection'])];state.containers[owner]=Container(owner,members,call['collection_epoch'],False)
   result=transfer(plan,index,root,call,end,Value(call['receiver']),[Value(v)for v in call['args']],state,lambda v:v.observed)
   copied=state.containers[result.observed['object']]
   assert copied.elements==members and state.containers[owner].elements==members
   assert copied.local is False  # Identity copying is not a locality certificate.
   checks.append({'mode':mode,'first_member_unknown':unknown,'member_origins_selectors_unknown_and_identity_preserved':True,'no_private_ownership_claim':True})
 save(out/'checks.json',checks)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.home.resolve(),a.out.resolve())
