#!/usr/bin/env python3
import argparse,copy,json,shutil,datetime
from pathlib import Path
from run_planned_service import ROOT,load,save,sha
from infer_planned_service import infer_service
from portability_piggy_oracle import database

def normalized(x):
 if isinstance(x,dict):return{k:('clock'if k=='lastNotified'and v is not None else normalized(v))for k,v in x.items()}
 if isinstance(x,list):return[normalized(v)for v in x]
 return x

def run(root,out,recipient_subdir='recipient-01'):
 out.mkdir(parents=True);old=ROOT/'artifacts/portability-first-20261028/diagnostics/collector-preservation/original/control';control=load(old/'results.json');checks=[]
 for mode in('full','selective'):
  for index in(0,4):
   home=root/recipient_subdir/'diagnostics/collector-preservation'/mode/('query-%03d'%index);cases=load(home/'results.json')['cases'];assert len(cases)==6
   for c,w in zip(cases,control['cases']):
    assert c['case']==w['case']and c['body']==w['body']and c['http_status']==w['http_status']
    if c['http_status']>=400:
     assert database(home/(c['api']+'-'+c['case']+'-database-before.jsonl'))==database(home/(c['api']+'-'+c['case']+'-database-after.jsonl'))
    if c['http_status']==200:
     assert normalized(c['response'])==normalized(w['response'])
     docs=database(home/(c['api']+'-'+c['case']+'-database-after.jsonl'))[('piggy-notification','recipients')];assert len(docs)==1;assert normalized(docs)==normalized(database(old/(w['api']+'-'+w['case']+'-database-after.jsonl'))[('piggy-notification','recipients')]);d=docs[0];assert d['_id']==c['response']['accountName']and d['email']==c['response']['email']
     assert set(d['scheduledNotifications'])==set(c['response']['scheduledNotifications'])
     for k,v in d['scheduledNotifications'].items():
      original_db=database(old/(w['api']+'-'+w['case']+'-database-after.jsonl'))[('piggy-notification','recipients')][0]
      assert v['active']==c['response']['scheduledNotifications'][k]['active']and v['frequency']==original_db['scheduledNotifications'][k]['frequency']
      assert datetime.datetime.fromisoformat(v['lastNotified'].replace('Z','+00:00'))==datetime.datetime.strptime(c['response']['scheduledNotifications'][k]['lastNotified'],'%Y-%m-%dT%H:%M:%S.%f%z')
   rows=[json.loads(l)for l in(home/'capture/events.jsonl').open()];enters=[r for r in rows if r['kind']=='enter'];assert len(enters)==5 and all(r.get('parent')is None for r in enters)and len({r['thread']for r in enters})==1
   assert rows[-1]['kind']=='metrics'and rows[-1]['capture_invalid']and any(r['kind']=='problem'for r in rows)
   # A lost problem event still cannot resurrect a certified capture.
   shadow=[dict(r)for r in rows if r['kind']!='problem']
   for i,r in enumerate(shadow,1):r['seq']=i
   path=out/(mode+'-'+str(index)+'-without-problem.jsonl');path.write_text('\n'.join(json.dumps(r)for r in shadow)+'\n');plan=load(ROOT/'artifacts/portability-first-20261028/planning-first/piggymetrics-5'/('%03d-plan.json'%index))
   try:infer_service(plan,path)
   except ValueError as e:assert str(e)=='Failed collection'
   else:raise AssertionError('Capture-invalid flag did not reject')
   checks.append({'mode':mode,'old_plan_index':index,'responses_and_saving_match_original':6,'normal_200':5,'invalid_400':1,'subsequent_roots_parent_none':5,'single_worker':True,'capture_still_invalid':True,'capture_invalid_footer_guard':True,'events_sha256':sha(home/'capture/events.jsonl')})
 save(out/'checks.json',{'checks':checks,'source_semantics_extended':False,'scope':'Reliability only. Old Map/JDK proof limitations still reject the whole capture.'});print(checks)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--recipient-subdir',default='recipient-01');a=p.parse_args();run(a.root.resolve(),a.out.resolve(),a.recipient_subdir)
