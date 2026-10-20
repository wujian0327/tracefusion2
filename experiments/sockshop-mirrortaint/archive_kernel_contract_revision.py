#!/usr/bin/env python3
"""Verified content archive for the shared-contract stage, with original dependencies."""
import argparse,json
from pathlib import Path
from archive_execution_kernel_revision import archive
from run_planned_service import load


def run(root,out):
    archive(root,out);v=load(out/'verification.json')
    (out/'START-HERE.txt').write_text('公共契约与对象数组阶段备份\n\n代码提交：'+v['commit']+'\n算法冻结：'+v['algorithm_commit']+'\n\nevidence.tar.gz 包含本轮冻结前失败、冻结后原版Cart及Station/Route捕获、独立真值、九个原JAR与工具依赖、原36实例和旧213答案复算工件。\nSHA256：'+v['archive_sha256']+'\n逐路径验证：'+str(v['regular_file_paths_verified'])+' 个常规文件。\nrepository.bundle 保存代码历史，git bundle verify 已通过。\n\nCart统一内核恢复各6/6；36个差距仍规划拒绝，剩余109，未达到382/431整体验收。\n这是同盘副本，不是异机冗余；不含Docker镜像层，须按digest另外准备。历史绝对路径在迁移后重新构建。\n报告：experiments/sockshop-mirrortaint/KERNEL-CONTRACT-REVISION-20261020.md\n算法：experiments/sockshop-mirrortaint/KERNEL-CONTRACT-ALGORITHM-20261020.md\n推送由用户完成。\n')
    print(json.dumps({'algorithm':v['algorithm_commit'],'archive_sha256':v['archive_sha256'],'all_passed':v['all_passed']},indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',required=True,type=Path);p.add_argument('--out',required=True,type=Path);a=p.parse_args();run(a.root.resolve(),a.out.resolve())
