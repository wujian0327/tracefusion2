"""Find the first conservative effect invalidating each actual source version.

Diagnostics only: it inspects TF state and cannot define independent truth.
"""
import argparse,json,sys
from pathlib import Path
from run_planned_service import load,save,sha
from infer_execution_kernel import infer_execution

def run(plan_path,events,out):
 out.mkdir(parents=True,exist_ok=False);digest=sha(events);plan=load(plan_path);rows=[json.loads(s)for s in events.read_text().splitlines()];sources=[(r,f)for r in rows if r['kind']=='binding-source'for f in r['fields']];active={};first={};errors=[]
 def trace(frame,event,arg):
  if frame.f_code.co_filename.endswith('/infer_application_execution.py')and frame.f_code.co_name=='poison':
   parent=frame.f_back;scope=parent.f_locals;lookup=scope.get('lookup');fr=scope.get('fr');call=scope.get('call');seq=frame.f_locals.get('seq')
   if lookup and fr and call and seq:
    if event=='call':
     fields=[]
     for source,field in sources:
      if not source['seq']<call['seq']:continue
      try:value=lookup(field,call['seq'])
      except ValueError as e:errors.append(str(e));continue
      if not value.unknown:fields.append((source,field))
     active[id(frame)]={'fields':fields,'seq':seq,'method':scope.get('entry'),'pc':fr.pc,'callee':scope.get('key'),'call_id':call['call_id'],'frame':fr.invocation}
    elif event=='return':
     record=active.pop(id(frame),None)
     if record:
      for source,field in record.pop('fields'):
       if not lookup(field,seq+1).unknown:continue
       key=(source['seq'],field['owner'],field['field'],field['version']);first.setdefault(key,{**record,'source_seq':source['seq'],'source_callee':source.get('callee'),'source_field':field['field'],'source_path':field['path'],'source_owner':field['owner'],'source_version':field['version']})
  return trace
 try:sys.settrace(trace);result=infer_execution(plan,rows)
 finally:sys.settrace(None)
 assert sha(events)==digest;save(out/'source-first-loss.json',{'diagnostic_only':True,'independent_truth':False,'capture_sha256':digest,'plan_sha256':sha(plan_path),'first_losses':list(first.values()),'lookup_diagnostic_errors':errors,'answers':[{'root':v['root_frame'],'path':v['path'],'known':v['known']}for v in result['answers']]})
 print({'first_losses':len(first),'groups':sorted({(x['method'],x['pc'],x['callee'])for x in first.values()},key=str)},flush=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--events',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.plan.resolve(),a.events.resolve(),a.out.resolve())
