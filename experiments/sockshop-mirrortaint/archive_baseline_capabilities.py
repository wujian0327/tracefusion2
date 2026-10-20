#!/usr/bin/env python3
"""Archive capability evidence/dependencies and verify every regular file."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
from run_planned_service import ROOT,HERE,load,save,sha
from run_query_planner import JARS


def archive(root,out):
    out.mkdir(parents=True,exist_ok=False)
    inputs=ROOT/'artifacts/trainticket-cost-preparation-20261016/inputs/inputs.json'
    selected=[root,ROOT/'artifacts/call-lifecycle-revision-20261020/base-build',
        ROOT/'artifacts/call-lifecycle-revision-20261020/cart-create-guard',
        ROOT/'artifacts/call-lifecycle-revision-20261020/algorithm-freeze.json',
        ROOT/'artifacts/call-lifecycle-revision-20261020/base-inputs.json',
        ROOT/'artifacts/query-coverage-first-20261019/pool.json',
        ROOT/'artifacts/desktop-inputs/images-lock.json',
        ROOT/'artifacts/real-path-expansion-preflight-20261015/images.json',
        ROOT/'artifacts/external-tools/mirrortaint',inputs,*JARS]
    selected += [Path(v['jar']) for v in load(inputs).values()]
    files={}
    for p in selected:
        assert p.exists(),p
        for f in ([p] if not p.is_dir() else [p,*p.rglob('*')]):
            if '__pycache__' not in f.parts:files[str(f.relative_to(ROOT))]=f
    manifest={};content={};archive=out/'evidence.tar.gz'
    with tarfile.open(archive,'w:gz',compresslevel=6,dereference=False) as tar:
        for name,p in sorted(files.items()):
            info=tar.gettarinfo(str(p),arcname=name)
            if p.is_symlink():
                manifest[name]={'kind':'symlink','target':str(p.readlink())};tar.addfile(info)
            elif p.is_file():
                digest=sha(p);manifest[name]={'kind':'file','sha256':digest,'bytes':p.stat().st_size}
                if digest in content:
                    info.type=tarfile.LNKTYPE;info.linkname=content[digest];info.size=0;tar.addfile(info)
                else:
                    content[digest]=name
                    with p.open('rb') as stream:tar.addfile(info,stream)
            elif p.is_dir():manifest[name]={'kind':'directory'};tar.addfile(info)
    save(out/'manifest.json',manifest)
    checked=0;verified_hashes={};seen=set()
    with tarfile.open(archive,'r|gz') as tar:
        for member in tar:
            name=member.name;data=manifest[name];seen.add(name)
            if member.issym():assert member.linkname==data['target'];continue
            if data['kind']!='file':continue
            if member.islnk():assert verified_hashes[member.linkname]==data['sha256'],name
            else:
                stream=tar.extractfile(member);assert stream is not None;h=hashlib.sha256()
                while True:
                    chunk=stream.read(1024*1024)
                    if not chunk:break
                    h.update(chunk)
                assert h.hexdigest()==data['sha256'],name
            verified_hashes[name]=data['sha256'];checked+=1
    assert seen==set(manifest)
    bundle=out/'repository.bundle'
    subprocess.run(['git','bundle','create',str(bundle),'--all'],cwd=ROOT,check=True)
    verified=subprocess.run(['git','bundle','verify',str(bundle)],cwd=ROOT,text=True,capture_output=True,check=True)
    (out/'bundle-verify.log').write_text(verified.stdout+verified.stderr)
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    result={'all_passed':True,'commit':commit,'regular_file_paths_verified':checked,'unique_contents':len(content),
        'archive_bytes':archive.stat().st_size,'archive_sha256':sha(archive),'bundle_sha256':sha(bundle),'manifest_sha256':sha(out/'manifest.json'),
        'same_disk_only':True,'docker_image_layers_included':False,'git_push_performed':False}
    save(out/'verification.json',result)
    (out/'START-HERE.txt').write_text('基线能力对照证据备份\n\n提交：'+commit+'\n源代码/历史：repository.bundle（git bundle verify已通过）\n原始证据、9个原JAR及依赖：evidence.tar.gz\nSHA256：'+result['archive_sha256']+'\n逐路径验证：'+str(checked)+' 个常规文件\n\n这是同盘副本，不是异机冗余。Docker镜像层未包含，使用归档镜像digest另行准备。\n归档路径相对仓库根目录；部分历史符号链接/配置含旧绝对路径，迁移后在新目录重建，不能盲复用旧构建。\n报告：experiments/sockshop-mirrortaint/BASELINE-CAPABILITY-20261020.md\n原0/20与历史成本工件不在本包重复打包，仍保留于各自旧备份。\n所有push交给用户。\n')
    print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();archive(a.root.resolve(),a.out.resolve())
