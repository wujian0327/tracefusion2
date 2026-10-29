"""Separate revised results from all first/C1 and previous revision artifacts."""
import argparse,collections,csv,copy,json
from pathlib import Path
from run_plan_applicability_revision import ROOT,HERE,FIRST,load,save,sha
from audit_application_call_revision import class_hashes


def preserved_first():
 counts={}
 for label,base,path in (
  ('old_first',ROOT/'artifacts/portability-first-20261028',ROOT/'artifacts/monitor-reliability-account-20261028/protected-first-evidence.json'),
  ('external_first',FIRST,FIRST/'first-matrix-manifest-before-B1.json'),
  ('C1',FIRST,FIRST/'C1-first-captures-before-final-scoring.json')):
  files=load(path)['files']
  for p,h in files.items():assert sha(base/p)==h,p
  counts[label]=len(files)
 prior=ROOT/'artifacts/plan-applicability-revision-20261029'
 files=load(prior/'audit-final-reviewed-03/captures-manifest.json')['files']
 for p,h in files.items():assert sha(prior/'final-candidate-01'/p)==h,p
 counts['previous_revision']=len(files);return counts


def mall(home,out):
 out.mkdir(parents=True,exist_ok=False);progress=load(home/'matrix-progress.json');assert progress['complete']and len(progress['results'])==42
 freeze=load(home/'candidate-code.json')
 for p,h in freeze['sources'].items():assert sha(ROOT/p)==h,p
 for p,h in freeze['planning_inputs'].items():assert sha(home/p)==h,p
 previous=ROOT/'artifacts/plan-applicability-revision-20261029/audit-final-reviewed-03'
 before={(r['mode'],r['api'],r['case'],r['path']):r for r in load(previous/'instances.json')}
 mt={(r['api'],r['case'],r['path']):r for r in load(FIRST/'audit-C1-reviewed-02/instances.json')if r['tool']=='MT-B0'and r['api'].startswith('mall-')};assert len(mt)==103
 rows=[];summaries={};changes=[];manifest={}
 for mode in ('full','selective'):
  current=[r for p in sorted((home/'evaluation').glob('*/'+mode+'/*/instances.json'))for r in load(p)]
  assert len(current)==103 and len({(r['api'],r['case'],r['path'])for r in current})==103
  for r in current:
   key=(r['api'],r['case'],r['path']);b=mt[key];old=before[(mode,*key)]
   if r['state']!=old['state']:changes.append({'mode':mode,'api':key[0],'case':key[1],'path':key[2],'before':old['state'],'after':r['state']})
   record={k:v for k,v in r.items()if k not in ('answer','expected')};record.update(previous_TF_state=old['state'],MT_state=b['state'],MT_positive=bool(b.get('expected'))if b['state']=='known_correct'else None,MT_correct_preserved=b['state']=='known_correct'and r['state']=='known_correct');rows.append(record)
  selected=[r for r in rows if r['mode']==mode]
  summaries[mode]={'targets':103,'states':dict(collections.Counter(r['state']for r in selected)),'positive_correct':sum(r['state']=='known_correct'and r.get('positive',False)for r in selected),'known_empty_correct':sum(r['state']=='known_correct'and not r.get('positive',True)for r in selected),'MT_correct_preserved':sum(r['MT_correct_preserved']for r in selected),'MT_positive_preserved':sum(r['MT_positive']is True and r['state']=='known_correct'for r in selected),'previous_correct_preserved':sum(r['previous_TF_state']=='known_correct'and r['state']=='known_correct'for r in selected),'MT_gap':[{'api':r['api'],'case':r['case'],'path':r['path'],'positive':r['MT_positive'],'state':r['state'],'error':r.get('error')}for r in selected if r['MT_state']=='known_correct'and r['state']!='known_correct']}
 for receipt in progress['results']:
  assert receipt['returncode']==receipt['audit_returncode']==0,receipt
  cap=home/'tool-runs'/receipt['api']/receipt['mode']/('query-%03d'%receipt['index'])
  assert load(cap/'results.json')['cleanup_returncode']==0
  agent_files={p:h for p,h in load(cap/'tool-binaries.json')['files'].items()if p.endswith('/distributed-observer.jar')};assert len(agent_files)==1 and next(iter(agent_files.values()))==freeze['agent_sha256']
  for p in cap.rglob('*'):
   if p.is_file():manifest[str(p.relative_to(home))]=sha(p)
 full={(r['api'],r['case'],r['path']):r['state']for r in rows if r['mode']=='full'};selective={(r['api'],r['case'],r['path']):r['state']for r in rows if r['mode']=='selective'}
 summary={'modes':summaries,'full_selective_states_equal':full==selective,'agent_sha256':freeze['agent_sha256'],'sources':freeze['sources'],'protected_files_unchanged':preserved_first(),'fresh_deployments':42,'no_performance':True,'all40_completed':False,'Apollo_Gson_implemented':False}
 save(out/'summary.json',summary);save(out/'instances.json',rows);save(out/'changes.json',changes);save(out/'captures-manifest.json',{'files':manifest})
 with(out/'instances.csv').open('w',newline='')as f:
  fields=['api','mode','query_index','case','path','state','positive','TP','FP','FN','previous_TF_state','MT_state','MT_positive','MT_correct_preserved','error','oracle_gap'];w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore',lineterminator='\n');w.writeheader();w.writerows(rows)
 print({m:{k:v for k,v in s.items()if k!='MT_gap'}for m,s in summaries.items()},flush=True)


