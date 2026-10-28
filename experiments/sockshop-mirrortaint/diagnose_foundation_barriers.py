#!/usr/bin/env python3
"""Observe state before/after opaque effects; never used as an oracle or answer."""
import argparse,json,sys
from pathlib import Path
from run_planned_service import load,save,sha
from infer_execution_kernel import infer_execution

def run(plan_path,events,out):
 out.mkdir(parents=True);plan=load(plan_path);digest=sha(events);rows=[json.loads(l)for l in events.open()];records=[];entered={r['frame']:r for r in rows if r['kind']=='enter'}
 def observe(frame,event,arg):
  if frame.f_code.co_filename.endswith('/infer_application_execution.py')and frame.f_code.co_name=='poison':
   parent=frame.f_back;scope=parent.f_locals;call=scope.get('call');key=scope.get('key');lookup=scope.get('lookup');fr=scope.get('fr')
   if call is not None and lookup is not None and fr is not None:
    if event=='call':
     fields=[f for r in rows if r['kind']=='binding-opaque-touch'and r.get('frame')==fr.invocation and r.get('callee')==key and call['seq']<r['seq']<frame.f_locals['seq']for f in r['fields']]
     # Only the current call's touches, not earlier same-site invocations.
     owners={f['owner']for f in fields};fields=list({(f['owner'],f['field'],f['version']):f for f in fields}.values())
     values=[]
     for f in fields:
      value=lookup(f,call['seq']);values.append({'coordinate':f,'known':not value.unknown,'origins':[list(v)for v in sorted(value.origins,key=str)]})
     records.append({'method':scope.get('entry'),'pc':fr.pc,'callee':key,'call_id':call['call_id'],'call_seq':call['seq'],'effect_seq':frame.f_locals['seq'],'before':values,'_fields':fields})
    elif event=='return'and records and records[-1].get('call_id')==call['call_id']:
     record=records[-1];record['after']=[]
     for f in record.pop('_fields',[]):
      value=lookup(f,record['effect_seq']+1);record['after'].append({'coordinate':f,'known':not value.unknown,'origins':[list(v)for v in sorted(value.origins,key=str)]})
  return observe
 try:sys.settrace(observe);result=infer_execution(plan,rows)
 finally:sys.settrace(None)
 assert sha(events)==digest;save(out/'state-transitions.json',{'diagnostic_only':True,'not_independent_truth_or_certified_other_field_answers':True,'plan_sha256':sha(plan_path),'capture_sha256':digest,'transitions':records,'actual_query_answer_states':[{'root':a['root_frame'],'path':a['path'],'known':a['known']}for a in result['answers']]});print([(r['pc'],r['callee'],[(v['coordinate']['path'],v['known'])for v in r['before']])for r in records[:3]])
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--events',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.plan.resolve(),a.events.resolve(),a.out.resolve())
