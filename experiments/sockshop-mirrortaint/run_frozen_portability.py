#!/usr/bin/env python3
"""Run ae7 first-pass tools from an immutable source snapshot while main evolves.
Only filesystem relocation in the experiment verifier changes; no hash bypass.
"""
import argparse,collections,runpy,sys
from pathlib import Path
import json,hashlib
ROOT=Path(__file__).resolve().parents[2]

def main():
 p=argparse.ArgumentParser();p.add_argument('--script',choices=['run_portability_first.py','plan_portability_first.py','run_portability_piggy.py','run_portability_mall.py','run_portability_apollo.py'],required=True);p.add_argument('arguments',nargs=argparse.REMAINDER);a=p.parse_args()
 frozen=ROOT/'artifacts/monitor-reliability-account-20261028/frozen-first-code';assert frozen.exists(),'Frozen source snapshot not prepared'
 link=frozen/'artifacts'
 if not link.exists():link.symlink_to(ROOT/'artifacts',target_is_directory=True)
 here=frozen/'experiments/sockshop-mirrortaint';sys.path.insert(0,str(here))
 import run_portability_first as first
 def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
 def verify(root):
  proto=json.loads((root/'protocol-start.json').read_text());assert proto['TF_commit']=='ae7fe8d8b9e23d8ce197870ff0069c7f1bee84eb'
  assert sha(root/'task-original.json')==proto['task_sha256']
  for old,h in proto['core_sources'].items():
   source=Path(old);assert source.is_relative_to(ROOT);actual=frozen/source.relative_to(ROOT);assert sha(actual)==h,(old,'frozen hash differs')
  native=ROOT/'artifacts/external-tools/mirrortaint/mirrorTaint.jar';assert sha(native)==proto['native_jar_sha256']
  receipt=json.loads((root/'tool-runs/piggymetrics-2/full/query-011/tool-binaries.json').read_text());expected=[h for p,h in receipt['files'].items()if p.endswith('/distributed-observer.jar')];assert expected==[sha(first.BASE/'distributed-observer.jar')]
  task=json.loads((root/'task-original.json').read_text());assert len(task['methods'])==40 and collections.Counter(m['application']for m in task['methods'])=={x['application']:5 for x in task['applications']};return task
 first.verify=verify
 argv=a.arguments[1:]if a.arguments[:1]==['--']else a.arguments
 if a.script=='run_portability_first.py' and argv==['--stage','verify']:
  verify(first.TASK_ROOT);print('Frozen ae7fe8d sources, task, native JAR and Agent verified');return
 assert a.script!='run_portability_first.py','Use the per-application frozen runners; the entry module would redefine the relocation verifier'
 sys.argv=[str(here/a.script),*argv];runpy.run_path(str(here/a.script),run_name='__main__')
if __name__=='__main__':main()
