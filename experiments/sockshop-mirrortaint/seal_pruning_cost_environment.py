"""Record fixed inputs and actual dependencies after diagnosis, before formal costs."""
import argparse,inspect,json,os,subprocess
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save,sha

def run(home):
 assert load(home/'coarse/complete.json')['complete']
 cached={};tasks={}
 def digest(p):
  p=Path(p)
  if str(p)not in cached:cached[str(p)]={'sha256':sha(p),'bytes':p.stat().st_size}
  return cached[str(p)]
 for task in load(home/'protocol-before-change.json')['order']:
  folder=home/'coarse'/(task+'-none');cfg=load(folder/'compose.json');services={}
  for role,s in cfg['services'].items():
   files={};runtime={}
   for v in s.get('volumes',[]):
    if not isinstance(v,str)or not v.startswith('/'):continue
    src,target=v.split(':')[:2];p=Path(src)
    if 'cost-probe.jar'in target or target.startswith('/tf2/capture'):continue
    if p.is_file():files[src]=digest(p)
    elif 'jdk'in target.lower()or target.startswith('/usr/lib/jvm'):
     for name in ('bin/java','release','jre/lib/rt.jar'):
      f=p/name
      if f.exists():runtime[str(f)]=digest(f)
   services[role]={'image':s['image'],'cpus':s.get('cpus'),'mem_limit':s.get('mem_limit'),'command_before_ablation_options':[x for x in s.get('command',[])if not x.startswith(('-javaagent:/tf2/cost-probe','-Dprobe.','-Dservice.diagnostic.','-Dservice.target.observation=','-Dservice.write.observation=','-Dservice.body.observation='))],'mounted_file_hashes':files,'runtime_files':runtime}
  tasks[task]={'services':services,'task_plan':load(home/'protocol-before-change.json')['tasks'][task]['plan'],'original_input_constructor':'run_frozen_locality_cost.request: original valid admin OAuth login'if task=='mall'else'Original six sealed pagination or dictionary templates, cycled without replacement by outcome'}
 scripts=['run_pruning_cost_audit.py','run_pruning_audit_pipeline.py','measure_pruning_cost_offline.py','summarize_pruning_cost_audit.py','verify_pruning_short_answers.py','verify_pruning_same_capture.py','run_shared_work_business.py','run_target_closure_cost.py','run_frozen_locality_cost.py','raw_source_call_facts.py','audit_zlt_foundation_revision.py','external_transfer_oracle.py','check_pruning_target_completeness.py','seal_pruning_cost_environment.py','run_pruning_switch_controls.py','PruningCostProbeAgent.java']
 save(home/'formal-environment-before-runs.json',{'tasks':tasks,'driver_sources':{n:sha(HERE/n)for n in scripts},'frozen_matrix_sha256':sha(home/'formal-matrix-after-diagnosis.json'),'date':'Written after short/coarse diagnosis, before formal first deployment. Does not backdate expanded measurement details.','offline_logical_CPU':min(os.sched_getaffinity(0)),'OS_page_cache_cleared':False,'startup_only_controls':True,'no_new_business_prewarm':True,'docker_ps_before_formal':subprocess.check_output(['docker','ps','--format','{{.Names}}'],text=True).splitlines(),'machine':subprocess.check_output(['uname','-a'],text=True).strip()})
 print('Actual environments and driver hashes sealed before formal measurement')

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--home',required=True,type=Path);run(p.parse_args().home.resolve())
