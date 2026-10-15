#!/usr/bin/env python3
"""Source-backed summary of the frozen query planning experiment."""
import argparse
import csv
from pathlib import Path

from run_query_planner import load,save,sha


def summarize(base,helper,noise,collision,out):
    out.mkdir(parents=True,exist_ok=True)
    runs={'base':base,'helper':helper,'noise':noise};reports={name:load(path/'results.json') for name,path in runs.items()}
    assert all(load(path/'algorithm-audit.json')['passed'] for path in runs.values())
    assert load(collision/'collision.json')['passed']
    assert len({r['build']['sources'][k] for r in reports.values() for k in r['build']['sources'] if k.endswith('QueryObservationAgent.java')})==1
    assert len({r['freeze']['cases_sha256'] for r in reports.values()})==1
    for name,r in reports.items():
        for source,expected in r['freeze']['inference_sources'].items():assert sha(Path(source))==expected
        for query,modes in r['results'].items():
            assert modes['full']['exact']==modes['full']['queries']==modes['selective']['exact']
            assert modes['selective']['queries']==modes['selective']['exact']
    rows=[]
    for variant,r in reports.items():
        for query,modes in r['results'].items():
            for mode,m in modes.items():rows.append(dict(variant=variant,query=query,mode=mode,**{k:v for k,v in m.items() if k!='query_results'}))
    with (out/'comparison.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    lines=['# 查询驱动观测计划：首版算法与验证（2026-10-15）','',
      '已完成从原始应用 class、入口边界和目标字段生成观测计划的有界实现；采集器和还原器不包含 quantity/unitPrice/name 的业务规则。首版验证使用新增受控 Java 程序，其 Orders / Shipment 是夹具类型，不是原 Sock Shop 服务。','',
      '## 算法','',
      '1. ASM 从原始 class 导出字段、方法及指令；自动追入可确定分派的应用 helper，构造无环路径、字段赋值和覆盖后的来源表达式。',
      '2. 查询指定根对象的目标字段。对每条路径计算最终来源集合、对象参数身份和目标版本偏移；被覆盖的旧来源不进入最终答案。',
      '3. 固定保留入口／出口身份与版本以及目标字段写入；找出在固定证据相同情况下，仍产生不同来源答案的路径对。',
      '4. 贪心选择能区分这些路径对的分支观测，再删除冗余分支；自动导出所需边界字段。没有固定字段名或业务计算公式。',
      '5. 按计划在线插桩；同一个离线候选一致性还原器处理完整、选择性和固定证据。若一致候选的答案不同，就返回 unknown。','',
      '证书核验的性质：在声明模型与运行前提内，具有相同选定证据的候选执行，其字段来源集合与目标版本应相同。当前是有界路径模型内的可检查性质，不是任意 Java 的形式化正确性证明，也不保证全局最小观测。','',
      '## 换目标后的结果','',
      '| 目标集合 | 额外分支点 | 完整／自动答案 | 完整事件 | 自动事件 | 事件减少 | 完整日志 B | 自动日志 B |',
      '| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |']
    for query,modes in reports['base']['results'].items():
        full,selected=modes['full'],modes['selective'];p=reports['base']['build']['plans'][query]
        lines.append(f"| {query} | {p['selected_branches']} | {full['exact']}/{full['queries']}；{selected['exact']}/{selected['queries']} | {full['data_events']} | {selected['data_events']} | {1-selected['data_events']/full['data_events']:.1%} | {full['log_bytes']} | {selected['log_bytes']} |")
    lines += ['', '事件包含入口、出口、字段和分支记录；日志字节数还包含运行元数据。full 是同一声明范围内的完整实例字段／分支观测，不是全 JVM 逐指令追踪。三个模式都保留所需字段的显式写入版本计数，包括入口之外的应用赋值；版本钩子成本没有隐去，另存 field_hook_calls。','',
      '五个查询集合重复使用同一批 44 个输入：8 个定向实例／同值／覆盖案例、12 个真实重叠并发帧、24 个在计划和算法冻结后生成的新输入。不是 352 个独立业务案例，也不是独立第三方盲测。','',
      'name 查询不需要分支，固定证据已足够；payload 的两个写入位置本身区分来源，也不需要额外分支。total 需要一个分支；删去它时，固定模式只有两个输入对象实际别名的案例能确定来源，其余 42/44 为 unknown。','',
      '## 为什么少采还能答对','',
      '两个原生 JVM 执行采用相同输入字段值和相同输出值，仅隐藏的运行选择不同：quantity 分别来自 arg0 和 arg1。经对象身份 alpha 重命名后，固定语义证据完全相同；没有被选分支时两者都 unknown，有分支时来源正确区分。完整证据见 collision.json。','',
      '基础 total：748 → 220 个事件。差额 528 = 308 次字段读 + 176 次无关字段写 + 44 次无关分支；边界快照还由 8 种字段声明裁剪为 3 种。日志 318439 → 111254 B。此处比较的是同一重建器和同一程序范围，能隔离观测计划对记录量的贡献。','',
      '## 迁移和无关工作量','',
      '| 程序变体／total | 完整事件 | 自动事件 | 完整日志 B | 自动日志 B | 完整／自动答案 |',
      '| --- | ---: | ---: | ---: | ---: | --- |']
    for variant,r in reports.items():
        full,selected=r['results']['total']['full'],r['results']['total']['selective']
        lines.append(f"| {variant} | {full['data_events']} | {selected['data_events']} | {full['log_bytes']} | {selected['log_bytes']} | {full['exact']}/{full['queries']}；{selected['exact']}/{selected['queries']} |")
    lines += ['', 'helper 变体重命名计算方法并新增两层复制 helper；noise 变体加入 80 段无关字段读写。三种程序全部重新从 class 生成计划，使用相同算法／采集器／还原器，无业务答案补丁。','',
      f"三种程序 × 五组查询 × 三个模式，共 {sum(r['business_calls'] for r in reports.values())} 次业务调用，另有四次原生反例调用。单查询、双查询、三查询分母分别为 44、88、132，完整／自动均完全匹配。",'',
      '## 验证','',
      '每种程序有 13 项审计：独立 javap 逐指令及操作数核对、观测等价类答案一致、换目标、字段名整体替换、证书篡改、最后写入覆盖、循环拒绝、未知外部效果拒绝、缺失观测拒绝、请求名称无关性、版本破坏拒绝、同值来源歧义、重复对象版本保持。','',
      '重复调用在同一输出对象上保留目标版本 2 → 4，来源版本 1 → 2；评分保留对象／字段／版本，未合并为业务字段类型。12 个并发测试帧全部重叠，另有串行输入可能同时运行。','',
      '## 尚未覆盖','',
      '- 本轮验证单 JVM、根参数对象的最终标量／String 字段，未替换原 Sock Shop Spring／Stream／跨服务采集配置。入口仍是显式集成边界；查询之外无需修改业务名单。',
      '- 无环、有界路径（最多 256）、有限调用深度（12）、确定分派、线程独占 DTO、可分析应用副作用。反射、数组、递归、一般循环、嵌套 heap 别名和一般隐式流尚不支持。',
      '- ThreadLocal.get / Boolean.booleanValue 有明确的只读环境输入契约；未把环境选择值当作普通入口可重放数据。未知外部副作用拒绝规划。',
      '- fixed 保留入口／出口和必要目标写入，比纯边界快照更强；本轮没有把它冒称为纯边界重放。',
      '- 当前选择对有界路径模型充分、分支集合按删除意义不可再减，不保证全局最优，也未证明研究新颖性。',
      '- 没有正式延迟、吞吐、总 CPU 或峰值内存比较。运行记录中的整体 JVM 时间包括启动，不应解释为业务延迟；规划成本和模型导出成本仍需规范测量。','']
    (out/'results.md').write_text('\n'.join(lines))
    compact={variant:{q:{mode:{k:v for k,v in m.items() if k!='query_results'} for mode,m in modes.items()}
                      for q,modes in r['results'].items()} for variant,r in reports.items()}
    save(out/'summary.json',{'results':compact,'business_calls':sum(r['business_calls'] for r in reports.values()),
         'collision_calls':4,'same_reconstructor':True,'same_collector':True,'performance_eligible':False,
         'scope':'Bounded single-JVM controlled Java fixture; not original Sock Shop deployment.',
         'audits':{k:load(p/'algorithm-audit.json') for k,p in runs.items()},'collision':load(collision/'collision.json')})
    return compact


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('base','helper','noise','collision','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();summarize(*(getattr(a,n).resolve() for n in ('base','helper','noise','collision','out')))
