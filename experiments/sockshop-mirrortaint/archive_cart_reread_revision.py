#!/usr/bin/env python3
"""Archive original Cart reread facts, semantic guards and compatibility captures."""
import argparse,json
from pathlib import Path
from archive_execution_kernel_revision import archive
from run_planned_service import load

def run(root,out):
    archive(root,out);v=load(out/'verification.json')
    (out/'START-HERE.txt').write_text('Cart首次创建与实际再次读取备份\n\n代码提交：'+v['commit']+'\n算法冻结：'+v['algorithm_commit']+'\n\nevidence.tar.gz包含本轮原始Cart创建/重复读取、独立实例真值、必要证据扰动、语义控制、新Agent兼容部署、旧213答案离线复算、开发失败与原JAR/依赖。保存仍为不透明效果，来源来自实际第二次读取。\n本轮新增修复1个已暴露反例，累计97、剩余72；29候选未启封，无性能实验，未完成62查询统一版本验收。\nSHA256：'+v['archive_sha256']+'\n逐路径校验：'+str(v['regular_file_paths_verified'])+'\nrepository.bundle保存已提交代码，git bundle verify已通过。\n\n报告：experiments/sockshop-mirrortaint/CART-REREAD-REVISION-20261021.md\n算法：experiments/sockshop-mirrortaint/CART-REREAD-ALGORITHM-20261021.md\n这是同盘副本，不是异机冗余，不含Docker镜像层。迁移需另备镜像并在新目录重建。所有push由用户完成。\n')
    print(json.dumps({'all_passed':v['all_passed'],'algorithm':v['algorithm_commit'],'archive_sha256':v['archive_sha256']},indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.root.resolve(),a.out.resolve())
