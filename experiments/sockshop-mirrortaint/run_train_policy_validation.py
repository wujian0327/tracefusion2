#!/usr/bin/env python3
"""Fresh frozen Train Ticket inputs, original three-JVM path, same core/policies.

This checks transfer and record counts on the already admitted station-ID path;
it does not pretend to implement the harder multi-source travel-price query.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import random
import secrets
from run_planned_service import ROOT,HERE,load,save,sha
import run_distributed_paths as capture
from evaluate_distributed_paths import trainticket
from compare_w3c_paths import canonical


def run(out,build,seed):
    out.mkdir(parents=True,exist_ok=False);rng=random.Random(seed)
    frozen_sources={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),HERE/'infer_distributed_fields.py',HERE/'infer_planned_service.py',HERE/'PlannedServiceAgent.java']}
    source=out/'new-frozen-inputs';source.mkdir()
    # Draw new input values only after the caller has built/frozen all rules.
    cases={'sockshop':[]}
    stations=[{'id':'ID-'+str(rng.getrandbits(48)),'name':'NAME-'+str(rng.getrandbits(48)),'stayTime':rng.randrange(1,50)} for i in range(8)]
    stations[0]['id']=stations[0]['name']
    cases['stations']=stations
    cases['trainticket']=[{'case':'station-'+str(i),'name':s['name'],'expected_id':s['id']} for i,s in enumerate(stations)]
    cases['trainticket'] += [{'case':'repeat-'+str(i),'name':stations[0]['name'],'expected_id':stations[0]['id']} for i in range(4)]
    cases['trainticket'] += [{'case':'new-'+str(i),'name':stations[j]['name'],'expected_id':stations[j]['id']} for i in range(10) for j in [rng.randrange(8)]]
    cases['trainticket'] += [{'case':'parallel-'+str(i),'name':stations[0]['name'],'expected_id':stations[0]['id']} for i in range(8)]
    cases['trainticket'] += [{'case':'missing','name':'MISSING-'+str(rng.getrandbits(48)),'expected_id':None}]
    save(source/'cases.json',cases);save(out/'freeze.json',{'build_sha256':sha(build/'build.json'),'sources':frozen_sources,'input_sha256':sha(source/'cases.json'),'seed':seed,'new_inputs_after_rule_freeze':True,'independent_third_party_benchmark':False})
    reports={};answers={};original=capture.observed
    for policy in ('full','selective'):
        if any(sha(ROOT/p)!=h for p,h in frozen_sources.items()):raise ValueError('Frozen code changed')
        trial=out/policy;capture.freeze(trial,build,seed,source)
        def observed(spec,role,brole,dest,b):
            original(spec,role,brole,dest,b)
            cfg=spec['services'][role]
            cfg['environment']['JAVA_OPTS']=cfg['environment']['JAVA_OPTS'].replace('-Dservice.mode=selective','-Dservice.mode='+policy)
        capture.observed=observed
        try:capture.capture_train(trial,build)
        finally:capture.observed=original
        result=trainticket(trial,build);answers[policy]=canonical(result['queries']);totals={}
        for role in ('station','basic','ticketinfo'):
            path=trial/'trainticket'/role/'events.jsonl';rows=[json.loads(l) for l in path.read_text().splitlines()]
            if rows[0]['mode']!=policy or any(r['kind']=='problem' for r in rows):raise ValueError('Capture policy/error')
            totals[role]={'events':len(rows),'bytes':path.stat().st_size,'by_kind':dict(Counter(r['kind'] for r in rows))}
        if result['summary']['exact']!=31 or result['summary']['fp'] or result['summary']['fn']:raise ValueError('Train Ticket provenance regression')
        reports[policy]={'summary':result['summary'],'capture':totals}
        save(out/'progress.json',reports)
    if answers['full']!=answers['selective']:raise ValueError('Logical answers differ')
    for r in reports.values():r['total_events']=sum(v['events'] for v in r['capture'].values());r['total_bytes']=sum(v['bytes'] for v in r['capture'].values())
    save(out/'comparison.json',{'all_passed':True,'results':reports,'same_logical_answers':True,'multi_source_travel_price_supported':False,
        'scope':'Original Station.id -> Response.data -> Basic -> TicketInfo; new frozen values and real null branch. Two policy deployments, record-count validation only, no formal performance claim.'})
    lines=['# Train Ticket 新冻结输入的策略迁移验证','',
       '沿用原版Station→Basic→TicketInfo路径，同一自动计划、采集器和还原核心。构建/规则冻结后生成新站点值，包含同值异字段、缺失站点常量分支、8路并发。不是独立第三方盲测。','',
       '| 策略 | exact | TP/FP/FN | 事件数 | 字节数 |','| --- | --- | --- | ---: | ---: |']
    for mode,r in reports.items():
        s=r['summary'];lines.append(f"| {mode} | {s['exact']}/{s['queries']} | {s['tp']}/{s['fp']}/{s['fn']} | {r['total_events']} | {r['total_bytes']} |")
    lines+=['','仅两次策略部署验证记录量，不是五轮性能实验。未新增业务专用推断规则；只修改部署观测策略和测试输入。',
       '多来源价格候选queryForTravel包含Route列表索引、Integer解包、距离差、双精度乘法、StringBuilder转换、HashMap写入及异常回退。当前核心不能完整重建此链；没有将该候选报成已完成。','']
    (out/'results.md').write_text('\n'.join(lines));print(json.dumps(reports,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);p.add_argument('--build',type=Path,required=True);p.add_argument('--seed',type=int,default=151045)
    a=p.parse_args();run(a.out.resolve(),a.build.resolve(),a.seed)
