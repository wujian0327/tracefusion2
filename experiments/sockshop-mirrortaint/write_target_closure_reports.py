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
      '六查询族／应用的选择及来源规则先封存，包含非空正来源、重复值、集合选择及副作用。v1／v2 在核心修改前保存；SysConfig 声明类坐标的 v3 修正发生在核心开发后、首次工具规划前，原协议完整保留。原源码提交先固定，但完整JAR／WAR及依赖清单在核心开发期间完成，02:13 UTC保存构建回执；没有满足“全部构建工件均在首次核心修改前锁定”的严格顺序。这不是完整坐标和工件均事前注册的盲测。输入未按工具成功更换，封存新查询未用于核心调试。','',
      '评分前发现原 SQL 用 `sysdate()` 初始化 create_time，各独立数据库的 createTime 不同。跨 JVM 业务对比仅将这些非查询时间字段规范化，原始完整响应是否相等另存；已关闭部署缺少的自身 DB 时间事实不补造。此澄清发生在捕获后，单独保存。它不参与所选字段的实例来源真值，也不能证明所有未查询时间字段正确。','',
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
       '本批所选目标合计 141。TF 两模式均没有认证来源答案；固定 MT 已独立匹配 90 项，其中 84 个正来源、6 个已知空来源。未完成共同接入的任务不用于完整关系 Recall 或工具排名。','',
       'RuoYi 的 TF 捕获有实际来源记录，但监测退出失败留下 problem／粘性无效标记；仍拒绝整批，不将其说成传播算错。RuoYi config 查询的封存边界是 selectConfigById，而原入口服务实际调用 selectConfig(SysConfig)，固定 MT 没有这次已声明来源事实，因此 5 项未评分。这是首次任务接入缺口，本轮不移动边界补成成功。','',
       'TeaStore 的固定 MT 记录仅有 export-start／closed，native_available 为 false，缺少所选目标与实际来源事实；独立控制可启动没有转化为应用接入成功。生成 ID 的 6 项还缺配对生成器状态：原版顺序执行全部 API，工具逐查询新部署，返回 ID 不同不能直接归因于插桩。继续保留生成事实和真值缺口，不猜空来源。','',
       '第一份派生评分误把容器 nobody 用户文件的读取权限失败归为 evidence_invalid。仅增加读取权限后，全部首次运行文件 SHA256 逐项相同，02／03 在新目录重算；原评分和原始文件保持。03 另将生成状态未配对与已证明的业务变化区分，未重跑业务或修改工具。','',
       '查询族级适用性为：RuoYi 五项 conditional、一项目标接口不支持；TeaStore 六项 TF 运行时必要条件不满足。实际执行10份TF配置和12份MT配置；部署前拒绝没有伪造捕获。规划有条件接纳不等于端到端可回答，不能只报告接纳率。','',
       'RuoYi 六份 MT 运行另核对实际 ObjectMapper 类定义与原业务 JAR 一致；TeaStore 仍缺完整框架接入，不能把控制程序启动等同于原生传播能力校准。逐实例表另保存 [CSV](target-external-first-instances-20261103.csv)。','',
       '需要新增通信绑定、运行时／库适配、动态返回接口或完整复制／生成事实时，只记录迁移需求。本轮不开发 Gson、动态 Principal、新 sink，也不扩大 TeaStore 框架适配。没有回答的一方不能计为性能获胜。','',
       '工件：`artifacts/target-closure-revision-20261103/external-first-01/`；独立评分：`'+str(audit)+'`。原版环境失败、Java 11 探针的首次类路径失败及修正、全部首次工具日志均保留。正式输入、版本、配置、实际字段／调用坐标及逐实例缺口见 JSON／CSV。']
    (HERE/'FROZEN-EXTERNAL-FIRST-20261103.md').write_text('\n'.join(lines)+'\n')
    save(HERE/'target-external-first-results-20261103.json',s)
    (HERE/'target-external-first-instances-20261103.csv').write_bytes((audit/'instances.csv').read_bytes())


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
       '| 开发任务 | selective 完整字节 | 关闭新增值投影字节 | 实际省去标量值 | 实际省去 Map 叶记录 | 图节点：开／关 | 边列表：开／关 | 答案保持 |',
       '| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |']
    from summarize_target_closure_development import describe
    from run_planned_service import ROOT
    for task in('mall','zlt-client','zlt-user'):
        a=describe(cost/('cal-'+task+'-selective/capture/events.jsonl'))
        b=describe(cost/('cal-'+task+'-selective-without-value-projection/capture/events.jsonl'))
        sa=load(cost/('cal-'+task+'-selective/offline-single-pass/summary.json'));sb=load(cost/('cal-'+task+'-selective-without-value-projection/offline-single-pass/summary.json'))
        assert sa['correct']==sa['targets']==sb['correct']==sb['targets']
        counter=a['snapshot_omissions_by_kind']
        pa=load(cost/('cal-'+task+'-selective/offline-single-pass/process.json'))
        pb=load(cost/('cal-'+task+'-selective-without-value-projection/offline-single-pass/process.json'))
        work=lambda p,k:sum(r[k]for r in p['graph_work_counts'])
        lines.append('| '+task+' | '+str(a['complete_bytes'])+' | '+str(b['complete_bytes'])+' | '+str(counter['scalar_fields'])+' | '+str(counter['container_values'])+' | '+str(work(pa,'nodes'))+'／'+str(work(pb,'nodes'))+' | '+str(work(pa,'edge_lists'))+'／'+str(work(pb,'edge_lists'))+' | '+str(sa['correct'])+'/'+str(sa['targets'])+' |')
    lines+=['','Scalar 计数是实际取值前省略；Map 计数是未构建的叶记录，引用遍历与已有值读取继续执行。正常离线构建的节点及边列表数也保留在各新进程 summary；没有为计数重复还原一次图。完整 full/selective 收益仍混合既有机制，不能全部算作本轮新增投影。','',
       '本轮没有完成任意 Java 方法体最小切片。解释字段及有限转换仍保守扩张；不适用时采全。详见[算法与伪代码](TARGET-OBSERVATION-ALGORITHM-20261103.md)。']
    (HERE/'TARGET-OBSERVATION-DEVELOPMENT-20261103.md').write_text('\n'.join(lines)+'\n')


