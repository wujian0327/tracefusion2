"""Small durable reports sourced from immutable first/cost audit outputs."""
import argparse
from collections import Counter
from pathlib import Path
import statistics
from run_planned_service import HERE,load,save,sha
from run_target_closure_cost import FINAL


def external(audit):
    s=load(audit/'summary.json');lines=['# RuoYi／TeaStore：冻结后首次复用','',
      '本轮固定算法 `'+s['candidate']+'`，新入口首次规划及运行后没有修改核心、Agent 或公共契约使其通过。只评价封存的两个应用、各六个查询族；原 40 API 及其未完成任务继续保留，不合成全 API 正确率。','',
      'RuoYi 使用[官方 springboot2 固定提交](https://github.com/yangzongzhuan/RuoYi-Cloud/tree/86527f4da8448a11630ea8dcd03a585cdd6565c6)，没有使用 master；TeaStore 使用[官方固定提交](https://github.com/DescartesResearch/TeaStore/tree/34b37f7e7be433ce72d5f9455e66922a13116749)，原版 Java 11／Tomcat 10 部署。实际原始 JAR／WAR、依赖、JDK及镜像 digest 保存在本批清单。源码和环境已审阅，不称第三方盲测。','',
      '六查询族／应用的选择及来源规则先封存，包含非空正来源、重复值、集合选择及副作用。v1／v2 在核心修改前保存；SysConfig 声明类坐标的 v3 修正发生在核心开发后、首次工具规划前，原协议完整保留。这不是完整坐标均事前注册的盲测。输入未按工具成功更换。','',
      '| 查询 | 原版所选目标 | TF full | TF selective | 固定 MT B2.2 |','| --- | ---: | --- | --- | --- |']
    def states(v):
        return '；'.join(k+' '+str(n)for k,n in sorted(v['states'].items()))or(v['first_state']+'；所选叶未生成')
    for r in s['APIs']:
        lines.append('| '+r['query']+' | '+str(r['selected_original_targets'])+' | '+states(r['tools']['full'])+' | '+states(r['tools']['selective'])+' | '+states(r['tools']['mirrortaint'])+' |')
    lines+=['','拒绝、业务变化、证据无效和真值不足均保留在原版共同所选目标的分母。目标没有绑定或实例事实不足时，不以图、标签或同值匹配生成真值；不填完整关系 FP／FN 为零。导出成功也不直接计作来源正确。','',
       '各工具业务比较、目标绑定、来源调用完整配对和 oracle 充分性在逐实例表中分别保存。TeaStore 原版成功不能证明工具适用；独立 Java 11 控制中，TF 保持业务输出但运行时核验拒绝，固定 MT 原生控制启动成功也不能证明其完整 Jakarta／JPA／JAX-RS 接入。','',
       '| 查询 | 其他实际 null／handler 义务 | TF 首道条件／阻断 | MT 首道条件／阻断 |','| --- | ---: | --- | --- |']
    for r in s['APIs']:
        tf=r['tools']['full'];mt=r['tools']['mirrortaint']
        lines.append('| '+r['query']+' | '+str(len(r['additional_output_obligations']))+' | '+str(tf['failure']or tf['first_state']).replace('|','／').replace('\n',' ')+' | '+str(mt['failure']or mt['first_state']).replace('|','／').replace('\n',' ')+' |')
    lines+=['','原版实际 null 祖先字段、空容器及异常 handler 输出另外列义务；它们不因所选成员叶缺失而计成功或整 API N/A。所选返回叶不是整个 HTTP API、更不是保存／消息 sink 的完整范围。','',
       '需要新增通信绑定、运行时／库适配、动态返回接口或完整复制／生成事实时，只记录迁移需求。本轮不开发 Gson、动态 Principal、新 sink，也不扩大 TeaStore 框架适配。没有回答的一方不能计为性能获胜。','',
       '工件：`artifacts/target-closure-revision-20261103/external-first-01/`；独立评分：`'+str(audit)+'`。原版环境失败、Java 11 探针的首次类路径失败及修正、全部首次工具日志均保留。正式输入、版本、配置、实际字段／调用坐标及逐实例缺口见 JSON／CSV。']
    (HERE/'FROZEN-EXTERNAL-FIRST-20261103.md').write_text('\n'.join(lines)+'\n')
    save(HERE/'target-external-first-results-20261103.json',s)


