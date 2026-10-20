#!/usr/bin/env python3
"""Archive Date controls, actual unknown business targets and compatibility evidence."""
import argparse,json
from pathlib import Path
from archive_execution_kernel_revision import archive
from run_planned_service import load

def run(root,out):
    archive(root,out);v=load(out/'verification.json')
    (out/'START-HERE.txt').write_text('Date有限投影与保守效果核验备份\n\n代码提交：'+v['commit']+'\n算法冻结：'+v['algorithm_commit']+'\n\nevidence.tar.gz 包含Date语义控制、入口参数与同值修改保护、原版Orders各6个unknown的完整输入/真值/事件、Cart/Station/Route/TicketInfo兼容回归、开发失败、原JAR及依赖。\n本轮没有新增真实基线差距修复，累计96、剩余73；29候选未启封，无性能实验。\nSHA256：'+v['archive_sha256']+'\n校验常规文件路径：'+str(v['regular_file_paths_verified'])+'\nrepository.bundle保存已提交代码，git bundle verify已通过。\n\n报告：experiments/sockshop-mirrortaint/DATE-PROJECTION-REVISION-20261020.md\n算法：experiments/sockshop-mirrortaint/DATE-PROJECTION-ALGORITHM-20261020.md\n这是同盘副本，不是异机冗余，不包含Docker镜像层。迁移按镜像digest另行准备，在新目录重建；历史配置与符号链接包含绝对路径。所有push由用户完成。\n')
    print(json.dumps({'all_passed':v['all_passed'],'algorithm':v['algorithm_commit'],'archive_sha256':v['archive_sha256']},indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.root.resolve(),a.out.resolve())
