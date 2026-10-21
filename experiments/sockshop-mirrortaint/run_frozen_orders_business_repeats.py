#!/usr/bin/env python3
"""Fixed two independent repeats, preserving primary availability failures."""
import argparse,json
from pathlib import Path
from run_planned_service import HERE,load,save,sha
import run_frozen_capability_acceptance as driver

def run(root):
 primary=root/'all62-orders-serial';original=load(primary/'results.json')['results'];protocol=HERE/'capability-business-repeat-protocol-20261021.json';selected=[]
 for row in original:
  if 'failure'not in row:continue
  if 'Unable to create order due to timeout from one of the services.'not in row['failure']:raise ValueError('Noneligible failure requires review: '+str(row))
  original_capture=primary/(row['mode']+'-'+row['query'])/'capture/orders/events.jsonl';events=[json.loads(line)for line in original_capture.read_text().splitlines()]
  assert not any(r['kind']=='problem'for r in events),'Collector failure is not eligible for business repeat'
  assert any(r['kind']=='collection-call-throw'and r.get('exception_type')=='java.util.concurrent.TimeoutException'and r.get('async_future',{}).get('operation')=='get'for r in events),'Missing actual original Future deadline proof'
  selected.append({'query':row['query'],'mode':row['mode'],'primary':str(primary/(row['mode']+'-'+row['query'])),'reason':row['failure'],'timeout_evidence_sha256':sha(original_capture)})
 dest=root/'business-repeats';dest.mkdir();save(dest/'protocol-before-repeats.json',{'protocol_sha256':sha(protocol),'selected':selected,'repeats':2,'no_answer_based_selection':True});rows=[]
 for item in selected:
  attempts=[]
  for index in (1,2):
   out=dest/(item['mode']+'-'+item['query']+'-repeat-'+str(index));driver.orders(out,root/'frozen-base',only=item['query'],modes=(item['mode'],));r=load(out/'results.json')['results'];assert len(r)==1
   attempts.append({'directory':str(out/(item['mode']+'-'+item['query'])),'result':r[0]});save(dest/'progress.json',{'completed':rows,'current':{**item,'attempts':attempts}})
  query=next(q for q in driver.QUERIES if q['id']==item['query']);baseline=load(driver.previous(query)/'run.json')['cases'];expected=sum(len(driver.old.leaves(c['response'],query['path']))for c in baseline);wanted={'known_correct':expected}if expected else{}
  passed=all(a['result'].get('targets')==expected and a['result'].get('states')==wanted and not a['result'].get('oracle_unavailable')for a in attempts)
  row={**item,'attempts':attempts,'both_repeats_passed':passed,'selected_receipt':attempts[0]['directory']if passed else None};rows.append(row);save(dest/'results.json',{'complete':len(rows)==len(selected),'results':rows,'all_repeats_passed':all(r['both_repeats_passed']for r in rows)})
 if not selected:save(dest/'results.json',{'complete':True,'results':[],'all_repeats_passed':True})
 return rows
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();run(a.root.resolve())
