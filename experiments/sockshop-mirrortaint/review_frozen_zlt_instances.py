#!/usr/bin/env python3
"""Require paired source facts, preserve unscoped snapshots as diagnostic only."""
import argparse,collections,csv,json
from pathlib import Path
from run_frozen_zlt_reuse import load,save,sha

def review(home):
 records=load(home/'audit/instances.json');details=[];out=home/'audit-reviewed';out.mkdir(exist_ok=False)
 for r in records:
  if r['mode']=='mirrortaint':continue
  cap=home/'runs'/r['api']/r['mode']/'capture/events.jsonl';rows=[json.loads(s)for s in cap.read_text().splitlines()]
  q=next(q for q in load(home/'task-seal.json')['entries']if q['id']==r['api']);req=next(c for c in load(home/'runs'/r['api']/r['mode']/'selected-requests.json')if c['case']==r['case'])
  sources=[s for s in rows if s['kind']=='binding-source'and s['callee']==q['oracle']['source']and s.get('message')==req['message']]
  scoped=[s for s in sources if s.get('source_call_id')is not None and s.get('source_caller_method')is not None and s.get('source_pc')is not None]
  if len(scoped)!=1:
   r['oracle_adequate']=False;r['oracle_gap']='No unique paired actual mapper call/caller Frame/PC. Unscoped snapshots are diagnostic facts, not certified source occurrence.'
   if r['state']=='known_correct':r['state']='known_unchecked'
   r.pop('expected',None)
  details.append({'api':r['api'],'mode':r['mode'],'case':r['case'],'path':r['path'],'raw_source_facts':len(sources),'paired_source_facts':len(scoped),'source_scope':sorted({s.get('source_scope','missing')for s in sources})})
 modes={m:dict(collections.Counter(r['state']for r in records if r['mode']==m))for m in('full','selective','mirrortaint')}
 summary={**load(home/'audit/summary.json'),'states':modes,'oracle_adequate':{m:sum(r['oracle_adequate']for r in records if r['mode']==m)for m in modes},'correct_answers':{m:sum(r['state']=='known_correct'for r in records if r['mode']==m)for m in modes},'full_relationship_metrics':'not scored: paired source/oracle or baseline export missing','review_scope':'Stricter raw call pairing after first audit; earlier derived audit preserved. No core, declarations, inputs or captures changed.'}
 save(out/'instances.json',records);save(out/'source-coverage.json',details);save(out/'summary.json',summary)
 paired=[]
 for key in sorted({(r['api'],r['case'],r['path'])for r in records}):
  rr=[r for r in records if(r['api'],r['case'],r['path'])==key];assert len(rr)==3
  paired.append({'api':key[0],'case':key[1],'path':key[2],**{r['mode']:r['state']for r in rr},'certified_relative_gap':'unresolved_oracle_export_gap'})
 with(out/'paired.csv').open('w',newline='')as f:
  w=csv.DictWriter(f,fieldnames=['api','case','path','full','selective','mirrortaint','certified_relative_gap']);w.writeheader();w.writerows(paired)
 print(summary)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--home',required=True,type=Path);a=p.parse_args();review(a.home.resolve())
