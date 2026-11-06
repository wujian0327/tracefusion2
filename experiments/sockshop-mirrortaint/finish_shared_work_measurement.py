"""Wait for the one capability pass, then measure without overlapping experiments."""
import argparse,copy,json,os,subprocess,sys,time
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save,sha

def run(home):
 gates={'historical':home/'capability-pass-01/summary.json','C1':home/'final-C1-score/summary.json','C2':home/'final-C2-score/summary.json','diagnostics':home/'business-work-diagnostics-02/complete.json','reliability':home/'reliability-final/checks.json'}
 deadline=time.monotonic()+4*3600
 while not all(p.exists()for p in gates.values()):
  save(home/'measurement-wait.json',{'waiting_for':[str(p)for p in gates.values()if not p.exists()],'formal_started':False})
  if time.monotonic()>deadline:raise RuntimeError('Capability pass did not complete; no formal measurements started')
  time.sleep(10)
 assert load(gates['historical'])['passed']
 states=load(gates['C1'])['states'];assert all(states[m]=={'known_correct':80,'unknown':9}for m in('full','selective')),states
 c2=load(gates['C2']);assert all(c2['states'][m]=={'known_correct':5}for m in('full','selective'));assert all(r['business_rows_equal']==27 and r['parent_scope_checks']==5 for r in load(gates['reliability'])['checks']);save(home/'gate-receipt-before-cost.json',{'gates':{k:{'path':str(p),'sha256':sha(p)}for k,p in gates.items()},'C1':states,'C2':c2})
 freeze=load(home/'final-candidate/historical/algorithm-freeze.json')
 for p,h in freeze['sources'].items():assert sha(Path(p))==h,p
 # Resource summaries remain linked to raw sampling records. Never include the
 # count/profiler Agent in this formal workload.
 env={'uname':dict(zip(('sysname','nodename','release','version','machine'),os.uname())),'cpu_affinity':sorted(os.sched_getaffinity(0)),'drivers':{str(HERE/n):sha(HERE/n)for n in('run_shared_work_business.py','measure_shared_work_revision.py',Path(__file__).name)}}
 for name,args in(('containers',['docker','ps','--no-trunc','--format','{{json .}}']),('docker-info',['docker','info','--format','{{json .}}'])):
  env[name]=subprocess.check_output(args,text=True)
 save(home/'environment-before-cost.json',env)
 def execute(args,log):
  with log.open('w')as f:subprocess.run(args,check=True,stdout=f,stderr=subprocess.STDOUT)
 save(home/'measurement-wait.json',{'waiting_for':[],'formal_started':True,'stage':'offline-paired-formal'})
 execute([sys.executable,str(HERE/'measure_shared_work_revision.py'),'run','--home',str(home),'--repo',str(ROOT),'--series','offline-paired-formal'],home/'offline-paired-formal.log')
 execute([sys.executable,str(HERE/'run_shared_work_business.py'),'run','--home',str(home)],home/'online-paired.log')
 # Prespecified same tasks at the standard 180-request workload volume. Compare
 # both offline versions on round one's OLD Agent complete captures; do not pick
 # the capture giving the greatest speedup.
 large=home/'offline-standard-volume';large.mkdir();(large/'old-repository').symlink_to((home/'old-repository').resolve(),target_is_directory=True)
 protocol=copy.deepcopy(load(home/'protocol-before-change.json'));protocol['supplement']='Same tasks and inputs, complete round-01 old-Agent 180-request captures; no result-based capture choice.'
 for task in('zlt-user','ruoyi-dictionary'):
  for mode in('full','selective'):
   trial=home/'online-paired'/('01-'+task+'-old-'+mode);spec=load(trial/'offline-protocol.json')['tasks'][task][mode];protocol['tasks'][task][mode]=spec
 save(large/'protocol-before-change.json',protocol)
 execute([sys.executable,str(HERE/'measure_shared_work_revision.py'),'run','--home',str(large),'--repo',str(ROOT),'--series','paired'],large/'paired.log')
 for p,h in freeze['sources'].items():assert sha(Path(p))==h,p
 save(home/'measurement-complete.json',{'complete':True,'core_sources_unchanged':True,'timed_business_deployments':40,'online_profiler_or_counter':False})

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);run(p.parse_args().home.resolve())
