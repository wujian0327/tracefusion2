#!/usr/bin/env python3
"""Render independently checked deployment-level Train Ticket cost results."""
import argparse
import csv
from pathlib import Path
import statistics
from run_planned_service import load,save,sha


def summarize(out):
    c=load(out/'config.json');a=load(out/'independent-audit.json')
    env=load(out/'environment.json');commit=next(r['stdout'].strip() for r in env['commands'] if r['command']==['git','rev-parse','HEAD'])
    if not a['all_passed']:raise ValueError('Independent audit required')
    modes=['original','full','selective'];s=a['summary']
    def fmt(v):return 'N/A' if v is None else f'{v:.3f}'
    def value(mode,key,div=1):
        x=s[mode][key]
        if not x:return 'N/A'
        if key in ('capture_events','capture_bytes','console_bytes'):return f"{x['median']:,.0f}"
        return fmt(x['median']/div)
    paired={p['comparison']:p['metrics'] for p in a['paired']}
    reduction=lambda key:100*(1-paired['selective/full'][key]['median'])
    overhead=lambda key:100*(paired['selective/original'][key]['median']-1)
    lines=['# Train Ticket 多来源价格路径正式低负载成本实验','',
        '本报告只使用本批新部署数据。测量单位为原版 Basic 的 POST /api/v1/basicservice/basic/travel，同时回答 economyClass 与 confortClass 两个实际价格字段的数据来源查询。', '',
        '测量驱动提交：`'+commit+'`。本轮未修改Java Agent、规划器或来源还原规则；离线阶段计时在外层驱动中完成。后续独立审计与报告生成属于后处理，未改写原始计时或采集。', '',
        f"独立审计：通过；正式资格：{'满足' if a['performance_eligible'] else '未满足，仅冒烟'}。{c['rounds']}轮，每轮三配置随机顺序、新容器和新数据卷；种子{c['seed']}。每次预热{c['warmup']:g}秒、测量{c['seconds']:g}秒，固定{c['rate']:g}请求/秒、最大并发{c['concurrency']}、资源采样间隔{c['sample_interval']:g}秒。", '',
        '三配置使用相同五个原版业务JAR、固定镜像、数据库事实、输入次序与JVM参数。业务容器各1 CPU/768 MiB，四个Mongo各1 CPU/384 MiB。JVM：`'+c['jvm']+'`。full/selective为同一采集器、计划、事件格式与还原器，只改变service.mode；原版没有观测Agent。', '',
        '性能模板为已有20个校准输入中19个能产生目标的输入，按冻结顺序循环。缺失Train导致原版上游404、Basic在价格产生前500，预先排除于性能负载；它仍在完整校准中验证，两个目标为N/A。正常、同值、重排、短列表、缺失Route/Price/Station及重复模板保留。业务层status=0的已预期常量回退不属于传输错误。', '',
        '## 当前证据支持的结论', '',
        'full和selective各1800/1800个查询准确，TP4330、FP/FN/目标unknown均为0；三配置全部业务检查通过，15次部署的稳态HTTP错误率均为0。', '',
        f"以同轮selective/full成本比的中位数计算，事件减少{reduction('capture_events'):.2f}%，采集字节减少{reduction('capture_bytes'):.2f}%，离线核心时间减少{reduction('offline_core_seconds'):.2f}%，离线进程CPU减少{reduction('offline_process_cpu_seconds'):.2f}%，离线峰值RSS减少{reduction('offline_peak_rss_bytes'):.2f}%。这些项目在本批五轮中均更低。", '',
        f"在线CPU没有改善：配对比中位数{paired['selective/full']['cpu']['median']:.4f}，即增加{-reduction('cpu'):.2f}%，五轮有三轮更高。p95配对点估计下降{reduction('latency_p95'):.2f}%，但范围跨过1，不能称稳定降低。相对原版，selective的p50/p95延迟开销配对中位数为{overhead('latency_p50'):.2f}%/{overhead('latency_p95'):.2f}%，五JVM在线CPU增加{overhead('cpu'):.2f}%。这些结果只适用于本批固定低负载、输入与版本。", '',
        '## 五轮中位数', '',
        '| 指标 | 原版 | full | selective |','| --- | ---: | ---: | ---: |']
    definitions=[('HTTP p50 ms','latency_p50',1),('HTTP p95 ms','latency_p95',1),('HTTP p99 ms（次要）','latency_p99',1),('窗内完成吞吐 req/s','throughput_rps',1),('五个业务JVM CPU，单核%之和','cpu',1),('五个业务JVM RSS均值 MiB','rss_mean',2**20),('五个业务JVM RSS采样峰值 MiB','rss_peak',2**20),('九容器CPU，单核%之和','deployment_cpu',1),('九容器RSS均值 MiB','deployment_rss_mean',2**20),('九容器RSS采样峰值 MiB','deployment_rss_peak',2**20),('测量批次采集增量事件','capture_events',1),('测量批次采集增量字节','capture_bytes',1),('全程应用控制台导出字节','console_bytes',1),('离线核心秒','offline_core_seconds',1),('离线解码/还原/评分/导出总秒','offline_restore_score_export_seconds',1),('离线子进程墙时秒','offline_subprocess_wall_seconds',1),('离线子进程CPU秒','offline_process_cpu_seconds',1),('离线子进程峰值RSS MiB','offline_peak_rss_bytes',2**20),('请求完成→答案文件可读p95秒','answer_p95',1)]
    for label,key,div in definitions:lines.append('| '+label+' | '+' | '.join(value(m,key,div) for m in modes)+' |')
    lines+=['','原版没有来源输出：来源准确率与离线来源处理均为N/A，业务响应逐请求检查。两观测配置的完整来源口径仅包含实际数值操作数；索引和控制选择证据另存，不计入来源TP。MirrorTaint尚未校准此查询，全部为N/A。','','## 请求与来源计数','','| 配置 | 预热请求 | 测量请求 | 预热查询 exact / queries（TP） | 测量查询 exact / queries（TP） | FP / FN / 目标unknown |','| --- | ---: | ---: | --- | --- | --- |']
    for m in modes:
        pop=a['populations'][m];p=pop['populations']
        if p:
            w,t=p['warmup'],p['steady'];cells=[f"{w['exact']}/{w['queries']} ({w['tp']})",f"{t['exact']}/{t['queries']} ({t['tp']})",f"{w['fp']+t['fp']} / {w['fn']+t['fn']} / {w['unknown']+t['unknown']}"]
        else:cells=['N/A']*3
        lines.append(f"| {m} | {pop['warmup_requests']} | {pop['steady_requests']} | "+' | '.join(cells)+' |')
    lines+=['','预热请求检查业务及来源，但完全排除于在线分位数。离线成本针对整批采集（预热＋测量），不能把该批处理时间仅除以测量期查询数。每轮p99为120个样本中的第119个，易受最慢少数请求影响，主要解释p50/p95。固定2请求/秒的完成吞吐不能说明最大吞吐相同。','','## 同轮配对与不确定性','','下表是每轮成本比的中位数及范围，不能用分组中位数相除替代。独立重复单位为部署；不把同一部署内请求当作独立实验。','','| 比较 | 指标 | 配对比中位数 | 五轮范围 | 探索性配对bootstrap 95% | 低于/高于1的轮数 |','| --- | --- | ---: | --- | --- | --- |']
    primary=['latency_p50','latency_p95','cpu','rss_mean','deployment_cpu','deployment_rss_mean','capture_events','capture_bytes','offline_core_seconds','offline_process_cpu_seconds','offline_peak_rss_bytes']
    for pair in a['paired']:
        for key in primary:
            if key not in pair['metrics']:continue
            r=pair['metrics'][key];lo,hi=r['exploratory_paired_bootstrap_percentile_95']
            lines.append(f"| {pair['comparison']} | {key} | {r['median']:.4f} | {r['min']:.4f}–{r['max']:.4f} | {lo:.4f}–{hi:.4f} | {r['lower_count']}/{r['higher_count']} |")
    lines+=['','只有五轮：bootstrap区间是探索性描述；样本min/max对连续总体中位数的分布无关覆盖率仅93.75%；即便五轮同向，双侧符号检验最小p仍为0.0625。检验未做多指标校正，不称统计显著或总体稳定改善。原始逐轮比、区间和未校正p在independent-audit.json。','','## 逐部署结果','','| 轮次配置 | p50 / p95 / p99 ms | 吞吐 req/s | 五JVM CPU% | JVM RSS均值MiB | 事件 / 字节增量 | 核心秒 / 总离线秒 | 离线峰值MiB | 答案等待p95秒 |','| --- | --- | ---: | ---: | ---: | --- | --- | ---: | ---: |']
    flat=[]
    for r in a['rows']:
        j=r['resources']['observed_jvms'];off=r['offline'];capture=r['steady_capture'];events=sum(x['events'] for x in capture.values());size=sum(x['bytes'] for x in capture.values());lat=' / '.join(fmt(r['online_latency_ms'][p]) for p in ('p50','p95','p99'))
        lines.append(f"| {r['trial']} | {lat} | {r['throughput_rps']:.3f} | {j['cpu_one_core_percent_mean']:.3f} | {j['rss_bytes_mean']/2**20:.2f} | {events} / {size} | "+('N/A' if not off else f"{off['core_seconds']:.3f} / {off['restore_score_export_seconds']:.3f}")+' | '+('N/A' if not off else f"{off['peak_rss_bytes']/2**20:.2f}")+' | '+('N/A' if not off else fmt(r['completion_to_batch_answers_seconds']['p95']))+' |')
        flat.append({'trial':r['trial'],'mode':r['mode'],'p50_ms':r['online_latency_ms']['p50'],'p95_ms':r['online_latency_ms']['p95'],'p99_ms':r['online_latency_ms']['p99'],'throughput_rps':r['throughput_rps'],'cpu_single_core_percent':j['cpu_one_core_percent_mean'],'rss_mean_bytes':j['rss_bytes_mean'],'capture_events':events,'capture_bytes':size,'offline_core_seconds':off['core_seconds'] if off else None,'offline_total_seconds':off['restore_score_export_seconds'] if off else None,'offline_cpu_seconds':off['process_cpu_seconds'] if off else None,'offline_peak_bytes':off['peak_rss_bytes'] if off else None})
    lines+=['','## 离线阶段','','各列为五轮独立批次的中位数，单位秒。阶段之和与整段时间可能有计时/调用间隙。核心包含语义和协议验证、图构建及当前字节码重放，不称为排除所有验证的纯算法时间。','','| 阶段 | full | selective |','| --- | ---: | ---: |']
    phases=list(next(r['offline']['phases'] for r in a['rows'] if r['offline']))
    for key in phases:lines.append('| '+key+' | '+' | '.join(fmt(statistics.median(r['offline']['phases'][key] for r in a['rows'] if r['mode']==m)) for m in ('full','selective'))+' |')
    lines+=['','阶段计时显示，本批差异主要集中在解码与验证/构图/本地重放；目标来源查询本身约0.22秒，两组接近。这是当前管线的阶段成本分解，不能据此把在线CPU差异归因于某一个采集机制。离线阶段时间、CPU和峰值来自冻结子进程的计时及内核rusage记录；审计核对记录一致性，未重跑后将新计时冒充原始测量。']
    lines+=['','## 解释与复现边界','','CPU按Docker累计容器CPU计数/主机单调时钟差计算，五业务JVM与完整九容器分别保存。RSS是Docker top进程RSS之和，共享页会重复计数；采样峰值不是连续峰值。资源只计所声明容器，不包含主机上的负载驱动和采样器。没有CPU亲和性固定，其他常驻容器见environment.json，五轮范围反映本机这一实验块的波动。','','事件/字节主表只计观测输出的测量批次增量，边界包括排空及采样调用耗时，不是每秒稳态写出率；capture-window.json保存前后字节与行位置。应用原生日志独立导出，console_bytes是整个部署的控制台文本（含启动和预热），不能与仅测量期结构化字节混算。','','答案等待以响应体读取完毕至答案JSON文件关闭可读的时刻计，包含剩余批次窗口、采集器停止、解码和还原；另有评分证据完成时刻。目标创建与原始证据首次可用时刻未单独计时，标N/A；采集关闭只给原始证据完整可读的保守上界。不能用约一分钟的批处理等待推断工具固有流式报告延迟。','','JSON解码、图/字节码还原、目标来源查询、答案导出、独立真值评分和证据导出分别计时。Python子进程CPU/峰值包含解释器导入、所有阶段和该批数据；父进程另测子进程墙时。旧版成本数据未进入本报告。','','独立审计重算所有部署的业务真值、原始HTTP来源实例、客户端计时、采集字节/行边界、Docker stats/top CPU和RSS、实际资源限制及随机顺序；不调用来源还原器。机器、JVM、原版镜像/JAR与冻结源文件见config.json、environment.json、sources/及各部署trainticket目录。失败/未知保持原样，正式资格要求全轮通过。','','重要节点在logs/round-*.json。原始数据不会自动随Git同步，需单独备份。新目录复现命令如下（依赖与固定镜像须先准备；输出目录不可已有）：','','```bash',
        'python3 experiments/sockshop-mirrortaint/run_train_cost.py freeze --out artifacts/train-cost-new --build '+c['build']+' --inputs '+c['inputs']+' --calibration '+c['calibration'],
        'python3 experiments/sockshop-mirrortaint/run_train_cost.py run --out artifacts/train-cost-new --build '+c['build'],
        'python3 experiments/sockshop-mirrortaint/audit_train_cost.py --out artifacts/train-cost-new',
        'python3 experiments/sockshop-mirrortaint/summarize_train_cost.py --out artifacts/train-cost-new',
        '```','','上面使用本机冻结构建/校准；换机器或路径应先按Train Ticket多来源路径报告重新prepare/build/calibrate，不能修改旧清单绕过绝对路径校验。所有push由用户手动完成。']
    (out/'results.md').write_text('\n'.join(lines)+'\n')
    with (out/'trials.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(flat[0]));w.writeheader();w.writerows(flat)
    save(out/'summary.json',{'measurement_code_commit':commit,'performance_eligible':a['performance_eligible'],'config_sha256':sha(out/'config.json'),'independent_audit_sha256':sha(out/'independent-audit.json'),'summary':a['summary'],'paired':a['paired'],'populations':a['populations'],'scope':'Five matched independent low-rate deployments; selected two Train Ticket value-origin queries; not saturation throughput'})


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);a=p.parse_args();summarize(a.out.resolve())
