#!/usr/bin/env python3
"""Reconcile raw warmup/steady populations and paired deployment uncertainty.

No new performance measurements. Exact bootstrap enumeration is exploratory
with five deployments; requests are never resampled as independent deployments.
"""
import argparse
from collections import Counter
import csv
import hashlib
import itertools
import json
import math
from pathlib import Path
import statistics


def load(p):
    return json.loads(p.read_text())


def quantile(values, p):
    return sorted(values)[max(0, math.ceil(p*len(values))-1)]


def uncertainty(values):
    n=len(values)
    bootstrap=sorted(statistics.median(s) for s in itertools.product(values,repeat=n))
    below=sum(v<1 for v in values);above=sum(v>1 for v in values);non_ties=below+above
    sign_p=min(1.,2*sum(math.comb(non_ties,i) for i in range(min(below,above)+1))/2**non_ties) if non_ties else 1.
    return {'n_deployments':n,'ratios':values,'median':statistics.median(values),
            'min':min(values),'max':max(values),'lower_count':below,'higher_count':above,
            'exploratory_paired_bootstrap_percentile_95':[quantile(bootstrap,.025),quantile(bootstrap,.975)],
            'distribution_free_median_range_coverage':1-2**(1-n),
            'exact_two_sided_sign_p_unadjusted':sign_p,
            'caveat':'Bootstrap reuses only five deployment pairs; its narrow intervals do not establish stable population effects. The observed range covers a continuous population median with only 93.75% confidence for n=5. Sign tests are descriptive, unadjusted for multiple metrics.'}