def development(home,cost):
    base=(home/'development-cost-description-02/report.md').read_text();lines=[base,'\n## 最终候选和能力保持\n']
    gate=load(FINAL/'capability-compatibility-receipt.json');controls=load(home/'final-guard-controls-01/results.json')
    lines+=['算法冻结 `'+gate['final_candidate']+'`。新增值投影和更强体内省略资格没有新增公共框架契约。原完整部署先在 candidate01 完成；最终 Python 修订核对 Agent class 和实际计划，仅四个转换查询的两模式重新采集，其余一致捕获在新目录正常复算，不称又一批新 Agent 部署。','',
       '| 集合，每模式 | 保持结果 | 边界 |','| --- | --- | --- |',
       '| Mall | 98/103，MT 正确 88 项全部保持 | 5 项仍 unknown／真值不足 |',
       '| ZLT | 15/15 正来源 | 两个已暴露入口的开发回归 |',
       '| Account | 40/40 | 4 正来源、36 已知空来源 |',
       '| 原 62 查询 | 428/431 | 原 3 unknown 保持 |',
       '| 原 29 字段 | 232/244 | 原 12 真值不足 unknown 保持 |',
       '| 原 15 写入口 | 96/96 | 原边界和来源签名保持 |','']
    known=sum(v['modes']['full']['known']for v in controls['entries'].values());total=sum(len(v['modes']['full']['answers'])for v in controls['entries'].values())
    checks=sum(len(v['guards'])for v in controls['entries'].values())
    lines+=['针对性 JVM 控制每模式 '+str(total)+' 个目标，'+str(known)+' 个独立来源／空来源匹配，其余必要不透明效果 unknown；'+str(checks)+' 项派生证据保护通过。正常／异常／finally、构造器同对象发布、Map／lambda 发布及守卫失败前采全均比较无 Agent 业务输出。旧同对象泄露及本轮发现的旧资格失败原捕获永久保留。','',
       'SQL 早回调留下工厂或 handler 的两种严格反例，每模式四个目标均保持 unknown。原局部性、应用调用、可靠性及源坐标保护的结果另存，不将预期 unknown 合并成准确率。','',
       '## 新机制独立消融\n',
       '以下是新的短捕获：同一 Agent、同一计划和既有体内守卫，只关闭运行时值投影。它不是过滤旧日志，不据短窗口判断速度。','',
       '| 开发任务 | selective 完整字节 | 关闭新增值投影字节 | 实际省去标量值 | 实际省去 Map 叶记录 | 答案保持 |',
       '| --- | ---: | ---: | ---: | ---: | --- |']
    from summarize_target_closure_development import describe
    from run_planned_service import ROOT
    for task in('mall','zlt-client','zlt-user'):
        a=describe(cost/('cal-'+task+'-selective/capture/events.jsonl'))
        b=describe(cost/('cal-'+task+'-selective-without-value-projection/capture/events.jsonl'))
        sa=load(cost/('cal-'+task+'-selective/offline-single-pass/summary.json'));sb=load(cost/('cal-'+task+'-selective-without-value-projection/offline-single-pass/summary.json'))
        assert sa['correct']==sa['targets']==sb['correct']==sb['targets']
        counter=a['snapshot_omissions_by_kind']
        lines.append('| '+task+' | '+str(a['complete_bytes'])+' | '+str(b['complete_bytes'])+' | '+str(counter['scalar_fields'])+' | '+str(counter['container_values'])+' | '+str(sa['correct'])+'/'+str(sa['targets'])+' |')
    lines+=['','Scalar 计数是实际取值前省略；Map 计数是未构建的叶记录，引用遍历与已有值读取继续执行。正常离线构建的节点及边列表数也保留在各新进程 summary；没有为计数重复还原一次图。完整 full/selective 收益仍混合既有机制，不能全部算作本轮新增投影。','',
       '本轮没有完成任意 Java 方法体最小切片。解释字段及有限转换仍保守扩张；不适用时采全。详见[算法与伪代码](TARGET-OBSERVATION-ALGORITHM-20261103.md)。']
    (HERE/'TARGET-OBSERVATION-DEVELOPMENT-20261103.md').write_text('\n'.join(lines)+'\n')


