#!/usr/bin/env python3
"""Business non-interference and conservative unproved collection ownership."""
import argparse,copy,json
from pathlib import Path
from zipfile import ZipFile
from run_planned_service import ROOT,HERE,load,save
from run_query_planner import JARS,command
from experiment_environment import java8_target
from build_distributed_plans import build
import run_response_binding_revision as old
from infer_execution_kernel import infer_execution

def run(out):
 out.mkdir(parents=True,exist_ok=False);classes=out/'classes';classes.mkdir();cp=':'.join(map(str,[ROOT/'artifacts/date-effects-capability-20261021/frozen-base/tools',*JARS]));command(['javac',*java8_target()[1],'-cp',cp,'-d',str(classes),str(HERE/'ReceivedMutationFixture.java')],out/'compile.log');jar=out/'fixture.jar'
 with ZipFile(jar,'w') as z:
  for f in classes.glob('*.class'):z.write(f,'BOOT-INF/classes/'+f.name)
 b=out/'build';build(b,{'fixture':{'jar':str(jar),'entry':'ReceivedMutationFixture.root(LReceivedMutationFixture$Input;I)LReceivedMutationFixture$Out;','targets':['ReceivedMutationFixture$Out.text'],'response_path':'/text','execution_kernel':True,'application_calls':True}});results={}
 for mode in ('full','selective'):
  cap=out/mode;(cap/'fixture').mkdir(parents=True);command(['java','-javaagent:'+str(b/'distributed-observer.jar'),'-Dservice.plan='+str(b/'fixture/plan.json'),'-Dservice.mode='+mode,'-Dservice.events='+str(cap/'fixture/events.jsonl'),'-cp',str(classes)+':'+':'.join(map(str,JARS)),'ReceivedMutationFixture'],cap/'stdout.json');cases=load(cap/'stdout.json');g=old.Reconstruction(b,cap,['fixture']);rs=g.rows['fixture'];checks=[]
  for c in cases:
   a=g.query(c['message'],'/text','fixture',boundary=old.BOUNDARY);assert a['known']==(c['mode']==0),(c,a)
   expected=set()
   if c['mode']==0:
    source=next(r for r in rs if r['kind']=='binding-input' and r.get('message')==c['message'] and r['argument']==0);f=next(f for f in source['fields'] if f['path']=='/items/0');expected={old.source_coord('fixture',source,f)};assert {old.predicted_coord(s)for s in a['sources']}==expected
   checks.append({'case':c,'expected':sorted(expected,key=str)if c['mode']==0 else None,'answer':a})
  faults={}
  for label in ('missing-post-state','wrong-post-version','wrong-post-member'):
   bad=copy.deepcopy(rs);start=next(r for r in bad if r['kind']=='collection-call-enter'and r['callee']=='java/util/List.add(Ljava/lang/Object;)Z'and len(r.get('collection',[]))==1);end=next(r for r in bad if r['kind']=='collection-call-exit'and r.get('call_id')==start['call_id'])
   if label=='missing-post-state':end.pop('collection_after')
   elif label=='wrong-post-version':end['collection_epoch']+=1
   else:end['collection_after'][0]={'object':'other','value':'WRONG'}
   try:infer_execution(g.plans['fixture'],bad)
   except ValueError:faults[label]=True
   else:raise AssertionError('Accepted '+label)
  results[mode]={'targets':6,'known_exact':2,'expected_unknown':4,'business_mutations_completed':4,'faults':faults,'checks':checks};save(out/'results.json',{'all_passed':True,'modes':results});print(mode,{k:v for k,v in results[mode].items()if k!='checks'},flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.out.resolve())
