#!/usr/bin/env python3
"""Publish only completed, audited evidence; original reports remain intact."""
import argparse,statistics
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save


def run(root,cost):
    freeze=load(root/'algorithm-freeze.json');a=load(root/'capability-audit/audit.json');b=load(root/'regression29-audit/audit.json');h=load(root/'heldout21-first/audit-first.json');c=load(cost/'cost-audit.json');assert a['all_passed']and b['all_passed']and c['all_passed'];scale=load(cost/'input-scale/results.json');assert scale['all_passed'];controls=load(root/'closure-controls/results.json');assert controls['all_passed']
    snapshot={'algorithm':freeze['commit'],'core_sources':len(freeze['sources']),'original_jars':freeze['original_jars'],'development62':{k:a[k]for k in('queries','modes','parent_431_state_preservation_passed','mapper_configurations_verified')},'exposed29':{k:b[k]for k in('queries','modes','all_passed','changes')},'new21_first':{k:h[k]for k in('candidate_queries','entries','accepted','rejected','modes','runtime_failures')},'new21_failure_layers':load(root/'heldout21-first/failure-layer-audit.json'),'cost':{k:c[k]for k in('algorithm','independent_deployments','shared_alias_index','format_compression','results')},'Orders_oracle_gap_audit':str(root/'orders-oracle-gap-audit/audit.json'),'general_call_or_instruction_slicing_complete':False,'auth_followup':'User chose to retain403 and omit authenticated follow-up in this round. Earlier automatic approval rejected private signing-configuration access; action was not executed.','external_current_cost':'N/A; historical MirrorTaint cost results remain attached to their original version.'}
    snapshot['controls']=controls
    snapshot['cost_audit_revision']=c.get('audit_revision')
    save(HERE/'execution-closure-results-20261023.json',snapshot)
    lines=['# 执行观测闭包：能力保持、首次新入口与成本', '',f"算法冻结 **`{freeze['commit']}`**。本轮完成共享 alias 索引，以及一个保守的构造字段写值收缩试点；**尚未完成通用应用调用／指令切片**。原始结果和旧成本表不改写，全部新在线成本来自本批新部署。",'',
    '## 机制与实际收缩范围','',
    '规划器在统一执行方法上计算操作数依赖闭包，并显式保留调用实现、实参／返回、字段效果、别名、容器和成员、分支／循环及异常义务。每个保留位置附理由。首版对这些义务仍作保守扩张：保留全部已计划应用方法的调用、读取、必要写入和路径证据。', '',
    '第一个可执行收缩只作用于已声明读取来源边界内部、未被解释为应用 Frame 的简单参数赋值构造器。只有字段类型为受支持标量、字段不在目标及全部保守字段义务中、构造器无 handler 且字节码被精确核验，才成为候选。真正运行时还必须同时满足实际查询根在栈内、当前最内层调用是原声明来源调用、selective 模式且策略启用。引用字段和任何必要字段不省略。', '',
    'Agent 在实际 PUTFIELD 成功后仍递增对象／字段写入版本并执行原有只读修改保护；仅省去该无关字段值的装箱、取值事件构建和持久化。来源调用完成时附省略站点计数，离线核验其闭合、作用域、版本和候选证明。返回快照仍不创建来源。异常完成也保留证据，full 使用同一格式和核验但不省略。', '',
    '这不同于此前只投影响应输出：本轮确实减少了运行中的写值观测；同时也不是一般调用可安全删除的证明。全部快照、必要来源和语义核验仍保留，不宣称最小计划或对任意 Java 程序完备。', '',
    '实现入口：[闭包规划](plan_execution_closure.py)、[Agent 作用域与完成事实](ExecutionKernelHooks.java)、[字段写入插桩](PlannedServiceAgent.java)、[离线证书检查](infer_execution_closure.py)。策略由统一路由预先附加，没有逐字段手写传播公式。','',
    '## 同一冻结版本的新部署回归','',
    '| 集合，每种配置分别统计 | 查询族 | 实际目标 | 已知且实例正确 | unknown | 证据无效／错误确定答案 |','| --- | ---: | ---: | ---: | ---: | --- |']
    for label,d,n in [('开发集',a,62),('已启封字段回归',b,29)]:
        for mode in('full','selective'):
            m=d['modes'][mode];states=m['states'];targets=m.get('actual_targets',m.get('targets'));lines.append(f"| {label} {mode} | {n} | {targets} | {states.get('known_correct',0)} | {states.get('unknown',0)} | {states.get('evidence_invalid',0)}／{states.get('known_wrong',0)} |")
    lines+=['','开发集每配置关系TP397／FP0／FN3，FN包含3个unknown阳性目标，不能只报告已知答案的条件匹配率。29字段回归每配置190次请求，其中41次没有目标；12个真值不足目标保留目标级unknown，不据此计算完整关系Recall。','',f"收缩保护：{controls['certificate_faults']}项完成证据扰动与{controls['runtime_scope_guards']}项实际JVM作用域／版本／修改保护检查通过；新内核及旧集合、绑定、调用生命周期等控制回归通过。预期unknown与异常根单列，不合并成准确率。"]
    lines+=['','62查询逐项保持历史MirrorTaint正确368个及旧TF正确213个实例，开发集428/431＝99.30%可回答；已知428/428匹配。29字段回归232/244＝95.08%可回答，已知232/232匹配；其12个unknown仍缺独立完整真值。二者现在都使用本轮新Agent重新部署，但都已用于开发分析，不能再当作未见查询。两集合分别报告，不合成泛化准确率。', '',
    '## 修改前封存的新入口：首次负结果','',
    '在本轮任何核心改动前，按API和原业务响应结构封存21个候选，来自5个未测试服务入口：Station.create/update、Route.createAndModify、Price.createNewPriceConfig/updatePriceConfig。全部纳入，无成功筛选和替换。Sock Shop没有符合本轮纳入标准的剩余新领域响应入口，明确报告候选不足。类和应用此前已被研究者审阅，不是第三方盲测。', '',
    '每个查询六组输入及独立真值投影规则在首次规划前保存；创建路径使用给定ID，不声称验证生成ID分支。原版JAR不变。规划21/21接纳，**接纳并未转化为端到端成功**。', '',
    '| 首次业务结果，每种配置 | 查询族 | 请求 | 实际目标 | 已知／unknown／证据无效 |','| --- | ---: | ---: | ---: | --- |']
    for mode,m in h['modes'].items():lines.append(f"| {mode}：Route／Price | {m['runtime_query_families']} | {m['requests']} | {m['targets']} | {m['states'].get('known_correct',0)}／{m['states'].get('unknown',0)}／{m['states'].get('evidence_invalid',0)} |")
    lines+=['','另6个Station查询族的两配置共12次运行在首个请求被原应用返回403，未进入待测方法；它们是认证准备失败，不能计成业务N/A、TF unknown或来源正确。Route／Price各配置另有10次请求未生成目标。192个实际目标（两配置）有独立入口字段真值，但首轮驱动均记为evidence_invalid；其中一部分实属语义限制，须按下述诊断区分，不能统称证据损坏。可回答率为0，条件来源匹配率及关系准确率N/A，不能引用评分中空样本的FP/FN零值。', '',
    '逐项诊断进一步区分两层：每种配置76个目标因原有保存／任务接入附加的Sock Shop框架契约与新Train Ticket写入口不符，触发Collector problem；其余20个Price.update标量目标在旧bounded-scalar还原器遇到未支持GETFIELD（opcode180）。后20个属于语义／profile路由限制，首轮评分驱动却也记作evidence_invalid，不能把它们解释成采集缺失或矛盾。原始分类保持，另存分层诊断；没有放宽哈希、修复核心后覆盖首次结果。', '',
    '因此，新的未见入口实验没有提供正向来源覆盖证据。它暴露了此前旧入口新字段验证没有覆盖的写入口集成问题；论文应连同规划接纳率一起披露，而非只展示历史成功路径。本次21查询未运行MirrorTaint，其能力列为N/A，不能据此判断这些入口上的基线能力差距。每个查询仍只声明入口、响应目标和原来源边界；本轮首次测试后没有新增库摘要或修改冻结实现来消除失败。', '',
    '## 共享 alias 索引先行校准','',
    '184份图和1350个完整目标答案在原还原器与索引还原器间逐项相同；索引保留完整坐标和全部歧义候选，不取第一个匹配。对原20份成本捕获进行40次新进程配对复算，旧捕获和在线计时不变。', '',
    '同一批捕获的新复算中，单独输出投影的核心收益从未索引时48.81%降为索引后2.80%，后者范围0.9012–1.0025；CPU约1.16%，范围也跨1；VmHWM约减少6.25%。索引后的严格selective/full核心变化为约−8.97%，同时包含既有读取选择与投影。旧正式表49.63%只对应其原实现和计时批次，不能移用于当前还原器。详细结果见[共享索引审计](ALIAS-INDEX-20261023.md)。','',
    '## 新成本：两条路径分别报告','',
    'Cart四配置五轮20次部署，票价三配置五轮15次部署，随机顺序、独立容器和数据卷，全部在线实验顺序执行。预热30秒、测量60秒，2请求/秒、并发2；JVM32/256MiB、GC1/CI2，业务JVM1CPU/768MiB、Mongo1CPU/384MiB。原始HTTP审计开关保留，必要核验全部计入；所有模式共用alias索引。机器为AMD Ryzen 9 7950X、32逻辑CPU的WSL2环境；已有非实验容器未操作，起始容器清单及机器配置保存在environment.json，不宣称独占物理机。', '',
    'Cart的selective_without_closure保留现有读取选择和输出投影，只关闭新增写值省略；与selective的配对差异用于归因本轮新增收缩。没有事件格式压缩。票价沿用原集合计算快速路径，因此不把其收益当作统一内核通用切片证据。每轮约120个性能请求，p99仅作描述，不能据此稳健估计尾部极值。两配置完成2请求/秒只说明完成当前固定负载，不代表最大吞吐能力相同。票价正式负载按预先冻结协议排除未生成目标的missing-train模板，该模板保留在正确性校准中；正式表不覆盖全部业务失败路径。', '']
    metrics=[('p50_ms','p50 ms',1),('p95_ms','p95 ms',1),('p99_ms','p99 ms',1),('throughput_rps','完成请求/秒',1),('error_rate','错误率',1),('online_cpu_percent','业务CPU，单核%',1),('online_rss_mean_bytes','业务平均RSS MiB',2**20),('online_rss_peak_bytes','业务采样峰值RSS MiB',2**20),('capture_events','测量请求事件',1),('capture_bytes','测量请求字节 MiB',2**20),('whole_capture_events','整批事件',1),('whole_capture_bytes','整批字节 MiB',2**20),('offline_core_seconds','整批离线核心 s',1),('offline_child_wall_seconds','离线子进程墙时 s',1),('offline_child_cpu_seconds','离线子进程CPU s',1),('offline_child_peak_rss_bytes','复算VmHWM MiB',2**20),('answer_wait_p50_seconds','完成至批次答案p50 s',1),('answer_wait_p95_seconds','完成至批次答案p95 s',1),('deployment_cpu_percent','整部署CPU，单核%',1),('deployment_rss_mean_bytes','整部署平均RSS MiB',2**20),('deployment_rss_peak_bytes','整部署采样峰值RSS MiB',2**20),('console_bytes','整部署控制台 MiB',2**20)]
    pair_metrics={'p95_ms','online_cpu_percent','capture_events','capture_bytes','offline_core_seconds','offline_child_wall_seconds','offline_child_cpu_seconds','offline_child_peak_rss_bytes'}
    for kind,data in c['results'].items():
        arms=[arm for arm in ('original','full','selective_without_closure','selective') if arm in data['summary']];lines+=['','### '+('Cart读取'if kind=='cart'else'跨服务票价'),'','| 五轮中位数 | '+' | '.join(arms)+' |','| --- | '+' | '.join('---:'for _ in arms)+' |']
        for metric,label,scaleunit in metrics:lines.append('| '+label+' | '+' | '.join('N/A'if metric not in data['summary'][arm]else format(data['summary'][arm][metric]['median']/scaleunit, '.0f' if metric in ('capture_events','whole_capture_events') else '.3f')for arm in arms)+' |')
        lines+=['','| 配对指标 | 比较 | 中位变化 | 逐轮比值范围 |','| --- | --- | ---: | --- |']
        for comparison in ['selective/selective_without_closure','selective/full','selective/original']:
            if comparison not in data['paired']:continue
            for metric,label,_ in metrics:
                if metric not in pair_metrics:continue
                value=data['paired'][comparison].get(metric)
                if value:lines.append(f"| {label} | {comparison} | {(value['median']-1)*100:+.2f}% | {value['min']:.4f}–{value['max']:.4f} |")
        for arm,pops in data['populations'].items():
            queries=sum(p['summary']['queries']for p in pops);exact=sum(p['summary']['exact']for p in pops);tp=sum(p['summary']['tp']for p in pops);lines.append(f"\n{arm}：900请求（300预热、600测量），{exact}/{queries}目标来源完全匹配，关系TP{tp}，FP/FN/unknown均为0。")
    lines+=['','配置表为五次部署中位数，配对变化为同轮比值的中位数，不能由汇总中位数相除替代。5轮配对不是请求级独立重复；范围跨1的CPU／p95不称稳定改善，不宣称显著性或最大吞吐相同。稳态事件和字节由关闭后的完整记录按实际消息／Frame归属核算，文件可见窗口另存。离线处理整批预热、测量及准备证据；核心、解码、评分和导出阶段分别保留。25份来源配置在在线全部结束后用相同捕获fresh-exec复算VmHWM，原始墙时／CPU未覆盖。批次答案等待包含采集窗口和关闭流程，不是固有流式延迟。当前版本MirrorTaint外部成本N/A，旧跨工具成本优势仍只对应其原冻结版本。', '',
    '## 输入规模与规划成本','',
    '资源审计首次失败及修正均保留：原审计器按模型文件顺序累加五个业务JVM的CPU，测量驱动采用固定角色顺序，导致5次部署约1.8e-15的浮点差异。单独的audit_execution_closure_cost_v2.py恢复原驱动顺序后，全部35次资源汇总严格相等，没有加容差或修改原数值；70份原始metrics/resources文件哈希不变。原86个冻结源码及首次失败日志仍保留，修订仅属派生审计。', '',
    '同一itemId查询另测1、4、16个购物车元素，三种来源配置各作短捕获；每配置6次预热和12次测量请求。此组只验证独立来源、实际记录数／字节和输入规模关系，不把短捕获延迟当正式性能结果。下表事件／字节只对应12次测量请求，来源匹配则包含全部18次请求，两个分母明确分开。', '',
    '| 元素数 | 配置 | 测量请求事件 | 测量字节 MiB | 整批目标匹配（含预热） |','| ---: | --- | ---: | ---: | ---: |']
    from audit_cost_request_records import cohort
    for rec in scale['results']:
        d=Path(rec['directory']);messages={r['message']for r in load(d/'steady.json')['requests']};co=cohort({'carts':d/'capture/carts/events.jsonl'},messages)['request_records']['carts'];s=rec['summary'];lines.append(f"| {rec['items']} | {rec['arm']} | {co['events']} | {co['bytes']/2**20:.4f} | {s['exact']}/{s['queries']} |")
    plan=load(cost/'static-planning/results.json');lines+=['','静态规划每条路径5次新进程、固定同一逻辑CPU，计划与部署逐项相同；OS页缓存未清空。Agent编译和部署启动排除，15ms进程树RSS采样可能重复计算共享页。','','| 路径 | 流程墙时 s | CPU s | 进程树RSS峰值 MiB |','| --- | ---: | ---: | ---: |']
    for kind in('cart','price'):
        rs=[v for v in plan['measurements']if v['kind']==kind];lines.append(f"| {kind} | {statistics.median(v['wall_seconds']for v in rs):.4f} | {statistics.median(v['cpu_seconds']for v in rs):.4f} | {statistics.median(v['process_tree_sampled_peak_rss_bytes']for v in rs)/2**20:.2f} |")
    lines+=['','## 剩余边界与工件','',
    'Orders的12个独立真值缺口已逐项审阅：生成ID还缺实际生成调用到实体写入的配对；customerId已有raw self-link及调用身份，但还缺解码时Link.href的来源坐标。本轮没有补出这些缺失原始事实，继续保留unknown与oracle unavailable，不能改判空来源。通用调用／指令收缩和新Train Ticket写入口契约仍待后续处理；Station按用户决定保留403，本轮不做鉴权后复验。', '',
    f'主工件：`{root.relative_to(ROOT)}/`；新成本：`{cost.relative_to(ROOT)}/`。协议、冻结源码／JAR哈希、镜像digest、命令、原始事件、独立真值、预测、逐轮CSV、阶段时间、保护检查及重要节点日志均保留。Git保存代码和小型摘要，完整工件／Docker镜像需单独备份；推送由用户完成。', '',
    'Station鉴权后复验的拟议动作曾被自动审批拒绝，原因是读取应用私有JWT签名配置并生成管理员测试身份的材料使用未明确授权；动作未执行、未绕过。用户随后选择保留403、本轮不做鉴权后复验，其余实验照常完成。']
    (HERE/'EXECUTION-CLOSURE-20261023.md').write_text('\n'.join(lines)+'\n');(cost/'results.md').write_text('\n'.join(lines)+'\n');save(root/'report-complete.json',{'all_audits_passed':True,'new21_failures_reported':True,'Orders_oracle_gaps_not_filled':True,'general_slicing_not_claimed':True,'report':str(HERE/'EXECUTION-CLOSURE-20261023.md')})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',required=True,type=Path);p.add_argument('--cost',required=True,type=Path);a=p.parse_args();run(a.root.resolve(),a.cost.resolve())
