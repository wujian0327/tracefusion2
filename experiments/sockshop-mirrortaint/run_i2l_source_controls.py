"""Actual JVM I2L, observation-only sources, damaged-evidence controls."""
import argparse,copy,json
from pathlib import Path
from zipfile import ZipFile
from run_query_planner import command,JARS
from run_planned_service import HERE,load,save,sha
from build_distributed_plans import build
from plan_response_binding import plan_response
from infer_execution_kernel import infer_execution
from infer_source_observation import validate
from execution_dependency_state import Value,i2l

def run(out):
 out.mkdir(parents=True,exist_ok=False);classes=out/'classes';classes.mkdir();java='/usr/lib/jvm/java-8-openjdk-amd64/bin/java';javac=java[:-4]+'javac'
 agent=HERE.parents[1]/'artifacts/offline-zlt-revision-20261031/candidate-build-01/distributed-observer.jar'
 command([javac,'-cp',':'.join(map(str,[agent,*JARS])),'-d',str(classes),str(HERE/'I2LSourceFixture.java')],out/'compile.log');jar=out/'fixture.jar'
 with ZipFile(jar,'w')as z:
  for p in classes.glob('I2LSourceFixture*.class'):z.write(p,'BOOT-INF/classes/'+p.name)
 source='I2LSourceFixture$Source.read()LI2LSourceFixture$Box;';entry=lambda name:'I2LSourceFixture.'+name+'(LI2LSourceFixture$Input;)LI2LSourceFixture$Result;'
 b=out/'build';build(b,{'fixture':{'jar':str(jar),'entry':entry('root'),'targets':['I2LSourceFixture$Result.value'],'response_path':'/value','execution_kernel':True,'application_calls':True,'source_calls':[source]}});model=load(b/'fixture/model.json');cp=':'.join(map(str,[classes,b/'distributed-observer.jar',*JARS]));reports={}
 for task in ('root','unknown','observation'):
  plan=plan_response(model,entry(task),'I2LSourceFixture$Result.value','/value',execution_kernel=True,application_calls=True,source_calls=[source]);save(out/(task+'-plan.json'),plan)
  args=[]if task=='root'else[task];baseline=command([java,'-cp',cp,'I2LSourceFixture',*args],out/(task+'-baseline.log'));expected=json.loads(baseline.stdout.splitlines()[-1])
  for mode in ('full','selective'):
   cap=out/(task+'-'+mode);cap.mkdir();command([java,'-javaagent:'+str(b/'distributed-observer.jar'),'-Dservice.plan='+str(out/(task+'-plan.json')),'-Dservice.events='+str(cap/'events.jsonl'),'-Dservice.mode='+mode,'-cp',cp,'I2LSourceFixture',*args],cap/'stdout.log');actual=json.loads((cap/'stdout.log').read_text().splitlines()[-1]);assert actual==expected
   rows=[json.loads(s)for s in(cap/'events.jsonl').read_text().splitlines()];assert not any(r['kind']=='problem'for r in rows),[r for r in rows if r['kind']=='problem'];answers=infer_execution(plan,rows)['answers'];assert len(answers)==10
   for case in expected:
    ret=next(r for r in rows if r['kind']=='binding-return'and r['message']==case['message']);a=next(a for a in answers if a['root_frame']==ret['frame']);assert a['known']==(task=='root'or task=='observation'and case['value']==-1),(task,a)
    if task=='root':
     inp=next(r for r in rows if r['kind']=='binding-input'and r['frame']==ret['frame']and r['argument']==0);field='I2LSourceFixture$Input.'+('left'if case['choose']else'right');idx=next(i for i,f in enumerate(inp['fields'])if f['field']==field);assert a['origins']==[('field',inp['seq'],idx)]or set(map(tuple,a['origins']))=={('field',inp['seq'],idx)}
   guards={}
   if task in ('root','unknown'):
    for fault in ('missing','input','result','pc'):
     bad=copy.deepcopy(rows);e=next(r for r in bad if r['kind']=='execution-i2l')
     if fault=='missing':bad.remove(e)
     else:e[fault]=99999999999
     try:infer_execution(plan,bad)
     except ValueError:guards[fault]=True
     else:raise AssertionError(fault)
   else:
    audit=validate(plan,rows);assert audit['calls']==12 and audit['facts']==12,audit
    for fault in ('missing-completion','duplicate','wrong-caller','wrong-result','wrong-parent'):
     bad=copy.deepcopy(rows);e=next(r for r in bad if r['kind']=='source-call-exit')
     if fault=='missing-completion':bad.remove(e)
     elif fault=='duplicate':bad.insert(bad.index(e),copy.deepcopy(e))
     elif fault=='wrong-caller':e['caller_method']='other'
     elif fault=='wrong-result':e['result']={'object':'wrong'}
     else:next(r for r in bad if r['kind']=='source-context-enter')['parent_observation_frame']='wrong'
     try:validate(plan,bad)
     except ValueError:guards[fault]=True
     else:raise AssertionError(fault)
   reports[task+'-'+mode]={'business_equal':True,'targets':10,'known':sum(a['known']for a in answers),'guards':guards,'source_audit':validate(plan,rows)}
 for n in (-2**31,-1,0,1,2**31-1):
  for unknown in (False,True):
   v=Value({'value':n},frozenset({('origin',n)}),frozenset({('selector',1)}),unknown,42);r=i2l(v);assert r.observed=={'value':n}and r.origins==v.origins and r.selectors==v.selectors and r.unknown==unknown and r.allocation is None
 for n in (True,1.0,2**31,-2**31-1):
  try:i2l(Value({'value':n}))
  except ValueError:pass
  else:raise AssertionError('Non-int accepted')
 save(out/'results.json',{'all_passed':True,'agent_sha256':sha(b/'distributed-observer.jar'),'checks':reports,'pure_signed_value_dependency_selector_unknown_checks':True});print(reports)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.out.resolve())
