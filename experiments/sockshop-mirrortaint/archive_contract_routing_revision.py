#!/usr/bin/env python3
"""Archive final capability evidence, retained failures and symlink dependencies."""
import argparse
from pathlib import Path
from run_planned_service import ROOT,load,save,sha
from archive_execution_kernel_revision import archive
from archive_execution_closure_revision import dependency_closure
from run_query_planner import JARS


def run(root,out):
    receipt=load(root/'report-complete.json');assert receipt['all_audits_passed']
    final=Path(receipt['final_root']);assert load(final/'capability-audit/audit.json')['all_passed']and load(final/'regression29-audit/audit.json')['all_passed']
    extras=[root,ROOT/'artifacts/execution-closure-revision-20261023',ROOT/'artifacts/heldout29-first-20261023',ROOT/'artifacts/transport-observation-shared-20261023/capability-audit']
    fixed=[final,ROOT/'artifacts/baseline-capability-20261020',ROOT/'artifacts/call-lifecycle-revision-20261020/base-build',ROOT/'artifacts/call-lifecycle-revision-20261020/cart-create-guard',ROOT/'artifacts/desktop-inputs/images-lock.json',ROOT/'artifacts/query-coverage-first-20261019/pool.json',ROOT/'artifacts/trainticket-cost-preparation-20261016/inputs/inputs.json',ROOT/'artifacts/real-path-expansion-preflight-20261015/images.json',*JARS]
    fixed += [Path(v['jar'])for v in load(ROOT/'artifacts/trainticket-cost-preparation-20261016/inputs/inputs.json').values()]
    deps,links=dependency_closure(fixed+extras);save(root/'archive-dependencies.json',{'repository_local_targets_added':list(map(str,deps)),'links':links,'external_runtimes_not_copied':True})
    archive(final,out,extras+deps);v=load(out/'verification.json')
    (out/'START-HERE.txt').write_text('写入口契约修订与有限应用内观测：本机备份\n\n代码提交：'+v['commit']+'\n最终算法：'+v['algorithm_commit']+'\n\n本轮原始捕获、原生基线及首次/纠正评分、独立真值纠正、全部开发失败和中断、最终62+29回归、写入口96目标、有限写值消融、控制与拒绝检查均保留。Station403不做鉴权后复验。\n\nevidence.tar.gz SHA256：'+v['archive_sha256']+'\n常规文件逐路径核验：'+str(v['regular_file_paths_verified'])+'\nrepository.bundle 已通过git bundle verify。\n\n这是同盘副本，不是异机冗余；不含Docker镜像层，须按digest另行准备。归档路径相对仓库根目录；历史配置与链接含绝对路径，迁移后在新目录重新构建，保留原始证据只读。\n报告：experiments/sockshop-mirrortaint/CONTRACT-ROUTING-20261023.md\n\n没有新五轮性能实验；通用应用调用/指令切片仍未完成。所有push由用户完成。\n')
    save(out/'guide-verification.json',{'guide_sha256':sha(out/'START-HERE.txt'),'same_disk_only':True,'docker_layers_included':False,'push_performed':False})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.root.resolve(),a.out.resolve())
