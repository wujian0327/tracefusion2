"""Finite client protocol selection by API shape and actual dependency inventory."""
import json
from pathlib import Path

def attach(plan,model):
 cfg=plan.get('execution_kernel')
 if not cfg or not plan.get('scalar_projection'):return plan
 contract=json.loads(Path(__file__).with_name('feign-input-effect-contracts-20261028.json').read_text());inventory=model.get('library_inventory',{});actual=inventory.get('classes',{})
 if not all(actual.get(c)==h for c,h in contract['class_sha256'].items()):return plan
 jars=set(inventory.get('jar_sha256',{}).values())
 if not set(contract['library_jar_sha256'].values())<=jars:return plan
 calls=[]
 for m in cfg['methods'].values():
  for i in m['instructions']:
   c=model['classes'].get(i.get('owner'))
   if i['op']==185 and c and c['access']&512 and i.get('desc','').startswith('(L') and i['desc'].endswith(';)V') and i['desc'].count(';')==1:calls.append(i['owner']+'.'+i['name']+i['desc'])
 if calls:cfg['feign_input_effects']={**contract,'potential_calls':sorted(set(calls))}
 return plan
