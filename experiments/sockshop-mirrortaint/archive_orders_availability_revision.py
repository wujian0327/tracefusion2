#!/usr/bin/env python3
"""Verified self-contained local evidence archive; image layers stay separate."""
import argparse
from pathlib import Path
from archive_execution_kernel_revision import archive
from run_planned_service import ROOT,load

def run(root,out):
    result=load(root/'quota-all62/audit-qualified/audit.json');assert result['all_passed'];assert not load(root/'audit-frozen-final/audit.json')['all_targeted_checks_passed']
    archive(root/'quota-all62',out,extra=[root,ROOT/'artifacts/date-effects-capability-20261021',ROOT/'artifacts/async-dependency-revision-20261021/inspection/libs'])
    verified=load(out/'verification.json')
    (out/'START-HERE.txt').write_text('TraceFusion 2 采集/JVM配置修订及62查询全量验收备份\n\n算法源码：'+result['algorithm_commit']+'\n代码和报告提交：'+verified['commit']+'\n\n原JVM配置72请求：67完成、2超时、3未执行；来源67/67正确，业务验收失败。\n限定GC/JIT线程1/2的新配置：相同CPU1、内存768MiB、堆32m/256m、5秒业务期限；固定72请求全部完成且来源正确。\n同一Agent在新配置下重新部署62查询：full/selective各382正确、39unknown、10规划拒绝、0错误确定答案；保留基线368/368和旧TF213/213，首轮业务验收通过，没有使用成功重试替换失败。\n参数审计首次未全过：Cart补充两组误用旧64m/G1预设，原捕获保留，按协议重跑两组；符合条件的124个部署来自122原主查询和2修正补充，总实际126。\n这不是全部431目标100%可回答；尚未证明所有历史超时唯一根因，不含新性能结论，29候选未启封。\n\n包含原始失败、诊断/原始和线程受限验收、全部62查询新捕获及旧能力对照、独立真值、源码快照、9个原JAR、编译/控制依赖和Git历史。\n\nevidence.tar.gz SHA256：'+verified['archive_sha256']+'\n逐路径常规文件校验数：'+str(verified['regular_file_paths_verified'])+'\nrepository.bundle 已通过git bundle verify。\n\n同盘副本，不是异机冗余；不含Docker镜像层，请按工件digest单独准备。解压路径相对仓库根目录；原配置含绝对路径和链接，迁移后在新目录重新构建。\n报告：experiments/sockshop-mirrortaint/ORDERS-AVAILABILITY-20261021.md\n复核：python3 experiments/sockshop-mirrortaint/audit_quota_capability_acceptance.py --root artifacts/orders-availability-20261021/quota-all62 --out artifacts/orders-availability-20261021/quota-all62/audit-new-directory\n不自行推送；由用户手动push。\n')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.root.resolve(),a.out.resolve())
