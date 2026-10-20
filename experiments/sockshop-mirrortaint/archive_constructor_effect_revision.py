#!/usr/bin/env python3
"""Archive constructor/predicate evidence, original inputs and complete Git history."""
import argparse,json
from pathlib import Path
from archive_execution_kernel_revision import archive
from run_planned_service import load


def run(root,out):
    archive(root,out);v=load(out/'verification.json')
    (out/'START-HERE.txt').write_text('构造器与过滤链修订备份\n\n代码提交：'+v['commit']+'\n算法冻结：'+v['algorithm_commit']+'\n\nevidence.tar.gz 保存本轮原始捕获、独立真值、15个Cart差距和同值第二成员保护、框架javap、JDK无网络探针、兼容回归、原业务JAR及依赖。\nSHA256：'+v['archive_sha256']+'\n校验常规文件路径：'+str(v['regular_file_paths_verified'])+'\nrepository.bundle 保存代码历史，git bundle verify 已通过。\n\n本轮新修复原15个差距；累计75，剩余94，未达到382/431全量验收。29候选未启封，无新性能实验。\n报告：experiments/sockshop-mirrortaint/CONSTRUCTOR-EFFECT-REVISION-20261020.md\n算法：experiments/sockshop-mirrortaint/CONSTRUCTOR-EFFECT-ALGORITHM-20261020.md\n这是同盘副本，不是异机冗余；不含Docker镜像层，按digest另外准备，迁移后在新目录重建。\n所有push由用户完成。\n')
    print(json.dumps({'all_passed':v['all_passed'],'algorithm':v['algorithm_commit'],'archive_sha256':v['archive_sha256']},indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',required=True,type=Path);p.add_argument('--out',required=True,type=Path);a=p.parse_args();run(a.root.resolve(),a.out.resolve())
