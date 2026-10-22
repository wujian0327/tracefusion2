#!/usr/bin/env python3
"""Frozen original-62 acceptance after private Agent JSON packaging."""
import argparse,copy,os,subprocess
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save,sha
import run_library_gap_acceptance as previous
from run_remaining_semantics_revision import run as development


def prepare(root):
    previous.prepare(root)
    f=load(root/'algorithm-freeze.json')
    f['jackson_isolation_required']=True
    f['experiment_protocol_sha256']=sha(HERE/'jackson-isolation-protocol-20261022.json')
    f['original_runtime_library_caveat']='Agent internal Jackson is private; native business mapper hashes must match original embedded libraries in every capture. No new performance claim.'
    save(root/'algorithm-freeze.json',f)
    for name,group in [('date-controls','date'),('received-controls','received'),('legacy-collection-controls','legacy')]:
        (root/name).symlink_to(root.parent/'frozen-controls'/group,target_is_directory=True)
    (root/'drivers/run_jackson_isolation_acceptance.py').write_bytes(Path(__file__).read_bytes())
    save(root/'isolation-protocol-before-business.json',{'algorithm_commit':f['commit'],'protocol':load(HERE/'jackson-isolation-protocol-20261022.json'),'protocol_sha256':f['experiment_protocol_sha256']})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--prepare',action='store_true');p.add_argument('--out',type=Path);p.add_argument('--group');p.add_argument('--query',action='append');a=p.parse_args();root=a.root.resolve()
    if a.prepare:prepare(root)
    elif a.out:development(root,a.out.resolve(),a.group,a.query)
    else:previous.run(root)
