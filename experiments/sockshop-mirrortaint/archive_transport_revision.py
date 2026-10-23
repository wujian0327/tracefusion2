#!/usr/bin/env python3
"""Archive completed coverage, capability and fair cost evidence; verify paths."""
import argparse
from pathlib import Path
from run_planned_service import ROOT,load,save,sha
from archive_execution_kernel_revision import archive


def run(capability,cost,out):
    assert load(capability/'capability-audit/audit.json')['all_passed']
    assert load(cost/'pipeline-complete.json')['all_passed']
    assert load(cost/'cost-audit.json')['all_passed']
    first=ROOT/'artifacts/heldout29-first-20261023'
    assert load(first/'audit-final-reviewed/audit.json')['all_passed']
    native=Path(load(ROOT/'artifacts/baseline-capability-20261020/mirror-build-09/build.json')['native_jar'])
    extra=[cost,first,native.parent,
        ROOT/'artifacts/jackson-isolation-20261022/candidate-v2/final-capability',
        ROOT/'artifacts/jackson-isolation-20261022/candidate-v2/audit-final-first',
        ROOT/'artifacts/isolated-cost-20261022',
        ROOT/'artifacts/transport-observation-revision-20261023',
        ROOT/'artifacts/transport-cart-cost-20261023',
        ROOT/'artifacts/transport-cart-cost-v2-20261023']
    archive(capability,out,extra=extra)
    verified=load(out/'verification.json')
    (out/'START-HERE.txt').write_text(
        'TraceFusion 2：29字段首次验证、最终能力保持与公平Cart成本备份\n\n'
        f"代码历史HEAD：{verified['commit']}\n最终算法冻结：{verified['algorithm_commit']}\n"
        '29字段首次结果对应原核心76d2050，不作为最终版本的新未见测试。\n'
        'TF两配置各232/244正确、12unknown；其中12个独立物理来源真值不足，不判定双方能力优劣。\n'
        '最终62查询两配置各428/431正确、3unknown，历史基线368及旧TF213正确实例逐项保留。\n'
        '公平成本为五配置各五轮，25次独立部署；公共传输清理不计入查询选择性收益。\n'
        '首次失败、独立评分修正、旧423能力捕获和排除的6次成本前缀均保留。\n\n'
        f"归档SHA256：{verified['archive_sha256']}\n"
        f"逐项核验常规文件路径：{verified['regular_file_paths_verified']}\n"
        'repository.bundle保存当前代码历史，git bundle verify已通过。\n'
        '报告：experiments/sockshop-mirrortaint/PROGRESS-20261023.md\n'
        '成本：experiments/sockshop-mirrortaint/TRANSPORT-CART-COST-20261023.md\n\n'
        '这是同盘副本，不是异机冗余；不含Docker镜像层。按镜像清单/digest另备。\n'
        '归档路径相对仓库根目录。迁移到新目录后重新构建，核对含绝对路径的配置与符号链接。\n'
        '不在旧捕获上覆盖审计结果；复核应使用新输出目录。push交给用户。\n')
    save(out/'delivery-guide.json',{'guide_sha256':sha(out/'START-HERE.txt'),'script_sha256':sha(Path(__file__)),'archive_sha256':verified['archive_sha256'],'verified':True})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--capability',type=Path,required=True);p.add_argument('--cost',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.capability.resolve(),a.cost.resolve(),a.out.resolve())
