#!/usr/bin/env python3
"""Render current-version costs, keeping three query tasks separate."""
import argparse
from pathlib import Path
import statistics
from run_planned_service import load, save, sha


def render(root):
    a=load(root/'cost-audit.json');s=load(root/'static-planning/results.json');f=load(root/'algorithm-freeze.json')
    assert a['all_passed'] and s['all_passed'] and len(s['measurements'])==15
    lines=['# Jackson隔离版：三类查询的固定负载性能','',
        f"算法冻结 `{f['algorithm_commit']}`。三任务各五轮，原版/full/selective随机顺序、独立容器和数据卷，45次正式部署顺序执行。仅使用本批新捕获；旧成本不移用于新版。",'',
        '每次预热30秒、测量60秒，固定2请求/秒、并发上限2，资源采样2秒。所有业务JVM统一1CPU/768MiB、堆32m/256m、GC/JIT线程1/2；Mongo各1CPU/384MiB。完整JVM参数、镜像digest、原版JAR、输入与顺序在各config.json。', '',
        '`source_evidence=true`统一保留：必要字段、身份/版本、调用与异常、响应绑定等证据，加上原始HTTP诊断/独立真值字节，其在线及采集成本均计入本表。本表不是关闭额外诊断后的最低必要开销。full/selective的全局开关和来源核验条件相同。', '',
        'Cart按运行前统一结构策略选择execution-dependency，当前仍保守保留必要语义证据；Train选择response-forward；票价使用既有字节码生成的collection-computation快速路径。full限于任务纳入的应用类/方法范围，不是整个JVM指令追踪。没有运行后改选成功策略。原版不输出来源，相关离线能力/成本为N/A。外部基线未校准并重新计时本批任务，成本保持N/A。','',
        '表内为五次部署中位数；变化使用同轮selective/full或selective/original比值的中位数，并列五轮范围。请求不是独立部署重复。2请求/秒是完成当前负载，不能推断最大吞吐。p99每轮约120个样本，仅作描述。','']
    metrics=[('p50_ms','在线p50，ms',1),('p95_ms','在线p95，ms',1),('p99_ms','在线p99，ms',1),('throughput_rps','完成吞吐，请求/秒',1),('error_rate','错误率',1),('online_cpu_percent','业务JVM CPU，单核%',1),('online_rss_mean_bytes','业务JVM平均RSS，MiB',2**20),('online_rss_peak_bytes','业务JVM采样峰值RSS，MiB',2**20),('capture_events','测量请求归属事件',1),('capture_bytes','测量请求归属记录，MiB',2**20),('whole_capture_bytes','整批采集字节，MiB',2**20),('offline_core_seconds','整批离线核心，秒',1),('offline_child_wall_seconds','离线子进程墙时，秒',1),('offline_child_cpu_seconds','离线子进程CPU，秒',1),('offline_child_peak_rss_bytes','同批复算VmHWM，MiB',2**20),('answer_wait_p50_seconds','请求完成到批次答案p50，秒',1),('answer_wait_p95_seconds','请求完成到批次答案p95，秒',1),('deployment_cpu_percent','整部署CPU，单核%',1),('deployment_rss_mean_bytes','整部署平均RSS，MiB',2**20),('deployment_rss_peak_bytes','整部署采样峰值RSS，MiB',2**20),('console_bytes','整批控制台输出，MiB',2**20)]
    names={'cart':'Cart：getItems → /*/itemId，新执行内核','train':'Train：retrieve → /data/economyClass，第二次仓储返回','price':'五服务票价：两个prices Map条目，原多来源计算'}
    for kind in ('cart','train','price'):
        d=a['results'][kind];lines+=['## '+names[kind],'']
        for mode in ('full','selective'):
            ps=d['populations'][mode];n=sum(p['queries'] for p in ps);tp=sum(p['tp'] for p in ps)
            lines+=[f"{mode}：900请求＝300预热＋600测量；来源完全匹配{n}/{n}，TP{tp}/FP0/FN0/unknown0；预热目标{sum(p['warmup_targets'] for p in ps)}、测量目标{sum(p['steady_targets'] for p in ps)}。"]
        lines+=['','| 指标 | 原版 | full | selective |','| --- | ---: | ---: | ---: |']
        for key,label,scale in metrics:
            vals=[]
            for mode in ('original','full','selective'):
                v=d['summary'][mode].get(key)
                vals.append('N/A' if v is None else f"{v['median']:,.0f}" if key=='capture_events' else f"{v['median']/scale:,.3f}")
            lines+=['| '+label+' | '+' | '.join(vals)+' |']
        lines+=['','| selective/full 配对变化 | 中位数 | 五轮比值范围 |','| --- | ---: | ---: |']
        for key,label in [('capture_events','测量请求事件'),('capture_bytes','测量请求字节'),('offline_core_seconds','离线核心'),('offline_child_wall_seconds','离线子进程墙时'),('offline_child_cpu_seconds','离线CPU'),('offline_child_peak_rss_bytes','离线峰值RSS'),('online_cpu_percent','在线CPU'),('p95_ms','在线p95')]:
            p=d['paired']['selective/full'][key];lines+=[f"| {label} | {(p['median']-1)*100:+.2f}% | {p['min']:.4f}–{p['max']:.4f} |"]
        p=d['paired']['selective/original'];lines+=['',f"selective相对原版，配对中位数：p95 {(p['p95_ms']['median']-1)*100:+.2f}%，业务JVM CPU {(p['online_cpu_percent']['median']-1)*100:+.2f}%。"]
        for key,label in [('online_cpu_percent','在线CPU'),('p95_ms','在线p95'),('offline_core_seconds','离线核心')]:
            v=d['paired']['selective/full'][key]
            direction='范围跨1，不能称稳定改善' if v['min']<=1<=v['max'] else '本批五轮均较低，仅作样本描述' if v['max']<1 else '本批五轮均较高，仅作样本描述'
            lines+=[label+'：'+direction+'。']
        if d['paired']['selective/full']['capture_bytes']['median']>.95:
            lines+=['当前新执行路径的记录量缩减有限，不能沿用旧read-forward快速路径的节省比例；语义能力与查询切片收缩是两项不同工作。']
        lines+=['']
    if (root/'figures/isolated-cost-20261022-online-overhead.png').exists():
        lines+=['## 五轮配对点图','',
            '每个点是一轮独立部署的配对比值，黑线为五轮中位数，虚线1表示相同成本。图中没有置信区间，不把请求当作独立重复。','',
            '![selective相对原版的五轮在线开销](figures/isolated-cost-20261022-online-overhead.png)','',
            '![selective相对full的五轮采集与离线成本](figures/isolated-cost-20261022-observation-benefit.png)','']
    lines+=['## 静态规划与离线阶段','',
        '每任务五次新进程、固定同一逻辑CPU，重新提取原JAR、生成字节码模型、选策略并生成计划；每份计划必须与实际部署计划完全相等。编译Agent和容器启动不计入规划时间。OS页缓存未清空；进程树RSS为15ms采样求和，共享页可能重复。预检期间的静态试测单独保留，主表使用正式在线实验结束后的测量。','',
        '| 任务 | 流程墙时，秒 | 子进程墙时，秒 | CPU，秒 | 进程树RSS峰值，MiB | 纯计划分析，ms |','| --- | ---: | ---: | ---: | ---: | ---: |']
    for kind in ('cart','train','price'):
        rs=[r for r in s['measurements'] if r['kind']==kind];med=lambda k:statistics.median(r[k] for r in rs)
        pure=statistics.median(sum(p['plan_analysis_seconds'] for p in r['phases'].values()) for r in rs)
        lines+=[f"| {kind} | {med('wall_seconds'):.4f} | {med('subprocess_wall_seconds'):.4f} | {med('cpu_seconds'):.4f} | {med('process_tree_sampled_peak_rss_bytes')/2**20:.2f} | {pure*1000:.3f} |"]
    lines+=['','离线另存JSON解码、图核验/还原、目标反向查询、答案导出、独立评分及证据导出时间。核心＝图核验/还原＋目标查询；子进程CPU和VmHWM还含解码、评分与导出，不能称纯算法独立峰值。30份原始捕获在在线实验结束后用新exec进程复算内存，读取自身/proc/self/status的VmHWM；不使用可继承父进程高水位的ru_maxrss替代。原计时、原预测和事件保持不变。','',
        '## 计数边界、审计与限制','',
        '新版写出有缓冲，在线文件位置可能落在未完整的JSON行。本轮在边界只计完整行，原始文件可见窗口计数仍保存在metrics/capture-window及CSV的file_visible列。主表记录量另从关闭后的完整捕获按实际消息、RPC父消息和Frame父子身份归属测量请求；不按trace-id整体合并、不按值匹配，不包含全局启动记录。归属依据和逐类事件见request-record-audit.json。整批成本仍包含预热、启动、就绪和合法业务准备，Cart准备后的六次一致性GET不混入正确性目标。','',
        '答案等待来自批处理：请求完成至整批关闭，再至答案导出。它包含剩余测量窗口、关闭采集和离线工作，不代表工具固有流式延迟；没有单独测量业务内部目标生成时间。','',
        '70个正式被观测JVM均验证业务ObjectMapper哈希与原版JAR内定义一致；Agent全部854个class与62查询能力验收版相同，无原包Jackson类或直接类型链接。所有45次部署核对资源限制与相同JVM参数。独立来源检查逐轮通过，原始输入、客户端响应、源坐标、预测和清理记录保留。','',
        '第一份Cart预检的旧评分器只在根Frame寻找仓储调用，无法处理新内核嵌套Frame；保留于artifacts/isolated-cost-preflight-first-20261022。正式实验前改用已有独立实例真值程序并重新校准，未改冻结核心、来源边界或业务JAR。正式计时前也修正了缓冲完整行计数，原冻结协议及修订说明保留。','',
        '本轮三任务没有测量Orders实际异步/保存链或Cart首次创建路径的性能，不能代表全部62查询。没有新增未见查询覆盖，也没有声称跨工具成本排名、统计显著性、最大吞吐或跨机器普适优势。29候选继续封存。原成本只对应原版本；当前新版的能力结果见JACKSON-ISOLATION-20261022.md，完整进展见PROGRESS-20261022.md。','',
        '原始根目录：artifacts/isolated-cost-20261022/。算法/驱动/协议、机器环境、命令、镜像digest、各轮数据及重要节点logs/单独归档；Git保存代码与小型汇总，Docker层需另行准备。']
    (root/'results.md').write_text('\n'.join(lines)+'\n')
    save(root/'summary.json',{'algorithm_commit':f['algorithm_commit'],'cost':a,'static_planning':s,'raw_HTTP_audit_cost_included':True,'report_generator_sha256':sha(Path(__file__))})
    progress(root,a)


