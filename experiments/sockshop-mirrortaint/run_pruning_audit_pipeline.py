"""Finish diagnosis, freeze a minimal matrix, validate once, then measure sequentially."""
import argparse,subprocess,sys,time
from pathlib import Path
from run_planned_service import HERE,load,save,sha

def run(home):
 deadline=time.monotonic()+8*3600
 while not(home/'short/complete.json').exists():
  if time.monotonic()>deadline:raise RuntimeError('Short diagnosis did not complete; formal measurements not started')
  time.sleep(10)
 def command(script,*args):return[sys.executable,str(HERE/script),*map(str,args)]
 def execute(name,args):
  save(home/'pipeline-progress.json',{'stage':name,'state':'started'})
  with(home/(name+'.log')).open('w')as f:r=subprocess.run(args,stdout=f,stderr=subprocess.STDOUT)
  save(home/(name+'-receipt.json'),{'returncode':r.returncode,'command':args});assert r.returncode==0,name
  save(home/'pipeline-progress.json',{'stage':name,'state':'completed'})
 if not(home/'formal-matrix-after-diagnosis.json').exists():execute('matrix',command('run_pruning_cost_audit.py','matrix','--home',home))
 else:assert load(home/'short-evidence-comparison-02/checks.json')['passed']
 if not(home/'same-capture-compatibility/checks.json').exists():execute('same-capture-compatibility',command('verify_pruning_same_capture.py','--home',home,'--out',home/'same-capture-compatibility'))
 else:assert load(home/'same-capture-compatibility/checks.json')['passed']
 execute('capability',command('run_target_closure_acceptance.py','--root',home/'final-candidate'))
 assert load(home/'capability-pass-01/summary.json')['passed']
 build=home/'final-candidate/historical/frozen-base'
 execute('ruoyi-C1',command('run_ruoyi_tolist_revision.py','run','--home',home/'final-C1','--build',build))
 execute('ruoyi-C1-score',command('run_ruoyi_tolist_revision.py','audit','--home',home/'final-C1','--out',home/'final-C1-score'))
 # Explicit C2 configuration remains distinct; run TF only, unchanged MT reference.
 import run_ruoyi_wrapper_revision as wrapper
 from audit_ruoyi_wrapper_facts import run as audit
 dest=home/'final-C2';wrapper.prepare(dest,build,calibrated=True,inventory=load(build/'ruoyi/model.json')['library_inventory'])
 driver,_=wrapper.install(dest,build);q=load(dest/'task-seal.json')['tasks']['ruoyi'][0]
 for mode in('full','selective'):driver.trial('ruoyi',q,mode)
 audit(dest,home/'final-C2-score')
 for mode in('full','selective'):
  assert load(home/'final-C1-score/summary.json')['states'][mode]=={'known_correct':80,'unknown':9}
  assert load(home/'final-C2-score/summary.json')['states'][mode]=={'known_correct':5}
 save(home/'capability-gate-before-formal.json',{'passed':True,'historical_and_RuoYi_new_deployments':True,'agent_sha256':sha(build/'distributed-observer.jar'),'formal_matrix_sha256':sha(home/'formal-matrix-after-diagnosis.json')})
 execute('formal',command('run_pruning_cost_audit.py','formal','--home',home))
 save(home/'pipeline-complete.json',{'complete':True,'no_MT_or_new_application':True,'formal_without_probe_or_profiler':True})
 print('Pruning audit capability and formal runs complete',flush=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);run(p.parse_args().home.resolve())
