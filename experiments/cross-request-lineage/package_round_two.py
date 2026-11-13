#!/usr/bin/env python3
"""Package new round-two raw directories with portable file content and hashes."""
import argparse
import json
from pathlib import Path
import shutil
import tarfile
from run import ROOT,HERE,CORE,save,sha


def package(out,includes):
    selected=[p.resolve()for p in includes]if includes else sorted(p for p in (ROOT/'artifacts').glob('cross-request-lineage-round-two-*')if '-delivery-'not in p.name)
    out.mkdir(parents=True,exist_ok=False);snapshot=out/'source-snapshot'
    for directory in (HERE,CORE):
        dest=snapshot/directory.relative_to(ROOT);dest.mkdir(parents=True)
        for p in directory.iterdir():
            if p.is_file()and p.suffix in ('.java','.py','.json','.md')and not p.name.startswith('results-round-two'):shutil.copyfile(p,dest/p.name)
    selected.append(snapshot);files={}
    for folder in selected:
        assert folder!=out and folder.is_relative_to(ROOT)
        for p in folder.rglob('*'):
            if not p.is_file()or '__pycache__'in p.parts:continue
            if not p.resolve().is_relative_to(ROOT):continue
            files[str(p.relative_to(ROOT))]=sha(p)
    save(out/'evidence-files.json',files)
    archive=out/'raw-evidence.tar.gz'
    with tarfile.open(archive,'w:gz')as tar:
        for relative in sorted(files):
            p=ROOT/relative;info=tar.gettarinfo(str(p.resolve()),arcname=relative)
            with p.open('rb')as source:tar.addfile(info,source)
        tar.add(out/'evidence-files.json',arcname='evidence-files.json')
    with tarfile.open(archive,'r|gz')as tar:
        import hashlib
        verified=set()
        for member in tar:
            if member.name in files:
                assert hashlib.sha256(tar.extractfile(member).read()).hexdigest()==files[member.name],member.name
                verified.add(member.name)
        assert verified==set(files),'Archive file coverage differs'
    receipt={'archive':str(archive.relative_to(ROOT)),'sha256':sha(archive),'bytes':archive.stat().st_size,'files':len(files),'stream_hash_verification':True,'excludes':['__pycache__','external symlink targets'],'source_snapshot':str(snapshot.relative_to(ROOT))}
    save(out/'delivery-receipt.json',receipt);print(json.dumps(receipt));return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--include',type=Path,action='append');a=p.parse_args();package(a.out.resolve(),a.include)
