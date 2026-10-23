#!/usr/bin/env python3
"""Render the indexed offline sensitivity result without replacing old costs."""
import argparse,statistics
from pathlib import Path
from run_planned_service import HERE,load,save,sha


def run(root):
    d=load(root/'audit.json');assert d['all_passed'];p=load(root/'protocol.json');lines=['# 共享alias索引：已有捕获的公平离线复算','','本阶段只改服务内root-return查找索引，未重新部署业务，也未重新测在线成本。原e78cc04五配置25部署及49.63%离线核心结果完整保留；本表来自同20份来源捕获的40个新进程配对复算。','','## 正确性与索引规则','','按服务、Frame预建返回消息的候选列表；字段提供者仍按服务、对象、字段、版本索引，保留全部候选及原序列先后约束。不同Frame、具体RPC父消息、对象及版本的规则不变；同坐标多个候选保持unknown，重复root-return不再依赖字典覆盖次序，直接拒绝。','','6项索引保护检查通过。原62开发查询及已暴露29查询的全部模式：184份完整图和1350个目标答案逐项相同，包括unknown；这是兼容性核验，不合并为新版总体准确率，也不冒充新Agent部署。','','## 离线复算','',f"20份原始独立部署数据，每份均运行reference和indexed；配对顺序以种子{p['seed']}预先随机固定，新进程固定逻辑CPU {p['cpu']}，OMP/OpenBLAS/MKL线程均1，OS页缓存未清空。原始事件、真值、旧墙时/CPU及输出哈希保持不变。峰值为各exec镜像自身VmHWM，包含评分及导出。",'','| 比较 | 核心时间变化 | 逐轮比值范围 | 离线CPU变化 | VmHWM变化 |','| --- | ---: | --- | ---: | ---: |']
    for key,label in [('reference/projection','未索引：selective/selective_base'),('indexed/projection','已索引：selective/selective_base'),('indexed/strict','已索引：selective/full')]:
        v=d['paired'][key];c=v['core_seconds'];lines.append(f"| {label} | {(c['median']-1)*100:+.2f}% | {c['min']:.4f}–{c['max']:.4f} | {(v['cpu_seconds']['median']-1)*100:+.2f}% | {(v['vmhwm_bytes']['median']-1)*100:+.2f}% |")
    lines+=['','投影的核心时间点估计从约−48.81%缩小至−2.80%，后者范围跨1；不能继续把旧49.63%称为共同索引优化后的收益。已索引严格selective/full为−8.97%，同时包含既有读取位点选择和输出投影；它不是新执行闭包的成本结果。内存缩减仍存在。五轮仅作描述，不宣称显著性或普适比例。','','## 工件与首次失败','','`artifacts/execution-closure-revision-20261023/alias-index/`保存协议、reference源码、40次命令/阶段计量/完整图/预测、逐项相等检查及原始哈希。`regression/`保留首次定位失败：独立_id评分修正目录本来没有业务捕获；最终驱动按原不可变receipt定位回原捕获，在`regression-final/`完成核验，没有改核心或重跑业务。','','当前21个新入口字段已先在8e62954封存，未尝试规划；原62+29仅作下一阶段回归。剩余12个Orders真值缺口的独立原始事实检查见`orders-oracle-gap-audit/audit.json`：生成器配置与目标ID写入不能替代实际生成调用配对，self-link及后续Link调用仍缺解码字段来源坐标，未改判正确或空来源。']
    (HERE/'ALIAS-INDEX-20261023.md').write_text('\n'.join(lines)+'\n');save(HERE/'alias-index-results-20261023.json',{k:v for k,v in d.items()if k!='graph_answer_receipts'})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);run(p.parse_args().root.resolve())
