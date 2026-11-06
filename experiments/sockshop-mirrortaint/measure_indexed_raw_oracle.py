"""Same normal offline workflow with only independent raw-call lookup indexed."""
import argparse,sys
from pathlib import Path
from raw_source_call_facts import RawSourceCallFacts
from measure_shared_work_revision import worker

def run(home,protocol,task,mode,repo,out,graph=False):
 sys.path.insert(0,str(repo/'experiments/sockshop-mirrortaint'));sys.path.insert(1,str(repo/'scripts'))
 import audit_zlt_foundation_revision as audit
 original=audit.tf_pair;index=None
 def pair(rows,source):
  nonlocal index
  if index is None:index=RawSourceCallFacts(rows)
  return original(index.matching(rows,source),source)
 audit.tf_pair=pair
 # Lazy construction occurs within the scoring stage; no work is omitted from
 # CPU/wall measurements, and no Source/known answer is cached.
 worker(protocol,task,mode,repo,out,False,graph)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);p.add_argument('--protocol',type=Path,required=True);p.add_argument('--task',required=True);p.add_argument('--mode',required=True);p.add_argument('--repo',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--graph',action='store_true');a=p.parse_args();run(a.home.resolve(),a.protocol.resolve(),a.task,a.mode,a.repo.resolve(),a.out.resolve(),a.graph)
