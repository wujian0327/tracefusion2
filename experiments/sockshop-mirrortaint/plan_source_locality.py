"""Plan birth/nonpublication obligations independently of provenance labels."""
import json
from pathlib import Path

def attach(plan,model):
 cfg=plan['execution_kernel'];profile=Path(__file__).with_name('source-locality-contracts-20261030.json')
 if not profile.exists():return plan
 contract=json.loads(profile.read_text());inventory=model.get('library_inventory',{}).get('classes',{})
 required=['feign/SynchronousMethodHandler','feign/AsyncResponseHandler','org/springframework/http/converter/json/AbstractJackson2HttpMessageConverter','com/fasterxml/jackson/databind/deser/std/UntypedObjectDeserializer$Vanilla']
 if any(inventory.get(k)!=contract['class_sha256'].get(k)for k in required):return plan
 # A proof is optional precision, never a reason to load mismatched contracts.
 if any(k in inventory and inventory[k]!=v for k,v in contract['class_sha256'].items()):return plan
 beans={}
 for key,birth in cfg.get('decoder_birth_sites',{}).items():
  owner=key.split('.')[0];fields=[f for f in model['classes'][owner]['fields']if not f['access']&8]
  if model['classes'][owner]['super']!='java/lang/Object'or any(f['desc']not in ('J','I','Z','Ljava/lang/String;','Ljava/lang/Object;')for f in fields):continue
  m=model['methods'][key]
  if [i['op']for i in m['instructions']]!=[25,183,177]:continue
  props=plan['json_schema'].get(owner,[])
  if {p['field']for p in props}!={owner+'.'+f['name']for f in fields}:continue
  if any(not any(s['field']==p['field']for s in plan['collection_setters'].values())for p in props):continue
  beans[owner]={'class_sha256':model['classes'][owner]['sha256'],'fields':[{'field':owner+'.'+f['name'],'descriptor':f['desc']}for f in fields]}
 if beans:cfg['source_locality']={**contract,'beans':beans}
 return plan
