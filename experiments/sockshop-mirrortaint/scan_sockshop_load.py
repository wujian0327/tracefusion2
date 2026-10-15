#!/usr/bin/env python3
"""Sequential offered-load scan with fresh deployments and common total queries.

Points are exploratory single deployments, not five-round cost estimates. A
capture failure preserves online evidence but leaves provenance costs N/A.
"""
import argparse
import json
from pathlib import Path
import random
import subprocess
import sys
from run_planned_service import HERE, load, save
from run_sockshop_cost import percentiles


def summarize(out):
    config=load(out/'scan.json');rows=[]
    for entry in config['order']:
        run=out/entry['name'];trials=sorted(run.glob('round-*'))
        metric=next(run.glob('round-*/metrics.json'),None)
        if metric:
            row={**entry,**load(metric),'provenance_eligible':load(metric)['status']=='passed'}
        else:
            row={**entry,'status':'N/A: deployment/capture/offline failed','provenance_eligible':False}
            window=next(run.glob('round-*/steady.json'),None)
            if window:
                steady=load(window);requests=steady['requests'];good=[r for r in requests if r['business_passed']]
                row.update(steady_requests=len(requests),successful_requests=len(good),error_rate=1-len(good)/len(requests),
                           throughput_rps=sum(r['online_end_ns']<=steady['scheduled_end_ns'] for r in good)/config['seconds'],
                           online_latency_ms=percentiles([(r['online_end_ns']-r['online_start_ns'])/1e6 for r in good]),
                           scheduled_to_response_ms=percentiles([(r['online_end_ns']-r['scheduled_ns'])/1e6 for r in good]))
            failure=next(run.glob('round-*/failure.json'),None)
            if failure:row['failure']=load(failure)
        rows.append(row)
    save(out/'scan-results.json',{'rows':rows,'scope':'Exploratory independent deployments. Offered load is not measured capacity; capture failures do not establish service saturation.'})
    def number(value):return 'N/A' if value is None else f'{value:.3f}'
    lines=['# Orders.total 共同查询负载扫描','','每个点重新部署，随机配置顺序；固定 JVM、资源、模板、预热及窗口。单点不是五轮正式开销估计。', '',
           '| 到达率 req/s | 配置 | 成功吞吐 req/s | 错误率 | HTTP p95 ms | 计划到达至响应 p95 ms | 来源验证 |',
           '| ---: | --- | ---: | ---: | ---: | ---: | --- |']
    for r in rows:
        lines.append(f'| {r["rate"]} | {r["mode"]} | {number(r.get("throughput_rps"))} | {number(r.get("error_rate"))} | {number(r.get("online_latency_ms",{}).get("p95"))} | {number(r.get("scheduled_to_response_ms",{}).get("p95"))} | {"通过" if r["provenance_eligible"] and r["mode"]!="original" else "N/A"} |')
    lines+=['','资源、采集日志、离线耗时/峰值内存和整批答案等待时间见每点 results.md 与 scan-results.json。失败点保留原始请求、采样及错误日志，来源答案和离线成本为 N/A。', '',
            '结合实际成功吞吐、错误、计划到达延迟、调度滞后和各组件 CPU 判断负载压力。并发上限或客户端排队也可能限制吞吐，不能仅据吞吐相等或某点失败宣称最大服务吞吐相同/不同。','']
    (out/'results.md').write_text('\n'.join(lines))


def main(a):
    a.out=a.out.resolve();a.out.mkdir(parents=True,exist_ok=False);rng=random.Random(a.seed);order=[]
    for rate in a.rates:
        modes=['original','tracefusion','mirrortaint'];rng.shuffle(modes)
        for i,mode in enumerate(modes):order.append({'name':f'rate-{rate:g}-{i+1}-{mode}','rate':rate,'mode':mode})
    cfg={k:str(v) if isinstance(v,Path) else v for k,v in vars(a).items()};cfg['order']=order;save(a.out/'scan.json',cfg)
    try:
        for entry in order:
            cmd=[sys.executable,str(HERE/'run_sockshop_cost.py'),'run','--out',str(a.out/entry['name']),
                 '--build',str(a.build.resolve()),'--correctness',str(a.correctness.resolve()),'--rounds','1',
                 '--warmup',str(a.warmup),'--seconds',str(a.seconds),'--rate',str(entry['rate']),
                 '--concurrency',str(a.concurrency),'--cpus',str(a.cpus),'--memory',a.memory,
                 '--sample-interval','2','--seed',str(a.seed),'--query-scope','total','--modes',entry['mode'],
                 '--mt-bundle',str(a.mt_bundle.resolve()),'--mt-calibration',str(a.mt_calibration.resolve()),
                 '--tf-calibration',str(a.tf_calibration.resolve()),'--allow-errors']
            print('Scan',entry,flush=True)
            with (a.out/(entry['name']+'.log')).open('w') as log:
                r=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT)
            save(a.out/(entry['name']+'.command.json'),{'command':cmd,'returncode':r.returncode})
            summarize(a.out)
    finally:summarize(a.out)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('out','build','correctness','mt-bundle','mt-calibration','tf-calibration'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--rates',nargs='+',type=float,default=[2,4,8,16,32])
    p.add_argument('--warmup',type=float,default=10);p.add_argument('--seconds',type=float,default=20)
    p.add_argument('--concurrency',type=int,default=32);p.add_argument('--cpus',type=float,default=1)
    p.add_argument('--memory',default='768m');p.add_argument('--seed',type=int,default=151031)
    a=p.parse_args()
    if any(r<=0 or not (r*a.seconds).is_integer() or not (r*a.warmup).is_integer() for r in a.rates):p.error('positive rates and integral request counts required')
    main(a)
