"""Only after all online work: audit, aggregate, report and back up, without push."""
import argparse,json,shutil,subprocess,sys,time
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save,sha

def run(home):
 deadline=time.monotonic()+12*3600
 while not(home/'pipeline-complete.json').exists():
  if time.monotonic()>deadline:raise RuntimeError('Pipeline incomplete; do not publish results')
  time.sleep(15)
 def execute(script,args,name):
  with(home/(name+'.log')).open('w')as f:subprocess.run([sys.executable,str(HERE/script),*map(str,args)],stdout=f,stderr=subprocess.STDOUT,check=True)
 execute('audit_pruning_cost_delivery.py',['--home',home,'--out',home/'delivery-audit'],'delivery-audit')
 execute('summarize_pruning_cost_audit.py',['--home',home,'--formal','--out',home/'derived-final'],'derive-final')
 report=HERE/'PRUNING-CONTRIBUTION-AUDIT-20261106.md'
 execute('report_pruning_cost_audit.py',['--home',home,'--summary',home/'derived-final/summary.json','--out',report],'generate-report')
 full=load(home/'derived-final/summary.json');small={'gates':load(home/'delivery-audit/summary.json'),'formal_matrix':{task:{'selected_arms':v['selected_arms'],'omission_vectors':v['omission_vectors']}for task,v in load(home/'formal-matrix-after-diagnosis.json')['tasks'].items()},'diagnosis':{task:{arm:rec['counts']for arm,rec in arms.items()}for task,arms in full['diagnosis'].items()},'coarse_baseline_diagnosis':{task:{k:v for k,v in rec.items()if k!='methods'}for task,rec in full['coarse_baseline_diagnosis'].items()},'formal':{'paired':full['formal']['paired'],'resource_recomputed_exact':True,'independent_oracle_is_excluded_from_trace':True},'frozen_agent_files':load(home/'agent-content-equivalence.json')['JAR_files'],'scope':'Existing development tasks; no new framework semantics or MT cost ranking.'}
 result=HERE/'pruning-contribution-results-20261106.json';save(result,small);csv=HERE/'pruning-contribution-rounds-20261106.csv';shutil.copyfile(home/'derived-final/rounds.csv',csv)
 delivery=home/'delivery';delivery.mkdir(exist_ok=False)
 files=[report,result,csv,*[HERE/n for n in('PruningCostProbeAgent.java','run_pruning_cost_audit.py','run_pruning_audit_pipeline.py','measure_pruning_cost_offline.py','summarize_pruning_cost_audit.py','report_pruning_cost_audit.py','audit_pruning_cost_delivery.py','seal_pruning_cost_environment.py','check_pruning_target_completeness.py','verify_pruning_short_answers.py','verify_pruning_same_capture.py','run_pruning_switch_controls.py','backup_pruning_cost_audit.py','finish_pruning_cost_audit.py')]]
 for p in files:shutil.copyfile(p,delivery/p.name)
 save(home/'delivery-file-hashes.json',{p.name:sha(p)for p in files})
 with(home/'source-code-main-at-delivery.tar.gz').open('wb')as f:subprocess.run(['git','archive','--format=tar.gz','HEAD'],stdout=f,check=True)
 execute('backup_pruning_cost_audit.py',['--home',home,'--out',ROOT/'artifacts/backups/pruning-contribution-audit-20261106','--receipt',HERE/'pruning-contribution-backup-20261106.json'],'backup-final')
 save(home/'delivery-complete.json',{'complete':True,'main_commit_pending_small_results':True,'report':str(report),'all_online_finished_before_postprocessing':True,'no_push':True})
 print('Pruning contribution reports and backups complete',flush=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--home',required=True,type=Path);run(p.parse_args().home.resolve())
