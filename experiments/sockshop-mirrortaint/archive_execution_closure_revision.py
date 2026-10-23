#!/usr/bin/env python3
"""Verified local archive after all online work and the final report complete."""
import argparse
from pathlib import Path
from run_planned_service import ROOT,load,save,sha
from archive_execution_kernel_revision import archive
from run_query_planner import JARS


def dependency_closure(paths):
    """Include repository-local symlink targets, without copying host runtimes."""
    roots=[];added=[];links=[];pending=list(paths)
    while pending:
        path=pending.pop().resolve()
        if any(path==p or p.is_dir() and path.is_relative_to(p) for p in roots):continue
        roots.append(path)
        for p in ([path,*path.rglob('*')] if path.is_dir() else [path]):
            if not p.is_symlink():continue
            target=p.resolve();record={'path':str(p),'target':str(target),'exists':target.exists()}
            record['repository_local']=target.is_relative_to(ROOT)
            links.append(record)
            if target.exists() and record['repository_local']:
                pending.append(target);added.append(target)
    return list(dict.fromkeys(added)),links


def run(root,cost,out):
    assert load(root/'pipeline-status.json')['node']=='31-pipeline-complete'
    assert load(root/'report-complete.json')['all_audits_passed']
    assert load(cost/'cost-audit.json')['all_passed']
    extras=[cost,ROOT/'artifacts/transport-observation-shared-20261023',ROOT/'artifacts/transport-cart-cost-v3-20261023',ROOT/'artifacts/heldout29-first-20261023',ROOT/'artifacts/jackson-isolation-20261022/candidate-v2/audit-final-first']
    fixed=[root,ROOT/'artifacts/baseline-capability-20261020',ROOT/'artifacts/call-lifecycle-revision-20261020/base-build',ROOT/'artifacts/call-lifecycle-revision-20261020/cart-create-guard',ROOT/'artifacts/desktop-inputs/images-lock.json',ROOT/'artifacts/query-coverage-first-20261019/pool.json',ROOT/'artifacts/trainticket-cost-preparation-20261016/inputs/inputs.json',ROOT/'artifacts/real-path-expansion-preflight-20261015/images.json',*JARS]
    fixed += [Path(v['jar']) for v in load(ROOT/'artifacts/trainticket-cost-preparation-20261016/inputs/inputs.json').values()]
    dependencies,links=dependency_closure(fixed+extras)
    save(root/'archive-dependency-audit.json',{'repository_local_targets_added':list(map(str,dependencies)),'links':links,'external_runtimes_and_dangling_legacy_build_links_reported':True})
    extras+=dependencies
    archive(root,out,extras)
    verification=load(out/'verification.json')
    (out/'START-HERE.txt').write_text(
        '执行观测闭包与新入口首次验证：本机备份\n\n'
        '代码提交：'+verification['commit']+'\n算法冻结：'+verification['algorithm_commit']+'\n\n'
        'evidence.tar.gz包含本轮全部原始捕获、首次失败、冻结协议/输入/模型/JAR、控制测试、62+29新部署、21新入口首次结果、35次正式成本部署、输入规模捕获、离线/规划计量，以及alias40次复算和184份图兼容核验所依赖的历史原始工件。\n'
        'Station按用户决定保留403，不做鉴权后复验；被自动审批拒绝的认证提案没有执行。\n'
        '其余失败不删：新入口76个Collector问题、20个语义/profile问题（每配置），Orders12个独立真值缺口，原型/驱动首次失败及计时前协议草稿均保留。\n\n'
        '归档SHA256：'+verification['archive_sha256']+'\n'
        '常规文件逐路径核验：'+str(verification['regular_file_paths_verified'])+'\n'
        'manifest.json逐项记录SHA256/链接目标；repository.bundle保存代码历史，git bundle verify已通过。\n\n'
        '这是同盘副本，不是异机冗余；不含Docker镜像层。镜像需按digest另行准备。\n'
        '路径相对仓库根目录归档；历史配置/符号链接可能保留旧绝对路径。迁移后保留原始证据只读，在新目录重新构建，不原地改写原始事件或假装旧构建可直接部署。\n'
        '报告：experiments/sockshop-mirrortaint/EXECUTION-CLOSURE-20261023.md\n'
        '本轮仅完成保守的来源边界构造字段写值收缩，未完成通用调用/指令切片；21新入口没有端到端正向覆盖证据。旧成本和旧首次结果均不覆盖。\n'
        '所有推送由用户完成。\n')
    save(out/'guide-verification.json',{'guide_sha256':sha(out/'START-HERE.txt'),'all_online_and_analysis_complete_before_backup':True,'same_disk_only':True,'docker_layers_included':False,'push_performed':False})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',required=True,type=Path);p.add_argument('--cost',required=True,type=Path);p.add_argument('--out',required=True,type=Path);a=p.parse_args();run(a.root.resolve(),a.cost.resolve(),a.out.resolve())
