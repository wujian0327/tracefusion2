#!/usr/bin/env python3
"""Archive Orders unknowns, constructor failures, runtime reuse and compatibility."""
import argparse,json
from pathlib import Path
from archive_execution_kernel_revision import archive
from run_planned_service import load

def run(root,out):
    archive(root,out);v=load(out/'verification.json')
    (out/'START-HERE.txt').write_text('Orders统一内核基础与保守效果核验备份\n\n代码提交：'+v['commit']+'\n最终算法冻结：'+v['algorithm_commit']+'\n\nevidence.tar.gz包含原版Orders两查询full/selective各6个unknown、独立真值、原始消息及事件；首次内部类构造器失败、可变Date构造器失败；语义与兼容控制、旧213答案离线复算、双冻结及复用证明、原JAR和依赖。\n本轮新增真实基线差距修复0，累计97、剩余72；29候选未启封，无性能实验，62查询统一验收尚未完成。\nSHA256：'+v['archive_sha256']+'\n逐路径校验：'+str(v['regular_file_paths_verified'])+'\nrepository.bundle保存已提交代码，git bundle verify已通过。\n\n报告：experiments/sockshop-mirrortaint/ORDERS-FOUNDATION-REVISION-20261021.md\n机制：experiments/sockshop-mirrortaint/ORDERS-FOUNDATION-ALGORITHM-20261021.md\n这是同盘副本，不是异机冗余，不含Docker镜像层。迁移需另备镜像、在新目录重建，不能盲用历史绝对路径。所有push由用户完成。\n')
    print(json.dumps({'all_passed':v['all_passed'],'algorithm':v['algorithm_commit'],'archive_sha256':v['archive_sha256']},indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.root.resolve(),a.out.resolve())
