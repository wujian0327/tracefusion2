"""Actual JVM ablations on existing independent-source effect-body controls."""
import argparse,json,subprocess
from pathlib import Path
from run_planned_service import ROOT,save,load
from run_query_planner import JARS
from infer_execution_kernel import infer_execution
from run_pruning_cost_audit import ARMS

def run(home,out):
 fixture=ROOT/'artifacts/target-closure-revision-20261103/body-controls-01';agent=home/'build/distributed-observer.jar';plan=fixture/'build/fixture/plan.json';deps=sorted((ROOT/'artifacts/zlt-completion-slice-20261031/locality-sequence-controls-01/libs').glob('*.jar'))
 cp=':'.join(map(str,[fixture/'classes',agent,*deps,*JARS]));out.mkdir(parents=True,exist_ok=False);expected=None;records=[]
 for arm,bits in ARMS.items():
  dest=out/arm;dest.mkdir();cmd=['/usr/lib/jvm/java-8-openjdk-amd64/bin/java','-javaagent:'+str(agent),'-Dservice.plan='+str(plan),'-Dservice.events='+str(dest/'events.jsonl'),'-Dservice.mode=selective']+['-Dservice.'+k+'.observation='+str(v).lower()for k,v in zip(('target','write','body'),bits)]+['-cp',cp,'BodyObservationFixture']
  save(dest/'command.json',cmd);r=subprocess.run(cmd,capture_output=True,text=True);(dest/'stdout.log').write_text(r.stdout);(dest/'stderr.log').write_text(r.stderr);assert r.returncode==0,r.stderr
  business=json.loads(r.stdout.splitlines()[-1]);expected=business if expected is None else expected;assert business==expected
  rows=[json.loads(l)for l in(dest/'events.jsonl').read_text().splitlines()];answers=infer_execution(load(plan),rows)['answers'];checks=[]
  for case in business:
   ret=next(v for v in rows if v['kind']=='binding-return'and v['message']==case['message']);a=next(a for a in answers if a['root_frame']==ret['frame']);assert a['known']==(case['mode']not in(3,7))
   source=next(v for v in rows if v['kind']=='binding-source'and v.get('message')==case['message']);index=next(i for i,v in enumerate(source['fields'])if v['field']=='BodyObservationFixture$Result.message')
   if a['known']:assert set(map(tuple,a['origins']))==(set()if case['mode']==1 else {('field',source['seq'],index)})
   decision=next(v['body_observation']for v in rows if v['kind']=='collection-call-enter'and v.get('body_observation',{}).get('root_frame')==ret['frame']);assert decision['selected']==(bits[2]and case['mode']in(0,5,6))
   checks.append({'case':case['mode'],'known':a['known'],'selected':decision['selected']})
  records.append({'arm':arm,'business_equal':True,'checks':checks,'events':len(rows)})
 save(out/'checks.json',{'records':records,'positive_and_required_unknown_preserved':True});print('Five switch combinations passed independent source and fallback controls')

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--home',required=True,type=Path);p.add_argument('--out',required=True,type=Path);a=p.parse_args();run(a.home.resolve(),a.out.resolve())
