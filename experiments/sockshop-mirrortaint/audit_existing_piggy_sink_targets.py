#!/usr/bin/env python3
"""Check whether OLD facts define sink targets; do NOT invent sink answers."""
import copy
from pathlib import Path
from run_planned_service import ROOT,load,save,sha
FIRST=ROOT/'artifacts/portability-first-20261028'

def verify(f,rows):
 byseq={r['seq']:r for r in rows};snap=byseq[f['snapshot_seq']]
 begin=[r for r in rows if r['kind']=='collection-call-enter'and r['call_id']==f['call_id']];assert len(begin)==1
 call=begin[0];assert call['frame']==f['call_frame']and call['pc']==f['call_pc']and'.AccountRepository.save('in call['callee']
 ends=[r for r in rows if r['kind']=='collection-call-exit'and r['call_id']==f['call_id']];assert len(ends)==1
 assert call['args'][0]['object']==f['save_argument_object']and call['seq']<snap['seq']<ends[0]['seq']
 assert snap['message']==f['message']and snap['frame']==call['frame']and snap['callee']==call['callee']
 fields=[v for v in snap['fields']if v['path']==f['path']and all(v[k]==f['target_coordinate'][k]for k in('owner','field','version'))];assert len(fields)==1
 return {'kind':'call-argument-field','message':f['message'],'call_id':f['call_id'],'caller_frame':f['call_frame'],'pc':f['call_pc'],'argument':0,'path':f['path'],**f['target_coordinate'],'snapshot_seq':f['snapshot_seq'],'phase':'before-invoke','source_answer':None}

def run(out):
 out.mkdir(parents=True,exist_ok=False);facts=load(FIRST/'piggy-save-fact-supplement-01/pre-save-raw-facts.json');cache={};targets=[]
 for f in facts:
  path=FIRST/'tool-runs/piggymetrics-2'/f['mode']/'query-011/capture/events.jsonl';assert sha(path)==f['raw_capture_sha256']
  if f['mode']not in cache:cache[f['mode']]=[__import__('json').loads(v)for v in path.open()]
  targets.append({'mode':f['mode'],**verify(f,cache[f['mode']])})
 assert len(targets)==72
 guards={}
 for name in('wrong-call','wrong-object','wrong-field-version','wrong-message','duplicate-coordinate'):
  f=copy.deepcopy(facts[0]);rows=copy.deepcopy(cache[f['mode']])
  if name=='wrong-call':f['call_id']=-1
  elif name=='wrong-object':f['save_argument_object']='different-same-value-entity'
  elif name=='wrong-field-version':f['target_coordinate']['version']+=1
  elif name=='wrong-message':f['message']='other-request'
  else:row=next(r for r in rows if r['seq']==f['snapshot_seq']);row['fields'].append(copy.deepcopy(next(v for v in row['fields']if v['path']==f['path'])))
  try:verify(f,rows)
  except AssertionError:guards[name]=True
  else:raise AssertionError('Accepted wrong sink coordinate '+name)
 save(out/'target-definitions.json',targets);save(out/'summary.json',{'all_passed':True,'physical_targets_per_mode':36,'fields_per_request':9,'normal_requests_per_mode':4,'missing_currency_targets_per_mode':4,'guards':guards,'extra_collection_required_for_these36':False,'frozen_TF_sink_query_interface':'target_binding_unsupported','required_next_core_interface':'Expose dependency state at the actual call argument before the save effect; do not substitute returned-field answers or make the sink a source. New version required.','raw_facts_not_source_answers':True,'raw_files_unmodified':True})
 print({'targets_defined_per_mode':36,'additional_collection_for_these36':False,'source_answers_claimed':0})
if __name__=='__main__':run(ROOT/'artifacts/external-frozen-transfer-20261029/piggy-existing-sink-audit')