def costs(audit):
    s=load(audit/'summary.json');lines=['# 同版本共同任务成本：目标相关观测','',
      '算法冻结 `'+s['candidate']+'`，能力参照 `7e4ad0b`。四个查询任务和联合判据均在正式结果前固定；不按请求数投票，不更换失败或没有优势的任务。以下是新的在线捕获及同版本正常离线单次流程，不覆盖旧成本表。','',
      '**预设内部判据通过 '+str(s['task_wins'])+'/4；统一内核子集通过 '+str(s['unified_task_wins'])+'/3。** 这是selective相对full的内部判据，不能推出多数应用优于 MT，也不等于相对原版低开销。ZLT两个任务相对原版p95的配对中位增幅仍约131%。Orders 是既有专用路径，另外三项是统一内核。新应用完整候选的能力覆盖另见首次复用报告。','',
      '判据要求完整批次协议字节和正常离线进程 CPU 同时下降，且业务 CPU／p95 配对中位比值不超过 1.05、每轮不超过 1.10。五轮不是请求级独立重复，不声称统计显著性；2 请求／秒完成率不代表最大吞吐。','',
      '每任务比较原版、TF full、selective、固定 MT；同 JAR、JDK、资源限制和原输入。五轮独立部署、轮内随机配置顺序；预热 30 秒、测量 60 秒、2 请求／秒、并发上限 2。正确性包含预热，在线指标排除预热。正式在线实验顺序执行，原有非实验容器未操作，不宣称独占物理机。','']
    lines+=['| 共同任务 | 所选返回路径 | 原声明来源边界 |', '| --- | --- | --- |',
      '| Mall 管理员登录 | `/data/expiresIn` | 本次 `AuthService.getAccessToken` 调用返回字段 |',
      '| ZLT Client 列表 | `/data/*/clientId` | 本次 `ClientMapper.findList(Page,Map)` 返回字段 |',
      '| ZLT User 列表 | `/data/*/username` | 本次 `SysUserMapper.findList(Page,Map)` 返回字段 |',
      '| Orders 创建 | `/total` | 本次 Carts 响应的 quantity／unitPrice，沿用原固定任务 |','',
      '短校准覆盖原版与三种工具的业务行为、真实来源调用、目标及独立物理坐标；依赖校准核对实际 ObjectMapper 定义与原业务 JAR 字节码。MT 使用既有固定适配器，原生传播 JAR 未改；这不是任意库的传播等价性证明。Mall 跨 JVM 仅规范化新 token 和 86400 秒有效期的时钟舍入；各 JVM 内来源／目标值与实例坐标仍精确核对，每部署另查 180 条登录日志。ZLT 完整 JSON 按原分页模板核对，原始数据库事实保留。','',
      '机器为 Ryzen 9 7950X／32 逻辑 CPU 的 WSL2。Mall／ZLT采用固定 OpenJDK 8u504，Orders保留锁定原镜像的运行时；各任务内部四配置JDK一致。JVM32/256MiB、GC1/CI2，各 JVM 1CPU/768MiB；资源采样间隔2秒，RSS峰值为采样峰值。Mall业务组为admin/auth/portal，ZLT为user/uaa，Orders业务组为orders/carts/shipping；部署组另含其依赖。MySQL512MiB、Redis128MiB、Mongo／Rabbit384MiB，ZLT Nacos768MiB，实际角色、限制、镜像ID及原有四个容器清单见环境与compose文件。负载客户端不计入业务或部署资源，curl HTTP时间排除Docker exec调度及评分。','']
    labels=[('p50 ms','p50_ms',1),('p95 ms','p95_ms',1),('p99 ms','p99_ms',1),('完成请求/秒','completed_rps',1),('错误率','error_rate',1),('业务 CPU，单核%','business_CPU',1),
      ('业务平均 RSS MiB','business_RSS_MiB',1),('业务采样峰值 RSS MiB','business_peak_RSS_MiB',1),
      ('整部署 CPU，单核%','deployment_CPU',1),('整批协议事件','batch_events',1),('整批协议 MiB','batch_bytes',2**20),
      ('可归属测量事件','measure_events',1),('可归属测量 MiB','measure_bytes',2**20),('未归属／共享 MiB','shared_unattributed_bytes',2**20),
      ('全部 capture 文件 MiB','all_capture_file_bytes',2**20),('各自离线核心墙时 s','offline_core_s',1),('各自离线核心 CPU s','offline_core_CPU_s',1),
      ('正常离线总墙时 s','offline_wall_s',1),('正常离线进程 CPU s','offline_CPU_s',1),('fresh-exec VmHWM MiB','offline_VmHWM_MiB',1),
      ('正常还原图节点','graph_nodes',1),('正常还原边列表','graph_edge_lists',1)]
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
        if task=='zlt-client':
            lines+=['','每种配置的900次请求中，150次为空列表、未产生所选成员目标；它们仍参与业务与成本统计，不能将其算作150个来源答案。其余请求共生成900个实际成员目标。','']
        lines+=['','| 离线阶段墙时，五轮中位数 s | full | selective | MT |', '| --- | ---: | ---: | ---: |']
        phase_keys=list(dict.fromkeys(k for r in s['formal_rows']if r['task']==task and r['mode']!='original'and r['completed']for k in r['phases_seconds']))
        for phase in phase_keys:
            values=[]
            for mode in('full','selective','mirrortaint'):
                v=[r['phases_seconds'][phase]for r in s['formal_rows']if r['task']==task and r['mode']==mode and r['completed']and phase in r['phases_seconds']]
                values.append(format(statistics.median(v),'.4f')if v else'N/A')
            lines.append('| '+phase+' | '+' | '.join(values)+' |')
    planning=load(audit.parent/'static-planning/summary.json')
    lines+=['','## 静态规划','', '| 任务，五次 fresh-exec 中位数 | 进程墙时 s | 进程 CPU s | 进程内规划 s | 当前 exec VmHWM MiB |',
            '| --- | ---: | ---: | ---: | ---: |']
    for task in s['absolute_medians']:
        rows=[r for r in planning['rows']if r['task']==task];assert len(rows)==5
        lines.append('| '+task+' | '+' | '.join(format(statistics.median(r[k]for r in rows)/scale,'.4f')for k,scale in(
            ('process_wall_seconds',1),('process_cpu_seconds',1),('wall_seconds',1),('VmHWM_KiB',1024)))+' |')
    lines+=['','## 口径和限制','',
       'full/selective 共享工程开关、索引、协议编码和所有必要证书／来源／绑定／完整性核验。新增值投影开／关是本轮独立短消融；此前局部性证书关闭的精度消融单独保留，本轮没有重跑成正式便宜参照。不能拿丢失答案的配置比较同答案成本。没有压缩协议或少导出诊断来冒充目标剪枝。','',
       '事件与字节只按实际 Frame、调用、消息及明确父关系归属，不凭 trace-id、值或可见时间窗猜配。未配对／共享记录保留；可归属量不是全部稳态写入。协议 JSON 与全部 capture 文件分列，后者还包含 MT 诊断和 class dump，均不是最大磁盘 I/O。','',
       '离线核心：TF 为必要核验、依赖还原及目标查询；MT 为相应原生标签解码。它们不是相同操作。完整正常进程 CPU、墙时及当前 exec VmHWM 同时报告；独立事实索引／评分、解码／核验、导出阶段在每轮 JSON 中分别保存，不混称核心。计数复用同一次图构建，没有追加完整证书审计或第二次还原。','',
       '静态规划每任务五次 fresh-exec、固定逻辑 CPU。计时含模型 JSON 载入及实际规划；排除原 JAR 提取、初次依赖清单／JDK探针、Agent编译及服务启动，不能叫完整冷启动建模成本。OS页缓存未清空。','',
       '本轮只有单目标接口，未将多次单字段部署相加称多目标实验。MT 即使导出多个字段，每部署也只评分同一固定任务；其他导出及必要适配成本仍计入。未回答的新应用任务不参加性能排名，其失败由能力表完整保留。','',
       '相对原版和相对 MT 的在线开销、绝对 CPU 与延迟均如表；收益范围跨 1 时不能称稳定改善。不能由专用 Orders 的局部收益概括统一内核，不能将共同工程或独立评分提速算成选择性贡献。','',
       '配置表是五次部署各指标的中位数；配对表是同轮比值的中位数，不能用前者相除替代。通过在线约束不等于在线稳定加速：Mall及ZLT的若干CPU／p95范围仍跨1。Orders整批字节缩减主要来自未归属／共享部分，可归属测量字节只小幅减少；不将整批57.74%说成每个目标请求少采57.74%。','',
       '最终完整性审计核对111项核心源码、23份公共契约、10份计量源码、1774份新应用首次文件和1746份复用Mall文件；80份资源汇总与原始样本严格相同。首次派生审计误写构建器文件名，其失败目录保留，修正只在审计驱动。最终审计与交付源码见 `delivery-integrity-04/`；03之后只补充报告的时间顺序说明及跨配置业务JAR哈希复核，没有改测量、评分或算法。','',
       '本批备份位置为 `artifacts/backups/target-closure-20261103/`，CRC和SHA256以[备份回执](target-observation-backup-receipt-20261103.json)为准。保留符号链接及其外部引用清单，旧JDK／依赖和历史捕获继续使用原备份，不将本批归档称为全部历史工件的独立包或异机备份。','',
       '全部逐轮原始值、源坐标／答案、环境与镜像、静态计划、当前 exec 内存、失败及校准见 `'+str(audit.parent)+'`。原始与派生结果分目录；算法、驱动、评分和报告分别锁定哈希。未 push。']
    (HERE/'TARGET-OBSERVATION-COMMON-COST-20261103.md').write_text('\n'.join(lines)+'\n')
    save(HERE/'target-observation-cost-results-20261103.json',{k:v for k,v in s.items()if k!='formal_rows'})
    (HERE/'target-observation-cost-rounds-20261103.csv').write_bytes((audit/'rounds.csv').read_bytes())


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['external','development','cost']);p.add_argument('--audit',type=Path);p.add_argument('--home',type=Path);p.add_argument('--cost',type=Path);a=p.parse_args()
    if a.stage=='external':external(a.audit.resolve())
    elif a.stage=='cost':costs(a.audit.resolve())
    else:development(a.home.resolve(),a.cost.resolve())