def progress(root,a):
    lines=['# TraceFusion 2：当前方法、结果与剩余工作','',
        '截至2026-10-22，当前算法冻结为`76d2050`。Java主线已从多个受限profile发展为“响应目标绑定＋统一执行依赖内核＋有限公共库契约”，保留原有快速路径。最新原生Jackson环境下，62个已暴露查询、431个目标，full/selective各428正确、3unknown、0错误确定答案；本轮另完成三类任务45次固定负载成本部署。','',
        '这是声明边界内的自动来源还原，不需要用户手动逐个匹配来源实例；人工仍需声明查询入口、目标字段/路径和来源边界，并审查公共库契约。当前实现与实验主要针对Java，不宣称任意程序、任意库和任意语言都能直接接入。','',
        '## 当前算法怎样工作','',
        '```mermaid','flowchart TD','    Q[查询入口 目标路径 来源边界] --> P[字节码分析与自动观测计划]','    P --> C[Java Agent 按计划采集]','    C --> E[调用 对象 版本 路径 消息等原始证据]','    E --> K[离线执行依赖内核及有限库契约]','    K --> G[实例依赖图与来源答案]','    E --> O[独立真值程序]','    B[独立审阅原业务逻辑与实际数据库事实] --> O','    G --> S[逐实例评分]','    O --> S','```','',
        '1. **运行前规划。** 读取原业务JAR字节码，将响应JSON路径绑定到实际返回对象、包装、字段、列表元素或Map条目；依据目标结构和支持条件选择专用复制/归约/集合/标量/转发证明，或统一执行内核。控制流定义集合在汇合和回边合并到有限不动点，不靠枚举所有循环路径；不根据执行答案挑profile。',
        '2. **在线采集事实。** Java Agent按计划记录实际调用Frame、实参/返回、对象身份、字段写版本、分支/循环、构造和容器操作、异常完成，以及必要RPC、解码、任务/Future和保存效果。在线不计算完整来源集合。Agent内部Jackson已迁入私有包，业务使用自身原版库。',
        '3. **离线解释执行。** 统一Value/Frame/State/Call/Container状态按原字节码和实际路径解释栈、局部变量、字段、数组及有限集合语义；非递归应用调用通过实参、共享字段状态、返回和异常传递依赖。必要库调用必须满足固定版本及可执行检查，不透明调用对可能受影响的结果/字段保守失效。',
        '4. **跨服务与异步连接。** RPC使用W3C上下文、具体span、方向和JSON路径；来源连接还核对实际解码写入、对象和版本。私有任务、worker Frame、完成结果和Future.get按实例配对，不能只凭trace-id或相同数值连接。保存按实际改写、配置、监听器和编码器核验，不统一视为只读。',
        '5. **回答或明确未回答。** 从目标实例反向查询到声明的入口、实际仓储返回、RPC字段边界。返回/序列化快照只绑定目标，不创建来源。必要语义不明为unknown；预算耗尽为analysis_limited；必要证据缺失/矛盾为evidence_invalid；业务未产生目标为N/A。已知空来源与unknown严格分开。','',
        '同值不同对象、同一方法重复调用、同一字段多次写入以及列表重复值均使用实例坐标区分。分支、索引和过滤保留选择证据，当前表中的数据来源不混入一般隐式控制流。来源从声明边界开始，不追数据库完整写历史；时间生成在字段输入边界上可为空，不等于环境时间是常量。','',
        '两个实际案例说明身份与契约检查的作用：HATEOAS线上id非空，但默认解码忽略该属性，content.id仍为null，不能按同名JSON路径补源；Cart首次GET与再次GET返回相同customerId，却必须依据本次实际仓储读取区分来源。保存返回同一个对象，也不能单凭身份或前后值相同证明所有字段保持来源。','',
        '字节码分析、采集器和离线计算在执行阶段上分开，但当前规划器和解释器仍含JVM语义。图、实例坐标和消息协议具有复用空间；换语言仍需相应前端、采集适配和语义验证。仓库已有Go/C/eBPF早期原型，不能与本页Java结果合并成统一多语言正确率或成本结论。','',
        '## 最新正确性与基线能力','',
        '| 同一固定评估范围 | 当前TF full | 当前TF selective | 历史MirrorTaint＋披露适配器 |',
        '| --- | ---: | ---: | ---: |',
        '| 实际目标 | 431 | 431 | 431 |',
        '| 独立实例来源完全匹配 | 428（99.30%） | 428（99.30%） | 368（85.38%） |',
        '| 错误确定答案 | 0 | 0 | 35 |',
        '| unknown／未能回答 | 3 | 3 | 28 |',
        '| 关系TP / FP / FN | 397 / 0 / 3 | 397 / 0 / 3 | 337 / 14 / 63 |','',
        'TF的62查询来自两个应用18个入口，当前全部规划接纳；每模式388次查询请求、431个目标，另85个查询请求N/A。Sock Shop128/131正确、3unknown，Train Ticket300/300。31个正确目标为空数据来源，因此关系TP不等于目标数。full/selective逐项431/431状态一致。','',
        '当前TF逐项保留原MirrorTaint正确368/368、旧TF正确213/213及两者联合382/382，已满足原先定义的联合能力验收。MirrorTaint列是原固定任务中保留的历史独立评分，本轮没有重新运行基线；不能据此对其任意配置或所有能力排名。也不能把“已知答案428/428匹配”写成“431/431全部可回答”。','',
        '最后3个unknown是Cart首次新建商品的itemId、quantity、unitPrice，涉及尚未闭合的监听器/工厂、保存/DBRef及接收容器修改效果；来源边界没移动，未按同值补来源。这3个在原MirrorTaint配置中也未回答，不妨碍原368正确实例保持，但仍是TF自身能力边界。','',
        '隔离后同一Agent重新部署的历史跨服务回归：Sock Shop198/198、TP258；Train Ticket Station31/31、TP30，FP/FN/unknown均0。它们与431集合存在重叠，不相加成总体准确率。语义及负控制包括同值身份、重复调用、循环成员、写版本、数组/lambda、异步、保存、Date/UUID、真实转换及缺失/歧义证据；预期unknown单独报告。','',
        '## 自动规划与未见查询：证据到哪里','',
        '原候选池Sock Shop37＋Train Ticket54＝91。最初冻结版对预选新查询0/20接纳，负结果永久保留。后续响应绑定冻结版在Train Ticket封存新入口10/12查询族接纳、71/71实际目标正确；Sock Shop同轮8/10接纳但24个目标全unknown。再后续有限模型封存测试的可回答率为Sock Shop6/24、Train Ticket35/49，已知答案分别6/6和35/35匹配，Basic批次证据问题单列保留。','',
        '这些封存查询一旦用于后续开发，就成为回归集。今天的428/431是62个已暴露查询的统一版本复验，不能重新称为未见泛化。剩余29个候选仍封存；当前新版尚需冻结后的新查询首次验证，才能判断开发集外的覆盖。','',
        '## 当前版本新性能结果','',
        '三类任务各五轮原版/full/selective、45次独立部署；预热30秒、测量60秒，2请求/秒、并发上限2。统一业务JVM/资源限制，保留全部必要证据及原始HTTP审计字节。原版没有来源输出。下表均为五轮配对比值中位数变化；完整绝对值、范围、各阶段与逐轮数据见[新版成本报告](ISOLATED-COST-20261022.md)。','',
        '| 任务 | full/selective各自正确目标 | selective相对原版p95 | selective相对原版CPU | selective/full测量请求字节 | selective/full离线核心 |',
        '| --- | ---: | ---: | ---: | ---: | ---: |']
    for k,label in [('cart','Cart读取，新内核'),('train','Train返回绑定'),('price','五服务票价计算')]:
        d=a['results'][k];p=d['paired']['selective/original'];v=d['paired']['selective/full'];n=sum(r['queries'] for r in d['populations']['selective'])
        lines+=[f"| {label} | {n}/{n} | {(p['p95_ms']['median']-1)*100:+.2f}% | {(p['online_cpu_percent']['median']-1)*100:+.2f}% | {(v['capture_bytes']['median']-1)*100:+.2f}% | {(v['offline_core_seconds']['median']-1)*100:+.2f}% |"]
    lines+=['','三任务分别解释，不合并成一个速度提升数字。每配置900次请求，其中300预热、600测量；在线性能排除预热，来源正确性检查全部调用。两种模式都正确不等于都有记录量收益，新内核的查询切片收缩仍未完成。低负载结果不说明最大吞吐；小样本范围不是总体显著性证明，答案等待主要含批处理窗口。','',
        '## 历史外部成本与严格消融','',
        '2026-10-15共同Orders.total任务，TF与MirrorTaint精简原生来源输出＋适配器各900/900正确；五轮固定2请求/秒下TF相对MT的配对中位数：p95−43.89%、业务JVM CPU−31.77%、采集字节−50.50%、离线核心−50.20%。这是`8a92bf4`历史配置证据，事件数反而略高0.34%，不能把字节差全归因于事件更少。它不是`76d2050`的新外部成本比较。Phosphor/FlowDist尚无本次同实例任务资格校准，相关排名及成本保持N/A。','',
        '早期内部full/selective消融在相同采集/还原体系内已显示减少记录与离线负担：Sock Shop total事件−80.37%、字节−63.03%；Train Ticket票价事件−52.92%、字节−32.57%。当时在线CPU分别+8.36%、+1.10%，没有支持所有在线成本全面改善。后续`2b3b929`三任务成本也保留；这些数字不移用于当前版本，当前应引用上表新测量。','',
        '## 安全应用与早期原型','',
        'Log4j受控验证已完成，未在本轮重复：22个跨服务日志泄露查询为TP9/FP0/FN1/TN12，一个必要helper未知按漏检计，Recall90%。漏洞配置Log4j2.14.1、缓解配置、修复版2.17.1各5例；前者3触发＋2负例，后两组均不触发本组lookup。证据是实际日志参数、JNDI参数和本地无害回调；没有LDAP、远程加载或RCE。真实Solr只有源码预检，运行结果N/A。37个业务调用通过不等于37个来源查询全部正确。','',
        'Go/C二进制及eBPF原型、Gin请求/线程迁移、checkout金额链与早期Galette/libdft64比较保留在各自报告。本轮未重跑，不与Java对象实例任务、不同机器的绝对成本或安全判据混算。','',
        '## 目前可以主张与下一步','',
        '当前可主张：在已声明的Java/框架/库契约和字段边界内，自动生成观测计划并按实际执行恢复实例来源；固定62查询上覆盖了历史基线的全部正确实例，且没有错误确定答案；新成本由本轮单独测量，选择性收益应逐profile、逐任务解释。','',
        '仍不能主张：任意Java/多语言通用完备、431/431全部可回答、所有查询无需人工公共模型、当前新版普遍比所有基线便宜，或开发集428/431证明了未见查询泛化。递归、任意反射/native、共享并发修改、自定义序列化和任意库效果仍有边界。','',
        '下一步优先：在核心冻结后按原协议启封剩余29候选，完整保留拒绝/unknown/N/A/无效与独立真值；再依据本轮不同profile的成本结果决定新内核的查询切片收缩。最后3个Cart目标如继续扩展，须用有限可核验效果补齐并另行冻结，不能用白名单抹除未知。新增外部成本排名须先重校准当前共同任务。','',
        '## 复核入口','',
        '- [当前依赖隔离与431目标验收](JACKSON-ISOLATION-20261022.md)，原始工件artifacts/jackson-isolation-20261022/candidate-v2/。',
        '- [本轮成本与逐轮范围](ISOLATED-COST-20261022.md)，原始工件artifacts/isolated-cost-20261022/，包含冻结协议、45部署、真值/预测、原库哈希、阶段计时、内存复算与规划成本。',
        '- [原431目标基线对照](BASELINE-CAPABILITY-20261020.md)、[首次0/20](QUERY-COVERAGE-20261019.md)、[封存绑定验证](RESPONSE-BINDING-REVISION-20261019.md)。',
        '- [历史外部比较、消融、安全证据索引](PAPER-EVIDENCE-20261016.md)，按各自版本引用。','',
        '代码和小型摘要在main提交，所有push由用户完成。完整artifacts与Docker镜像不随Git同步；备份入口artifacts/isolated-cost-backup-20261022/START-HERE.txt。归档是同盘恢复副本，迁移仍须按digest准备镜像、在新目录重建，不能盲用旧绝对路径。']
    (root/'progress.md').write_text('\n'.join(lines)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',required=True,type=Path);render(p.parse_args().root.resolve())
