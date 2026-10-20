#!/usr/bin/env python3
"""Render audited separate-query costs and static-planning repeats."""
import argparse,statistics
from pathlib import Path
from run_planned_service import load,save,sha


def summarize(root):
    audit=load(root/'cost-audit.json');assert audit['all_passed'] and audit['performance_eligible']
    static=load(root/'static-planning-final/results.json');freeze=load(root/'algorithm-freeze.json')
    lines=['# 调用配对修复后的三类查询成本实验','',
           '算法冻结 `'+freeze['algorithm_commit']+'`；只使用本批重新部署数据。三任务各5轮，原版/full/selective随机顺序、独立容器和数据卷，共45次部署，顺序运行。每次预热30秒、测量60秒、2请求/秒、并发上限2、资源采样2秒。', '',
           '额外 source_evidence 原始 HTTP 字节旁路关闭；必要 HTTP/JSON 字段、对象/版本、调用效果与异常闭合、响应/序列化绑定均保留且计入成本。开关校准、必要证据破坏检查和票价157个原始事实的去除复算均通过。full/selective的全局开关和核验要求相同。', '',
           '业务 JVM 各1 CPU/768 MiB，Mongo各1 CPU/384 MiB。Cart/Train采用同一Sock Shop JVM参数；票价沿用已有票价JVM参数，详见各config.json，不跨任务合成一个优势数字。原版没有来源输出，相关成本/能力记N/A。MirrorTaint等工具未校准本次新任务，记N/A。', '',
           '各配置数值为5次部署的中位数；配对变化使用同一轮selective/full比值的中位数及范围，不能用汇总中位数相除替代。性能请求排除预热，正确性同时计预热与测量。p99每轮仅约120个请求，仅作描述；不宣称显著性、最大吞吐相同或跨机器普适优势。','']
    names={'cart':'Cart：有限读取模型，ItemsController.getItems → /*/itemId','train':'Train：响应绑定，retrieve → /data/economyClass（第二次仓储读取）','price':'五服务票价：原多来源计算，两个 prices Map 条目'}
    metrics=[('p50_ms','在线p50，ms',1),('p95_ms','在线p95，ms',1),('p99_ms','在线p99，ms',1),('throughput_rps','完成吞吐，请求/秒',1),('error_rate','错误率',1),('online_cpu_percent','业务JVM CPU，单核百分比',1),('online_rss_mean_bytes','业务JVM平均RSS，MiB',2**20),('online_rss_peak_bytes','业务JVM采样峰值RSS，MiB',2**20),('capture_events','稳态事件条数',1),('capture_bytes','稳态采集字节，MiB',2**20),('whole_capture_bytes','整批采集字节，MiB',2**20),('offline_core_seconds','整批离线核心，秒',1),('offline_child_wall_seconds','离线子进程墙时，秒',1),('offline_child_cpu_seconds','离线子进程CPU，秒',1),('offline_child_peak_rss_bytes','离线子进程峰值RSS，MiB',2**20),('answer_wait_p50_seconds','请求完成到批次答案p50，秒',1),('answer_wait_p95_seconds','请求完成到批次答案p95，秒',1)]
    for kind in ('cart','train','price'):
        result=audit['results'][kind];summ=result['summary'];paired=result['paired']['selective/full'];lines+=['## '+names[kind],'']
        for mode in ('full','selective'):
            pops=result['populations'][mode];q=sum(p['queries'] for p in pops);tp=sum(p['tp'] for p in pops);warm=sum(p['warmup_targets'] for p in pops);steady=sum(p['steady_targets'] for p in pops)
            lines+=[f'{mode}：900请求（300预热、600测量），{q}/{q}目标实例来源完全匹配，TP{tp}/FP0/FN0/unknown0；其中预热{warm}、测量{steady}个目标。']
        lines+=['','| 指标 | 原版 | full | selective |','| --- | ---: | ---: | ---: |']
        for key,label,scale in metrics:
            if key=='offline_child_peak_rss_bytes':label='同批证据离线复算VmHWM，MiB'
            vals=[]
            for mode in ('original','full','selective'):
                v=summ[mode].get(key);vals.append('N/A' if v is None else f"{v['median']/scale:,.3f}" if key!='capture_events' else f"{v['median']:,.0f}")
            lines.append('| '+label+' | '+' | '.join(vals)+' |')
        for key,label,scale in [('deployment_cpu_percent','整部署CPU，单核百分比',1),('deployment_rss_mean_bytes','整部署平均RSS，MiB',2**20),('deployment_rss_peak_bytes','整部署采样峰值RSS，MiB',2**20),('console_bytes','整部署整批控制台字节，MiB',2**20)]:
            lines.append('| '+label+' | '+' | '.join(f"{summ[mode][key]['median']/scale:,.3f}" for mode in ('original','full','selective'))+' |')
        lines+=['','| selective/full 配对变化 | 中位数 | 逐轮比值范围 |','| --- | ---: | ---: |']
        for key,label in [('capture_events','稳态事件'),('capture_bytes','稳态字节'),('offline_core_seconds','离线核心'),('offline_child_wall_seconds','离线子进程墙时'),('offline_child_cpu_seconds','离线CPU'),('offline_child_peak_rss_bytes','离线峰值RSS'),('online_cpu_percent','在线CPU'),('p95_ms','在线p95')]:
            p=paired[key];lines.append(f"| {label} | {(p['median']-1)*100:+.2f}% | {p['min']:.4f}–{p['max']:.4f} |")
        p=paired['online_cpu_percent'];lat=paired['p95_ms'];baseline=result['paired']['selective/original']
        lines+=['',f"在线CPU比值范围{'跨1，不能称稳定改善' if p['min']<=1<=p['max'] else '全部小于1' if p['max']<1 else '全部大于1'}；p95比值范围{'跨1，不能称稳定改善' if lat['min']<=1<=lat['max'] else '全部小于1' if lat['max']<1 else '全部大于1'}。这是五轮描述，不是总体显著性证明。",f"相对无来源输出的原版，selective 的配对中位数：p95 {(baseline['p95_ms']['median']-1)*100:+.2f}%，业务JVM CPU {(baseline['online_cpu_percent']['median']-1)*100:+.2f}%。",'']
    lines+=['## 静态规划与阶段成本','',
            '每任务5次新进程，固定同一逻辑CPU，所有计划与部署计划完全一致。OS页缓存未清空。流程墙时从worker函数入口计时；子进程墙时另包含解释器/模块启动。CPU为新进程及其Java子进程总量；RSS为15ms采样的进程树RSS和峰值，共享页可能重复计数。Agent编译和部署启动排除，full/selective共用计划。','',
            '| 任务 | 流程墙时中位数，秒 | 子进程墙时中位数，秒 | CPU中位数，秒 | 进程树RSS峰值中位数，MiB | 纯计划分析中位数，ms |','| --- | ---: | ---: | ---: | ---: | ---: |']
    for kind in ('cart','train','price'):
        rs=[r for r in static['measurements'] if r['kind']==kind];med=lambda k:statistics.median(r[k] for r in rs)
        plan=statistics.median(sum(v['plan_analysis_seconds'] for v in r['phases'].values()) for r in rs)
        lines.append(f"| {kind} | {med('wall_seconds'):.4f} | {med('subprocess_wall_seconds'):.4f} | {med('cpu_seconds'):.4f} | {med('process_tree_sampled_peak_rss_bytes')/2**20:.2f} | {plan*1000:.3f} |")
    lines+=['','离线阶段另存解码、图验证/还原、目标查询、答案导出、独立评分和证据导出时间。原子进程CPU及复算VmHWM均包括评分和导出；不能称为算法核心的独立峰值。所有逐部署数字见cost-deployments.csv，配对比值及阶段见cost-audit.json。','',
            '本机控制实验确认ru_maxrss可继承fork父进程高水位；原始计数保存在metrics/offline文件及CSV的offline_launch_rusage_peak_rss_bytes列，不能用它代替exec后处理峰值。主表RSS来自全部30份来源配置捕获的独立复算，读取进程自身/proc/self/status的VmHWM；复算在在线实验全部结束后顺序进行，原始捕获和墙时/CPU计时未改写，来源评分逐份相同。测量协议和原始状态见offline-memory-replays/，审计见offline-memory-audit.json。','',
            '答案等待来自批处理：请求完成到整批采集关闭、再到答案导出。原始证据关闭时间是完整批次可用的上界；目标字段内部产生时间未单独计时，不能把请求完成当作精确目标生成时间，也不能把约一分钟窗口解释成工具固有流式延迟。','',
            '整批采集与离线阶段处理全捕获文件，还包括固定的启动/就绪/输入准备记录；Cart准备后的6次一致性GET也产生根记录，但不混入正式计分目标。来源统计只针对明确列出的预热和测量请求，稳态事件/字节按捕获窗口单列。','',
            'cost-cart为计时边界修正前的试运行，完整保留但排除于本表；正式Cart使用cost-cart-final。修正只影响实验驱动，算法核心未变。静态规划和正确性校准未受影响，直接复用。','',
            '## 审计与限制','',
            '调用配对修复、Basic unknown、效果核验条件及历史回归见仓库CALL-LIFECYCLE-REVISION-20261020.md。旧0/20、803b92f及c3e6739首次覆盖结果不改写。本轮不新增未见查询泛化证据；Orders保存/异步、一般循环等仍不支持。','',
            '运行命令和逐轮重要节点保存在logs/，机器环境在各cost-*/environment.json；镜像digest、资源限制、冻结输入、原始事件、独立真值和预测保存在各部署目录。完整工件需单独备份，Git仅保存代码及小型摘要。','']
    (root/'results.md').write_text('\n'.join(lines));save(root/'summary.json',{'algorithm_commit':freeze['algorithm_commit'],'cost':audit,'static_planning':static,'report_generator_sha256':sha(Path(__file__))})
    print('Lifecycle cost report rendered',flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);summarize(p.parse_args().root.resolve())