def historical(root,out):
 from audit_frozen_capability_acceptance import audit
 from audit_execution_closure_revision import fields29
 from audit_transport_observation_revision import key,signatures
 import run_frozen_capability_acceptance as driver
 out.mkdir(parents=True,exist_ok=False);driver.HOME=root;current=audit(root,out/'source-union',partial=True)
 parent=ROOT/'artifacts/contract-routing-revision-20261023/final-v2'
 before={key(r):r for r in load(parent/'capability-audit/source-union/instances.json')};after={key(r):r for r in load(out/'source-union/instances.json')};assert set(before)==set(after)and len(after)==862
 changes=[{'key':k,'before':v['state'],'after':after[k]['state']}for k,v in before.items()if v['state']!=after[k]['state']or signatures(v)!=signatures(after[k])]
 fields29(root,out/'fields29');writes=[];write_changes=[];agent=class_hashes(root/'frozen-base/distributed-observer.jar')
 for role in ('route','price'):
  home=root/('development-'+role+'-frozen');status=load(home/'results.json');assert status['complete']and not any('failure'in r for r in status['results'])
  for p in sorted(home.glob('*/evaluation.json')):
   ev=load(p);old=load(parent/('development-'+role+'-frozen')/p.parent.name/'evaluation.json');assert class_hashes(p.parent/'build/distributed-observer.jar')==agent
   a={(v['case'],v['path']):v for v in old['predictions']};b={(v['case'],v['path']):v for v in ev['predictions']};assert set(a)==set(b)
   for k,v in a.items():
    if v['state']!=b[k]['state']or signatures(v)!=signatures(b[k]):write_changes.append([ev['query'],ev['mode'],k])
   writes.append({'mode':ev['mode'],'query':ev['query'],'targets':ev['targets'],'states':ev['states'],'evaluation_sha256':sha(p)})
 assert len(writes)==30
 # This is historical regression. Do not repeat the compatibility auditor's
 # old unexamined-candidate metadata as a present-day unseen-query claim.
 current['heldout_candidates_unexamined']=0;current['first_unseen_claim']=False;save(out/'source-union/audit.json',current)
 summary={'algorithm':load(root/'algorithm-freeze.json')['commit'],'historical62':current['modes'],'historical62_changes':changes,'fields29':load(out/'fields29/audit.json'),'write15':{m:{'targets':sum(v['targets']for v in writes if v['mode']==m),'states':dict(sum((collections.Counter(v['states'])for v in writes if v['mode']==m),collections.Counter()))}for m in ('full','selective')},'write15_changes':write_changes,'fresh_Agent_deployments':True,'all_passed':not changes and not write_changes,'no_performance':True}
 save(out/'write15-records.json',writes);save(out/'summary.json',summary);assert summary['all_passed'];print(summary,flush=True)

def source_guards(home,out):
 from infer_distributed_fields import Reconstruction
 out.mkdir(parents=True,exist_ok=False);checks=[];boundary=[{'kind':'binding-source'},{'kind':'argument'},{'kind':'http-json','direction':'response','phase':'read'}]
 for mode in ('full','selective'):
  raw=home/'tool-runs/mall-swarm-1'/mode/'query-002/capture/events.jsonl';digest=sha(raw);rows=[json.loads(s)for s in raw.read_text().splitlines()];plan=home/'planning-first/mall-swarm-1/002-plan.json';path=load(plan)['response_binding']['path'];run=load(raw.parents[1]/'results.json');message=next(c['message']for c in run['cases']if c['case']=='input-00')
  def graph_for(label,changed=None):
   work=out/(mode+'-'+label);(work/'build/mall-portal').mkdir(parents=True);(work/'capture/mall-portal').mkdir(parents=True);(work/'build/mall-portal/plan.json').write_bytes(plan.read_bytes());target=work/'capture/mall-portal/events.jsonl'
   if changed is None:target.symlink_to(raw.resolve())
   else:
    for seq,row in enumerate(changed,1):row['seq']=seq
    target.write_text(''.join(json.dumps(row)+'\n'for row in changed))
   return Reconstruction(work/'build',work/'capture',['mall-portal'])
  assert graph_for('positive').query(message,path,'mall-portal',boundary=boundary)['known'],'Guard must have a working positive on the same frozen path'
  for fault in ('wrong-source-callsite','wrong-source-call-id','missing-source','ambiguous-source','wrong-source-caller','missing-source-completion'):
   changed=copy.deepcopy(rows);source=next(row for row in changed if row['kind']=='binding-source'and row.get('message')==message and 'AuthService.getAccessToken'in row.get('callee',''));callid=source['source_call_id']
   if fault=='wrong-source-callsite':source['source_callsite']='other.method()V@0'
   elif fault=='wrong-source-call-id':source['source_call_id']=-999
   elif fault=='missing-source':changed=[row for row in changed if row['kind']!='binding-source']
   elif fault=='ambiguous-source':changed.insert(changed.index(source)+1,copy.deepcopy(source))
   elif fault=='wrong-source-caller':source['source_caller_method']='other.method()V'
   else:changed=[row for row in changed if not(row['kind']=='collection-call-exit'and row.get('call_id')==callid)]
   try:
    answer=graph_for(fault,changed).query(message,path,'mall-portal',boundary=boundary);assert not answer['known'],(mode,fault,answer);status='unknown';error=None
   except ValueError as e:status='rejected';error=str(e)
   checks.append({'mode':mode,'fault':fault,'path':path,'positive_control_known':True,'state':status,'error':error,'source_capture_sha256':digest})
  assert sha(raw)==digest
 save(out/'checks.json',{'all_passed':True,'checks':checks,'derived_only':True});print({'source_guards':len(checks),'all_passed':True},flush=True)


if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--stage',choices=('mall','historical','source-guards'),required=True);p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();{'mall':mall,'historical':historical,'source-guards':source_guards}[a.stage](a.root.resolve(),a.out.resolve())
