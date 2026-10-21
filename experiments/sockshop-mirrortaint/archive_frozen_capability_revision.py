#!/usr/bin/env python3
"""Verified raw evidence backup; preserves source success and availability failure."""
import argparse
from pathlib import Path
from archive_execution_kernel_revision import archive
from run_planned_service import ROOT,load

def run(root,out):
 final=root/'final-capability';a=load(final/'audit-final/audit.json');assert a['provenance_union_passed']
 archive(final,out,extra=[root,ROOT/'artifacts/async-dependency-revision-20261021/inspection/libs'])
 v=load(out/'verification.json')
 (out/'START-HERE.txt').write_text('TraceFusion 2 统一来源核验备份\n\n算法冻结：'+a['algorithm_commit']+'\n代码/报告提交：'+v['commit']+'\n\n包含新旧冻结、全部开发失败、主轮与固定复验、旧能力对照输入/真值、九个原版 JAR、编译依赖及控制库。\n来源联合复核：full/selective 各382正确、39 unknown、10拒绝，错误确定答案0；包含固定复验。\n首次业务完成情况仍未全部通过：full 376正确；selective 377正确；各有1次原Future超时及5/4个后续未执行目标。\n不能以复验成功覆盖首次失败。审计的 provenance_union_passed=true 与 unqualified_end_to_end_acceptance=false 必须分开引用。\n\nevidence.tar.gz SHA256：'+v['archive_sha256']+'\n逐路径验证常规文件：'+str(v['regular_file_paths_verified'])+'\nrepository.bundle 已通过 git bundle verify。\n\n同盘备份，不是异机冗余；不含 Docker 镜像层，镜像需按工件 digest 另外准备。\n归档路径相对仓库根目录；历史配置和符号链接含绝对路径，迁移后必须在新目录重新构建。\n完整报告：experiments/sockshop-mirrortaint/CAPABILITY-ACCEPTANCE-20261021.md\n复核：python3 experiments/sockshop-mirrortaint/audit_frozen_capability_acceptance.py --root artifacts/date-effects-capability-20261021/final-capability --out artifacts/date-effects-capability-20261021/final-capability/audit-new-directory\n29个候选继续封存，未运行新成本实验。未推送；由用户手动 push。\n')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.root.resolve(),a.out.resolve())
