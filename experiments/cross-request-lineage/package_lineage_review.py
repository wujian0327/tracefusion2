#!/usr/bin/env python3
"""Portable raw-evidence subset for offline review, small enough to commit.

Original bytes are retained. This does not replace the complete raw archive:
JVM binaries, dependency JARs, build classes and runtime installations are not
needed for offline prediction/scoring and are listed as excluded explicitly.
"""
import argparse
import hashlib
from pathlib import Path
import tarfile
from run import ROOT,load,save,sha


def package(run,out,round_name):
    out.mkdir(parents=True,exist_ok=False);selected={}
    for p in run.rglob('*'):
        if not p.is_file()or p.is_symlink():continue
        relative=p.relative_to(run)
        keep=(len(relative.parts)==1 and p.suffix in ('.json','.log'))or relative.parts[0]=='captures'and p.name in ('run.json','http.jsonl','events.jsonl','native.jsonl','process.log')or str(relative)in ('build/manifest.json','build/tf/build.json','build/tf/A/plan.json','build/tf/B/plan.json')
        if keep:selected['capture/'+str(relative)]=p
    files={name:sha(p)for name,p in selected.items()};save(out/'files.sha256.json',files)
    archive=out/'offline-review.tar.gz'
    with tarfile.open(archive,'w:gz')as tar:
        for name,p in sorted(selected.items()):tar.add(p,arcname=name,recursive=False)
        tar.add(out/'files.sha256.json',arcname='files.sha256.json')
    with tarfile.open(archive,'r|gz')as tar:
        verified=set()
        for m in tar:
            if m.name in files:assert hashlib.sha256(tar.extractfile(m).read()).hexdigest()==files[m.name];verified.add(m.name)
        assert verified==set(files)
    save(out/'receipt.json',{'round':round_name,'original_capture':str(run.relative_to(ROOT)),'archive':str(archive.relative_to(ROOT)),'sha256':sha(archive),'bytes':archive.stat().st_size,'files':len(files),'raw_bytes_unchanged':True,'purpose':'All inputs for JVM-free replay, independent scoring and regeneration of synthetic evidence checks','excludes':['Agent/dependency/runtime binaries','compiled classes','source snapshot (in Git and full archive)','derived negatives (regenerated from raw positives)']})
    print(archive,archive.stat().st_size)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--round',required=True);a=p.parse_args();package(a.run.resolve(),a.out.resolve(),a.round)
