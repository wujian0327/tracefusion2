#!/usr/bin/env python3
"""Verify the cost archive and keep the earlier capability backup distinct."""
import argparse
from pathlib import Path
from run_planned_service import ROOT, load
from archive_execution_kernel_revision import archive
from run_isolated_cost import CURRENT, OLD_COST


def run(root,out):
    assert load(root/'cost-audit.json')['all_passed']
    assert load(root/'native-cost-audit.json')['all_passed']
    assert load(root/'offline-memory-audit.json')['all_passed']
    price=load(OLD_COST/'cost-price/config.json')
    extra=[ROOT/'artifacts/isolated-cost-preflight-first-20261022',
           Path(price['inputs']), OLD_COST/'cost-price/config.json',
           OLD_COST/'price-build/build.json', CURRENT/'algorithm-freeze.json',
           CURRENT/'frozen-base', CURRENT.parent/'audit-final-first/audit.json',
           ROOT/'artifacts/jackson-isolation-backup-20261022/START-HERE.txt',
           ROOT/'artifacts/jackson-isolation-backup-20261022/verification.json']
    archive(root,out,tuple(p.resolve() for p in extra))
    v=load(out/'verification.json')
    (out/'START-HERE.txt').write_text(
        'Jackson隔离版正式成本与进展备份\n\n'
        f"代码/报告提交：{v['commit']}\n算法冻结：{v['algorithm_commit']}\n"
        f"evidence.tar.gz SHA256：{v['archive_sha256']}\n"
        f"逐路径核验：{v['regular_file_paths_verified']}个常规文件；内容去重：{v['unique_contents']}。\n"
        'repository.bundle包含本机Git历史，git bundle verify已通过；没有push。\n\n'
        '本包包括本轮45次正式部署、校准、首次预检失败、实际Agent/计划、原版JAR、'
        '源码及输入快照、原始事件、独立真值/预测、资源样本、离线复算、规划测量、图表与审计。\n'
        '本轮完整进展：experiments/sockshop-mirrortaint/PROGRESS-20261022.md\n'
        '本轮成本：experiments/sockshop-mirrortaint/ISOLATED-COST-20261022.md\n'
        '431目标能力验收的完整原始捕获另在jackson-isolation-backup-20261022归档；'
        '本包保留其校验/入口和构建资料，不宣称重复包含全部126配置捕获。\n\n'
        '这是同盘副本，不是异机冗余；artifacts不会随Git push同步。不含Docker镜像层，须按原记录digest准备。\n'
        '解包路径相对仓库根目录；历史配置、命令与符号链接包含绝对路径。迁移时保留原始记录，'
        '使用归档内original.jar和源配置在新目录重建输入/计划/Agent，不能改旧哈希绕过核验。\n'
        '所有性能仅对应各自冻结版本、任务和固定2请求/秒；不代表最大吞吐、所有查询或跨机器优势。\n'
        '归档完成后的日志另存原始根logs/，不在已封存tar内。\n')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',required=True,type=Path);p.add_argument('--out',required=True,type=Path);a=p.parse_args();run(a.root.resolve(),a.out.resolve())
