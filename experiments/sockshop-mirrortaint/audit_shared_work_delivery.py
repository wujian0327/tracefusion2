"""Check completed experiment receipts; never substitute for business execution."""
import argparse,hashlib,json,zipfile
from pathlib import Path
from run_planned_service import ROOT,load,save,sha

def run(home,out):
 out.mkdir(parents=True,exist_ok=False)
 assert load(home/'postprocessing-complete.json')['strict_clean_round_used']
 assert load(home/'capability-pass-01/summary.json')['passed']
 integrity=load(home/'final-source-and-oracle-integrity.json')
 assert integrity['core139_unchanged'] and integrity['four_original_captures_and_plans_unchanged']
 assert all(r['all_original_pair_results_equal']for r in integrity['checks'])
 b=load(home/'binary-source-receipt.json')
 for f in b['files']:assert sha(ROOT/f['file'])==f['sha256']
 for scope in ('offline-paired-formal','offline-standard-volume/paired'):
  r=load(home/scope/'results.json');assert r['answers_full_graph_and_root_audits_equal'] and len(r['records'])==40
 r=load(home/'indexed-oracle-paired/results.json');assert r['all_answers_and_independent_coordinates_equal'] and len(r['records'])==80
 for scope in ('index-protection','new-capture-protection'):
  checks=load(home/scope/'checks.json')['checks'];assert len(checks)==24 and all(c['state']in('rejected','unknown')for c in checks)
 c1=load(home/'final-C1-score/summary.json')['states'];c2=load(home/'final-C2-score/summary.json')['states']
 for m in ('full','selective'):
  assert c1[m]=={'known_correct':80,'unknown':9} and c2[m]=={'known_correct':5}
 metrics=load(home/'derived-final/summary.json');assert metrics['online']['raw_resource_summaries_exact']
 result={'passed':True,'algorithm':'4cb5943c8b43f3f1eecace85dc462cf75d8294eb','core_sources':139,'RuoYi_C1':c1,'RuoYi_C2':c2,'new_Agent_historical_acceptance_passed':True,'full_graph_versions_selectors_root_audits_equal':True,'source_pair_results_equal':integrity['checks'],'strict_clean_round_override_used':True,'original_interference_disclosed':load(home/'measurement-interference.json'),'online_paired':metrics['online']['paired'],'offline_core_and_score':{k:{'paired':v['paired']}for k,v in load(home/'oracle-derived-recheck/oracle-summary.json').items()},'no_new_framework_semantics_or_pruning':True,'results_are_development_regression_not_unseen_validation':True}
 save(out/'summary.json',result)
 print('Delivery receipts, complete captures and protected states validated')

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.home.resolve(),a.out.resolve())
