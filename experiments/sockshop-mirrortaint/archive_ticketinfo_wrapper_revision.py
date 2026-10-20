#!/usr/bin/env python3
"""Archive TicketInfo original facts, both freezes, regressions and Git history."""
import argparse,json
from pathlib import Path
from archive_execution_kernel_revision import archive
from run_planned_service import load

def run(root,out):
    archive(root,out);v=load(out/'verification.json')
    (out/'START-HERE.txt').write_text('TicketInfo HTTP包装及实际Map来源备份\n\n代码提交：'+v['commit']+'\n最终算法冻结：'+v['algorithm_commit']+'\n\nevidence.tar.gz 包含原21目标full/selective新部署、独立真值、首冻结21个unknown、开发失败、全部兼容回归、原版业务JAR及依赖。\nSHA256：'+v['archive_sha256']+'\n逐路径核对：'+str(v['regular_file_paths_verified'])+' 个常规文件。\nrepository.bundle 保存提交历史，git bundle verify 已通过。\n\n累计修复96个暴露差距，剩余73；尚未进行全62查询同版本验收，不能推称总体正确率。29候选未启封，无新性能数据。\n报告：experiments/sockshop-mirrortaint/TICKETINFO-WRAPPER-REVISION-20261020.md\n算法：experiments/sockshop-mirrortaint/TICKETINFO-WRAPPER-ALGORITHM-20261020.md\n\n这是同盘副本，不是异机冗余；不包含Docker镜像层，须按digest另行准备。历史配置及符号链接含绝对路径，迁移后在新目录重新构建。所有push由用户完成。\n')
    print(json.dumps({'all_passed':v['all_passed'],'algorithm':v['algorithm_commit'],'archive_sha256':v['archive_sha256']},indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.root.resolve(),a.out.resolve())
