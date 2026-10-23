#!/usr/bin/env python3
"""Audit fresh25 deployments, paired arms and exact closed-cohort byte counts."""
import argparse,copy,csv,json,statistics
from pathlib import Path
from collections import Counter
from run_planned_service import ROOT,HERE,load,save,sha
from run_transport_cart_cost import check,ARMS
from audit_lifecycle_cost import values
from audit_cost_request_records import cohort
from audit_jackson_isolation import mapper_hash
from audit_application_call_revision import class_hashes
from run_sockshop_cost import Sampler,percentiles


def audit(root):
    c=check(root);assert load(root/'run-status.json')['status']=='passed';memory=load(root/'offline-memory-audit.json');assert memory['all_passed']and len(memory['measurements'])==20
    assert all(sha(Path(p))==h for p,h in memory['guarded_original_sha256'].items())
    planning=load(root/'static-planning/results.json');assert planning['all_passed']and len(planning['measurements'])==5
    assert all(v['plans_equal_deployed']and v['affinity']==[planning['cpu']]for v in planning['measurements'])
    planning_summary={k:statistics.median(v[k]for v in planning['measurements'])for k in ('wall_seconds','subprocess_wall_seconds','cpu_seconds','process_tree_sampled_peak_rss_bytes')}
    planning_summary['plan_analysis_seconds']=statistics.median(sum(p['plan_analysis_seconds']for p in v['phases'].values())for v in planning['measurements'])
    records={};populations={};rows=[];projects=set();scope_checks=[];phases={}
    for job in c['order']:
        name,arm,mode=job['name'],job['arm'],job['mode'];d=root/'deployments'/name;cap=d/'capture';build=root/'builds'/arm;m=load(d/'metrics.json');assert m['mode']==mode and m['status']=='passed';clean=load(d/'cleanup.json');assert clean['returncode']==0 and clean['project']not in projects;projects.add(clean['project'])
        warm=load(d/'warmup.json');steady=load(d/'steady.json');assert len(warm['requests'])==60 and len(steady['requests'])==120 and all(r['business_passed']for r in warm['requests']+steady['requests']);assert max(r['online_end_ns']for r in warm['requests'])<=steady['start_ns']
        assert m['online_latency_ms']==percentiles([(r['online_end_ns']-r['online_start_ns'])/1e6 for r in steady['requests']]);samples=[json.loads(v)for v in (d/'resources.jsonl').read_text().splitlines()];sampler=Sampler({r:None for r in samples[0]},2,d/'unused-audit-sampler.jsonl',observed_roles=['carts']);sampler.rows=samples;assert sampler.summary(steady['start_ns'],steady['scheduled_end_ns'])==m['resources']
        spec=load(cap/'compose.json');opts=spec['services']['carts']['environment']['JAVA_OPTS'];assert opts==c['jvm']+(''if mode=='original'else ' -javaagent:/tf2/observer.jar -Dservice.plan=/tf2/plan.json -Dservice.events=/tf2/capture/events.jsonl -Dservice.mode='+mode)
        assert spec['services']['carts']['cpus']==spec['services']['carts-db']['cpus']==1
        assert spec['services']['carts']['mem_limit']=='768m'and spec['services']['carts-db']['mem_limit']=='384m'
        pop=None;m=copy.deepcopy(m)
        if mode!='original':
            data=load(d/'field-results.json');s=data['summary'];assert s['queries']==s['exact']==270 and s['tp']==270 and s['fp']==s['fn']==s['unknown']==0;assert m['offline']['populations']['steady']['exact']==180 and m['offline']['populations']['warmup']['exact']==90
            pop=s;phases.setdefault(arm,[]).append(load(d/'offline.json')['phases']);events=cap/'carts/events.jsonl';raw=[json.loads(v)for v in events.read_text().splitlines()];assert not any(v['kind']=='problem'for v in raw);proof=[v for v in raw if v['kind']=='jackson-isolation'];assert proof and all(v['business_class_sha256']==mapper_hash(build/'carts/original.jar')[1]for v in proof)
            assert raw[0]['plan_sha256']==sha(build/'carts/plan.json');plan=load(build/'carts/plan.json');assert plan['source_evidence']is True;policy=plan['transport_evidence_policy'];assert policy['version']==2 and policy['request_proofs_outbound_only']==ARMS[arm][1]and policy['project_bound_response_fields']==ARMS[arm][2]
            measured={v['message']:v for v in steady['requests']};writes=[v for v in raw if v['kind']=='http-json'and v['phase']=='write'and v['direction']=='response'and v['message']in measured];assert len(writes)==120
            for v in writes:
                assert ('request_serialization'in v)==(arm=='full_legacy')
                response=measured[v['message']]['response'];expected={f'/{i}/itemId'for i in range(len(response))}if arm=='selective'else {f'/{i}/{k}'for i,item in enumerate(response)for k in item}
                assert {f['path']for f in v['fields']}==expected,('Incorrect field persistence scope',name)
            classes=class_hashes(build/'distributed-observer.jar');assert all(v['agent_class_sha256']==classes['tracefusion/internal/jackson/databind/ObjectMapper.class']for v in proof)
            co=cohort({'carts':events},{v['message']for v in steady['requests']});save(d/'measured-request-records.json',co);m['file_visible_capture']=m['steady_capture'];m['steady_capture']=co['request_records'];m['offline']['replay_vmhwm_bytes']=memory['measurements'][name]['vmhwm_bytes'];scope_checks.append({'trial':name,'arm':arm,'events_sha256':sha(events),'mapper_hash':proof[0]['business_class_sha256']})
        v=values(m);records.setdefault(arm,{})[name[:8]]=v;populations.setdefault(arm,[]).append(pop);rows.append({'arm':arm,'trial':name,'mode':mode,**v})
    assert len(projects)==25
    summaries={arm:{k:{'median':statistics.median(v[k]for v in rs.values()),'min':min(v[k]for v in rs.values()),'max':max(v[k]for v in rs.values())}for k in next(iter(rs.values()))}for arm,rs in records.items()};paired={}
    for arm,reference in [('full','full_legacy'),('selective_base','full'),('selective','selective_base'),('selective','full'),('selective','original')]:
        p={}
        for k in summaries[arm].keys()&summaries[reference].keys():
            if any(v[k]==0 for v in records[reference].values()):continue
            ratios=[records[arm][i][k]/records[reference][i][k]for i in sorted(records[arm])];p[k]={'ratios':ratios,'median':statistics.median(ratios),'min':min(ratios),'max':max(ratios)}
        paired[arm+'/'+reference]=p
    phase_summary={arm:{k:statistics.median(v[k]for v in values)for k in values[0]}for arm,values in phases.items()}
    result={'all_passed':True,'algorithm_commit':c['algorithm_commit'],'independent_deployments':25,'summary':summaries,'paired':paired,'populations':populations,'trials':records,'scope_checks':scope_checks,'planning_medians':planning_summary,'offline_phase_medians':phase_summary,'auditor_sha256':sha(Path(__file__)),'original_metrics_unchanged':True,'raw_HTTP_audit_included':True,'format_compression':False,'instruction_or_call_site_slicing':False}
    save(root/'cost-audit.json',result);fields=list(dict.fromkeys(k for r in rows for k in r))
    with (root/'deployments.csv').open('w',newline='')as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
    labels={'original':'原版','full_legacy':'full保留旧证明','full':'清理后full','selective_base':'清理后selective，不投影','selective':'清理后selective＋投影'}
    metrics=[('p50_ms','在线p50，ms',1),('p95_ms','在线p95，ms',1),('p99_ms','在线p99，ms',1),('throughput_rps','完成吞吐，rps',1),('error_rate','错误率',1),('online_cpu_percent','业务JVM CPU，单核%',1),('online_rss_mean_bytes','业务平均RSS，MiB',2**20),('online_rss_peak_bytes','业务采样峰值RSS，MiB',2**20),('deployment_cpu_percent','整部署CPU，单核%',1),('deployment_rss_mean_bytes','整部署平均RSS，MiB',2**20),('deployment_rss_peak_bytes','整部署采样峰值RSS，MiB',2**20),('capture_events','稳态事件',1),('capture_bytes','稳态原始字节，MiB',2**20),('whole_capture_bytes','整批原始字节，MiB',2**20),('console_bytes','整部署控制台，MiB',2**20),('offline_core_seconds','整批离线核心，秒',1),('offline_child_wall_seconds','离线子进程墙时，秒',1),('offline_child_cpu_seconds','离线子进程CPU，秒',1),('offline_child_peak_rss_bytes','同批复算VmHWM，MiB',2**20),('answer_wait_p50_seconds','完成至批次答案p50，秒',1),('answer_wait_p95_seconds','完成至批次答案p95，秒',1)]
    lines=['# 传输观测收缩：Cart五轮独立成本消融','',f"算法冻结 `{c['algorithm_commit']}`。五配置各五轮，25次独立部署，随机顺序；全部使用本批新数据。每轮预热30秒、测量60秒、2请求/秒、并发2，JVM32/256MiB、GC1/CI2，业务1CPU/768MiB，Mongo1CPU/384MiB。原始HTTP审计开关保留。",'','full与selective共同取消绑定服务端响应上不被还原器消费的出站请求证明，必要出站请求证明保持。full_legacy仅作旧工程审计参照，公共清理收益不归为查询选择性贡献。selective_base与selective仅相差目标响应字段持久化投影；完整前后快照仍保留，临时字段采集没有减少。来源、调用、分支、构造、写入、异常和目标序列化检查均保留，没有格式压缩或通用指令/调用切片。','','每个来源配置900次请求（300预热、600性能测量），1350/1350目标来源正确，TP1350、FP/FN/unknown0。原版无来源输出，相应能力/离线成本N/A。稳态字节使用关闭后的完整记录按实际消息/Frame归属计算，文件可见窗口另存。','','| 指标（五轮中位数） | '+' | '.join(labels[a]for a in ARMS)+' |','| --- | '+' | '.join('---:'for _ in ARMS)+' |']
    lines.insert(4,'full_legacy同样使用当前冻结代码，仅关闭公共清理和字段投影；它不是旧二进制版本。本表没有使用旧版性能数字。')
    for k,label,scale in metrics:lines.append('| '+label+' | '+' | '.join('N/A'if k not in summaries[a]else f"{summaries[a][k]['median']/scale:.3f}"for a in ARMS)+' |')
    lines+=['','| 顺序消融配对变化 | 公共清理 full/旧full | 读取位点 selective_base/full | 输出投影 selective/selective_base | 严格selective/full | 严格比较逐轮范围 |','| --- | ---: | ---: | ---: | ---: | --- |']
    for k,label,_ in metrics:
        if k not in paired['selective/full']:continue
        p=paired['selective/full'][k]
        comparisons=('full/full_legacy','selective_base/full','selective/selective_base','selective/full')
        lines.append('| '+label+' | '+' | '.join(f"{(paired[a][k]['median']-1)*100:+.2f}%"if k in paired[a]else 'N/A'for a in comparisons)+f" | {p['min']:.4f}–{p['max']:.4f} |")
    lines+=['','变化是同轮配置比值的中位数，不以汇总中位数相除替代。各消融为条件于参照配置的顺序差异，不相加百分比；公共清理不计入严格选择性收益。不把每次部署内请求当独立重复；5轮仅描述点估计和范围，不宣称显著性、最大吞吐、跨机器普适优势。每轮仅120个测量请求，p99仅描述。','','离线处理整批预热、测量与准备证据；核心、评分和导出分别存阶段时间。VmHWM为在线全部结束后20份相同证据的fresh-exec复算，原始墙时/CPU未改写，保留受fork高水位影响的原ru_maxrss。批次答案等待包含剩余采集窗口及关闭流程，不是流式算法固有延迟。当前没有新MirrorTaint成本校准，外部工具本表N/A；旧76d2050成本不填入本表。']
    lines+=['','## 静态规划与离线阶段','',f"Cart五次新进程规划固定逻辑CPU {planning['cpu']}，生成计划均与实际部署一致。流程墙时中位数{planning_summary['wall_seconds']:.4f}秒，含解释器启动的子进程墙时{planning_summary['subprocess_wall_seconds']:.4f}秒，CPU {planning_summary['cpu_seconds']:.4f}秒，15ms采样的进程树RSS峰值{planning_summary['process_tree_sampled_peak_rss_bytes']/2**20:.2f}MiB，纯计划分析{planning_summary['plan_analysis_seconds']*1000:.3f}ms。OS页缓存未清空，进程树共享页可能重复计数，Agent编译和部署启动排除。",'','| 整批离线阶段（五轮中位数，秒） | '+' | '.join(labels[a]for a in phases)+' |','| --- | '+' | '.join('---:'for _ in phases)+' |']
    for key,label in [('decode_json_seconds','JSON解码'),('validate_graph_reconstruct_seconds','验证/图构建/还原'),('target_origin_restore_seconds','目标来源查询'),('answer_export_seconds','答案导出'),('oracle_score_seconds','独立真值评分'),('evidence_export_seconds','评分证据导出')]:
        lines.append('| '+label+' | '+' | '.join(f"{phase_summary[a][key]:.6f}"for a in phases)+' |')
    lines+=['','完整环境、镜像ID/digest、命令、冻结配置和每轮原始数据保存在本报告所在工件目录；运行入口为run_transport_cart_cost.py，审计入口为audit_transport_cart_cost.py。能力验收门槛及配置/源码哈希在config.json中固定，任何正式部署前均再次核对。逐轮表见deployments.csv，阶段原值见各部署offline.json。']
    (root/'results.md').write_text('\n'.join(lines)+'\n');print('25-deployment Cart audit passed',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);audit(p.parse_args().root.resolve())
