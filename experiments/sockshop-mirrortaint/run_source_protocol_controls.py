"""Targeted nested/exception identity guards; not ordinary sample expansion."""
import argparse,copy,json
from pathlib import Path
from zipfile import ZipFile
from run_query_planner import command,JARS
from run_planned_service import HERE,ROOT,load,save
from build_distributed_plans import build
from infer_source_observation import validate
from infer_execution_kernel import infer_execution

def run(out):
 out.mkdir(parents=True,exist_ok=False);classes=out/'classes';classes.mkdir();java='/usr/lib/jvm/java-8-openjdk-amd64/bin/java';agent=ROOT/'artifacts/offline-zlt-revision-20261031/candidate-build-01/distributed-observer.jar'
 command([java[:-4]+'javac','-cp',':'.join(map(str,[agent,*JARS])),'-d',str(classes),str(HERE/'SourceProtocolFixture.java')],out/'compile.log');jar=out/'fixture.jar'
 with ZipFile(jar,'w')as z:
  for p in classes.glob('SourceProtocolFixture*.class'):z.write(p,'BOOT-INF/classes/'+p.name)
 b=out/'build';build(b,{'fixture':{'jar':str(jar),'entry':'SourceProtocolFixture.root(I)LSourceProtocolFixture$Result;','targets':['SourceProtocolFixture$Result.value'],'response_path':'/value','execution_kernel':True,'application_calls':True,'source_calls':['SourceProtocolFixture$Source.read(I)LSourceProtocolFixture$Box;']}});plan=load(b/'fixture/plan.json');cp=':'.join(map(str,[classes,b/'distributed-observer.jar',*JARS]));expected=json.loads(command([java,'-cp',cp,'SourceProtocolFixture'],out/'baseline.log').stdout.splitlines()[-1]);checks={}
 for mode in('full','selective'):
  cap=out/mode;cap.mkdir();result=command([java,'-javaagent:'+str(b/'distributed-observer.jar'),'-Dservice.plan='+str(b/'fixture/plan.json'),'-Dservice.events='+str(cap/'events.jsonl'),'-Dservice.mode='+mode,'-cp',cp,'SourceProtocolFixture'],cap/'stdout.log');assert json.loads(result.stdout.splitlines()[-1])==expected;rows=[json.loads(s)for s in(cap/'events.jsonl').read_text().splitlines()];assert not any(r['kind']=='problem'for r in rows)
  audit=validate(plan,rows);assert audit['calls']==6 and audit['facts']==5,audit;assert sum(r['kind']=='source-call-throw'for r in rows)==1
  contexts=[r for r in rows if r['kind']=='source-context-enter'];assert sum(r['parent_observation_frame']is not None for r in contexts)==3
  roots=[r for r in rows if r['kind']=='enter'and r['method']==plan['entry']];assert len(roots)==3 and all(r.get('parent')is None for r in roots)and len({r['thread']for r in roots})==1
  answers=infer_execution(plan,rows)['answers'];assert len(answers)==2 and not any(a['known']for a in answers);guards={}
  for fault in('wrong-nested-parent','source-throw-without-error','missing-throw','wrong-context-hash','duplicate-entry'):
   bad=copy.deepcopy(rows)
   if fault=='wrong-nested-parent':next(r for r in bad if r['kind']=='source-context-enter'and r['parent_observation_frame'])['parent_observation_frame']='wrong'
   elif fault=='source-throw-without-error':next(r for r in bad if r['kind']=='source-call-throw')['exception']=None
   elif fault=='missing-throw':bad.remove(next(r for r in bad if r['kind']=='source-call-throw'))
   elif fault=='wrong-context-hash':next(r for r in bad if r['kind']=='source-context-enter')['caller_class_sha256']='wrong'
   else:bad.insert(-1,copy.deepcopy(next(r for r in bad if r['kind']=='source-call-enter')))
   try:validate(plan,bad)
   except ValueError:guards[fault]=True
   else:raise AssertionError(fault)
  checks[mode]={'business_equal':True,'same_exception_object':True,'nested_contexts':3,'source_calls':6,'source_normal_facts':5,'exceptional_sources':1,'subsequent_root_state_clean':True,'still_unknown':2,'guards':guards}
 save(out/'checks.json',checks);print(checks)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.out.resolve())
