#!/usr/bin/env python3
"""Native finite Feign pipeline controls; independent root-input field oracle."""
import argparse,json,copy
from pathlib import Path
from zipfile import ZipFile
from run_planned_service import ROOT,HERE,load,save
from run_query_planner import JARS,command
from experiment_environment import java8_target
from build_distributed_plans import build
from infer_execution_kernel import infer_execution

def run(out):
 out.mkdir(parents=True);classes=out/'classes';classes.mkdir();tools=ROOT/'artifacts/account-semantics-20261028/feign-build-02/tools';libs=sorted((ROOT/'artifacts/portability-first-20261028/metadata/piggy-account/libs').glob('*.jar'));cp=':'.join(map(str,[tools,*[p for p in JARS if 'asm'in p.name],*libs]));command(['javac',*java8_target()[1],'-cp',cp,'-d',str(classes),str(HERE/'FeignValueFixture.java')],out/'compile.log');jar=out/'fixture.jar'
 with ZipFile(jar,'w')as z:
  for p in classes.glob('*.class'):z.write(p,'BOOT-INF/classes/'+p.name)
  for p in libs:z.write(p,'BOOT-INF/lib/'+p.name)
 b=out/'build';build(b,{'fixture':{'jar':str(jar),'entry':'FeignValueFixture.root(LFeignValueFixture$Input;)LFeignValueFixture$Result;','targets':['FeignValueFixture$Result.text'],'response_path':'/text','execution_kernel':True,'application_calls':True}});plan=load(b/'fixture/plan.json');assert plan['execution_kernel'].get('feign_input_effects');save(out/'protocol-selection.json',plan['execution_kernel']['feign_input_effects'])
 runtime_cp=str(classes)+':'+str(b/'distributed-observer.jar')+':'+':'.join(map(str,libs))
 original=command(['java','-cp',runtime_cp,'FeignValueFixture'],out/'original.stdout.log');baseline=json.loads(next(l for l in original.stdout.splitlines()if l.startswith('[{')));checks={}
 for mode in ('full','selective'):
  cap=out/mode;cap.mkdir();log=cap/'events.jsonl';command(['java','-javaagent:'+str(b/'distributed-observer.jar'),'-Dservice.plan='+str(b/'fixture/plan.json'),'-Dservice.mode='+mode,'-Dservice.events='+str(log),'-cp',runtime_cp,'FeignValueFixture'],cap/'stdout.log');cases=json.loads(next(l for l in(cap/'stdout.log').read_text().splitlines()if l.startswith('[{')));assert [{k:v for k,v in c.items()if k!='message'}for c in cases]==[{k:v for k,v in c.items()if k!='message'}for c in baseline];rows=[json.loads(l)for l in log.open()];assert not any(r['kind']=='problem'for r in rows),[r for r in rows if r['kind']=='problem'];answers=infer_execution(plan,rows)['answers'];got=[]
  for c in cases:
   returns=[r for r in rows if r['kind']=='binding-return'and r.get('message')==c['message']]
   if c['aborted']:assert not returns;continue
   assert len(returns)==1;matched=[a for a in answers if a['root_frame']==returns[0]['frame']];assert len(matched)==1;answer=matched[0];known=c['kind']in('normal','repeat');assert answer['known']==known,(c,answer)
   if known:
    inputs=[r for r in rows if r['kind']=='binding-input'and r['frame']==answer['root_frame']and r['argument']==0];assert len(inputs)==1;f=[i for i,f in enumerate(inputs[0]['fields'])if f['field']=='FeignValueFixture$Input.text'];assert len(f)==1;assert answer['origins']==[['field',inputs[0]['seq'],f[0]]]
   got.append({'case':c,'answer':answer})
  guards={}
  for mutation in ('missing-worker','duplicate-worker','wrong-command','wrong-future','wrong-input','missing-serializer','missing-converter','wrong-runtime','changed-version'):
   bad=copy.deepcopy(rows);end=next(r for r in bad if r['kind']=='feign-call-end'and r['valid']);task=end['task'];cert=next(r['feign_effect']for r in bad if r['kind']=='collection-call-exit'and r.get('feign_effect',{}).get('task')==task)
   if mutation in ('missing-worker','duplicate-worker','missing-serializer','missing-converter'):
    kind={'missing-worker':'worker-enter','duplicate-worker':'worker-enter','missing-serializer':'serialization-enter','missing-converter':'converter'}[mutation];event=next(r for r in bad if r['kind']=='feign-'+kind and r['task']==task)
    if mutation=='duplicate-worker':bad.insert(bad.index(event)+1,copy.deepcopy(event))
    else:bad.remove(event)
   elif mutation=='wrong-runtime':next(r for r in bad if r['kind']=='feign-runtime')['class_sha256']={}
   elif mutation=='changed-version':
    for f in (end,cert):f['after'][0]['version']+=1
   elif mutation in ('wrong-command','wrong-future'):
    key='command'if mutation=='wrong-command'else'future'
    for f in (end,cert):f[key]={'object':'same-value-different-instance'}
   else:
    for r in bad:
     if r.get('task')==task and r['kind'].startswith('feign-'):r['input']={'object':'same-value-different-input'}
    cert['input']={'object':'same-value-different-input'}
   try:infer_execution(plan,bad)
   except ValueError:guards[mutation]=True
   else:raise AssertionError('Damaged Feign evidence admitted '+mutation)
  save(cap/'guards.json',guards)
  save(cap/'checks.json',got);checks[mode]={'targets':len(got),'known':sum(x['answer']['known']for x in got),'unknown':sum(not x['answer']['known']for x in got),'aborted':1};print(mode,checks[mode],flush=True)
 save(out/'results.json',checks)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=Path);a=p.parse_args();run(a.out.resolve())
