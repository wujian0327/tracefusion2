#!/usr/bin/env python3
"""Content-verified local evidence backup, with duplicate immutable files linked.

The archive stores symlinks without following them, never extracts them, and
contains no Docker image layers. Git bundle is supplied separately by the caller.
"""
import argparse
import hashlib
import json
from pathlib import Path
import stat
import tarfile
from run_planned_service import ROOT,load,save,sha


def archive(out):
    evidence=ROOT/'artifacts/response-binding-revision-20261019'
    from run_query_planner import JARS
    roots=[evidence,ROOT/'artifacts/query-coverage-first-20261019',ROOT/'artifacts/trainticket-cost-preparation-20261016/inputs',
           ROOT/'artifacts/desktop-inputs/images-lock.json',ROOT/'artifacts/real-path-expansion-preflight-20261015/images.json',*JARS]
    roots += [Path(q['jar']) for q in load(evidence/'legacy-inputs.json').values()]
    paths={}
    def visit(p):
        assert p.exists() or p.is_symlink(),p
        name=str(p.relative_to(ROOT));paths[name]=p
        if p.is_dir() and not p.is_symlink():
            for child in sorted(p.iterdir()):visit(child)
    for p in roots:visit(p)
    out.mkdir(parents=True,exist_ok=True);records=[]
    for name,p in sorted(paths.items()):
        s=p.lstat();r={'path':name,'mode':stat.S_IMODE(s.st_mode),'uid':s.st_uid,'gid':s.st_gid}
        if p.is_symlink():r.update(type='symlink',target=str(p.readlink()))
        elif p.is_file():r.update(type='file',size=s.st_size,sha256=sha(p))
        else:r.update(type='directory')
        records.append(r)
    save(out/'manifest.json',records);by_name={r['path']:r for r in records};stored={};unique_bytes=0
    target=out/'evidence.tar.gz';assert not target.exists(),'Backup immutable; choose a new directory'
    with tarfile.open(target,'w:gz',compresslevel=1,dereference=False) as tar:
        for r in records:
            p=paths[r['path']];info=tar.gettarinfo(str(p),arcname=r['path'])
            if r['type']=='file':
                key=(r['sha256'],r['size'],r['mode'],r['uid'],r['gid'])
                if key in stored:info.type=tarfile.LNKTYPE;info.linkname=stored[key];info.size=0;tar.addfile(info)
                else:
                    stored[key]=r['path'];unique_bytes+=r['size']
                    with p.open('rb') as f:tar.addfile(info,f)
            else:tar.addfile(info)
    checked={};verified=0
    with tarfile.open(target,'r:gz') as tar:
        for member in tar:
            r=by_name[member.name]
            if member.isfile():
                digest=hashlib.sha256()
                with tar.extractfile(member) as f:
                    for data in iter(lambda:f.read(1024*1024),b''):digest.update(data)
                checked[member.name]=digest.hexdigest();assert checked[member.name]==r['sha256'];verified+=1
            elif member.islnk():
                assert checked[member.linkname]==r['sha256'];checked[member.name]=checked[member.linkname];verified+=1
            elif member.issym():assert member.linkname==r['target']
    result={'all_passed':True,'file_paths_verified':verified,'unique_file_contents':len(stored),'unique_bytes':unique_bytes,
            'archive_bytes':target.stat().st_size,'archive_sha256':sha(target),'manifest_sha256':sha(out/'manifest.json'),
            'bundle_sha256':sha(out/'code.bundle') if (out/'code.bundle').exists() else None,
            'same_disk_only':True,'docker_images_included':False,'symlinks_followed':False,'deduplication':'Tar hard links for equal content, permissions and ownership; live evidence unchanged.'}
    save(out/'verification.json',result)
    (out/'START-HERE.txt').write_text('TraceFusion response-binding revision local backup\n\nSee verification.json for SHA256 and manifest.json for each original path.\ncode.bundle contains local main; evidence.tar.gz contains raw evidence, original JARs, dependency JARs and input/image locks.\nThis is a same-disk backup, not off-machine redundancy. Docker images are NOT included.\nAbsolute workspace symlinks and frozen build paths are retained as evidence: on another machine rebuild in a fresh directory, preserve original hashes, and review paths instead of executing old absolute paths blindly.\nArchive verification reads content without extracting symlinks.\n')
    print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();archive(a.out.resolve())
