"""Trace the unchanged reference interpreter's lookup work; never formal timing."""
import argparse,collections,json,sys
from pathlib import Path
from measure_shared_work_revision import worker

def run(home,task,mode,out):
 repo=home/'old-repository';source=repo/'experiments/sockshop-mirrortaint/infer_application_execution.py';lines=source.read_text().splitlines()
 points={i+1:('source_start'if 'starts=[r for r in relevant' in s else'source_finish'if 'finishes=[r for r in relevant' in s else'render')for i,s in enumerate(lines)if 'starts=[r for r in relevant' in s or'finishes=[r for r in relevant' in s or'events[pos:]'in s}
 counts=collections.Counter();scopes=collections.Counter()
 def trace(frame,event,arg):
  if event=='line'and not frame.f_code.co_name.startswith('<')and frame.f_code.co_filename==str(source)and frame.f_lineno in points:
   kind=points[frame.f_lineno];v=frame.f_locals;counts[kind+'_lookups']+=1
   counts[kind+'_candidate_slots']+=len(v['relevant'])if kind!='render'else len(v['events'])-v['pos']
   if kind=='render':scopes[str(v.get('key'))]+=1
  return trace
 sys.settrace(trace)
 try:worker(home/'protocol-before-change.json',task,mode,repo,out,False)
 finally:sys.settrace(None)
 (out/'lookup-work.json').write_text(json.dumps({'diagnostic_only':True,'counts':counts,'render_call_targets':scopes,'line_map':points},indent=2)+'\n')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);p.add_argument('--task',required=True);p.add_argument('--mode',required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.home.resolve(),a.task,a.mode,a.out.resolve())
