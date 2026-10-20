#!/usr/bin/env python3
"""Reuse verified content archive, identify the final application-call freeze."""
import argparse,json
from pathlib import Path
from archive_execution_kernel_revision import archive
from run_planned_service import load,save


def run(root,out):
    archive(root,out)
    final=load(root/'algorithm-freeze-final.json');v=load(out/'verification.json');v['predecessor_algorithm_commit']=v['algorithm_commit'];v['algorithm_commit']=final['commit'];save(out/'verification.json',v)
    (out/'START-HERE.txt').write_text('非递归应用调用与字段效果备份\n\n代码提交：'+v['commit']+'\n最终算法冻结：'+v['algorithm_commit']+'\n初始候选：'+v['predecessor_algorithm_commit']+'\n\nevidence.tar.gz 包含本轮原始捕获、首次失败、原业务JAR和依赖、构造写入缺失反例副本，以及旧213答案离线回归的原能力工件。\nSHA256：'+v['archive_sha256']+'\n逐路径验证：'+str(v['regular_file_paths_verified'])+' 个常规文件。\nrepository.bundle 包含代码历史，git bundle verify 已通过。\n\n这是同盘副本，不是异机冗余；不含Docker镜像层，须按记录digest另行准备。\n部分历史路径或链接含绝对路径；迁移后在新目录重新构建。\n报告：experiments/sockshop-mirrortaint/APPLICATION-CALL-REVISION-20261020.md\n整体382/431验收尚未完成。所有push由用户完成。\n')
    print(json.dumps({'final_algorithm_commit':v['algorithm_commit'],'archive_sha256':v['archive_sha256'],'all_passed':v['all_passed']},indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',required=True,type=Path);p.add_argument('--out',required=True,type=Path);a=p.parse_args();run(a.root.resolve(),a.out.resolve())
