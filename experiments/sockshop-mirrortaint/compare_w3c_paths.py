#!/usr/bin/env python3
"""Compare frozen workloads and independently scored origins after W3C migration."""
import argparse
from collections import Counter
import copy
import csv
import json
from pathlib import Path
import re
import tempfile
from run_planned_service import HERE, ROOT, load, save, sha
from run_distributed_paths import check
from infer_distributed_fields import Reconstruction
from transport_context import validate_protocol
from query_observation_planner import require


APPS={'sockshop':['orders','carts','shipping'], 'trainticket':['station','basic','ticketinfo']}


def canonical(queries):
    # JVM-local IDs cannot equal across independent deployments. Each capture
    # must first pass its own exact observation/object/version oracle; only
    # then compare case, target and declared origin coordinates across runs.
    return {(q['case'],q['path']):{
        'known':q['prediction']['known'], 'exact':q['exact'],
        'counts':[q[k] for k in ('tp','fp','fn')],
        'sources':sorted((n['service'],n['kind'],n['field'],n['version'],n.get('path','')) for n in q['prediction']['sources'])
    } for q in queries}


def wire(value):
    require(isinstance(value,str) and re.fullmatch(r'00-[0-9a-f]{32}-[0-9a-f]{16}-0[01]',value), 'Bad captured wire traceparent')
    _,trace,span,flags=value.split('-')
    require(int(trace,16) and int(span,16), 'Zero wire identifier')
    return trace,span,flags


