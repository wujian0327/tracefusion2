#!/usr/bin/env python3
"""Verified same-disk archive; no Docker image layers or symlink traversal."""
import argparse,hashlib,json,stat,tarfile
from pathlib import Path
from run_planned_service import ROOT,load,save,sha
from run_query_planner import JARS


def archive(evidence,out):
    roots=[evidence,ROOT/'artifacts/query-coverage-first-20261019/jars',ROOT/'artifacts/query-coverage-first-20261019/pool.json',
           ROOT/'artifacts/query-coverage-first-20261019/planning.json',ROOT/'artifacts/desktop-inputs/images-lock.json',
           ROOT/'artifacts/trainticket-cost-preparation-20261016/inputs',ROOT/'artifacts/real-path-expansion-preflight-20261015/images.json',*JARS]
    for name in ('legacy-inputs.json','price-inputs.json','base-inputs.json'):
        roots.extend(Path(v['jar']) for v in load(evidence/name).values())
    paths={}
    def visit(p):
        assert p.exists() or p.is_symlink(),p
        name=str(p.relative_to(ROOT));paths[name]=p
        if p.is_dir() and not p.is_symlink():
            for c in sorted(p.iterdir()):visit(c)
    for p in roots:visit(p)
    records=[]
    for name,p in sorted(paths.items()):
        s=p.lstat();r={'path':name,'mode':stat.S_IMODE(s.st_mode),'uid':s.st_uid,'gid':s.st_gid}
        if p.is_symlink():r.update(type='symlink',target=str(p.readlink()))
        elif p.is_file():r.update(type='file',size=s.st_size,sha256=sha(p))
        else:r.update(type='directory')
        records.append(r)
    out.mkdir(parents=True,exist_ok=True);save(out/'manifest.json',records);by_name={r['path']:r for r in records};stored={};unique_bytes=0
    target=out/'evidence.tar.gz';assert not target.exists(),'Choose another immutable backup destination'
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
                h=hashlib.sha256()
                with tar.extractfile(member) as f:
                    for b in iter(lambda:f.read(1048576),b''):h.update(b)
                checked[member.name]=h.hexdigest();assert checked[member.name]==r['sha256'];verified+=1
            elif member.islnk():assert checked[member.linkname]==r['sha256'];checked[member.name]=checked[member.linkname];verified+=1
            elif member.issym():assert member.linkname==r['target']
    result={'all_passed':True,'file_paths_verified':verified,'unique_contents':len(stored),'unique_bytes':unique_bytes,'archive_bytes':target.stat().st_size,
            'archive_sha256':sha(target),'manifest_sha256':sha(out/'manifest.json'),'bundle_sha256':sha(out/'code.bundle') if (out/'code.bundle').exists() else None,
            'same_disk_only':True,'docker_image_layers_included':False,'symlinks_followed':False}
    save(out/'verification.json',result)
    (out/'START-HERE.txt').write_text('TraceFusion finite-model revision backup\n\ncode.bundle: local main, no push.\nevidence.tar.gz: current revision evidence, original JARs, dependencies and input/image manifests.\nverification.json and manifest.json: verified SHA256.\nSame-disk copy only; Docker image layers are NOT included.\nPrevious 0/20 and 803b92f evidence remain in their existing independent backup; see the revision report.\nOn another computer rebuild in a fresh directory. Original absolute paths and symlinks are evidence and must be reviewed, not executed blindly.\n')
    print(json.dumps(result,indent=2),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();archive(a.root.resolve(),a.out.resolve())
