#!/usr/bin/env python3
"""Actual Mongo2 default/callback/converter/codec controls. No cost experiment."""
import argparse,copy,json,secrets,time
from pathlib import Path
from zipfile import ZipFile
from run_planned_service import ROOT,HERE,load,save,sha
from run_query_planner import JARS,command
from experiment_environment import java8_target
from build_distributed_plans import build
from plan_capability_policy import choose
from infer_execution_kernel import infer_execution
from infer_distributed_fields import Reconstruction
import run_response_binding_revision as old

def run(out):
 out.mkdir(parents=True);classes=out/'classes';classes.mkdir();base=ROOT/'artifacts/account-semantics-20261028/account-build-01';libs=sorted((ROOT/'artifacts/portability-first-20261028/metadata/piggy-account/libs').glob('*.jar'));cp=':'.join(map(str,[base/'tools',*[p for p in JARS if 'asm'in p.name],*libs]));command(['javac',*java8_target()[1],'-cp',cp,'-d',str(classes),str(HERE/'Mongo2EffectFixture.java')],out/'compile.log');jar=out/'fixture.jar'
 with ZipFile(jar,'w')as z:
  for p in classes.glob('*.class'):z.write(p,'BOOT-INF/classes/'+p.name)
  for p in libs:z.write(p,'BOOT-INF/lib/'+p.name)
 image='mongo@sha256:d314f7eca9d3f825d091b77c40d2f3c9d6fff4de88dde2962527353476f107ba';save(out/'compose.json',{'services':{'mongo':{'image':image,'ports':['127.0.0.1::27017'],'mem_limit':'384m','cpus':1}}});dep=old.CachedDeployment(argparse.Namespace(project='tf2-mongo2-controls-'+secrets.token_hex(5),ready_timeout=90),out,out/'compose.json');reports={}
 try:
  dep.compose('up','-d','--pull','never',timeout=120)
  for attempt in range(60):
   if dep.compose('exec','-T','mongo','mongo','--quiet','--eval','db.runCommand({ping:1})',check=False).returncode==0:break
   time.sleep(1)
  else:raise RuntimeError('Mongo not ready')
  port=dep.compose('port','mongo','27017').stdout.strip().rsplit(':',1)[1]
  for group in ('text','date'):
   home=out/group;home.mkdir();b=home/'build';entry='Mongo2EffectFixture.root(LMongo2EffectFixture$Repo;Ljava/lang/String;LMongo2EffectFixture$Input;I)LMongo2EffectFixture$Out;';target='Mongo2EffectFixture$Out.'+group;build(b,{'fixture':{'jar':str(jar),'entry':entry,'targets':[target],'response_path':'/'+group,'execution_kernel':True,'application_calls':True}});save(home/'pre-routing-plan.json',load(b/'fixture/plan.json'));plan,policy=choose(load(b/'fixture/model.json'),{'entry':entry,'target':target,'path':'/'+group});save(b/'fixture/plan.json',plan);save(home/'routing.json',policy);receipt=load(b/'build.json');receipt['inputs']['fixture']['plan_sha256']=sha(b/'fixture/plan.json');save(b/'build.json',receipt);assert plan['execution_kernel']['save_effect_contracts']['profile_kind']=='mongo2-provided-field-id';runtime_cp=str(classes)+':'+str(b/'distributed-observer.jar')+':'+':'.join(map(str,libs));r=command(['java','-cp',runtime_cp,'Mongo2EffectFixture',port],home/'original.log');original=json.loads(next(l for l in r.stdout.splitlines()if l.startswith('[{')));reports[group]={}
   for mode in ('full','selective'):
    cap=home/mode;(cap/'fixture').mkdir(parents=True);r=command(['java','-javaagent:'+str(b/'distributed-observer.jar'),'-Dservice.plan='+str(b/'fixture/plan.json'),'-Dservice.mode='+mode,'-Dservice.events='+str(cap/'fixture/events.jsonl'),'-cp',runtime_cp,'Mongo2EffectFixture',port],cap/'stdout.log');cases=json.loads(next(l for l in r.stdout.splitlines()if l.startswith('[{')));assert cases==original;g=Reconstruction(b,cap,['fixture']);rows=g.rows['fixture'];checks=[]
    for c in cases:
     a=g.query(c['message'],'/'+group,'fixture',boundary=old.BOUNDARY);known=c['mode']in((0,5,6,7,8)if group=='text'else(0,5,6));assert a['known']==known,(group,mode,c,a);truth=set()
     if known and c['mode']!=5:
      if group=='text':
       returned=next(r for r in rows if r['kind']=='binding-return'and r.get('message')==c['message']);root=next(r for r in rows if r['kind']=='enter'and r['frame']==returned['frame']);truth={('fixture',c['message'],root['frame'],root['seq'],root['args'][1]['object'],'@argument:1',0,None)}
      else:
       source=next(r for r in rows if r['kind']=='binding-input'and r.get('message')==c['message']and r['argument']==2);assert len(source['fields'])==1;truth={old.source_coord('fixture',source,source['fields'][0])}
     if known:assert {old.predicted_coord(s)for s in a['sources']}==truth,(group,mode,c,a,truth)
     checks.append({'case':c,'answer':a})
    guards={}
    for fault in ('missing-save','wrong-class','changed-field-version','executed-handler','save-registry','listener-unverified','wrong-result','missing-document','wrong-date','custom-registry','missing-listener-registry','missing-listener-object','unregistered-dispatch'):
     if fault in('missing-document','wrong-date','custom-registry')and group!='date':continue
     bad=copy.deepcopy(rows);proof=next(r for r in bad if r['kind']=='mongo-save-effect'and r['valid'])
     if fault=='missing-save':bad.remove(proof)
     elif fault=='wrong-class':proof['class_sha256']={}
     elif fault=='changed-field-version':proof['after'][0]['version']+=1
     elif fault=='executed-handler':proof['callback_invocations']=1
     elif fault=='save-registry':proof['registry']={}
     elif fault=='listener-unverified':proof['listeners_verified']=False
     elif fault=='wrong-result':proof['result']['object']='same-value-other-entity'
     elif fault=='missing-listener-registry':proof.pop('listener_registry')
     elif fault=='missing-listener-object':
      marker=next(v for v in proof['listener_registry']if v.get('multicaster'));marker['direct_instances'].append({'object':'missing-listener-proof'})
     elif fault=='unregistered-dispatch':proof['listeners'].append({'listener':'unregistered','listener_object':{'object':'never-registered'},'multicaster_object':next(v['multicaster']for v in proof['listener_registry']if 'multicaster'in v)})
     else:
      codec=next(c for c in proof['date_codecs']if c['before'])
      if fault=='missing-document':bad.remove(next(r for r in bad if r['kind']=='document-date-exit'and r['seq']==codec['end_seq']))
      elif fault=='wrong-date':codec['before'][0]['object']='same-time-other-date'
      else:codec['default_registry']=False
     try:infer_execution(plan,bad)
     except ValueError:guards[fault]=True
     else:raise AssertionError('Damaged Mongo2 evidence admitted '+fault)
    reports[group][mode]={'targets':len(checks),'known':sum(c['answer']['known']for c in checks),'unknown':sum(not c['answer']['known']for c in checks),'guards':guards};save(cap/'checks.json',checks);print(group,mode,reports[group][mode],flush=True)
  save(out/'results.json',reports)
 finally:
  r=dep.compose('down','--volumes','--remove-orphans',check=False);save(out/'cleanup.json',{'returncode':r.returncode})
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=Path);a=p.parse_args();run(a.out.resolve())