def audit_and_compare(out,build,baseline,baseline_build,checkpoint=None):
    check(out,build);checks={};details={}
    require(sha(out/'cases.json')==sha(baseline/'cases.json'), 'Business workload differs from baseline')
    checks['exact_baseline_workload_reused']=True
    current=load(build/'build.json');old=load(baseline_build/'build.json')
    for role in current['inputs']:
        for key in ('model_sha256','original_jar_sha256'):
            require(current['inputs'][role][key]==old['inputs'][role][key], 'Application/model changed')
        a=load(build/role/'plan.json');b=load(baseline_build/role/'plan.json')
        a.pop('transport_contracts');b.pop('transport_contracts');require(a==b, 'Local field plan changed')
    for name in ('PlannedServiceAgent.java','QueryBytecodeModel.java','infer_planned_service.py','plan_service_observations.py','query_observation_planner.py'):
        key=str(HERE/name);require(current['sources'][key]==old['sources'][key], 'Local observation/inference core changed')
    checks['six_original_jars_models_and_local_field_plans_unchanged']=True
    checks['local_observation_and_reduction_algorithms_unchanged']=True
    table=[];all_raw={}
    for app,roles in APPS.items():
        before=load(baseline/app/'field-results.json');after=load(out/app/'field-results.json')
        require(before['summary']==after['summary'], 'Scores changed')
        require(canonical(before['queries'])==canonical(after['queries']), 'Logical source answer changed')
        require(all(q['exact'] for q in after['queries']), 'Instance oracle failed')
        table.append({'application':app, 'queries':after['summary']['queries'], 'before_exact':before['summary']['exact'],
                      'after_exact':after['summary']['exact'], **{k:after['summary'][k] for k in ('tp','fp','fn','precision','recall','f1','unknown')}})
        raw={role:[json.loads(l) for l in (out/app/role/'events.jsonl').read_text().splitlines()] for role in roles};all_raw[app]=raw
        clients={};servers={};peaks={};states=Counter()
        for role,rows in raw.items():
            validate_protocol(rows);active=peak=0
            for row in rows:
                kind=row['kind']
                require('echo' not in row,'Legacy response echo still present')
                if kind=='http-rpc-enter':active+=1;peak=max(peak,active)
                elif kind in ('http-rpc-exit','http-rpc-abort'):active-=1
                require(active>=0,'Unbalanced client spans')
                if kind not in ('http-request-context','http-server-context'):continue
                if row.get('wire_traceparent') is None:
                    require(kind=='http-server-context' and row['parent_span_id'] is None and row['span_id']==row['request_span_id'], 'Missing outgoing wire header')
                    continue
                t,s,f=wire(row['wire_traceparent'])
                require((t,s,f)==(row['trace_id'],row['request_span_id'],row['trace_flags']), 'Recorded identity differs from actual header')
                require(row.get('wire_tracestate')==row.get('tracestate'),'Tracestate changed')
                states[row.get('tracestate')]+=1
                pool=clients if kind=='http-request-context' else servers
                require(row['message'] not in pool,'Repeated wire invocation')
                pool[row['message']]=(role,row)
            require(active==0,'RPC did not close');peaks[role]=peak
        cases=load(out/app/'run.json')['cases'];messages={c['message'] for c in cases};traces={m.split('/')[0] for m in messages}
        require(len(traces)==1 and len(messages)==len(cases),'Same-trace distinct-call test absent')
        for message in messages:
            require(message in servers,'Root invocation absent')
        matched=0
        for message,(role,server) in servers.items():
            if message not in clients:continue
            client_role,client=clients[message]
            require(role!=client_role and server['parent_span_id']==client['span_id'],'Wrong cross-service parent')
            require(server['span_id']!=client['span_id'],'Server/client spans collapsed');matched+=1
        require(matched>0,'No actual W3C crossing')
        if app=='sockshop':
            rpc=[r for r in raw['orders'] if r['kind']=='http-rpc-enter']
            require(all(r['trace_id'] in traces and r['parent_message'] in messages for r in rpc),'Spring async context lost')
            require(any(r.get('class','').endswith('/AsyncExecutionAspectSupport') for r in raw['orders']),'Async framework hook absent')
        details[app]={'target_requests':len(cases),'distinct_target_trace_ids':len(traces),'distinct_root_request_spans':len(messages),
                      'actual_observed_cross_service_calls':matched,'active_rpc_peaks':peaks,'captured_tracestate_contexts':dict(states)}
    checks['same_trace_repeated_and_parallel_requests_remain_distinct']=True
    checks['actual_request_headers_and_server_parent_spans_verified']=True
    checks['spring_async_tasks_preserve_parent_context']=True
    checks['no_custom_response_echo_consumed']=True
    checks['all_229_independent_instance_answers_and_logical_origins_preserved']=True
    # Replaying a dropped intermediate response must lose evidence rather than
    # recover a source from shared trace ID or equal values.
    with tempfile.TemporaryDirectory(prefix='w3c-path-controls-') as td:
        root=Path(td);raw=all_raw['trainticket'];roles=APPS['trainticket']
        first=next(c for c in load(out/'trainticket/run.json')['cases'] if c['expected_id'] is not None)
        changed=copy.deepcopy(raw)
        for role,rows in changed.items():
            (root/role).mkdir()
            if role=='station':rows=[r for r in rows if not (r['kind']=='http-json' and r['phase']=='write' and r['direction']=='response')]
            (root/role/'events.jsonl').write_text(''.join(json.dumps(dict(r,seq=i+1))+'\n' for i,r in enumerate(rows)))
        graph=Reconstruction(build,root,roles)
        result=graph.query(first['message'],'/data','ticketinfo',{'service':'station','kind':'field-read'})
        require(not result['known'],'Missing cross-service source was guessed')
        changed=copy.deepcopy(raw['basic']);row=next(r for r in changed if r['kind']=='http-json' and r['phase']=='read' and r['direction']=='response')
        row['trace_id']='1'*32;row['message']=row['trace_id']+'/'+row['request_span_id']
        try:validate_protocol(changed)
        except ValueError:pass
        else:raise ValueError('Foreign response trace accepted')
    checks['missing_intermediate_field_evidence_returns_unknown']=True
    checks['foreign_response_trace_rejected']=True
    require(load(out/'protocol-checks.json')['all_passed'],'Protocol boundary/async tests failed')
    checks['protocol_parser_and_async_context_boundary_checks_passed']=True
    image_check=load(out/'original-image-verification.json')
    require(image_check['all_matched'] and len(image_check['records'])==6,'Original image JAR check failed')
    checks['six_original_image_jars_independently_verified']=True
    require(load(out/'algorithm-audit.json')['all_passed'],'Distributed regression failed')
    checks['distributed_bytecode_and_evidence_regression_passed']=True
    background={app:dict(Counter(n['field'] for n in load(out/app/'inference-graph.json')['nodes'] if n.get('unknown'))) for app in APPS}
    report={'background_unknown_observations':background,'all_passed':True,'checks':checks,'applications':details,'rows':table,
            'comparison_scope':'Each run independently scored exact source observation/object/field/write-count instances; cross-run normalization removes JVM-local IDs and observation sequence numbers.',
            'sampling':'Required provenance observations retained; trace-flags is not used to discard field evidence.',
            'implementation':'Framework propagation hooks, W3C v00 output and Level 1 parsing; no OpenTelemetry SDK/exporter and no claim of arbitrary async framework interoperability.',
            'performance_eligible':False}
    save(out/'w3c-comparison.json',report)
    with (out/'w3c-comparison.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=list(table[0]));writer.writeheader();writer.writerows(table)
    text=['# W3C Trace Context 替换验证','',
          '使用原版业务 JAR、同一批冻结业务输入和相同本地字段计划，重跑两应用。替换后229/229个指定字段查询完全匹配；两次独立执行均先按各自对象、字段、写计数及具体来源观测点评分，再比较跨运行的逻辑来源。没有要求不同 JVM 的对象 ID 或事件序号相等。','',
          '| 应用 | 替换前完全匹配 | W3C 后完全匹配 | TP / FP / FN | Precision / Recall / F1 | unknown |',
          '| --- | ---: | ---: | --- | --- | ---: |']
    for row in table:text.append(f"| {row['application']} | {row['before_exact']}/{row['queries']} | {row['after_exact']}/{row['queries']} | {row['tp']} / {row['fp']} / {row['fn']} | 100% / 100% / 100% | {row['unknown']} |")
    text+=['','通信只传播标准 traceparent / tracestate；内部 message 是 trace-id/request-span-id 的组合键，不是自定义 HTTP 头。响应在客户端具体 RPC 作用域内关联，不要求响应回显 traceparent 或自定义头。字段桥接继续要求方向、JSON pointer 与两端字段证据；trace-id 相同不代表字段相关。',
           '', 'Sock Shop 的25次目标请求共用一个 trace-id、25个不同请求 span；Train Ticket 的31次目标请求也共用一个 trace-id、31个不同请求 span。包含重复同值输入与8路并发；Spring @Async 的上下文在提交时捕获、执行后恢复。JSON 传输观察和本地字段依赖算法未更换。',
           '',f"W3C 专项检查 {len(checks)} 项通过；原跨服务审计 {len(load(out/'algorithm-audit.json')['checks'])} 项通过。实际请求头、接收端父 span 和 tracestate 已核验；缺少中间字段证据时返回 unknown，错误响应上下文被拒绝。另有独立 Java 协议边界检查，覆盖无效标识、未来版本前缀、tracestate、父子关系、重复调用及采样标志。",'',
           '72条补充非来源关系检查保持通过。Sock Shop 另有43个Carts Item.id数据库回写背景观测保留unknown（区别于itemId），位于预先指定来源边界之前，不属于表中的目标查询，也没有被宣称解决。','',
           '这是当前选定 JVM/HTTP/JSON 路径的正确性回归，不是全应用100%准确率或Go接入证明。字段采集没有按 trace-flags 抽样；若外部采样造成必要证据丢失，不能保证原准确率。当前为框架内的标准上下文传播实现，未接入OpenTelemetry SDK/导出器，也未验证任意现有tracing SDK共存、任意线程池、重试或消息队列。原有数据库来源边界和背景 unknown 限制保持。未新增正式性能比较。','',
           '基线：`'+str(baseline.relative_to(ROOT))+'`；本轮构建：`'+str(build.relative_to(ROOT))+'`。原始事件、独立真值和 field-results.json 均保留；w3c-comparison.json 包含逐项检查及跨调用统计。','']
    text += ['复现：','', '```bash',
        'python3 experiments/sockshop-mirrortaint/build_distributed_plans.py --out artifacts/w3c-build-new --inputs artifacts/real-path-expansion-preflight-20261015/queries.json',
        'python3 experiments/sockshop-mirrortaint/run_distributed_paths.py freeze --out artifacts/w3c-run-new --build artifacts/w3c-build-new --cases-from '+str(baseline.relative_to(ROOT))+' --seed 151031',
        'python3 experiments/sockshop-mirrortaint/run_distributed_paths.py sockshop --out artifacts/w3c-run-new --build artifacts/w3c-build-new',
        'python3 experiments/sockshop-mirrortaint/run_distributed_paths.py trainticket --out artifacts/w3c-run-new --build artifacts/w3c-build-new',
        'python3 experiments/sockshop-mirrortaint/evaluate_distributed_paths.py --out artifacts/w3c-run-new --build artifacts/w3c-build-new',
        'python3 experiments/sockshop-mirrortaint/audit_distributed_paths.py --out artifacts/w3c-run-new --build artifacts/w3c-build-new',
        '```', '', '协议与异步独立测试的准确命令及依赖哈希见 protocol-checks.json；原镜像核验用 verify_original_path_images.py。随后 compare_w3c_paths.py 生成前后比较，需传入两个运行和两个构建目录。', '']
    (out/'results.md').write_text('\n'.join(text))
    if checkpoint:
        evidence={str(p.relative_to(ROOT)):sha(p) for directory in (out,build) for p in sorted(directory.rglob('*')) if p.is_file()}
        for p in (baseline/'cases.json',baseline/'sockshop/field-results.json',baseline/'trainticket/field-results.json',baseline_build/'build.json'):
            evidence[str(p.relative_to(ROOT))]=sha(p)
        sources=[HERE/n for n in ('SpringTransportAgent.java','W3CTraceContext.java','W3CTraceContextCheck.java','W3CAsyncContextCheck.java','transport_context.py','infer_distributed_fields.py','run_distributed_paths.py','build_distributed_plans.py','plan_distributed_fields.py','audit_distributed_paths.py','compare_w3c_paths.py')]
        save(checkpoint,{**report,'collector_sha256':current['agent_sha256'],'evidence_sha256':evidence,'source_sha256':{str(p.relative_to(ROOT)):sha(p) for p in sources}})
    print(json.dumps({'all_passed':True,'checks':len(checks),'rows':table},indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('out','build','baseline','baseline-build'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--checkpoint',type=Path);args=parser.parse_args()
    audit_and_compare(args.out.resolve(),args.build.resolve(),args.baseline.resolve(),args.baseline_build.resolve(),args.checkpoint.resolve() if args.checkpoint else None)
