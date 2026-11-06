"""Final gates for the unchanged semantics and independently controlled omissions."""
import argparse,json
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save,sha

def run(home,out):
 out.mkdir(parents=True,exist_ok=False);assert load(home/'pipeline-complete.json')['complete']
 ref=load(ROOT/'artifacts/shared-transfer-optimization-20261106/final-candidate/historical/algorithm-freeze.json');current=load(home/'final-candidate/historical/algorithm-freeze.json');assert set(ref['sources'])==set(current['sources'])
 changed=[]
 for file,digest in current['sources'].items():
  assert sha(Path(file))==digest,file
  if ref['sources'][file]!=digest:changed.append(file)
 assert changed==[str(HERE/'ExecutionKernelHooks.java')],changed
 assert load(home/'agent-content-equivalence.json')['all_members_equal']
 assert load(home/'same-capture-compatibility/checks.json')['passed']
 assert load(home/'short-evidence-comparison-03/checks.json')['passed']
 assert load(home/'short-target-completeness.json')['same_declared_denominator_all_arms']
 assert load(home/'capability-pass-01/summary.json')['passed']and load(home/'capability-gate-before-formal.json')['passed']
 for mode in('full','selective'):
  assert load(home/'final-C1-score/summary.json')['states'][mode]=={'known_correct':80,'unknown':9}
  assert load(home/'final-C2-score/summary.json')['states'][mode]=={'known_correct':5}
 matrix=load(home/'formal-matrix-after-diagnosis.json');env=load(home/'formal-environment-before-runs.json');assert sha(home/'formal-matrix-after-diagnosis.json')==env['frozen_matrix_sha256']and len(matrix['jobs'])==45
 for name,digest in env['driver_sources'].items():assert sha(HERE/name)==digest,('Formal driver changed',name)
 for repeat,task,arm in matrix['jobs']:
  folder=home/'formal'/('%02d-%s-%s'%(repeat,task,arm));assert load(folder/'complete.json')['complete'];target=load(folder/'target-completeness.json');score=load(folder/'oracle/summary.json');assert score['targets']==score['correct']==target['expected_targets']
  assert not(folder/'capture/monitor-cost.json').exists()and not(folder/'capture/events.jsonl.diagnostic.jsonl').exists()
  options=load(folder/'ablation-options.json');assert not options['diagnostic_only']and options['service_mode']=='selective'
  assert options['Agent_sha256']==load(home/'agent-content-equivalence.json')['JAR_files'][0]['sha256']
  for phase in ('trace','oracle'):assert load(folder/(phase+'-process.json'))['logical_cpu']==env['offline_logical_CPU']
 save(out/'summary.json',{'passed':True,'core_candidate':current['commit'],'core_reference':'4cb5943','source_files':len(current['sources']),'changed_core_files':changed,'scope':'Independent pre-omission control only; all Python reconstruction and contracts unchanged.','same_capture_full_graph_and_root_audits_equal':True,'declared_target_origins_versions_selectors_and_source_occurrences_equal':True,'formal_deployments':45,'formal_drivers_unchanged':True,'necessary_unknown_preserved':True,'MT_rerun':False,'new_applications_or_framework_models':False})
 print('All pruning contribution delivery gates passed')

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--home',required=True,type=Path);p.add_argument('--out',required=True,type=Path);a=p.parse_args();run(a.home.resolve(),a.out.resolve())
