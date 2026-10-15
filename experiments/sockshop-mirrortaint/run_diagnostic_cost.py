#!/usr/bin/env python3
"""Randomized paired deployments for default/quiet MirrorTaint and TraceFusion."""
import copy
import json
from pathlib import Path
import random
import statistics
import sys
from run_planned_service import HERE,ROOT,load,save,sha
from audit_current_acceptance import verify as verify_acceptance
import mirrortaint_instances as mt
import run_sockshop_cost as cost


def report(out):
    cfg=load(out/'config.json');rows=[]
    for name,variant in cfg['order']:
        p=out/name/'metrics.json'
        if p.exists():rows.append({'trial':name,'configuration':variant,**load(p)})
    lines=['# MirrorTaint诊断输出配置比较','',
           '同一块中新测：默认MirrorTaint、关闭agent-info的披露运行时适配配置、TraceFusion。固定2请求/秒；随机配置顺序、独立部署。诊断变体不是上游内置选项，不代表最低开销。必要原生标签、错误日志及类转储仍保留。','',
           '| 轮次 | 配置 | p50/p95/p99 ms | CPU单核% | 采集字节 | exact/queries |','| --- | --- | --- | ---: | ---: | --- |']
    for r in rows:
        q=r['offline']['summary'];p=r['online_latency_ms']
        lines.append(f"| {r['trial']} | {r['configuration']} | {p['p50']:.3f}/{p['p95']:.3f}/{p['p99']:.3f} | {r['resources']['observed_jvms']['cpu_one_core_percent_mean']:.3f} | {sum(v['bytes'] for v in r['steady_capture'].values())} | {q['exact']}/{q['queries']} |")
    eligible=load(out/'run-status.json')['status']=='passed' and len(rows)==3*cfg['rounds'] and cfg['rounds']>=5 and all(r['status']=='passed' for r in rows)
    lines+=['',f'五轮资格：{eligible}。逐阶段离线耗时见各轮offline.json；原始数据和配置均保留。窗口关闭时间是原始结果已关闭的上界，不能把原来的约61秒批次等待当作引擎固有报告延迟。','']
    save(out/'comparison.json',{'performance_eligible':eligible,'rows':rows,'scope':'Default vs disclosed quiet-agent-info plus TraceFusion; new fixed-load measurements only'})
    (out/'results.md').write_text('\n'.join(lines))


def run(a):
    a.out=a.out.resolve();a.build=a.build.resolve();a.correctness=a.correctness.resolve()
    verify_acceptance(a.acceptance.resolve(),a.correctness,a.build)
    bundles={'mt-default':a.default_bundle.resolve(),'mt-quiet':a.quiet_bundle.resolve(),'tracefusion':a.default_bundle.resolve()}
    calibrations={'mt-default':a.default_calibration.resolve(),'mt-quiet':a.quiet_calibration.resolve(),'tracefusion':a.tf_calibration.resolve()}
    if load(bundles['mt-default']/'build.json').get('diagnostics') is not None or load(bundles['mt-quiet']/'build.json').get('diagnostics')!='quiet-agent-info':raise ValueError('Diagnostic variants do not match')
    for variant,bundle in bundles.items():
        mt.verify(bundle);cal=load(calibrations[variant]/'calibration.json')
        if not cal['passed'] or cal['summary']['queries']!=24 or cal['bundle_sha256']!=sha(bundle/'build.json') or cal['evaluator_sha256']!=sha(HERE/'mirrortaint_instances.py') or cal['build_sha256']!=sha(a.build/'build.json') or cal['cases_sha256']!=sha(a.correctness/'cases.json'):raise ValueError('Fresh matching calibration required: '+variant)
        if variant.startswith('mt-') and not load(calibrations[variant]/'instance-audit.json')['all_passed']:raise ValueError('Native negative controls required')
    a.out.mkdir(parents=True,exist_ok=False);rng=random.Random(a.seed);order=[]
    for i in range(a.rounds):
        modes=list(bundles);rng.shuffle(modes)
        order.extend((f'round-{i+1:02d}-{j+1}-{m}',m) for j,m in enumerate(modes))
    frozen={str(p.relative_to(ROOT)):sha(p) for p in sorted([*HERE.glob('*.py'),*HERE.glob('*.java'),ROOT/'scripts/sockshop.py'])}
    cfg={k:str(v) if isinstance(v,Path) else v for k,v in vars(a).items()};cfg.update(order=order,source_sha256=frozen,query_scope='total',modes=list(bundles))
    save(a.out/'config.json',cfg);cost.environment(a.out);save(a.out/'command.json',{'argv':sys.argv,'cwd':str(Path.cwd())});save(a.out/'run-status.json',{'status':'running'})
    try:
        for name,variant in order:
            if any(sha(ROOT/p)!=h for p,h in frozen.items()):raise ValueError('Frozen experiment sources changed')
            settings=copy.copy(a);settings.mt_bundle=bundles[variant];settings.query_scope='total';settings.offline_program=HERE/'run_sockshop_cost.py'
            metric=cost.trial_run(settings,a.out/name,'tracefusion' if variant=='tracefusion' else 'mirrortaint',a.build)
            metric['configuration']=variant;save(a.out/name/'metrics.json',metric)
            if metric['status']!='passed' or metric['offline']['summary']['queries']!=round((a.warmup+a.seconds)*a.rate):raise ValueError('Correctness failed')
            if variant=='mt-quiet':
                info=list((a.out/name/'sockshop/orders').rglob('agent-info.log'))
                if len(info)!=1 or info[0].stat().st_size:raise ValueError('Agent-info suppression not confirmed')
                if 'TF2_MT_QUIET agent-info methods suppressed=3' not in (a.out/name/'container-console.log').read_text():raise ValueError('Quiet transformer missing')
            report(a.out)
        save(a.out/'run-status.json',{'status':'passed'})
    except BaseException as e:
        save(a.out/'run-status.json',{'status':'failed','error':str(e)});raise
    finally:report(a.out)
    save(a.out/'evidence-sha256.json',{str(p.relative_to(a.out)):sha(p) for p in sorted(a.out.rglob('*')) if p.is_file()})


if __name__=='__main__':
    p=cost.parser()
    for name in ('default-bundle','quiet-bundle','default-calibration','quiet-calibration'):p.add_argument('--'+name,type=Path)
    a=p.parse_args()
    if a.stage=='report':report(a.out.resolve())
    elif a.stage=='run':
        if not all((a.acceptance,a.default_bundle,a.quiet_bundle,a.default_calibration,a.quiet_calibration,a.tf_calibration)):p.error('Current acceptance, both bundles and all three calibrations required')
        run(a)
    else:p.error('Use run_sockshop_cost.py offline for child processing')
