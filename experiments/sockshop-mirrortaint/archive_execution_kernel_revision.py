#!/usr/bin/env python3
"""Content-deduplicated evidence archive with every regular path verified."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
from run_planned_service import ROOT,load,save,sha
from run_query_planner import JARS


def archive(root,out,extra=()):
    assert not out.is_relative_to(root);out.mkdir(parents=True,exist_ok=False)
    selected=[root,ROOT/'artifacts/baseline-capability-20261020',
        ROOT/'artifacts/call-lifecycle-revision-20261020/base-build',
        ROOT/'artifacts/call-lifecycle-revision-20261020/cart-create-guard',
        ROOT/'artifacts/query-coverage-first-20261019/pool.json',
        ROOT/'artifacts/desktop-inputs/images-lock.json',
        ROOT/'artifacts/trainticket-cost-preparation-20261016/inputs/inputs.json',
        ROOT/'artifacts/real-path-expansion-preflight-20261015/images.json',*JARS,*extra]
    inputs=load(ROOT/'artifacts/trainticket-cost-preparation-20261016/inputs/inputs.json');selected += [Path(v['jar']) for v in inputs.values()]
    files={}
    for path in selected:
        assert path.exists(),path
        for p in ([path,*path.rglob('*')] if path.is_dir() else [path]):
            if '__pycache__' not in p.parts:files[str(p.relative_to(ROOT))]=p
    content={};manifest={};tarpath=out/'evidence.tar.gz'
    with tarfile.open(tarpath,'w:gz',compresslevel=6,dereference=False) as tar:
        for name,p in sorted(files.items()):
            info=tar.gettarinfo(str(p),arcname=name)
            if p.is_symlink():manifest[name]={'kind':'symlink','target':str(p.readlink())};tar.addfile(info)
            elif p.is_file():
                digest=sha(p);manifest[name]={'kind':'file','sha256':digest,'bytes':p.stat().st_size}
                if digest in content:info.type=tarfile.LNKTYPE;info.linkname=content[digest];info.size=0;tar.addfile(info)
                else:
                    content[digest]=name
                    with p.open('rb') as source:tar.addfile(info,source)
            else:manifest[name]={'kind':'directory'};tar.addfile(info)
    save(out/'manifest.json',manifest);checked=0;verified={};seen=set()
    with tarfile.open(tarpath,'r|gz') as tar:
        for member in tar:
            name=member.name;expected=manifest[name];seen.add(name)
            if member.issym():assert member.linkname==expected['target'];continue
            if expected['kind']!='file':continue
            if member.islnk():assert verified[member.linkname]==expected['sha256']
            else:
                h=hashlib.sha256();stream=tar.extractfile(member)
                while True:
                    b=stream.read(1024*1024)
                    if not b:break
                    h.update(b)
                assert h.hexdigest()==expected['sha256'],name
            verified[name]=expected['sha256'];checked+=1
    assert seen==set(manifest)
    bundle=out/'repository.bundle';subprocess.run(['git','bundle','create',str(bundle),'--all'],cwd=ROOT,check=True)
    verify=subprocess.run(['git','bundle','verify',str(bundle)],cwd=ROOT,text=True,capture_output=True,check=True)
    (out/'bundle-verify.log').write_text(verify.stdout+verify.stderr)
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    result={'all_passed':True,'commit':commit,'algorithm_commit':load(root/'algorithm-freeze.json')['commit'],'regular_file_paths_verified':checked,'unique_contents':len(content),
        'archive_bytes':tarpath.stat().st_size,'archive_sha256':sha(tarpath),'manifest_sha256':sha(out/'manifest.json'),'bundle_sha256':sha(bundle),'same_disk_only':True,'docker_image_layers_included':False,'push_performed':False}
    save(out/'verification.json',result)
    (out/'START-HERE.txt').write_text('统一执行依赖内核循环试点备份\n\n提交：'+commit+'\n算法冻结：'+result['algorithm_commit']+'\n\nevidence.tar.gz 包含本轮原始证据、首次失败、九个原JAR、依赖和用于旧213答案离线回归的原能力工件。\nSHA256：'+result['archive_sha256']+'\n逐路径校验：'+str(checked)+' 个常规文件。\nrepository.bundle 保存代码历史，git bundle verify 已通过。\n\n这是同盘副本，不是异机冗余；不含Docker镜像层，须按记录digest另行准备。\n归档路径相对仓库根目录；历史符号链接/配置含绝对路径，迁移后在新目录重新构建。\n报告：experiments/sockshop-mirrortaint/EXECUTION-KERNEL-PILOT-20261020.md\n整体382/431验收尚未完成。推送由用户完成。\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',required=True,type=Path);p.add_argument('--out',required=True,type=Path);a=p.parse_args();archive(a.root.resolve(),a.out.resolve())
