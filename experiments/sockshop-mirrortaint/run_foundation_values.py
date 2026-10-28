#!/usr/bin/env python3
"""Actual JVM operand/default proofs, independent literal per-mode oracle.
No claim of HTTP serialization or Piggy Account correctness here.
"""
import argparse,json,copy,subprocess
from pathlib import Path
from zipfile import ZipFile
from run_planned_service import ROOT,HERE,load,save,sha
from run_query_planner import JARS,command
from experiment_environment import java8_target
from build_distributed_plans import build
from infer_execution_kernel import infer_execution

def run(out,only=None):
 out.mkdir(parents=True);classes=out/'classes';classes.mkdir();tools=ROOT/'artifacts/account-semantics-20261028/foundation-build-01/tools';spring=ROOT/'artifacts/portability-first-20261028/metadata/piggy-account/libs/spring-core-5.0.7.RELEASE.jar';cp=':'.join(map(str,[tools,spring,*JARS]));command(['javac',*java8_target()[1],'-cp',cp,'-d',str(classes),str(HERE/'FoundationValueFixture.java')],out/'compile.log')
 jar=out/'fixture.jar'
 with ZipFile(jar,'w')as z:
  for p in classes.glob('*.class'):
   if p.stem!='OpaqueFoundation':z.write(p,'BOOT-INF/classes/'+p.name)
  z.write(spring,'BOOT-INF/lib/spring-core-5.0.7.RELEASE.jar')
 expected={0:(0,'flag'),1:(1,'flag'),2:(0,'number'),3:(1,'number'),4:(),5:(),6:(),7:(),8:None,9:(),10:(),11:(0,'text'),12:(1,'text'),13:None,14:None,15:(1,'text'),16:(),18:(0,'text'),19:None,20:(0,'text'),21:(0,'number'),22:None};reports={}
 for group in ('flag','amount','text','number','live','empty'):
  if only and group!=only:continue
  home=out/group;home.mkdir();b=home/'build';build(b,{'fixture':{'jar':str(jar),'entry':'FoundationValueFixture.root(LFoundationValueFixture$Input;LFoundationValueFixture$Input;I)LFoundationValueFixture$Result;','targets':['FoundationValueFixture$Result.'+group],'response_path':'/'+group,'execution_kernel':True,'application_calls':True}});plan=load(b/'fixture/plan.json');assert 'FoundationValueFixture$Plain'in plan['execution_kernel']['plain_enum_classes'];assert 'FoundationValueFixture$Unproved'in plan['execution_kernel']['unproved_enum_classes']
  reports[group]={}
  runtime_cp=str(classes)+':'+str(b/'distributed-observer.jar')+':'+str(spring)+':'+':'.join(map(str,JARS))
  original=command(['java','-cp',runtime_cp,'FoundationValueFixture',group],home/'original.stdout.log');original_cases=json.loads(original.stdout.splitlines()[-1]);baseline=[{k:v for k,v in c.items()if k!='message'}for c in original_cases]
  for mode in ('full','selective'):
   cap=home/mode;cap.mkdir();log=cap/'events.jsonl';command(['java','-javaagent:'+str(b/'distributed-observer.jar'),'-Dservice.plan='+str(b/'fixture/plan.json'),'-Dservice.mode='+mode,'-Dservice.events='+str(log),'-cp',runtime_cp,'FoundationValueFixture',group],cap/'stdout.log');cases=json.loads((cap/'stdout.log').read_text().splitlines()[-1]);rows=[json.loads(l)for l in log.open()];assert [{k:v for k,v in c.items()if k!='message'}for c in cases]==baseline;assert [r['seq']for r in rows]==list(range(1,len(rows)+1)) and rows[-1]['kind']=='metrics'and not rows[-1]['capture_invalid'];assert not any(r['kind']=='problem'for r in rows),(group,mode,[r for r in rows if r['kind']=='problem']);answers=infer_execution(plan,rows)['answers'];checks=[]
   for case in cases:
    returned=[r for r in rows if r['kind']=='binding-return'and r.get('message')==case['message']]
    if case['aborted']:assert not returned;continue
    assert len(returned)==1;matches=[a for a in answers if a['root_frame']==returned[0]['frame']and a['path']=='/'+group];assert len(matches)==1;answer=matches[0];want=expected[case['mode']];assert answer['known']==(want is not None),(group,mode,case['mode'],answer)
    wanted=set()
    if want is not None and want!=():
     index,field=want;inputs=[r for r in rows if r['kind']=='binding-input'and r.get('frame')==answer['root_frame']and r['argument']==index];assert len(inputs)==1;fields=[(i,f)for i,f in enumerate(inputs[0]['fields'])if f['field']=='FoundationValueFixture$Input.'+field];assert len(fields)==1;wanted={('field',inputs[0]['seq'],fields[0][0])}
    if want is not None:assert {tuple(v)for v in answer['origins']}==wanted,(group,mode,case,answer,wanted)
    checks.append({'case_mode':case['mode'],'pass':case['pass'],'known':answer['known'],'origins':answer['origins'],'expected':sorted(wanted),'target_object':answer['observed'].get('object')})
   if group=='flag':
    for pass_ in range(3):assert len({c['target_object']for c in checks if c['pass']==pass_})==1,'Boolean cache identity changed; origin comparison remains per argument occurrence'
   faults={}
   for mutation in ('missing-default','duplicate-default','wrong-default-object','wrong-default-version','missing-foundation-call','wrong-enum-class','same-value-wrong-decimal'):
    bad=copy.deepcopy(rows)
    if mutation in ('missing-default','duplicate-default','wrong-default-object','wrong-default-version'):
     item=next(r for r in bad if r['kind']=='execution-defaults')
     if mutation=='missing-default':bad.remove(item)
     elif mutation=='duplicate-default':bad.insert(bad.index(item)+1,copy.deepcopy(item))
     elif mutation=='wrong-default-object':item['object']='other-object'
     else:item['fields'][0]['version']=1
    elif mutation=='missing-foundation-call':
     item=next((r for r in bad if r.get('foundation_value')),None)
     if item is None:continue
     item.pop('foundation_value')
    elif mutation=='same-value-wrong-decimal':
     if group!='amount':continue
     c=next(c for c in cases if c['mode']==21);ret=next(r for r in bad if r['kind']=='binding-return'and r.get('message')==c['message']);root=ret['frame'];constructs=[r for r in bad if r['kind']=='execution-constructed'and r.get('frame')==root and r['receiver_type']=='java.math.BigDecimal'and r['seq']<ret['seq']];constructs=constructs[-2:];assert len(constructs)==2
     replacement=constructs[1]['receiver'];victim=next(r for r in bad if r['kind']=='write'and r.get('frame')==root and r['field']=='FoundationValueFixture$Result.amount'and constructs[1]['seq']<r['seq']<ret['seq']);victim['observed']=copy.deepcopy(replacement);ret['fields'][0]['observed']=copy.deepcopy(replacement)
    else:
     item=next((r for r in bad if r.get('foundation_enum')),None)
     if item is None:continue
     item['foundation_enum']['class_sha256']='wrong'
    for i,r in enumerate(bad,1):r['seq']=i
    try:infer_execution(plan,bad)
    except ValueError:faults[mutation]=True
    else:raise AssertionError('Bad foundation evidence accepted '+mutation)
   reports[group][mode]={'targets':len(checks),'known':sum(c['known']for c in checks),'unknown':sum(not c['known']for c in checks),'aborted':sum(c['aborted']for c in cases),'checks':checks,'guards':faults};save(cap/'checks.json',reports[group][mode]);print(group,mode,{k:v for k,v in reports[group][mode].items()if k!='checks'},flush=True)
  save(out/'results.json',{'complete':False,'groups':reports,'scope':'Local execution semantics only, separate from HTTP projection and Account40.'})
 save(out/'results.json',{'complete':True,'groups':reports,'scope':'Local execution semantics only. Independent mode oracle, not business coverage/performance.'})
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--only');a=p.parse_args();run(a.out.resolve(),a.only)
