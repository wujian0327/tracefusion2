"""Render small, inspectable tables from completed protocol-locked evidence."""
import csv,json,shutil,statistics
from run_planned_service import ROOT,HERE,load,save
from run_jvm_rule_revision import H

def run():
 d=load(H/'cost-summary-final/results.json');a=load(H/'final-audit-02/results.json');p=load(H/'new-app-protocol-before-planning.json')
 assert d['completed_deployments']==60
 shutil.copyfile(H/'cost-summary-final/rounds.csv',HERE/'jvm-rule-cost-rounds-20261110.csv')
 shutil.copyfile(H/'final-audit-01/new-app-targets.csv',HERE/'jvm-rule-frozen-reuse-targets-20261110.csv')
 save(HERE/'jvm-rule-results-20261110.json',{'cost':d,'correctness':a,'paired_target_checks':load(H/'paired-answer-audit-01/results.json'),'pilot_gate':load(H/'gate-calibrated.json'),'core':load(H/'candidate-after-identity-fix.json'),'post_experiment_v1_fix':load(H/'post-experiment-v1-guard-fix.json'),'new_app_protocol_sha256':__import__('run_planned_service').sha(H/'new-app-protocol-before-planning.json')})
 correctness=[]
 for control in ('primitive-controls-01','primitive-guard-off-01'):
  for mode,r in load(H/control/'results.json').items():
   for c in r['checks']:
    answer=c['answer'];correctness.append({'group':control,'mode':mode,'case':c['case'],'known':answer['known'],'expected_origins':len(c['expected']),'actual_origins':len(answer['origins']),'exact_match':True,'target_version':answer['version'],'selectors':json.dumps(answer['selectors']),'score_file':str(H/control/'results.json')})
 for tier in ('low','medium','high','related-high'):
  for mode in ('full','selective','mirrortaint'):
   folder='audit-related-257'if tier=='related-high'and mode in ('full','selective')else'audit'
   path=H/'pilot'/(tier+'-'+mode)/folder/'scores.json'
   for index,c in enumerate(load(path)):
    expected=c.get('expected_count',len(c.get('expected',[])));actual=c.get('actual_count',len(c.get('actual',[])))
    correctness.append({'group':tier,'mode':mode,'case':index,'known':c['known'],'expected_origins':expected,'actual_origins':actual,'exact_match':c['correct'],'target_version':c.get('version',c.get('answer',{}).get('target',{}).get('version')),'selectors':json.dumps(c.get('selectors',c.get('answer',{}).get('selectors'))),'score_file':str(path)})
 with(HERE/'jvm-rule-correctness-20261110.csv').open('w',newline='')as f:
  w=csv.DictWriter(f,fieldnames=list(correctness[0]));w.writeheader();w.writerows(correctness)
 cpu=[];offline=[];work=[]
 for r in d['medians']:
  cpu.append('| %s | %s | %.3f | %.3f | %.3f | %.2f |'%(r['tier'],r['mode'],r['cpu_seconds_per_request']*1000,r['extra_cpu_seconds_per_request']*1000,r['p95_ms'],r['rss_mean_MiB']))
  if r['mode']!='original':
   offline.append('| %s | %s | %.4f | %.4f | %.4f | %.2f | %.4f |'%(r['tier'],r['mode'],r['normal_process_wall_seconds'],r['normal_process_cpu_seconds'],r['normal_cpu_seconds'],r['normal_VmHWM_KiB']/1024,r['independent_oracle_score_seconds']))
 for tier,n in [('low',8),('medium',64),('high',256)]:
  f=next(r for r in d['medians']if r['tier']==tier and r['mode']=='full');s=next(r for r in d['medians']if r['tier']==tier and r['mode']=='selective')
  work.append('| %d | %d→%d | %d | %.3f→%.3f | %.3f→%.3f |'%(n,f['field_hook_calls'],s['field_hook_calls'],s['boundary_payload_omissions'],f['batch_bytes']/2**20,s['batch_bytes']/2**20,f['measure_bytes']/2**20,s['measure_bytes']/2**20))
 growth=d['paired_increments'];diff=[r['difference']*1000 for r in growth]
 text='''# JVM公共原语、证据需求与冻结复用

**小范围实现通过正确性门；成本未支持selective额外CPU增长更慢；新应用冻结复用仍未认证成功。** 两模式的related-high各6/6目标精确匹配257个原始来源出现；正式三档四配置五轮共60份新部署全部通过。五轮中，selective高低档额外CPU增量都比固定MT更大。没有为取得优势更换任务或放宽认证。

参照main为`b9cd333267609555261eff6a910008494067340c`，核心冻结为 **`c8918bf8b0ed6ac90c0065558fe4df540bd76a2c`**。分阶段提交：`ece84a7`修复版本保护，`df594c4`加入公共规则，`c8918bf`修复分配身份接口兼容；`4b86075`锁定控制及实验驱动。Agent未重编译、事件格式不变，30份公共框架契约逐项未改；实际Agent SHA256为`367cbb2300e507e5db4716c4e2fcbed1a39898c5e6c6f5f23583c4c1487e2764`。源文件、原JAR、JDK、镜像和固定MT组件哈希见工件协议及最终审计。未push。

收尾另发现旧v1路由没有进入统一写版本核验，字面协议反例`4→3`仍被接受。独立提交 **`c866d67`**补齐入口；`4→3`现拒绝，`4→5`和无完整写覆盖证明时的`4→6`保持接受。所有正式计量和新应用首轮使用的都是v8，表格仍归c8918bf，不改标后续补丁；补丁的旧完整捕获复算另存`legacy-comparison-after-v1-fix/`。这不是c866d67的新性能实验或新的未见入口成功。

**原语与证据定义。** [jvm_semantic_rules.py](jvm_semantic_rules.py)集中定义五条指令的操作数、栈结果、数据／身份需求、效果义务及核验函数。两个解释路径实际调用同一转移函数；静态栈分析和写值需求也读取该定义。不是仅增加一份说明性清单。

| 公共原语 | 正向转移 | 静态反推与必留运行证据 | 代码与边界 |
| --- | --- | --- | --- |
| I2L、IADD、LADD | 保留输入的来源并集、已有selectors并集，任一unknown则结果unknown。IADD按signed32、LADD按signed64模运算；I2L保留signed32值并丢弃临时装箱身份。相同数值不合并来源出现。 | 栈分析保留真实操作数定义。I2L核对原JVM输入、输出、方法及调用点事件；加法复用实际字段／参数值、原字节码和实际控制路径，结果在后续写入／返回绑定处核验，不新增算术事件。 | `RULES`、`compute`；`plan_collection_service.analyze`、两个执行规划器及两个还原器。LADD新增一项规则及解释器分派接入，不是所有opcode已自动支持。未使用结果也不代表当前解释器可以省掉操作数核验。 |
| GETFIELD、PUTFIELD | 按已解析的实际对象身份、声明字段及版本查询／更新状态；保留已有origins、selectors、unknown。省略载荷的非必要字段仅记unknown，不造空来源。写同值仍是新版本。 | 接收者身份、字段／站点、成功读写记录、版本、必要载荷、原异常及别名／发布效果保留。所有已解释字段读取、getter及构造摘要输入仍保守进入值需求；没有最小跨过程切片。 | `field_event`、`field_transfer`、`write_payload_eligible`；`plan_execution_closure`、`infer_execution_closure`及原堆状态／异常调度。字段选择和可达性仍由现有状态核验，未把整个内核或所有框架自动规则化。 |

静态栈／输入依赖见`plan_collection_service.py:82`；GETFIELD值需求见`plan_execution_closure.py:23`，受限写许可见`:45`。计划携带`semantic_primitive_rules`，还原器核对它与内核定义一致，不能通过修改计划中的位宽更改语义。旧捕获的原有协议仍可复算。

**一条写路径的闭环。** 控制中的`Data.setOther(long)`写入不是目标、也未被后续已计划计算／getter／摘要读取的标量字段。共同定义产生保守需求集合，现有规划器再核验类／方法哈希、字段声明及受限setter，输出站点许可。原PUTFIELD成功后，原`ExecutionKernelHooks.versionOnly`在装箱／省略前检查开关、许可、精确实际类、查询根及当前Frame／setter调用；不成立采全。`Recorder.fieldVersionRecord`仍检查许可、更新版本及ACTIVE保护，再发原`write-version`。离线同时核验站点、实际receiver、调用区间、版本和载荷表示。

Agent消费的是共同规则派生的既有计划许可；Java守卫仍是现有实现，并非从Python规则自动生成。本轮没有发明新的省略形态。它只允许省掉监测载荷，业务写入、版本及必要效果不省。对不能解释的效果继续保守处理，不声称任意并发、反射或native效果的完备保证。

**反例先修。** 旧核验器可接受构造的同一物理字段连续可见写`4→3`，尤其跨根／没有写省略策略时缺少全局检查；这不是说Agent实际产生了倒退计数。`ece84a7`在任何策略提前返回前检查可见写严格递增，`4→4`也拒绝。不能证明中间没有写入时允许`4→6→9`，不把差一当默认事实；已有最终退出快照版本矛盾保护保留。没有新增全写覆盖证书或声称能从稀疏日志恢复所有隐含写。

**正确性与实际省略。** 真值是预先指定的Java分支规则及各JVM原始调用、字段、槽位和版本事实，不读TF图生成预期来源；不同JVM不比对象编号。

| 检查 | 结果 | 证据边界 |
| --- | --- | --- |
| 独立单元 | 原语8项、版本6项通过 | signed32／64溢出、双来源、unknown／selectors、来源null与省略unknown区别、错误规则／身份／位宽及版本倒退；含旧v1入口保护。 |
| 新JVM原语控制 | full/selective各8/8（6正来源、2已知空来源）；关闭写许可后仍各8/8 | MAX+1、MIN−1、7+7不同字段来源；IADD后I2L；同值常量覆盖及别名写的Data.a均1→2；空接收者读取的原catch路径。每模式4项损坏拒绝。 |
| 受限写实际省略 | selective有1次`write-version`，full为0；关闭许可后selective也为0 | 开关在省略前走采全分支，目标状态、版本、来源及selectors保持。目标写入始终保留实际载荷。不声称覆盖所有异常字段访问或任意回调。 |
| 原三档短试点 | 四配置业务各6/6；三种工具来源各6/6 | 原8／64／256字段JAR、输入及`/target`来源不变；selective边界载荷省略48／384／1536次。 |
| related-high必要观测 | TF full、selective和固定MT各6/6；每目标257来源 | 原LADD拒绝结果保留。新输出27371，链接原目标字段及全部256个成员字段的本次读取版本，不能按重复值合并。selective边界载荷省略为0。 |
| 旧完整捕获复算 | 8份全结果逐项相同 | 包括原Mall完整180请求捕获；声明路径396个已有已知目标保持，内核未查询字段中原540个unknown也保持。这是旧在线执行的新离线复算。 |

原短试点评分驱动曾把“返回字段版本等于原来源版本”用于related-high，导致新版本目标被错误拒评。原结果保留；独立校准评分器改为原协议预定的257个源字段事实，再与目标新版本的预测比较，输出另存`audit-related-257/`。不改变业务、来源边界或传播。旧Mall复算还暴露公共接口未使用既有分配身份映射的问题；`c8918bf`传入已经核验的实际身份后，八份完整捕获全结果恢复一致，原失败保留。

四个短试点组另机械比较24对声明目标：full/selective的状态、版本、规范化来源出现和selectors一致；这几条直线路径的selectors为空，非空选择标记的转移由独立原语单测覆盖，不把空选择比较说成复杂控制依赖证明。

没有单独的“省略前守卫成功”事件可从full捕获复原，因此不把改写full日志当作同执行投影证明。新采对照能验证这批目标的选择性保持；这与同执行派生投影证明不同。原Agent未变化，身份修订仅涉及离线，原计划字节及捕获未改写。

**正式成本：原三档各四配置、五轮，共60份独立部署。** 每部署预热30秒、测量60秒、2请求/秒、并发上限2；同轮配置顺序随机。业务JAR、JDK8u504、镜像、1CPU／768MiB及JVM参数固定；无额外业务预热、探针或profiler。正确性覆盖每部署180请求，在线指标仅120个测量请求。原版及每个工具各2700次业务正常；三工具来源各2700/2700匹配。保留四个原有非实验容器，不宣称物理独占。

下表为五部署中位数。CPU主指标先按同轮同档扣原版，再汇总；不能用两个表格中位数相减代替配对计算。p95为HTTP time_total，RSS为2秒采样均值。

| 档位 | 配置 | 业务CPU ms/请求 | 相对原版额外CPU ms/请求 | p95 ms | 平均RSS MiB |
| --- | --- | ---: | ---: | ---: | ---: |
'''+ '\n'.join(cpu)+'''

每轮先算高低档额外CPU增量，再比较selective和固定MT。五轮差值全部为正，中位 **%.3f ms/请求**，范围 **[%.3f, %.3f]**；本任务没有支持“TF selective增长更慢”，也不推广成所有入口的工具排名。五轮是独立部署重复，不以请求数做独立样本或宣称显著性。

**省了什么。** 下表是每180请求完整批次实际记录；hook数不是全部监测器内部工作，也不是测量期专属计数。原业务字段写入、getter及JSON输出照常发生。字节分别给完整批次和由实际消息／Frame／native root归属的测量请求，不用trace-id前缀或时间接近猜配，未归属部分留在全批次。

| 非目标字段 | Recorder字段hook调用full→selective | selective边界载荷省略次数 | 整批协议MiB full→selective | 可归属测量协议MiB full→selective |
| ---: | ---: | ---: | ---: | ---: |
'''%(statistics.median(diff),min(diff),max(diff))+'\n'.join(work)+'''

省略次数和hook降幅不能当速度提升。selective/full业务CPU五轮比值范围三档都跨1；中档p95五轮均较低，低／高档p95范围跨1。正式三档没有触发新增写省略形态：受限写路径只在控制中验证，三档成本是原有边界投影、读站点选择及响应持久化投影等既有selective组合，不把全部差异归给本轮共享规则，更不把LADD算作新的剪枝收益。LADD不在三档正式计量路径执行。

**正常离线与实验验证分开。** 正常流程包含解码、所有必要身份／来源／完整性与契约核验、还原、查询和导出；独立原始真值生成／评分另列。fresh-exec固定逻辑CPU，VmHWM读取该进程`/proc/self/status`，另保留ru_maxrss原值；没有用父进程继承高水位冒充当前峰值。

| 档位 | 配置 | 正常进程墙时s | 正常进程CPU s | 工作阶段CPU s | VmHWM MiB | 独立真值/评分墙时s |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
'''+ '\n'.join(offline)+'''

中／高档selective/full进程墙时配对比值分别约0.779和0.692，五轮均低于1；低档跨1。selective离线内存三档均低于full，但高档仍高于MT。离线阶段定义不同，不能把TF还原与MT原生标签解码当相同操作；本轮也没有普遍CPU或全部指标优势。

固定MT含原生JAR、B0导出适配器和运行时见证；多字段来源／目标导出不能关闭，仍只评分同一个`/target`。CSV另列完整协议量与离线阶段；native日志／class dump保留在原工件，不把协议JSON当全部磁盘I/O。这是固定完整审计配置的工具成本，不是无适配器的原生传播裸成本。

**冻结复用：官方新应用两个入口。** 冻结核心后选择`spring-guides/gs-accessing-data-rest`的`2.1.6.RELEASE`，原提交`%s`。原源码和原JAR未改；提前封存两条POST测试种子Alice/SAME、Bob/SAME，详情`/people/1`、`/people/2`及集合`/people?page=0&size=20`，保留同值不同实体。公开原应用无认证，不伪造身份。原JAR及相关完整依赖元数据接入是配置工作，来源仍为实际CrudRepository.findById与PagingAndSortingRepository.findAll(Pageable)，没有移到service/helper。

| 新入口，每模式分别统计 | 首次规划 | 新部署业务 | 首次来源结果 | 首道阻断与所需工作 |
| --- | --- | --- | --- | --- |
| Person详情，2目标 | 接纳，条件待运行核验 | 2/2响应与原版完整一致 | 2 evidence_invalid；无配对源事实 | Spring Data泛型元数据`TypeDiscoverer.resolveType`在启动阶段触发`binding-before: Non-string binding key`。需要框架快照资格／非字符串键观测规则及范围证据，不是补字段名或仅补哈希。 |
| Person集合，2目标 | 接纳，条件待运行核验 | 1/1响应与原版完整一致 | 2 evidence_invalid；无配对源事实 | 同一首道阻断先于正式查询根。后续仓储调用、Page／HAL映射尚未认证；不能推断修掉第一处就足够。 |

四份新捕获均粘性无效，实际已记录的问题保留，未删启动／准备记录以恢复有效性。`binding-return`记录数不是物理目标绑定认证数。原版有4目标义务／模式，但缺本JVM完整来源调用、字段和版本事实，FP/FN留空，不由相同lastName或URL生成物理真值。源码和环境本轮已审阅，不称第三方盲测；Petclinic原失败保留，没有拼接成新版成功。

**可写结论与边界。** (1) 该原型把五条指令的传播与输入／证据需求放在共同实现中，由静态规划及离线执行实际消费；LADD复用了来源／选择／unknown合并，无业务特判。(2) 必要来源257项保留，无关路径能执行既有观测省略；这不是新省略机制、最小切片或全JVM证明。(3) 本三档记录与部分离线成本下降，额外在线CPU增长反而未优于固定MT。(4) 公共指令正确不代替框架取证适用；新应用首轮仍未给可认证来源。(5) 现有普通写载荷省略只是受限站点：未知回调、反射/native及共享并发不能因此视为无效果，未查询字段整图也不要求与full一致。

后续可研究源方法中未进入现有许可范围的赋值，但应先建立省略前的影响范围及来源／写版本证据；事件占比不是时间占比，本轮不据此估算加速上限。没有形式化完备性证明，论文不能写成自动生成所有Agent钩子或任意框架直接可用。

**复核与工件。** `artifacts/jvm-rule-evidence-20261110/`保留修改前协议、4→3反例、首次分配身份复核失败、原及校准评分、全部新部署和原始资源、逐请求真值、正常离线与独立评分、新应用四份失败、旧捕获复算及备份。逐项正确性见[jvm-rule-correctness-20261110.csv](jvm-rule-correctness-20261110.csv)，机器可读规则见[jvm-rule-specifications-20261110.csv](jvm-rule-specifications-20261110.csv)，成本完整逐轮见[jvm-rule-cost-rounds-20261110.csv](jvm-rule-cost-rounds-20261110.csv)，新入口逐目标见[jvm-rule-frozen-reuse-targets-20261110.csv](jvm-rule-frozen-reuse-targets-20261110.csv)，快照见[jvm-rule-results-20261110.json](jvm-rule-results-20261110.json)。

```bash
python3 experiments/sockshop-mirrortaint/audit_jvm_rule_revision.py --out /tmp/tf2-jvm-rule-audit-new
python3 experiments/sockshop-mirrortaint/summarize_jvm_rule_cost.py --out /tmp/tf2-jvm-cost-summary-new
python3 experiments/sockshop-mirrortaint/run_jvm_rule_controls.py --out /tmp/tf2-jvm-controls-new
python3 experiments/sockshop-mirrortaint/check_jvm_rule_compatibility.py --out /tmp/tf2-jvm-old-capture-new
python3 experiments/sockshop-mirrortaint/check_jvm_rule_paired_answers.py --out /tmp/tf2-jvm-paired-new
```

输出必须使用新目录。第一、二条为已有证据复核，第三条是新JVM控制，第四条是旧执行的离线复算，第五条比较已采集的两模式目标，不冒充新Agent业务部署或新计时。正式驱动为`run_jvm_rule_revision.py --stage formal`，默认目录已有封存结果时拒绝覆盖；真正复跑需配置独立实验目录并重新封存，不能把汇总命令称重新计时。完整工件和外部二进制按[备份清单](jvm-rule-backup-20261110.json)保存，为本机副本。未机械重跑全部历史或40API，未扩展语言或框架契约；代码和小型报告提交main，不push。
'''%p['app_commit']
 (HERE/'JVM-RULE-EVIDENCE-20261110.md').write_text(text)

if __name__=='__main__':run()
