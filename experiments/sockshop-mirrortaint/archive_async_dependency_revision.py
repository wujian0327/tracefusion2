#!/usr/bin/env python3
"""Verified archive for bounded worker dependency transfer and shared-publication guards."""
import argparse,json
from pathlib import Path
from archive_execution_kernel_revision import archive
from run_planned_service import load


def run(root,out):
    archive(root,out);v=load(out/'verification.json')
    (out/'START-HERE.txt').write_text('工作Frame与Future依赖传递阶段备份\n\n代码提交：'+v['commit']+'\n最终算法：'+v['algorithm_commit']+'\n\n原版Orders24目标仍全部unknown，新增真实基线差距修复0，累计97、剩余72。\n控制full/selective各30目标：18已知来源匹配、12预期unknown；共享数组首次接纳失败及最终拒绝保护保留。\n原35055fb业务捕获与最终6a2e1ca计划/全部Agent类哈希相同，保留实际版本，由最终离线代码复算，不计新部署。\n包含双冻结、源码、原始日志与消息、原JAR/依赖、固定输入、独立真值、预测、控制及兼容回归、审计和命令。29候选未启封，没有新性能或62查询全量验收。\n\nSHA256：'+v['archive_sha256']+'\n逐路径验证：'+str(v['regular_file_paths_verified'])+'\nrepository.bundle已通过git bundle verify。\n报告：experiments/sockshop-mirrortaint/ASYNC-DEPENDENCY-REVISION-20261021.md\n机制：experiments/sockshop-mirrortaint/ASYNC-DEPENDENCY-ALGORITHM-20261021.md\n\n这是同盘副本，不是异机冗余，不含Docker镜像层。迁移须另备镜像，在新目录重建，不能盲用历史绝对路径。所有push由用户完成。\n')
    print(json.dumps(v,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.root.resolve(),a.out.resolve())
