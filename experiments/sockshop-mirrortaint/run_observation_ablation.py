#!/usr/bin/env python3
"""Fixed-load ablation: one collector, plan, JSONL serializer and reconstructor.

full means the existing admitted-class instance-field/conditional-branch policy,
with records inside the frozen query frames, not all JVM/native instructions.
boundary keeps HTTP/JSON plus identical admitted DTO write counters, but removes
internal frames, reads, reductions and target-write records. Its total answers
must remain unknown; it is an incomplete-answer control, not an equally capable alternative.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import copy
import json
import math
from pathlib import Path
import random
import resource
import secrets
import statistics
import subprocess
import sys
import threading

from run_planned_service import ROOT, HERE, load, save, sha
from run_distributed_paths import check
from calibrate_mirrortaint_total import common_spec
from host import prepare, submit
from flowdist_full_order import CachedDeployment
import mirrortaint_instances as common_query
import run_sockshop_cost as cost

POLICIES=('full','selective','boundary')
ROLES=('orders','carts')


def fingerprint(build,correctness):
    return {'build_sha256':sha(build/'build.json'),'cases_sha256':sha(correctness/'cases.json'),
            'images_sha256':sha(ROOT/'artifacts/desktop-inputs/images-lock.json'),
            'sources':{str(p.relative_to(ROOT)):sha(p) for p in sorted([*HERE.glob('*.py'),*HERE.glob('*.java'),ROOT/'scripts/sockshop.py'])}}


def qualified(policy,summary,expected=None):
    if summary['queries']<=0 or expected is not None and summary['queries']!=expected:return False
    if policy=='boundary':return summary['unknown']==summary['queries'] and summary['exact']==summary['tp']==summary['fp']==0
    return summary['exact']==summary['queries'] and summary['unknown']==summary['fp']==summary['fn']==0


def capture_breakdown(trial):
    result={};window=load(trial/'capture-window.json') if (trial/'capture-window.json').exists() else None
    policy=load(trial/'observation-policy.json')['policy']
    for role in ROLES:
        rows=[json.loads(l) for l in (trial/'sockshop'/role/'events.jsonl').read_text().splitlines()]
        if rows[0]['mode']!=policy or any(r['kind']=='problem' for r in rows):raise ValueError('Policy/capture differs')
        metrics=[r for r in rows if r['kind']=='metrics']
        if len(metrics)!=1:raise ValueError('Incomplete capture')
        steady=rows[window['before'][role]['events']:window['after'][role]['events']] if window else []
        if policy=='boundary' and any(r['kind'] in ('enter','exit','abort','read','write','branch','sum-enter','sum-exit') for r in rows):
            raise ValueError('Boundary unexpectedly collected local dependency evidence')
        result[role]={'whole_trial_by_kind':dict(Counter(r['kind'] for r in rows)),
                      'cohort_by_kind':dict(Counter(r['kind'] for r in steady)),
                      'whole_trial_hook_metrics':metrics[0],
                      'cohort_http_field_records':sum(len(r['fields']) for r in steady if r['kind']=='http-json'),
                      'cohort_producer_snapshot_fields':sum(len(i['fields']) for r in steady for i in r.get('inputs',[]))}
    save(trial/'observation-breakdown.json',result)
    return result


def normalized_spec(spec,trial):
    # Paths select a fresh output directory, never another app/plan/binary.
    text=json.dumps(spec,sort_keys=True).replace(str((trial/'sockshop').resolve()),'$CAPTURE')
    for policy in POLICIES:text=text.replace('-Dservice.mode='+policy,'-Dservice.mode=$POLICY')
    return json.loads(text)


def logical_answers(trial):
    results=load(trial/'sockshop/field-results.json')
    return {q['case']:{'target':{k:q['prediction']['target'][k] for k in ('field','version','observed')},
                       'sources':sorted([[n['service'],n['path'],n['field'],n['version'],n['observed'].get('value')] for n in q['prediction']['sources']],key=str)}
            for q in results['queries']}


def offline(trial,build):
    policy=load(trial/'observation-policy.json')['policy']
    report=common_query.evaluate(trial,build,'tracefusion')
    usage=resource.getrusage(resource.RUSAGE_SELF)
    timing=load(trial/'offline.json')
    timing['process_cpu_seconds']=usage.ru_utime+usage.ru_stime
    save(trial/'offline.json',timing)
    if not qualified(policy,report['summary']):raise ValueError('Unexpected provenance result: '+str(report['summary']))
    print(json.dumps(report['summary']),flush=True)


def calibrate(args):
    out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    build=args.build.resolve();correctness=args.correctness.resolve();check(correctness,build)
    frozen=fingerprint(build,correctness);signatures={};specs=[];results={}
    save(out/'config.json',{'frozen':frozen,'policies':POLICIES,'query':'Carts serialized response fields -> Orders.total'})
    for policy in POLICIES:
        if fingerprint(build,correctness)!=frozen:raise ValueError('Calibration sources changed')
        trial=out/policy;trial.mkdir();dest=trial/'sockshop';dest.mkdir()
        save(trial/'observation-policy.json',{'policy':policy})
        spec=common_spec('tracefusion',dest,build,None,observation_policy=policy)
        save(dest/'compose.json',spec);specs.append(normalized_spec(spec,trial))
        dep=CachedDeployment(argparse.Namespace(project='tf2-abl-cal-'+secrets.token_hex(5),ready_timeout=240),dest,dest/'compose.json')
        run={'status':'failed','project':dep.args.project,'cases':[]};save(dest/'run.json',run)
        try:
            dep.start();trace=secrets.token_hex(16);cases=load(correctness/'cases.json')['sockshop']
            def setup(case,name,shared=False):
                prepared=prepare(case,name,dest/name,'http://127.0.0.1:18580','http://127.0.0.1:18581',shared=shared)
                span=secrets.token_hex(8);prepared[1].headers={'traceparent':f'00-{trace}-{span}-01','tracestate':'research=ablation'}
                prepared[-1]['message']=trace+'/'+span;save(dest/name/'query-contract.json',prepared[-1]);return prepared
            for case in cases:
                p=setup(case,case['id']);r=submit(p,'http://127.0.0.1:18582',dest/case['id']);r['message']=p[-1]['message'];run['cases'].append(r)
                if not r['business_passed']:raise ValueError(r)
            pending=[setup(cases[0],'parallel-'+str(i),True) for i in range(8)];barrier=threading.Barrier(8)
            with ThreadPoolExecutor(max_workers=8) as pool:
                futures=[pool.submit(submit,p,'http://127.0.0.1:18582',dest/p[-1]['case'],barrier) for p in pending]
                for p,f in zip(pending,futures):
                    r=f.result();r['message']=p[-1]['message'];run['cases'].append(r)
                    if not r['business_passed']:raise ValueError(r)
            for role in ROLES:dep.compose('stop','-t','20',role,timeout=40)
            run['status']='business-passed';save(dest/'run.json',run)
        finally:
            dep.diagnostics();clean=dep.compose('down','--volumes','--remove-orphans',timeout=120,check=False)
            save(trial/'cleanup.json',{'returncode':clean.returncode,'project':dep.args.project})
            if clean.returncode:raise ValueError('Calibration cleanup failed')
        report=common_query.evaluate(trial,build,'tracefusion');capture_breakdown(trial)
        if not qualified(policy,report['summary'],24):raise ValueError('Policy calibration failed: '+str(report['summary']))
        results[policy]=report['summary']
        if policy!='boundary':
            signature=logical_answers(trial)
            # JVM object IDs have no meaning across deployments; values validate
            # equality of independently scored answers, never create origins.
            for value in signature.values():value['target']['observed'].pop('object',None)
            signatures[policy]=signature
        print('Calibration',policy,report['summary'],flush=True)
    if specs[0]!=specs[1] or specs[0]!=specs[2]:raise ValueError('Non-policy deployment difference')
    if signatures['full']!=signatures['selective']:raise ValueError('Full/selective logical answers differ')
    if fingerprint(build,correctness)!=frozen:raise ValueError('Calibration sources changed')
    save(out/'calibration.json',{'all_passed':True,'frozen':frozen,'results':results,'full_selective_same_logical_answers':True,
                                'same_spec_except_policy_and_output_paths':True,'same_trace_distinct_spans':True,'parallel_requests':8,
                                'boundary_is_unknown_cost_control':True})


def report(out):
    cfg=load(out/'config.json');state=load(out/'run-status.json');rows=[]
    for name,policy in cfg['order']:
        t=out/name
        if not (t/'metrics.json').exists():continue
        m=load(t/'metrics.json');s=m['offline']['summary'];r={'trial':name,'policy':policy,**m}
        r['control_qualified']=qualified(policy,s);rows.append(r)
    summaries={}
    for policy in POLICIES:
        rs=[r for r in rows if r['policy']==policy and r['control_qualified']]
        if not rs:continue
        values={}
        for p in ('p50','p95','p99'):values['latency_'+p+'_ms']=[r['online_latency_ms'][p] for r in rs]
        for key in ('cpu_one_core_percent_mean','rss_bytes_mean','rss_bytes_peak'):
            values[key]=[r['resources']['observed_jvms'][key] for r in rs]
        for key in ('events','bytes'):values['capture_'+key]=[sum(v[key] for v in r['steady_capture'].values()) for r in rs]
        for key in ('graph_build_seconds','restore_score_export_seconds','subprocess_wall_seconds','process_cpu_seconds','peak_rss_bytes'):
            values['offline_'+key]=[r['offline'][key] for r in rs]
        values['answer_wait_p95_seconds']=[r['completion_to_batch_answers_seconds']['p95'] for r in rs]
        summaries[policy]={'trials':len(rs),'metrics':{k:{'median':statistics.median(v),'min':min(v),'max':max(v),
                              'cv':statistics.stdev(v)/statistics.mean(v) if len(v)>1 and statistics.mean(v) else None} for k,v in values.items()},
                           'accuracy':{key:sum(r['offline']['summary'][key] for r in rs) for key in ('queries','exact','tp','fp','fn','unknown')}}
    paired=[]
    for i in range(cfg['rounds']):
        pair={r['policy']:r for r in rows if r['trial'].startswith(f'round-{i+1:02d}-') and r['control_qualified']}
        if not {'full','selective'}<=pair.keys():continue
        a,b=pair['selective'],pair['full'];ratios={'round':i+1}
        for p in ('p50','p95','p99'):ratios['latency_'+p]=a['online_latency_ms'][p]/b['online_latency_ms'][p]
        for key in ('cpu_one_core_percent_mean','rss_bytes_mean'):ratios[key]=a['resources']['observed_jvms'][key]/b['resources']['observed_jvms'][key]
        for key in ('events','bytes'):ratios['capture_'+key]=sum(v[key] for v in a['steady_capture'].values())/sum(v[key] for v in b['steady_capture'].values())
        for key in ('subprocess_wall_seconds','restore_score_export_seconds','process_cpu_seconds','peak_rss_bytes'):ratios['offline_'+key]=a['offline'][key]/b['offline'][key]
        paired.append(ratios)
    ratio_medians={k:statistics.median(p[k] for p in paired) for k in paired[0] if k!='round'} if paired else {}
    eligible=state['status']=='passed' and cfg['rounds']>=5 and len(rows)==len(cfg['order']) and all(r['control_qualified'] and r['error_rate']==0 for r in rows)
    save(out/'comparison.json',{'run_status':state,'performance_eligible':eligible,'rows':rows,'summary':summaries,
                               'paired_selective_over_full':paired,'paired_ratio_medians':ratio_medians,
                               'scope':'Same frozen Orders.total query/plan, collector binary, JSONL serializer and offline implementation. Boundary is an unknown-answer cost control.'})
    lines=['# Orders.total 严格观测消融','',f"状态：{state['status']}；五轮资格：{eligible}。",'',
           f"{cfg['rounds']}轮独立部署；预热{cfg['warmup']}秒、窗口{cfg['seconds']}秒；{cfg['rate']}请求/秒，并发{cfg['concurrency']}；每容器{cfg['cpus']}核/{cfg['memory']}。",'',
           '三种策略共用同一采集器 JAR、原业务 JAR、冻结计划、HTTP/JSON 边界、逐事件 JSONL 格式与同步flush策略，以及相同离线还原器/评分器。Shipping 不装观测器。', '',
           'full 是已纳入应用类的实例字段读写、条件跳转策略，记录限于冻结查询帧；不是所有JVM/库/本地指令的完整追踪。selective 使用自动计划。boundary 保留同样的HTTP/JSON证据和DTO写计数，但删除内部帧、读取、归约和目标写入记录；它必须保留unknown，不能当作同准确率替代方案。','',
           '| 轮次 | 策略 | p50 / p95 / p99 ms | CPU单核% | JVM RSS均值MiB | 采集事件 / 字节 | exact / queries | unknown |',
           '| --- | --- | --- | ---: | ---: | --- | --- | ---: |']
    for r in rows:
        q=r['offline']['summary'];res=r['resources']['observed_jvms'];lat=' / '.join(f'{r["online_latency_ms"][p]:.3f}' for p in ('p50','p95','p99'))
        events=sum(v['events'] for v in r['steady_capture'].values());size=sum(v['bytes'] for v in r['steady_capture'].values())
        lines.append(f'| {r["trial"]} | {r["policy"]} | {lat} | {res["cpu_one_core_percent_mean"]:.2f} | {res["rss_bytes_mean"]/2**20:.2f} | {events} / {size} | {q["exact"]}/{q["queries"]} | {q["unknown"]} |')
    if summaries:
        lines+=['','| 各轮中位数 | full | selective | boundary |','| --- | ---: | ---: | ---: |']
        for key in next(iter(summaries.values()))['metrics']:
            vals=[f'{summaries[p]["metrics"][key]["median"]:.6g}' if p in summaries and not (p=='boundary' and key=='answer_wait_p95_seconds') else 'N/A' for p in POLICIES]
            lines.append('| '+key+' | '+' | '.join(vals)+' |')
    if ratio_medians:
        lines+=['','| 同轮成本比中位数 | selective / full |','| --- | ---: |']
        for key,value in ratio_medians.items():lines.append(f'| {key} | {value:.4f} |')
        cpu=ratio_medians['cpu_one_core_percent_mean']
        lines+=['','同轮比值中位数显示：事件减少'+f'{(1-ratio_medians["capture_events"])*100:.2f}%'+
                '，采集字节减少'+f'{(1-ratio_medians["capture_bytes"])*100:.2f}%'+
                '，离线进程墙时减少'+f'{(1-ratio_medians["offline_subprocess_wall_seconds"])*100:.2f}%'+
                '，离线峰值内存减少'+f'{(1-ratio_medians["offline_peak_rss_bytes"])*100:.2f}%'+
                '。在线CPU'+('增加' if cpu>=1 else '减少')+f'{abs(cpu-1)*100:.2f}%。'+
                '应分别解释采集、离线和在线成本，不据此宣称所有资源均改善。']
    lines+=['','完整成本、范围与变异系数见 comparison.json；逐事件类别、边界字段数、输入快照字段数与整次部署hook计数见 observation-breakdown.json。资源原始采样、逐请求计时、独立真值、答案、unknown与清理均保留。', '',
            'CPU是三个业务JVM的单核百分比之和；RSS为进程RSS求和，含共享页重复计数。采集增量含排空和采样边界。离线进程墙时含启动，峰值内存为独立子进程ru_maxrss。答案等待是响应完成至整批结果写出，含剩余窗口与关闭采集器，不是流式延迟。', '',
            '只将full与selective的同准确率结果用于成本收益比较。boundary不提供total来源答案，已知来源答案的等待时间及每个正确答案的成本为N/A。公共驱动原始批次写出时间表示unknown结果文件就绪，不能解释为已知来源答案可用。只改变观测策略仍同时改变钩子、快照字段和输出量；本实验不把CPU差异全部归因于JSON写出，也不将其用于分解MirrorTaint的日志/适配器成本。', '',
            '固定2请求/秒的完成吞吐不代表最大容量；不混入旧机器或旧配置开销。本机最新main是后续版本基准，旧迁移包仅是历史快照。','']
    (out/'results.md').write_text('\n'.join(lines))


def run(args):
    out=args.out.resolve();build=args.build.resolve();correctness=args.correctness.resolve();cal=args.calibration.resolve()
    check(correctness,build);frozen=fingerprint(build,correctness);receipt=load(cal/'calibration.json')
    if not receipt['all_passed'] or receipt['frozen']!=frozen:raise ValueError('Ablation calibration/source/input hashes differ')
    for app,n in [('sockshop',198),('trainticket',31)]:
        s=load(correctness/app/'field-results.json')['summary']
        if s['exact']!=n or s['queries']!=n or s['fp'] or s['fn'] or s['unknown']:raise ValueError('Application regression required')
    for name in ('algorithm-audit.json','protocol-checks.json'):
        if not load(correctness/name)['all_passed']:raise ValueError('Application audit required')
    if not load(correctness/'original-image-verification.json')['all_matched']:raise ValueError('Original JAR verification required')
    out.mkdir(parents=True,exist_ok=False);rng=random.Random(args.seed);order=[]
    for i in range(args.rounds):
        policies=list(POLICIES);rng.shuffle(policies)
        order.extend((f'round-{i+1:02d}-{j+1}-{p}',p) for j,p in enumerate(policies))
    cfg={k:str(v) if isinstance(v,Path) else v for k,v in vars(args).items()};cfg.update(order=order,frozen=frozen,jvm=cost.JVM,calibration_sha256=sha(cal/'calibration.json'))
    save(out/'config.json',cfg);cost.environment(out);save(out/'command.json',{'argv':[sys.executable,*sys.argv],'cwd':str(Path.cwd())})
    templates=[c for c in load(correctness/'cases.json')['sockshop'] if c['expected_target']]
    save(out/'workload.json',{'templates':templates,'warmup_indices':[i%len(templates) for i in range(round(args.warmup*args.rate))],
                             'steady_indices':[i%len(templates) for i in range(round(args.seconds*args.rate))],
                             'query':'Carts serialized response fields -> Orders.total'})
    save(out/'run-status.json',{'status':'running'});specs={}
    try:
        for name,policy in order:
            check(correctness,build)
            if fingerprint(build,correctness)!=frozen:raise ValueError('Frozen sources changed')
            trial=out/name
            settings=copy.copy(args);settings.build=build;settings.correctness=correctness;settings.mt_bundle=None
            settings.query_scope='total';settings.allow_errors=False;settings.observation_policy=policy;settings.offline_program=Path(__file__).resolve()
            metric=cost.trial_run(settings,trial,'tracefusion',build)
            # Evidence accounting is outside online sampling and the measured
            # offline child. Counting JSON a second time is not reconstruction.
            capture_breakdown(trial)
            if metric['error_rate'] or not qualified(policy,metric['offline']['summary'],round((args.warmup+args.seconds)*args.rate)):
                raise ValueError('Business/source control failed')
            specs[name]=normalized_spec(load(trial/'sockshop/compose.json'),trial)
            if any(s!=specs[name] for s in specs.values()):raise ValueError('Non-policy configuration difference')
            if fingerprint(build,correctness)!=frozen:raise ValueError('Frozen sources changed')
            save(trial/'ablation-outcome.json',{'policy':policy,'passed':True,'boundary_unknown_expected':policy=='boundary'})
            report(out)
        save(out/'run-status.json',{'status':'passed'})
    except BaseException as e:
        save(out/'run-status.json',{'status':'failed','error_type':type(e).__name__,'error':str(e)});raise
    finally:report(out)
    save(out/'evidence-sha256.json',{str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.is_file()})


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('stage',choices=('calibrate','run','offline','report'))
    p.add_argument('--out',type=Path,required=True);p.add_argument('--build',type=Path);p.add_argument('--correctness',type=Path);p.add_argument('--calibration',type=Path)
    p.add_argument('--rounds',type=int,default=5);p.add_argument('--warmup',type=float,default=30);p.add_argument('--seconds',type=float,default=60)
    p.add_argument('--rate',type=float,default=2);p.add_argument('--concurrency',type=int,default=2);p.add_argument('--sample-interval',type=float,default=2)
    p.add_argument('--cpus',type=float,default=1);p.add_argument('--memory',default='768m');p.add_argument('--seed',type=int,default=151031)
    p.add_argument('--offline-timeout',type=float,default=600)
    # Reused cost trial subprocess protocol; backend is identical for all policies.
    p.add_argument('--query-scope',choices=('total',),default='total');p.add_argument('--mode',choices=('tracefusion',),default='tracefusion')
    a=p.parse_args()
    if a.stage=='report':report(a.out.resolve());return
    if not a.build:p.error('--build required')
    if a.stage=='offline':offline(a.out.resolve(),a.build.resolve());return
    if not a.correctness:p.error('--correctness required')
    if min(a.rounds,a.warmup,a.seconds,a.rate,a.concurrency,a.cpus,a.sample_interval)<=0:p.error('Positive load, resource and duration settings required')
    if any(not math.isclose(t*a.rate,round(t*a.rate)) for t in (a.warmup,a.seconds)):p.error('Integral request counts required')
    if a.seconds<a.sample_interval*3:p.error('At least three resource sampling intervals required')
    if a.stage=='calibrate':calibrate(a)
    else:
        if not a.calibration:p.error('--calibration required')
        run(a)

if __name__=='__main__':main()
