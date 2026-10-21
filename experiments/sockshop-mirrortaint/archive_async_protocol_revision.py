#!/usr/bin/env python3
"""Verified evidence archive for the bounded, observation-only async protocol."""
import argparse, json
from pathlib import Path
from archive_execution_kernel_revision import archive
from run_planned_service import load


def run(root,out):
    archive(root,out);v=load(out/'verification.json')
    (out/'START-HERE.txt').write_text('Spring任务与Future实例配对阶段备份\n\n代码提交：'+v['commit']+'\n算法冻结：'+v['algorithm_commit']+'\n\n原版Orders四配置144任务、264次get配对通过，24个目标全部unknown。仅观察/核验任务事实，尚未实现工作Frame到调用者的来源传递。\n新增基线差距修复0，累计97、剩余72；没有新成本或62查询整体正确率，29候选未启封。\n包含原始事件与独立真值、固定输入、原JAR、镜像digest、冻结代码、混合控制、失败和审计；新Agent循环各60/60、TicketInfo各21/21、Cart各2/2，以及原213答案离线兼容证据。\n\nSHA256：'+v['archive_sha256']+'\n逐路径校验：'+str(v['regular_file_paths_verified'])+'\nrepository.bundle已通过git bundle verify。\n报告：experiments/sockshop-mirrortaint/ASYNC-PROTOCOL-REVISION-20261021.md\n机制：experiments/sockshop-mirrortaint/ASYNC-PROTOCOL-ALGORITHM-20261021.md\n\n这是同盘副本，不是异机冗余，不含Docker镜像层。迁移须另备镜像并在新目录重新构建，不能盲用历史绝对路径。所有push由用户完成。\n')
    print(json.dumps(v,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();run(a.root.resolve(),a.out.resolve())
