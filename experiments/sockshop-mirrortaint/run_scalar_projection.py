#!/usr/bin/env python3
"""Actual native Jackson controls; independent source selection and wire oracle."""
import argparse,json,copy
from pathlib import Path
from zipfile import ZipFile
from run_planned_service import ROOT,HERE,load,save
from run_query_planner import JARS,command
from experiment_environment import java8_target
from build_distributed_plans import build
from infer_distributed_fields import Reconstruction
from infer_scalar_projection import validate
import run_response_binding_revision as old

def run(out):
 out.mkdir(parents=True);classes=out/'classes';classes.mkdir();base=ROOT/'artifacts/account-semantics-20261028/scalar-build-01';libs=sorted((ROOT/'artifacts/portability-first-20261028/metadata/piggy-account/libs').glob('*.jar'));cp=':'.join(map(str,[base/'tools',*[p for p in JARS if 'asm'in p.name],*libs]));command(['javac',*java8_target()[1],'-cp',cp,'-d',str(classes),str(HERE/'ScalarProjectionFixture.java')],out/'compile.log');jar=out/'fixture.jar'
 with ZipFile(jar,'w')as z:
  for p in classes.glob('*.class'):z.write(p,'BOOT-INF/classes/'+p.name)
  for p in libs:z.write(p,'BOOT-INF/lib/'+p.name)
 reports={};expected={0:(0,'number'),1:(1,'number'),2:(),3:(),4:(0,'enumeration'),5:(1,'enumeration'),6:(),7:(),8:(0,'date'),9:(),10:(),11:()}
 for group in ('amount','enumeration','date'):
  home=out/group;home.mkdir();b=home/'build';build(b,{'fixture':{'jar':str(jar),'entry':'ScalarProjectionFixture.root(LScalarProjectionFixture$Input;LScalarProjectionFixture$Input;I)LScalarProjectionFixture$Out;','targets':['ScalarProjectionFixture$Out.'+group],'response_path':'/'+group,'execution_kernel':True,'application_calls':True}});plan=load(b/'fixture/plan.json');assert plan.get('scalar_projection');runtime_cp=str(classes)+':'+str(b/'distributed-observer.jar')+':'+':'.join(map(str,libs));reports[group]={}
  for mode in ('full','selective'):
   for enc in (('default','timestamp')if group=='date'else('default',)):
    cap=home/(mode+'-'+enc);(cap/'fixture').mkdir(parents=True);log=cap/'fixture/events.jsonl';r=command(['java','-javaagent:'+str(b/'distributed-observer.jar'),'-Dservice.plan='+str(b/'fixture/plan.json'),'-Dservice.mode='+mode,'-Dservice.events='+str(log),'-cp',runtime_cp,'ScalarProjectionFixture',group,enc],cap/'stdout.log');cases=json.loads(next(l for l in r.stdout.splitlines()if l.startswith('[{')));g=Reconstruction(b,cap,['fixture']);rows=g.rows['fixture'];checks=[]
    for c in cases:
     a=g.query(c['message'],'/'+group,'fixture',boundary=old.BOUNDARY);assert a['known'];want=expected[c['mode']];truth=set()
     if want:
      source=next(r for r in rows if r['kind']=='binding-input'and r.get('message')==c['message']and r['argument']==want[0]);f=next(f for f in source['fields']if f['field']=='ScalarProjectionFixture$Input.'+want[1]);truth={old.source_coord('fixture',source,f)}
     assert {old.predicted_coord(s)for s in a['sources']}==truth,(c,a,truth);observed=a['target']['observed'];wire=c['response'][group]
     if group!='date':assert wire==observed['value']
     elif wire is not None:assert a['target']['wire_value']==wire
     checks.append({'case':c,'answer':a})
    guards={}
    if group!='date':
     for fault in ('missing-proof','wrong-object','wrong-wire','wrong-class'):
      bad=copy.deepcopy(rows);p=next(r for r in bad if r['kind']=='scalar-serialization')
      if fault=='missing-proof':bad.remove(p)
      elif fault=='wrong-object':p['observed']['object']='same-value-other-object'
      elif fault=='wrong-wire':p['wire_value']='wrong-wire'
      else:p['class_sha256']={}
      try:validate(plan,bad)
      except ValueError:guards[fault]=True
      else:raise AssertionError('Bad scalar proof admitted '+fault)
    reports[group][mode+'-'+enc]={'targets':len(checks),'known':len(checks),'positive':sum(bool(x['answer']['sources'])for x in checks),'empty':sum(not x['answer']['sources']for x in checks),'guards':guards};save(cap/'checks.json',checks);print(group,mode,enc,reports[group][mode+'-'+enc],flush=True)
  if group!='date':
   for enc in (('custom-number','number-string')if group=='amount'else('enum-index','enum-string')):
    cap=home/enc;cap.mkdir();r=command(['java','-javaagent:'+str(b/'distributed-observer.jar'),'-Dservice.plan='+str(b/'fixture/plan.json'),'-Dservice.mode=selective','-Dservice.events='+str(cap/'events.jsonl'),'-cp',runtime_cp,'ScalarProjectionFixture',group,enc],cap/'stdout.log');cases=json.loads(next(l for l in r.stdout.splitlines()if l.startswith('[{')));bad=[json.loads(l)for l in(cap/'events.jsonl').open()];assert any(r['kind']=='problem'for r in bad)and bad[-1]['capture_invalid'];assert not any(r['kind']=='scalar-serialization'for r in bad);reports[group][enc]={'unsupported_non_null_targets':sum(c['response'][group]is not None for c in cases),'business_completed':len(cases),'capture_invalid':True}
 save(out/'results.json',reports)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=Path);a=p.parse_args();run(a.out.resolve())
