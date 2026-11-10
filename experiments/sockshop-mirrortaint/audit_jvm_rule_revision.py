"""Frozen sources, independent raw facts and complete-capture delivery checks."""
import argparse,csv,json
from pathlib import Path
from run_planned_service import ROOT,load,save,sha
from run_jvm_rule_revision import H,verify

def run(out):
 out.mkdir(parents=True,exist_ok=False);freeze=verify();checks=[]
 protocol=load(H/'protocol-before-tools.json')
 for path,digest in protocol['binary_and_environment_files'].items():assert sha(Path(path))==digest,path
 initial=load(H/'protocol-before-change.json')
 unchanged_contracts=[p for p,d in initial['baseline_sources'].items()if p.endswith('.json')and sha(Path(p))==d]
 assert len(unchanged_contracts)==30
 for root in ('primitive-controls-01','primitive-guard-off-01'):
  signatures={}
  for mode in ('full','selective'):
   rows=[json.loads(s)for s in(H/root/mode/'events.jsonl').read_text().splitlines()];by={r['seq']:r for r in rows};sources={r['seq']:i for i,r in enumerate(r for r in rows if r['kind']=='binding-source')}
   def norm(t):
    if t[0]=='field':
     e=by[t[1]];f=e['fields'][t[2]];return(e['callee'],sources[e['seq']],f['field'],f['version'])
    return tuple(t)
   result=load(H/root/'results.json')[mode]
   signatures[mode]=[(r['answer']['known'],r['answer']['version'],sorted(map(norm,r['answer']['origins']),key=repr),sorted(map(norm,r['answer']['selectors']),key=repr))for r in result['checks']]
   writes=[r for r in rows if r['kind']=='write'and r['field']=='JvmRuleFixture$Data.a'and '.root('in r['site']]
   assert len(writes)==2 and all(r['version']==2 and r['observed']['value']==7 for r in writes)
   checks.append({'control':root,'mode':mode,'same_value_alias_writes':len(writes),'actual_versions':[r['version']for r in writes],'version_only':sum(r['kind']=='write-version'for r in rows),'known':sum(c['answer']['known']for c in result['checks']),'capture_sha256':sha(H/root/mode/'events.jsonl')})
  assert signatures['full']==signatures['selective'],root
 # New app first results, including the exact pre-query failure stage.
 original=load(H/'new-app-original-requests/requests.json');results=load(H/'new-app-first-run-results.json');app=[];targets=[]
 obligations=load(H/'new-app-original-requests/raw-obligations.json')
 for r in results:
  reference=[o for o in original if o['id']==r['query']];assert len(reference)==len(r['requests'])
  for old,new in zip(reference,r['requests']):assert new['status']==old['status']==200 and new['body']==old['body']
  rows=[json.loads(s)for s in(H/'new-app-first-runs'/(r['query']+'-'+r['mode'])/'capture/events.jsonl').read_text().splitlines()];assert rows[-1].get('capture_invalid')is True
  p=load(H/'new-app-first-planning'/(r['query']+'-plan.json'));problem=next(v for v in rows if v['kind']=='problem');frame=next(v for v in rows if v['kind']=='enter'and v['frame']==problem['frame']);entry=next(v for v in rows if v['kind']=='enter'and v['method']==p['entry']);assert problem['seq']<entry['seq']
  app.append({'query':r['query'],'mode':r['mode'],'business_full_responses_equal':True,'requests':len(reference),'first_problem':problem,'first_problem_method':frame['method'],'before_first_query_root':True,'source_facts':r['binding_sources'],'state':'evidence_invalid','oracle_adequate':False,'need':'Framework metadata snapshot qualification/non-string key contract, then actual repository-call coverage; no source-boundary changes.','not_proven':'Fixing the first blocker has not been shown sufficient.'})
  for row in obligations:
   if row['query']==r['query']and row['mode']==r['mode']:targets.append({**row,'state':'evidence_invalid','known_correct':'','first_blocker':problem['message']})
 with(out/'new-app-targets.csv').open('w',newline='')as f:
  w=csv.DictWriter(f,fieldnames=list(targets[0]));w.writeheader();w.writerows(targets)
 jobs=load(H/'formal-order-before-timing.json')['jobs'];assert len(jobs)==60;counts={}
 for job in jobs:
  d=H/'formal'/('%02d-%s-%s'%(job['round'],job['tier'],job['mode']));assert load(d/'formal-job.json')['passed']
  a=load(d/'audit/summary.json');assert a['business_passed']==a['requests']==180
  if job['mode']!='original':assert a['correct']==180
  counts[job['mode']]=counts.get(job['mode'],0)+a['requests']
  assert sha(d/'compose.json') # retained exact deployment configuration
 legacy=load(H/'legacy-comparison-02/results.json');assert all(r['entire_result_equal']for r in legacy['complete_captures'])
 save(out/'results.json',{'current_checked_core':freeze['frozen_commit'],'measurement_and_first_reuse_core':freeze.get('measurement_core_commit',freeze['frozen_commit']),'checks':checks,'full_selective_status_version_origins_selectors_equal':True,'cross_jvm_object_ids_compared':False,'contracts_unchanged':len(unchanged_contracts),'new_app':app,'formal_requests_by_mode':counts,'legacy_complete_captures':legacy['complete_captures'],'derived_full_projection':'Not claimed: full capture does not record a pre-omission guard success.','counterexample_development_note':'Initial audit selected constructor writes together with the two root overwrites; final check uses declared root PUTFIELD sites. Raw captures were never filtered or rewritten.'})

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);run(p.parse_args().out.resolve())
