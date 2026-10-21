#!/usr/bin/env python3
"""Verified evidence archive, including the actual original Spring/Jackson libs."""
import argparse
from pathlib import Path
from archive_execution_kernel_revision import archive
from run_planned_service import ROOT,load

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();root=a.root.resolve();out=a.out.resolve()
    archive(root,out,extra=[ROOT/'artifacts/async-dependency-revision-20261021/inspection/libs'])
    result=load(out/'verification.json')
    (out/'START-HERE.txt').write_text(
        '原版 Orders 端到端来源链修订备份\n\n代码提交：'+result['commit']+'\n算法冻结：'+result['algorithm_commit']+
        '\n报告：experiments/sockshop-mirrortaint/ORDERS-END-TO-END-REVISION-20261021.md\n\n'
        'evidence.tar.gz：本轮各候选、首次失败、正式捕获、原版 JAR、原库依赖、独立真值、计划、预测、复核和旧能力工件。\n'
        'SHA256：'+result['archive_sha256']+'\n逐路径校验：'+str(result['regular_file_paths_verified'])+' 个常规文件。\n'
        'repository.bundle 保存代码历史，git bundle verify 通过。\n\n'
        '同盘副本，不是异机冗余；不含 Docker 镜像层，按记录 digest 单独准备。\n'
        '从仓库根目录解压；历史配置和符号链接含绝对路径，迁移后在新目录重新构建，不直接沿用旧构建。\n'
        '当前不是全 62 查询联合验收，也未启封剩余 29 候选。旧成本表不适用于新版本。推送由用户完成。\n')