def inspect_run(root):
    config=load(root/'config.json');trials=[];fingerprints={}
    paths=sorted(root.glob('round-*/metrics.json'))
    for path in paths:
        trial=path.parent;m=load(path);steady=load(trial/'steady.json');records=load(trial/'sockshop/run.json')['cases']
        warm=[r for r in records if r['case'].startswith('warmup-')]
        measured=[r for r in records if r['case'].startswith('steady-')]
        assert len(warm)+len(measured)==len(records)
        assert len(warm)==round(config['warmup']*config['rate'])
        assert len(measured)==round(config['seconds']*config['rate'])
        assert {r['case'] for r in steady['requests']}=={r['case'] for r in measured}
        assert all(r['online_end_ns']<=steady['start_ns'] for r in warm)
        assert all(r['online_start_ns']>=steady['start_ns'] for r in measured)
        successful=[r for r in measured if r['business_passed']]
        raw_latency=[(r['online_end_ns']-r['online_start_ns'])/1e6 for r in successful]
        qs={p:quantile(raw_latency,v) for p,v in [('p50',.5),('p95',.95),('p99',.99)]}
        for p,v in qs.items():assert math.isclose(v,m['online_latency_ms'][p],abs_tol=1e-8)
        mode=load(trial/'observation-policy.json')['policy'] if (trial/'observation-policy.json').exists() else m.get('configuration',m['mode'])
        population={}
        if (trial/'sockshop/field-results.json').exists():
            queries=load(trial/'sockshop/field-results.json')['queries']
            for label in ('warmup','steady'):
                group=[q for q in queries if q['case'].startswith(label+'-')]
                population[label]={'queries':len(group),'exact':sum(q['exact'] for q in group),
                                   **{k:sum(q[k] for q in group) for k in ('tp','fp','fn')},
                                   'unknown':sum(not q['prediction']['known'] for q in group)}
            assert sum(g['queries'] for g in population.values())==len(queries)
        row={'trial':trial.name,'mode':mode,'round':int(trial.name.split('-')[1]),
             'warmup_requests':len(warm),'steady_requests':len(measured),'successful_steady_requests':len(successful),
             'query_populations':population,'within_deployment_latency_ms':{**qs,'min':min(raw_latency),'max':max(raw_latency)},
             'p99_nearest_rank':math.ceil(.99*len(successful)),'latency_sample_size':len(successful),
             'cpu':m['resources']['observed_jvms']['cpu_one_core_percent_mean'],
             'capture_events':sum(v['events'] for v in m['steady_capture'].values()),
             'capture_bytes':sum(v['bytes'] for v in m['steady_capture'].values())}
        if m['offline']:
            row.update(offline_wall=m['offline']['subprocess_wall_seconds'],offline_peak=m['offline']['peak_rss_bytes'])
        trials.append(row)
        for p in (path,trial/'steady.json',trial/'sockshop/run.json',trial/'sockshop/field-results.json'):
            if p.exists():fingerprints[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
    totals={mode:{'deployments':len(rows),'warmup_requests':sum(r['warmup_requests'] for r in rows),
                  'steady_requests':sum(r['steady_requests'] for r in rows),
                  'queries':{phase:{k:sum(r['query_populations'].get(phase,{}).get(k,0) for r in rows) for k in ('queries','exact','tp','fp','fn','unknown')} for phase in ('warmup','steady')}}
            for mode in sorted({r['mode'] for r in trials}) for rows in [[r for r in trials if r['mode']==mode]]}
    pairings=[]
    for numerator,denominator in [('tracefusion','original'),('tracefusion','mirrortaint'),('selective','full')]:
        pairs=[]
        for round_id in sorted({r['round'] for r in trials}):
            indexed={r['mode']:r for r in trials if r['round']==round_id}
            if numerator in indexed and denominator in indexed:pairs.append((indexed[numerator],indexed[denominator]))
        if not pairs:continue
        metrics={}
        for metric in ('p50','p95','p99','cpu','capture_events','capture_bytes','offline_wall','offline_peak'):
            def value(r):return r['within_deployment_latency_ms'][metric] if metric in ('p50','p95','p99') else r.get(metric)
            values=[value(a)/value(b) for a,b in pairs if value(a) is not None and value(b)]
            if values:metrics[metric]=uncertainty(values)
        pairings.append({'comparison':numerator+'/'+denominator,'metrics':metrics})
    return {'run':str(root),'verified':True,'trials':trials,'totals':totals,'paired':pairings,'evidence_sha256':fingerprints}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--runs',type=Path,nargs='+',required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=False)
    results=[inspect_run(r.resolve()) for r in a.runs]
    (a.out/'population-and-pairs.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
    lines=['# 预热、计数与部署级不确定性复核','',
           '仅重算已有数据；独立重复单位为部署，未将同一部署的请求当作独立实验。所有在线分位数均由steady原始请求重算并与原报告核对。',
           '每配置每轮60次预热、120次测量；五轮分别300和600次。共同total每请求1个查询，故900是预热加测量的准确性分母；在线延迟只用600个测量请求，先按部署分别统计。',
           '每轮p99为120个请求的第119顺序统计量，受最慢两个请求强烈影响，作为描述性补充。',
           '五轮比值仅提供小样本估计。精确枚举5^5重采样的配对bootstrap百分位区间为探索性结果；[min,max]作为总体中位数的分布无关区间覆盖率仅93.75%，不冒充95%。五对同方向结果的双侧符号检验最小p也只有0.0625。','']
    for result in results:
        lines+=['## '+Path(result['run']).name,'','| 配置 | 预热请求 | 测量请求 | 预热查询/TP | 测量查询/TP |','| --- | ---: | ---: | --- | --- |']
        for mode,v in result['totals'].items():
            w,s=v['queries']['warmup'],v['queries']['steady']
            lines.append(f"| {mode} | {v['warmup_requests']} | {v['steady_requests']} | {w['queries']} / {w['tp']} | {s['queries']} / {s['tp']} |")
        for pair in result['paired']:
            lines+=['','### '+pair['comparison'],'','| 指标 | 五轮配对比值 | 中位数 | 范围 | 探索性bootstrap 95% |','| --- | --- | ---: | --- | --- |']
            for metric,v in pair['metrics'].items():
                values=', '.join(f'{x:.4f}' for x in v['ratios']);ci=v['exploratory_paired_bootstrap_percentile_95']
                lines.append(f"| {metric} | {values} | {v['median']:.4f} | {v['min']:.4f}–{v['max']:.4f} | {ci[0]:.4f}–{ci[1]:.4f} |")
    lines+=['','部署内分位数及极值见JSON；部署之间的配对比值在上表。保留原报告已有的范围/CV，新增区间不修改原始测量。',
            '方法参考：[Kalibera & Jones, Rigorous Benchmarking in Reasonable Time (2013)](https://kar.kent.ac.uk/33611/45/p63-kaliber.pdf)。本文支持分层重复与不确定性报告；此处未声称完全实现其方差分配方法。','']
    (a.out/'results.md').write_text('\n'.join(lines))
    print(json.dumps({Path(r['run']).name:r['totals'] for r in results},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
