#!/usr/bin/env python3
"""Candidate Account40 paired scoring; never overwrites FIRST or input captures."""
import argparse,json,shutil,csv
from pathlib import Path
from run_planned_service import ROOT,load,save,sha
from infer_distributed_fields import Reconstruction
from account_candidate_oracle import expected
import run_response_binding_revision as old

def run(root,out,require_complete=False):
 out.mkdir(parents=True);first=ROOT/'artifacts/portability-first-20261028';historic=load(first/'piggy-independent-first-03/account-return-paired-instances.json');by={(r['case'],r['path']):r for r in historic};rows_out=[];captures={};summaries={}
 for mode in ('full','selective'):
  for i in range(10,20):
   home=root/'diagnostics/collector-preservation'/mode/('query-%03d'%i)
   if not(home/'results.json').exists():continue
   result=load(home/'results.json');assert result['status']=='business_attempts_completed',result;plan_path=root/'planning-first/piggymetrics-2'/('%03d-plan.json'%i);plan=load(plan_path);path=plan['response_binding']['path'];work=out/mode/('query-%03d'%i);(work/'build/piggy-account').mkdir(parents=True);(work/'capture/piggy-account').mkdir(parents=True);shutil.copyfile(plan_path,work/'build/piggy-account/plan.json');events=home/'capture/events.jsonl';captures[str(events)]=sha(events);(work/'capture/piggy-account/events.jsonl').symlink_to(events.resolve());g=Reconstruction(work/'build',work/'capture',['piggy-account']);raw=g.rows['piggy-account'];records=[]
   for c in result['cases']:
    if c['http_status']!=200:continue
    truth=expected(c,home,raw,path);a=g.query(c['message'],path,'piggy-account',boundary=old.BOUNDARY);client=c['response']
    for part in path.strip('/').split('/'):client=client[part]
    assert(a['target'].get('wire_value')if 'date_epoch_ms'in a['target']['observed']else a['target']['observed'].get('value'))==client,'Bound target differs from actual client wire value'
    got={old.predicted_coord(s)for s in a['sources']}if a['known']else set();want={tuple(s)for s in truth['sources']};correct=a['known']and got==want;assert a['target']['owner']==truth['target']['owner']and a['target']['field']==truth['target']['field']and a['target']['version']==truth['target']['version'];baseline=by[c['case'],path]['baseline']['state'];record={'mode':mode,'query_index':i,'case':c['case'],'path':path,'state':'known_correct'if correct else'known_wrong'if a['known']else'unknown','positive':bool(want),'TP':len(got&want),'FP':len(got-want),'FN':len(want-got),'historic_MT_state':baseline,'historic_TF_state':by[c['case'],path]['TF'][mode]['state'],'truth':truth,'answer':a};records.append(record);rows_out.append(record)
   assert len(records)==4;save(work/'scores.json',records)
  own=[r for r in rows_out if r['mode']==mode];summaries[mode]={'targets':len(own),'known_correct':sum(r['state']=='known_correct'for r in own),'known_wrong':sum(r['state']=='known_wrong'for r in own),'unknown':sum(r['state']=='unknown'for r in own),'known_positive':sum(r['state']=='known_correct'and r['positive']for r in own),'known_empty':sum(r['state']=='known_correct'and not r['positive']for r in own),'historic_MT_correct_present':sum(r['historic_MT_state']=='known_correct'for r in own),'historic_MT_correct_preserved':sum(r['historic_MT_state']=='known_correct'and r['state']=='known_correct'for r in own),'TP':sum(r['TP']for r in own),'FP':sum(r['FP']for r in own),'FN':sum(r['FN']for r in own)}
 complete=all(s['targets']==40 for s in summaries.values());save(out/'summary.json',{'complete40':complete,'modes':summaries,'no_performance':True,'first_results_unchanged':True,'captured_files_sha256':captures});save(out/'paired-instances.json',rows_out)
 with(out/'paired-instances.csv').open('w',newline='')as f:
  keys=['mode','query_index','case','path','state','positive','TP','FP','FN','historic_MT_state','historic_TF_state'];w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows({k:r[k]for k in keys}for r in rows_out)
 for p,h in captures.items():assert sha(Path(p))==h
 print(summaries)
 if require_complete:assert complete and all(s['known_correct']==40 and s['known_wrong']==0 and s['historic_MT_correct_preserved']==36 for s in summaries.values())
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',required=True,type=Path);p.add_argument('--out',required=True,type=Path);p.add_argument('--require-complete',action='store_true');a=p.parse_args();run(a.root.resolve(),a.out.resolve(),a.require_complete)
