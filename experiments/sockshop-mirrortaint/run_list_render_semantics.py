#!/usr/bin/env python3
"""Repeated library callbacks, actual parent invocation and historical field versions."""
import argparse,json,copy
from pathlib import Path
from zipfile import ZipFile
from build_distributed_plans import build
from experiment_environment import java8_target
from run_query_planner import command,JARS
from run_planned_service import ROOT,HERE,save,load
from infer_distributed_fields import Reconstruction
from infer_execution_kernel import infer_execution
import run_response_binding_revision as old

def run(out,libs,base):
 out.mkdir(parents=True,exist_ok=False);classes=out/'classes';classes.mkdir();cp=':'.join(map(str,[*JARS,*sorted(libs.glob('*.jar'))]));command(['javac',*java8_target()[1],'-cp',cp+':'+str(base/'tools'),'-d',str(classes),str(HERE/'ListRenderFixture.java')],out/'compile.log');jar=out/'fixture.jar'
 with ZipFile(jar,'w') as z:
  for f in classes.glob('*.class'):z.write(f,'BOOT-INF/classes/'+f.name)
 b=out/'build';build(b,{'fixture':{'jar':str(jar),'entry':'ListRenderFixture.root(Ljava/util/List;I)LListRenderFixture$Out;','targets':['ListRenderFixture$Out.text'],'response_path':'/text','execution_kernel':True,'application_calls':True,'async_dependencies':True}});reports={}
 for mode in ('full','selective'):
  cap=out/mode;(cap/'fixture').mkdir(parents=True);command(['java','-javaagent:'+str(b/'distributed-observer.jar'),'-Dservice.plan='+str(b/'fixture/plan.json'),'-Dservice.mode='+mode,'-Dservice.events='+str(cap/'fixture/events.jsonl'),'-cp',str(classes)+':'+cp,'ListRenderFixture'],cap/'stdout.log');cases=json.loads((cap/'stdout.log').read_text().splitlines()[-1]);g=Reconstruction(b,cap,['fixture']);rows=g.rows['fixture'];checks=[]
  for c in cases:
   a=g.query(c['message'],'/text','fixture',boundary=old.BOUNDARY);known=c['mode']!=4;assert a['known']==known,(c,a);truth=set()
   if known and c['mode'] in (0,1):
    inp=next(r for r in rows if r['kind']=='binding-input' and r.get('message')==c['message'] and r['argument']==0);path='/0/text' if c['mode']==0 else '/2/text';f=next(f for f in inp['fields'] if f['path']==path);truth={old.source_coord('fixture',inp,f)}
   if known:assert {old.predicted_coord(s) for s in a['sources']}==truth,(c,a,truth)
   checks.append({'case':c,'answer':a,'expected':sorted(truth,key=str) if known else None})
  faults={}
  for label in ('wrong-callback-site','wrong-callback-call','wrong-member-identity','missing-callback-frame','duplicate-frame'):
   changed=copy.deepcopy(rows);child=next(r for r in changed if r['kind']=='enter' and '$Item.toString' in r['method'])
   if label=='wrong-callback-site':child['callsite']='wrong-site'
   elif label=='wrong-callback-call':child['callback_call_id']=-1
   elif label=='wrong-member-identity':child['receiver']='wrong-member'
   elif label=='missing-callback-frame':changed.remove(child)
   else:changed.append(copy.deepcopy(child))
   try:infer_execution(g.plans['fixture'],changed)
   except ValueError:faults[label]=True
   else:raise AssertionError('Accepted '+label)
  reports[mode]={'targets':len(checks),'known_exact':sum(x['answer']['known'] for x in checks),'expected_unknown':sum(not x['answer']['known'] for x in checks),'faults':faults,'checks':checks};save(out/'results.json',{'all_passed':True,'modes':reports});print(mode,{k:v for k,v in reports[mode].items() if k!='checks'},flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--libs',type=Path,required=True);p.add_argument('--base-build',type=Path,required=True);a=p.parse_args();run(a.out.resolve(),a.libs.resolve(),a.base_build.resolve())
