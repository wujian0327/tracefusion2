"""After all online jobs, run clean round replacement and isolated offline analysis."""
import argparse,subprocess,sys,time
from pathlib import Path
from run_planned_service import HERE,load,save

def run(home):
 deadline=time.monotonic()+5*3600
 while not(home/'measurement-complete.json').exists():
  if time.monotonic()>deadline:raise RuntimeError('Original measurement workflow incomplete')
  time.sleep(10)
 def execute(script,args,log):
  with(home/log).open('w')as f:subprocess.run([sys.executable,str(HERE/script),*map(str,args)],stdout=f,stderr=subprocess.STDOUT,check=True)
 execute('run_shared_work_round_recheck.py',['--home',home],'clean-round-recheck.log')
 execute('run_raw_oracle_benchmark.py',['--home',home],'indexed-oracle-benchmark.log')
 execute('summarize_shared_work_revision.py',['--home',home,'--out',home/'derived-final'],'derived-final.log')
 save(home/'postprocessing-complete.json',{'complete':True,'strict_clean_round_used':True,'all_original_records_retained':True,'separate_scoring_optimization':True})

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);run(p.parse_args().home.resolve())
