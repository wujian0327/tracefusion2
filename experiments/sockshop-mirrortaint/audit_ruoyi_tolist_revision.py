"""Final exposed-query audit; frozen core, original inputs, per-JVM truth and separate cohorts."""
import argparse,collections,csv,json
from pathlib import Path
from run_planned_service import ROOT,load,save,sha
from audit_zlt_foundation_revision import tf_pair

def run(home,out):
 out.mkdir(parents=True,exist_ok=False);online=load(home/'final-freeze.json');freeze=load(home/'final-offline-freeze.json')
 for name,digest in freeze['sources'].items():assert sha(Path(name))==digest,name
 for name,digest in load(home/'protocol-before-change.json')['old_files'].items():assert sha(Path(name))==digest,name
 base=home/'final-candidate/historical/frozen-base';assert sha(base/'distributed-observer.jar')==freeze['agent_sha256']
 rows=load(home/'audit-offline-C1/instances.json');previous=load(ROOT/'artifacts/ruoyi-before-advice-20261105/revision-02/audit-final-03/instances.json')
 before={(r['query'],r['mode'],r['case'],r['path']):r for r in previous}
 for r in rows:
  key=(r['query'],r['mode'],r['case'],r['path']);r['previous_round_state']=before[key]['state']if key in before else'not_redeployed_in_previous_round'
  if r['state']=='known_correct':assert r['expected']==r['predicted']and r['oracle_adequate']and len(r['expected'])==1
 counts={mode:dict(collections.Counter(r['state']for r in rows if r['mode']==mode))for mode in('full','selective')}
 assert counts=={'full':{'known_correct':80,'unknown':9},'selective':{'known_correct':80,'unknown':9}},counts
 for mode in('full','selective'):
  for r in rows:
   if r['mode']!=mode:continue
   assert(r['state']=='unknown')==(r['query']=='ruoyi-4'or(r['query']=='ruoyi-2'and r['case']==0))
 logical=lambda r:(r['query'],r['case'],r['path'],r['state'],sorted((s[0],s[3],s[5],s[6])for s in r.get('predicted',[])))
 assert sorted(logical(r)for r in rows if r['mode']=='full')==sorted(logical(r)for r in rows if r['mode']=='selective')
 evidence=[];hashes={}
 for mode in('full','selective'):
  path=home/'final-C1/runs/ruoyi-3'/mode/'capture/events.jsonl';hashes[str(path)]=sha(path);raw=[json.loads(s)for s in path.read_text().splitlines()];index={r['seq']:r for r in raw}
  copies=[r for r in raw if r.get('json_list_copy',{}).get('valid')];assert len(copies)==5
  for copy in copies:
   start=next(r for r in raw if r['kind']=='collection-call-enter'and r['call_id']==copy['call_id']);owner=start['receiver']['object']
   sources=[r for r in raw if r['kind']=='binding-source'and r['callee']=='org/springframework/data/redis/core/ValueOperations.get(Ljava/lang/Object;)Ljava/lang/Object;'and r['seq']<start['seq']and any(index[s]['owner']==owner for s in r.get('json_tree_proofs',[]))]
   assert len(sources)==1;source=sources[0];tf_pair(raw,source)
   assert copy['json_list_copy']['members']==start['collection']==copy['collection_after']
   evidence.append({'mode':mode,'source_seq':source['seq'],'source_call_id':source['source_call_id'],'source_caller':source['source_caller_method'],'source_PC':source['source_pc'],'source_array_owner':owner,'copy_call_id':copy['call_id'],'copy_frame':copy['frame'],'copy_seq':copy['seq'],'new_list':copy['result'],'members':copy['json_list_copy']['members'],'cache_fact':index[copy['json_list_copy']['cache_seq']],'source_fields':source['fields']})
 c2=load(home/'audit-offline-C2/summary.json');assert all(c2['states'][m]=={'known_correct':5}for m in('full','selective'))
 historical=load(home/'capability-pass-01/summary.json');assert historical['passed']and historical['complete']
 graph_receipts=[load(p)for p in sorted(home.glob('graph-compatibility-*/checks.json'))]
 graph_records=[r for receipt in graph_receipts for r in receipt['records']]
 assert len(graph_records)==292 and all(r['complete_graph_equal']for r in graph_records),len(graph_records)
 for receipt in graph_receipts:
  assert receipt['complete']
  for n,digest in receipt['effective_changed_modules'].items():assert sha(Path(__file__).with_name(n+'.py'))==digest
 fixed=load(home/'offline-v2-replay-01/scalar-checks.json');assert len(fixed)==6 and all(r['matched']for r in fixed)
 summary={'algorithm':freeze['commit'],'online_algorithm':online['commit'],'whole_graph_pairs_equal':len(graph_records),'agent_sha256':freeze['agent_sha256'],'C1':load(home/'audit-final-C1/summary.json'),'C2_separate':c2,'full_selective_states_and_logical_sources_equal':True,'all_C1_correct_answers_positive':True,'cold_department_unknown_per_mode':4,'C1_config_declaration_unknown_per_mode':5,'dictionary_actual_copy_calls_per_mode':5,'capability_acceptance':historical,'raw_capture_hashes':hashes,'no_performance_experiments':True,'no_push':True}
 save(out/'summary.json',summary);save(out/'instances.json',rows);save(out/'dictionary-copy-evidence.json',evidence)
 with(out/'instances.csv').open('w',newline='')as f:
  keys=list(dict.fromkeys(k for r in rows for k in r));writer=csv.DictWriter(f,keys,lineterminator='\n');writer.writeheader();writer.writerows(rows)
 print(counts)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.home.resolve(),a.out.resolve())
