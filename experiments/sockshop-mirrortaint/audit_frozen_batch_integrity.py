#!/usr/bin/env python3
"""Recompute resource aggregates and protect captured/reference bytes."""
import argparse,collections,json
from pathlib import Path
from run_frozen_zlt_reuse import ROOT,load,save,sha
from run_frozen_locality_cost import verify

def run(home):
 import run_sockshop_cost as cost
 sources=verify();out=home/'final-integrity';out.mkdir(exist_ok=False);checks={}
 for p,h in load(home/'experiment-code-before-formal.json')['sources'].items():assert sha(ROOT/p)==h,p
 for p,h in load(home/'common-files-before-formal.json')['files'].items():assert sha(Path(p))==h,p
 checks['frozen_core_files']=len(sources);checks['experiment_and_common_inputs_unchanged']=True
 z=ROOT/'artifacts/frozen-zlt-reuse-20261030'
 for p,h in load(z/'raw-files-before-scoring.json')['files'].items():assert sha(z/p)==h,p
 checks['reuse_first_files_unchanged']=len(load(z/'raw-files-before-scoring.json')['files'])
 strict=load(home/'certificate-review/permanent-counterexample-and-guards-manifest.json');base=Path(strict['reference_root'])
 for p,h in strict['files'].items():assert sha(base/p)==h,p
 checks['confirmed_counterexample_and_final_guard_files_unchanged']=len(strict['files'])
 images=[];rounds=[]
 for trial in sorted(home.glob('round-*')):
  if not trial.is_dir():continue
  result=load(trial/'result.json');assert result['cleanup_returncode']==0 and result['requests']==result['business_passed']==180
  raw=[json.loads(s)for s in(trial/'resources.jsonl').read_text().splitlines()];sampler=cost.Sampler.__new__(cost.Sampler);sampler.containers={r:None for r in raw[0]};sampler.observed_roles=('admin','auth','portal');sampler.rows=raw;sampler.errors=[]
  phase=load(trial/'measure.json');assert sampler.summary(phase['start_ns'],phase['end_ns'])==load(trial/'resource-summary.json'),'Resource summary differs '+trial.name
  cfg=load(trial/'compose.json');ids={r:s['image']for r,s in cfg['services'].items()};images.append(ids)
  assert all(s['cpus']==1 for s in cfg['services'].values())
  for r in('admin','auth','portal'):assert '-Xms32m'in cfg['services'][r]['command']and '-Xmx256m'in cfg['services'][r]['command']
  for p in(trial/'capture').glob('*')if(trial/'capture').exists()else[]:
   if p.is_file()and p.name.endswith('.jsonl'):
    # A closed immutable file, not a still-visible write window.
    assert p.read_bytes().endswith(b'\n'),p
  rounds.append({'trial':trial.name,'business_requests':180,'resource_raw_rows':len(raw),'resource_summary_exact':True})
 assert len(rounds)==20 and all(i==images[0]for i in images),'Image set changed across modes'
 checks.update(formal_deployments=20,formal_requests=3600,resource_summaries_exact=20,same_images_all_modes=True)
 counts=collections.Counter();records={}
 for root,label in((home,'cost'),(z,'reuse')):
  files={}
  # Do not hash this audit's own output or follow external reference symlinks.
  for p in root.rglob('*'):
   if p.is_file()and not p.is_symlink()and not p.is_relative_to(out):files[str(p.relative_to(root))]=sha(p)
  records[label]=files;counts[label]=len(files)
 save(out/'round-checks.json',rounds);save(out/'files-manifest.json',records);save(out/'summary.json',{'all_passed':True,**checks,'files_hashed':dict(counts),'driver_sha256':sha(Path(__file__))});print(checks)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--home',required=True,type=Path);a=p.parse_args();run(a.home.resolve())
