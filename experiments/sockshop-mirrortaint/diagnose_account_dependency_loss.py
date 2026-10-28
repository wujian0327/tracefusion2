#!/usr/bin/env python3
"""Observe the frozen replay's first barriers. Does not change propagation.
Diagnostic only: no trace result is passed back as an answer or oracle.
"""
import argparse,sys,json
from pathlib import Path
from run_planned_service import ROOT,load,save,sha
from infer_application_execution import infer_application

def run(root,out):
 out.mkdir(parents=True);records=[]
 for index in (11,12,16,14):
  plan=load(root/'planning-first/piggymetrics-2'/('%03d-plan.json'%index));file=root/'tool-runs/piggymetrics-2/full'/('query-%03d'%index)/'capture/events.jsonl';digest=sha(file);rows=[json.loads(l)for l in file.open()];trace=[]
  def observe(frame,event,arg):
   code=frame.f_code
   if code.co_filename.endswith('/infer_application_execution.py'):
    parent=frame.f_back;state=parent.f_locals if parent else {};name=code.co_name;locals_=frame.f_locals
    if event=='call'and name=='poison':trace.append({'kind':'opaque_barrier','seq':locals_.get('seq'),'method':state.get('entry'),'pc':getattr(state.get('fr'),'pc',None)})
    if event=='call'and name=='write_field'and locals_.get('w',{}).get('field')==plan['target']:
     v=locals_['v'];trace.append({'kind':'target_field_write','field':plan['target'],'method':state.get('entry'),'pc':getattr(state.get('fr'),'pc',None),'write':locals_['w'],'dependency_already_unknown':v.unknown,'origin_count':len(v.origins)})
    if event=='return'and name=='lookup'and locals_.get('f',{}).get('field')==plan['target']:
     trace.append({'kind':'target_field_lookup','field':locals_['f'],'before_seq':locals_['before'],'unknown':getattr(arg,'unknown',None),'has_interpreted_write':tuple((locals_['f'][k]for k in ('owner','field','version')))in locals_.get('state',{}).fields if 'state'in locals_ else None})
   return observe
  try:sys.settrace(observe);answer=infer_application(plan,rows)
  finally:sys.settrace(None)
  assert sha(file)==digest
  record={'query_index':index,'path':plan['response_binding']['path'],'target':plan['target'],'first_capture_sha256':digest,'trace':trace,'answer_states':[{'root':a['root_frame'],'known':a['known']}for a in answer['answers']]};records.append(record);save(out/('query-%03d.json'%index),record)
 save(out/'summary.json',{'diagnostic_only':True,'semantic_changes':False,'records':records});print([(r['path'],len(r['trace']),r['answer_states'])for r in records])
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--first',type=Path,default=ROOT/'artifacts/portability-first-20261028');p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.first.resolve(),a.out.resolve())
