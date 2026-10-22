#!/usr/bin/env python3
"""Local verified archive; retain new failures and old raw compatibility evidence."""
import argparse
from pathlib import Path
from archive_execution_kernel_revision import archive
from run_planned_service import ROOT,load

def run(root,out):
    result=load(root/'audit-final/audit.json');assert result['all_passed']
    archive(root/'frozen-candidate',out,extra=[root,ROOT/'artifacts/orders-availability-20261021',ROOT/'artifacts/date-effects-capability-20261021',ROOT/'artifacts/async-dependency-revision-20261021/inspection/libs'])
    verified=load(out/'verification.json')
    (out/'START-HERE.txt').write_text('TraceFusion 2 构造字段投影/Runnable有限修订\n\n算法冻结：'+result['algorithm_commit']+'\n代码与报告提交：'+verified['commit']+'\n\n新20次业务部署：Cart每模式15正确/3unknown，Basic每模式21unknown，Station/Route每模式60/60正确。新增15个原开发目标正确，剩余34。\n旧382个已知答案仅使用旧Agent/旧计划/旧捕获在新离线代码上复算通过。没有新版62查询全量重新部署，不宣称397/431正式结果。29候选未启封，无新性能结论。\n\n保存新部署、开发失败、历史原始捕获、9个原JAR、源码快照、依赖和Git历史。\nevidence.tar.gz SHA256：'+verified['archive_sha256']+'\n逐路径常规文件校验数：'+str(verified['regular_file_paths_verified'])+'\nGit bundle verify已通过。\n\n同盘副本，不是异机冗余；不包含Docker镜像层。历史链接和配置包含绝对路径，迁移后重新构建。\n报告：experiments/sockshop-mirrortaint/REMAINING-SEMANTICS-REVISION-20261022.md\n推送交给用户。\n')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',required=True,type=Path);p.add_argument('--out',required=True,type=Path);a=p.parse_args();run(a.root.resolve(),a.out.resolve())
