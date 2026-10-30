"""Independent Mall scoring, prior answers, ownership witnesses and ablation.

Truth is supplied only by the existing independent oracle. Ownership state and
ablation diagnose mechanism use; they do not determine expected origins.
"""
import argparse,collections,copy,json
from pathlib import Path
from run_planned_service import ROOT,load,save,sha
from audit_constructor_chain_revision import run as paired
from infer_source_locality import validate
from infer_execution_kernel import infer_execution

PARENT=ROOT/'artifacts/constructor-chain-effects-20261030'
def run(home,out):
 paired(home,out)
 summary=load(out/'summary.json');before={(r['mode'],r['api'],r['case'],r['path']):r for r in load(PARENT/'audit-final-mall-02/paired/instances.json')};current=load(out/'paired/instances.json');assert len(before)==len(current)==206
 assert all(r['state']=='known_correct'for r in current if before[(r['mode'],r['api'],r['case'],r['path'])]['state']=='known_correct')
 # Independently scored signatures from the immediately preceding checkpoint.
 old_details={(r['mode'],r['api'],r['case'],r['path']):r for p in(PARENT/'final-mall-01/evaluation').glob('*/*/*/instances.json')for r in load(p)}
 def signature(r):return collections.Counter((v[0],v[3],v[5],v[6])for v in r.get('expected',[]))
 for p in(home/'evaluation').glob('*/*/*/instances.json'):
  for r in load(p):
   k=(r['mode'],r['api'],r['case'],r['path'])
   if before[k]['state']=='known_correct':assert signature(old_details[k])==signature(r)
 ablation=collections.defaultdict(collections.Counter);ownership=[]
 for task in load(home/'planning-summary.json'):
  if not task['query']['id'].startswith('mall-swarm-3-'):continue
  index=task['index'];p=load(home/'planning-first/mall-swarm-3'/('%03d-plan.json'%index))
  for mode in ('full','selective'):
   details=load(home/'evaluation/mall-swarm-3'/mode/('%03d'%index)/'instances.json')
   for r in details:
    k=(r['mode'],r['api'],r['case'],r['path'])
    if before[k]['state']=='known_correct':assert signature(old_details[k])==signature(r)
   rows=[json.loads(s)for s in(home/'tool-runs/mall-swarm-3'/mode/('query-%03d'%index)/'capture/events.jsonl').read_text().splitlines()];certificates=validate(p,rows);normal=infer_execution(p,rows)
   off=copy.deepcopy(p);off['execution_kernel'].pop('source_locality',None);disabled=infer_execution(off,rows)
   normal_answers=[a for a in normal['answers']if a['path']==task['query']['path']];disabled_answers=[a for a in disabled['answers']if a['path']==task['query']['path']]
   assert len(normal_answers)==len(disabled_answers)==len(details)
   ablation[mode].update(targets=len(normal_answers),with_certificate_known=sum(a['known']for a in normal_answers),without_certificate_known=sum(a['known']for a in disabled_answers))
   ownership.append({'mode':mode,'index':index,'certificates':len(certificates),'mutable_objects':sum(len(c['objects'])for c in certificates.values()),'known_targets':sum(a['known']for a in normal['answers']),'opaque_calls_retained':sum(len(a.get('opaque_calls',[]))for a in normal.get('roots',[]))})
 for mode in ('full','selective'):assert dict(ablation[mode])=={'targets':30,'with_certificate_known':30,'without_certificate_known':0},ablation
 assert summary['joint98_gate_passed']and summary['prior68_answers_preserved']
 assert all(s['states']=={'known_correct':98,'unknown':5}and s['MT_correct_preserved']==88 for s in summary['modes'].values())
 previous=load(PARENT/'audit-final-mall-02/captures-manifest.json')['files']
 for p,h in previous.items():assert sha(PARENT/'final-mall-01'/p)==h
 summary.update(previous_reference='7754624 constructor final-mall-01:68/103',constructor_files_preserved=len(previous),ownership_ablation={k:dict(v)for k,v in ablation.items()},source_boundary_unchanged=True,logging_readonly_contracts_added=0)
 save(out/'ownership-witnesses.json',ownership);save(out/'summary.json',summary);print({m:{k:v for k,v in s.items()if k!='MT_gap'}for m,s in summary['modes'].items()})
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.home.resolve(),a.out.resolve())
