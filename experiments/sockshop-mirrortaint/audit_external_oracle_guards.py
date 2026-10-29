#!/usr/bin/env python3
"""Check instance-oracle ambiguity guards, without consuming predictions."""
import copy,json
from pathlib import Path
from run_planned_service import ROOT,load,save,sha
import external_transfer_oracle as oracle
HOME=ROOT/'artifacts/external-frozen-transfer-20261029'

def run(out):
 out.mkdir(exist_ok=False);capture=HOME/'ae7fe8d/tool-runs/apollo-1/mirrortaint/fixed-adapter/capture/native-capability.jsonl'
 rows=[json.loads(line)for line in capture.open()]
 # Labels are intentionally removed before any expected answer is computed.
 for r in rows:
  for f in r.get('fields',[]):f.pop('native_ids',None);f.pop('tag_present',None)
 ret=next(r for r in rows if r['kind']=='target');rule=oracle.rule(load(HOME/'oracle-before-tools.json'),'apollo-1','/baseInfo/appId');expected=oracle.native_expected(rows,ret['root'],rule,'/baseInfo/appId');assert len(expected)==1
 guards={}
 def rejects(name,run):
  try:run()
  except ValueError:guards[name]=True
  else:raise AssertionError('Accepted '+name)
 source=next(r for r in rows if r['kind']=='source'and r['root']==ret['root']and r['ordinal']==expected[0][1]);field=next(f for f in source['fields']if f['path']=='/body/appId')
 rejects('wrong-root',lambda:oracle.native_expected(rows,'different-request',rule,'/baseInfo/appId'))
 duplicate=copy.deepcopy(source);duplicate['ordinal']+=100
 rejects('same-object-same-value-second-call',lambda:oracle.native_expected(rows+[duplicate],ret['root'],rule,'/baseInfo/appId'))
 missing=copy.deepcopy(rows);r=next(r for r in missing if r['kind']=='source'and r['root']==source['root']and r['ordinal']==source['ordinal']);next(f for f in r['fields']if f['path']=='/body/appId').pop('version')
 rejects('missing-field-version',lambda:oracle.native_expected(missing,ret['root'],rule,'/baseInfo/appId'))
 duplicate_fields=copy.deepcopy(rows);r=next(r for r in duplicate_fields if r['kind']=='source'and r['root']==source['root']and r['ordinal']==source['ordinal']);r['fields'].append(copy.deepcopy(field))
 rejects('ambiguous-physical-field',lambda:oracle.native_expected(duplicate_fields,ret['root'],rule,'/baseInfo/appId'))
 tf_source={'seq':2,'kind':'binding-source','frame':'f1','callee':source['call'],'fields':source['fields']};tf_ret={'seq':3,'kind':'binding-return','frame':'f1'}
 tf=[{'seq':1,'kind':'enter','frame':'f1','parent':None},tf_source,tf_ret,{'seq':4,'kind':'metrics','capture_invalid':False}]
 oracle.require_complete_raw_capture(tf);want=oracle.tf_expected(tf,tf_ret,rule,'/baseInfo/appId');assert want[0][2]==2
 extra=copy.deepcopy(tf_source);extra['seq']=3
 rejects('TF-repeated-same-object-read',lambda:oracle.tf_expected(tf+[extra],tf_ret,rule,'/baseInfo/appId'))
 rejects('missing-footer',lambda:oracle.require_complete_raw_capture(tf[:-1]))
 broken=copy.deepcopy(tf);broken[-1]['capture_invalid']=True
 rejects('sticky-invalid-footer',lambda:oracle.require_complete_raw_capture(broken))
 broken=copy.deepcopy(tf);broken[1]['kind']='problem'
 rejects('problem-even-with-clean-footer',lambda:oracle.require_complete_raw_capture(broken))
 broken=copy.deepcopy(tf);broken[1]['seq']=1
 rejects('duplicate-sequence',lambda:oracle.require_complete_raw_capture(broken))
 assert oracle.targets({'items':None})==[('/items',None)]
 assert oracle.targets({'items':[]})==[]
 assert not oracle.original_root_returns({'api':'mall-swarm-2','http_status':200,'response':{'code':500,'message':'duplicate'}})
 assert oracle.original_root_returns({'api':'mall-swarm-4','http_status':200,'response':{'code':500,'message':'invalid parameters'}})
 guards.update(actual_null_field_retained=True,empty_list_has_no_elements=True,handler_HTTP200_not_root_return=True,normal_failed_wrapper_not_filtered=True)
 assert not oracle.original_root_returns({'api':'mall-swarm-3','http_status':200,'body':{'password':'wrong'},'response':{'code':404}})
 assert oracle.original_root_returns({'api':'mall-swarm-3','http_status':200,'body':{'username':'test','password':'wrong'},'response':{'code':500}})
 guards.update(admin_missing_username_is_preentry_validation=True,admin_valid_body_failed_RPC_not_filtered=True)
 save(out/'checks.json',{'all_passed':True,'guards':guards,'truth_without_labels_or_TF_graph':True,'actual_original_capture_sha256':sha(capture),'new_business_targets':0})
 print({'guards':len(guards),'all_passed':True},flush=True)

if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=HOME/'independent-oracle-guards-01');a=p.parse_args();run(a.out.resolve())