def costs(audit):
    s=load(audit/'summary.json');lines=['# 同版本共同任务成本：目标相关观测','',
      '算法冻结 `'+s['candidate']+'`，能力参照 `7e4ad0b`。四个查询任务和联合判据均在正式结果前固定；不按请求数投票，不更换失败或没有优势的任务。以下是新的在线捕获及同版本正常离线单次流程，不覆盖旧成本表。','',
      '**预设内部判据通过 '+str(s['task_wins'])+'/4；统一内核子集通过 '+str(s['unified_task_wins'])+'/3。** 这只对应本批任务，不能推出多数应用优于 MT。Orders 是既有专用路径，另外三项是统一内核。新应用完整候选的能力覆盖另见首次复用报告。','',
      '判据要求完整批次协议字节和正常离线进程 CPU 同时下降，且业务 CPU／p95 配对中位比值不超过 1.05、每轮不超过 1.10。五轮不是请求级独立重复，不声称统计显著性；2 请求／秒完成率不代表最大吞吐。','',
      '每任务比较原版、TF full、selective、固定 MT；同 JAR、JDK、资源限制和原输入。五轮独立部署、轮内随机配置顺序；预热 30 秒、测量 60 秒、2 请求／秒、并发上限 2。正确性包含预热，在线指标排除预热。正式在线实验顺序执行，原有非实验容器未操作，不宣称独占物理机。','']
    labels=[('p50 ms','p50_ms',1),('p95 ms','p95_ms',1),('p99 ms','p99_ms',1),('业务 CPU，单核%','business_CPU',1),
      ('业务平均 RSS MiB','business_RSS_MiB',1),('业务采样峰值 RSS MiB','business_peak_RSS_MiB',1),
      ('整部署 CPU，单核%','deployment_CPU',1),('整批协议事件','batch_events',1),('整批协议 MiB','batch_bytes',2**20),
      ('可归属测量事件','measure_events',1),('可归属测量 MiB','measure_bytes',2**20),('未归属／共享 MiB','shared_unattributed_bytes',2**20),
      ('全部 capture 文件 MiB','all_capture_file_bytes',2**20),('各自离线核心墙时 s','offline_core_s',1),('各自离线核心 CPU s','offline_core_CPU_s',1),
      ('正常离线总墙时 s','offline_wall_s',1),('正常离线进程 CPU s','offline_CPU_s',1),('fresh-exec VmHWM MiB','offline_VmHWM_MiB',1)]
    for task,arms in s['absolute_medians'].items():
        lines+=['## '+task,'','| 配置 | 含预热请求 | 独立实例正确／实际目标 |','| --- | ---: | ---: |']
        for mode in('original','full','selective','mirrortaint'):
            rows=[r for r in s['formal_rows']if r['task']==task and r['mode']==mode and r['completed']]
            lines.append('| '+mode+' | '+str(sum(r['requests_including_warmup']for r in rows))+' | '+('N/A，不运行还原'if mode=='original'else str(sum(r['correct']for r in rows))+'/'+str(sum(r['targets']for r in rows)))+' |')
        lines+=['','| 五轮中位数 | original | full | selective | MT |','| --- | ---: | ---: | ---: | ---: |']
        for label,key,scale in labels:
            lines.append('| '+label+' | '+' | '.join(format(arms[m][key]/scale,'.3f')if key in arms[m]else'N/A'for m in('original','full','selective','mirrortaint'))+' |')
        lines+=['','| 配对 | 指标 | 中位变化 | 五轮比值范围 |','| --- | --- | ---: | --- |']
        for compare,metrics in s['paired'][task].items():
            if not metrics['complete']:lines.append('| '+compare+' | 未完成，保留失败 | N/A | N/A |');continue
            for key in('batch_bytes','offline_core_CPU_s','offline_CPU_s','offline_wall_s','offline_VmHWM_MiB','business_CPU','p95_ms'):
                if key not in metrics['metrics']:continue
                v=metrics['metrics'][key];lines.append('| '+compare+' | '+key+' | '+format((v['median_ratio']-1)*100,'+.2f')+'% | '+format(v['min_ratio'],'.4f')+'–'+format(v['max_ratio'],'.4f')+' |')
    planning=load(audit.parent/'static-planning/summary.json')
    lines+=['','## 静态规划','', '| 任务，五次 fresh-exec 中位数 | 进程墙时 s | 进程 CPU s | 进程内规划 s | 当前 exec VmHWM MiB |',
            '| --- | ---: | ---: | ---: | ---: |']
    for task in s['absolute_medians']:
        rows=[r for r in planning['rows']if r['task']==task];assert len(rows)==5
        lines.append('| '+task+' | '+' | '.join(format(statistics.median(r[k]for r in rows)/scale,'.4f')for k,scale in(
            ('process_wall_seconds',1),('process_cpu_seconds',1),('wall_seconds',1),('VmHWM_KiB',1024)))+' |')
    lines+=['','## 口径和限制','',
       'full/selective 共享工程开关、索引、协议编码和所有必要证书／来源／绑定／完整性核验。新增值投影开／关是独立短消融；局部性证书关闭是精度消融，不能拿丢失答案的配置当同答案便宜参照。没有压缩协议或少导出诊断来冒充目标剪枝。','',
       '事件与字节只按实际 Frame、调用、消息及明确父关系归属，不凭 trace-id、值或可见时间窗猜配。未配对／共享记录保留；可归属量不是全部稳态写入。协议 JSON 与全部 capture 文件分列，后者还包含 MT 诊断和 class dump，均不是最大磁盘 I/O。','',
       '离线核心：TF 为必要核验、依赖还原及目标查询；MT 为相应原生标签解码。它们不是相同操作。完整正常进程 CPU、墙时及当前 exec VmHWM 同时报告；独立事实索引／评分、解码／核验、导出阶段在每轮 JSON 中分别保存，不混称核心。计数复用同一次图构建，没有追加完整证书审计或第二次还原。','',
       '静态规划每任务五次 fresh-exec、固定逻辑 CPU。计时含模型 JSON 载入及实际规划；排除原 JAR 提取、初次依赖清单／JDK探针、Agent编译及服务启动，不能叫完整冷启动建模成本。OS页缓存未清空。','',
       '本轮只有单目标接口，未将多次单字段部署相加称多目标实验。MT 即使导出多个字段，每部署也只评分同一固定任务；其他导出及必要适配成本仍计入。未回答的新应用任务不参加性能排名，其失败由能力表完整保留。','',
       '相对原版和相对 MT 的在线开销、绝对 CPU 与延迟均如表；收益范围跨 1 时不能称稳定改善。不能由专用 Orders 的局部收益概括统一内核，不能将共同工程或独立评分提速算成选择性贡献。','',
       '全部逐轮原始值、源坐标／答案、环境与镜像、静态计划、当前 exec 内存、失败及校准见 `'+str(audit.parent)+'`。原始与派生结果分目录；算法、驱动、评分和报告分别锁定哈希。未 push。']
    (HERE/'TARGET-OBSERVATION-COMMON-COST-20261103.md').write_text('\n'.join(lines)+'\n')
    save(HERE/'target-observation-cost-results-20261103.json',{k:v for k,v in s.items()if k!='formal_rows'})
    (HERE/'target-observation-cost-rounds-20261103.csv').write_bytes((audit/'rounds.csv').read_bytes())


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['external','development','cost']);p.add_argument('--audit',type=Path);p.add_argument('--home',type=Path);p.add_argument('--cost',type=Path);a=p.parse_args()
    if a.stage=='external':external(a.audit.resolve())
    elif a.stage=='cost':costs(a.audit.resolve())
    else:development(a.home.resolve(),a.cost.resolve())
