"""Chinese report generated from the sealed ablation matrix and complete results."""
import argparse,statistics
from pathlib import Path
from run_planned_service import load
LABEL={'mall':'Mall管理员登录','zlt-user':'ZLT User','ruoyi-dictionary':'RuoYi字典'}
ARM={'none':'三类全关','boundary_only':'仅边界值','write_only':'仅写值','body_only':'仅方法体','all':'三类全开'}

def run(home,summary,out):
 data=load(summary);assert 'formal'in data and load(home/'pipeline-complete.json')['complete'];rows=data['formal']['rows'];paired=data['formal']['paired'];lines=[]
 def add(s=''):lines.append(s)
 def ratio(r):return f"{(r['median_ratio']-1)*100:+.2f}% [{r['min_ratio']:.4f}–{r['max_ratio']:.4f}]"
 def median(task,arm,key):return statistics.median(r[key]for r in rows if r['task']==task and r['arm']==arm)
 add('# 成本构成与三类观测省略的贡献核验')
 add();add('以核心`4cb5943`、独立评分索引`df977b7`为参照。新核心`bcdf059`只增加写值省略的独立控制门，未增加应用、JDK／框架语义或更强剪枝。旧结果与失败捕获保持；本轮是既有开发任务的内部消融，不是未见查询验证或新的MT排名。')
 add();add('## 成本构成')
 add();add('下表离线为每份完整180请求捕获、五轮基线中位CPU秒。恢复包含全部必要来源、通信、局部性、版本及完整性核验，不能把其中的证书检查排除后称正常溯源成本。在线列是额外16请求粗探针批次的诊断自身时间，含准备阶段，**不是正常业务CPU占比**。')
 add();add('| 任务 | 解码／完整性 CPU s | 恢复含证书 CPU s | 查询 CPU s | 导出 CPU s | 在线探针内主要组（self CPU s） |');add('| --- | ---: | ---: | ---: | ---: | --- |')
 for task in LABEL:
  coarse=data['coarse_baseline_diagnosis'][task]['groups'];top=sorted(coarse.items(),key=lambda kv:-kv[1]['self_cpu_seconds'])[:3]
  add('| '+LABEL[task]+' | '+' | '.join(f'{median(task,"none",key):.3f}'for key in('trace_decode_and_capture_integrity_cpu_seconds','trace_reconstruction_including_all_required_certificates_cpu_seconds','trace_query_cpu_seconds','trace_export_cpu_seconds'))+' | '+'；'.join(f"{k} {v['self_cpu_seconds']:.3f}"for k,v in top)+' |')
 add();add('探针只包围明确列出的监测方法及其原JDK取值／编码／写入调用，不把原业务invoke、谓词或回调执行包进hook区间。递归同方法只计外层；self仅在已覆盖方法间可加，累计时间不可相加。反射数据／容器布局读取与资格配置字段读取分列，未覆盖的监测工作、业务／框架自身执行不能由这些部分凑成100%。同步方法入锁前的等待不在方法计时内；细诊断线程状态样本只给阻塞次数线索，不换算等待秒数。探针仍有开销，全部不进入正式速度表。')
 add();add('细粒度诊断发现递归时钟调用过多，并包含内置采样器自己的JSON编码，故仅保留作工作计数；三份粗诊断关闭该采样器，减少递归计时并补入RPC／SQL资格核验。各版本原始诊断及控制保留。完整旧捕获的函数剖析另保存self／累计时间、调用次数；cProfile使用墙钟，仅用于定位，模块划分不把嵌在解释器内的必要核验漏算成可省工作。')
 add();add('## 机制覆盖')
 add();add('以下均为每配置16次原任务短请求；重复字段／成员观测计“次”，不等于不同来源实例数。静态字段、容器锚点、写入站点和方法候选的单位不同，不相加冒充统一候选数。')
 add();add('| 任务 | 机制 | 静态候选 | 实际资格／省略 | 采全或未触发 |');add('| --- | --- | --- | --- | --- |')
 for task in LABEL:
  diag=data['diagnosis'][task];b=diag['boundary_only']['counts'];w=diag['write_only']['counts'];e=diag['body_only']['counts'];s=b['static_candidates'];v=b['requests'];x=w['requests'];y=e['requests']
  add(f"| {LABEL[task]} | 边界值 | {s['boundary_scalar_candidates']}字段＋{s['boundary_container_candidates']}容器锚点 | {v['boundary_selected_scopes']}/{v['boundary_scope_checks']}快照选中；省{v['boundary_scalar_values_omitted']}标量＋{v['boundary_container_values_omitted']}容器值 | {v['boundary_scope_checks']-v['boundary_selected_scopes']}快照未选，仍采全 |")
  add(f"| {LABEL[task]} | 写值 | {s['constructor_write_candidates']}构造＋{s['application_write_candidates']}普通站点 | 构造省{x['constructor_write_values_omitted']}、普通省{x['application_write_values_omitted']}次 | 未命中不计失败；不反推未执行站点的资格 |")
  add(f"| {LABEL[task]} | 方法体 | {s['body_candidates']}方法 | {y['body_guard_eligible_calls']}次合格／{y['body_selected_calls']}次选中；省{y['body_field_reads_omitted']}读观测＋{y['body_branches_omitted']}分支事件 | 不合格{y['body_ineligible_calls']}次；无候选时为0 |")
 add();add('边界投影保留对象／容器结构、身份、版本及必要前后核验；Map成员值投影不等于省去原始容器读取。普通写值省略仍执行原PUTFIELD、递增版本、检查修改保护并保留write-version事件；本批实际触发的是Mall日志IP站点，不据此宣称整条日志链只读。有限构造写值在三任务均未触发。方法体收缩不删除业务方法或其字段读取：Mall每请求减少5个Recorder字段观测调用及6条分支事件，原分支hook／必要效果记录仍执行，原调用、写入、发布和异常证据保留。')
 add();add('“快照未选”是完整采集作用域，不等于丢失证据；原证明未细分每个未选谓词，不能猜成特定失败原因。Body证明保留具体资格原因。合法守卫不满足采全由独立反例确认；证据损坏仍拒绝认证。ZLT／字典没有方法体静态资格，不算失败样本或成功剪枝。')
 add();add('## 独立收益')
 add();add('共同基线为**同一selective模式、同计划，三类开关全关**；现有响应持久化投影、读取选择、共享索引、快照／元数据缓存、编码和必要验证不变。不是把所有TF full/selective差异都归给这三类。先锁定选择规则，再用省略向量去重：Mall五组合，另两任务仅基线／边界投影；三类全开在后两任务只作短正确性／覆盖验证，未计正式速度，不能声称其CPU等于边界单开。')
 add();add('| 任务／机制 | 整批协议字节 | 测量归属事件 | 正常溯源进程CPU | 业务CPU | p95 |');add('| --- | --- | --- | --- | --- | --- |')
 for task in LABEL:
  for arm in ('boundary_only','write_only','body_only','all'):
   key=task+'-'+arm
   if key not in paired:continue
   d=paired[key];add('| '+LABEL[task]+'／'+ARM[arm]+' | '+' | '.join(ratio(d[k])for k in('batch_bytes','measure_events','trace_process_cpu_seconds','business_CPU','p95_ms'))+' |')
 add();add('变化为同轮比值中位数，方括号为逐轮比值范围，不能用配置中位数相除替代。跨1不称稳定改善；五次部署不是请求级独立重复，不宣称显著性或最大吞吐相同。事件／字节下降不推算CPU或延迟收益。')
 add();add('## 正式绝对值与统计范围')
 add();add('45次独立新部署，五轮、轮内固定随机种子乱序；预热30秒、测量60秒、2请求/秒、并发上限2。业务JAR、JDK、依赖镜像ID、资源限制和输入构造沿用固定任务；无额外业务预热。全部180请求独立评分，在线性能仅120测量请求。正式窗口不带探针／profiler，不同时执行额外剖析、备份或历史部署。离线在关闭本次业务容器后fresh-exec、固定同一逻辑CPU，未清OS页缓存。')
 add();add('| 任务／组合 | CPU单核% | p95 ms | 平均／采样峰值RSS MiB | 整批／测量归属MiB | 溯源进程墙时／CPU s | VmHWM MiB |');add('| --- | ---: | ---: | ---: | ---: | ---: | ---: |')
 for task in LABEL:
  arms=load(home/'formal-matrix-after-diagnosis.json')['tasks'][task]['selected_arms']
  for arm in arms:
   v=lambda key:median(task,arm,key)
   add(f"| {LABEL[task]}／{ARM[arm]} | {v('business_CPU'):.3f} | {v('p95_ms'):.3f} | {v('business_RSS_MiB'):.2f}／{v('business_peak_RSS_MiB'):.2f} | {v('batch_bytes')/2**20:.3f}／{v('measure_bytes')/2**20:.3f} | {v('trace_process_wall_seconds'):.3f}／{v('trace_process_cpu_seconds'):.3f} | {v('trace_VmHWM_KiB')/1024:.2f} |")
 add();add('各机制的方向结论（相对共同基线）：');add()
 def direction(r):
  if r['min_ratio']==r['max_ratio']==1:return '不变'
  if r['max_ratio']<1:return '五轮均下降'
  if r['min_ratio']>1:return '五轮均上升'
  return '范围含1，无一致改善'
 for task in LABEL:
  for arm in ('boundary_only','write_only','body_only','all'):
   key=task+'-'+arm
   if key not in paired:continue
   d=paired[key];add(f"- {LABEL[task]}／{ARM[arm]}：记录字节{direction(d['batch_bytes'])}；正常溯源CPU{direction(d['trace_process_cpu_seconds'])}；业务CPU{direction(d['business_CPU'])}；p95{direction(d['p95_ms'])}。")
 add();add('进程时间含导入、输入哈希和回执；重建含必要证书＋查询的核心阶段另在CSV，不能把解码／导出变化都称解释器提速。RSS是2秒采样值；离线VmHWM来自当前fresh-exec进程。协议字节含关闭后完整JSON，不是最大磁盘I/O；按真实消息／Frame及RPC父关系归属测量请求，未配对启动／共享／关闭字节单列，未从整批删掉。原始HTTP审计保持，不能把省略字段值描述成删去整个审计。')
 add();add('## 独立验证成本与能力保持')
 add();add('| 任务（基线） | 独立oracle／评分CPU s | 独立验证进程墙时／CPU s | 独立VmHWM MiB |');add('| --- | ---: | ---: | ---: |')
 for task in LABEL:
  v=lambda key:median(task,'none',key)
  add(f"| {LABEL[task]} | {v('oracle_independent_raw_oracle_and_score_cpu_seconds'):.3f} | {v('oracle_process_wall_seconds'):.3f}／{v('oracle_process_cpu_seconds'):.3f} | {v('oracle_VmHWM_KiB')/1024:.2f} |")
 add();add('独立oracle进程还包括自己解码完整捕获、验证原始调用及导出；不读取TF传播或标签生成真值。旧“含评分总流程”表保持原样，新口径不能拿来跨旧表宣称提速。必要认证核验仍全部在正常溯源中；没有移到oracle后偷减核心检查。')
 add();add('同候选新部署验收：RuoYi C1每模式80/89、9unknown（4冷启动＋5原声明缺口），C2另5/5；Mall98/103、5真值不足，历史MT正确88项保持；Account40/40（4正来源、36已知空来源）；ZLT15/15正来源；原62查询428/431、3unknown；29字段232/244、12真值不足；15写入口96/96。各集合分别报告，不合成总体准确率。')
 add();add('同捕获参考／新流程全图、字段版本、来源、selectors和根审计逐项一致。跨省略组合比较的是封存查询目标；未查询token等内部输出被投影后可变unknown，首次范围过宽的比较失败及其视图保留，不把它伪装成整个API所有字段均保持。所有声明目标以业务JSON标量／null叶核对分母，空列表无成员不当作null字段；各JVM按自己的实际调用和物理坐标评分。新增原始来源调用序次、caller/PC也进入逻辑签名检查。')
 add();add('五组合控制保持源null／常量null、同值不同来源及覆盖、别名／全局／容器发布、后续状态读取、异常及守卫不成立采全；必要证据缺失、歧义、错坐标和粘性失败保护继续有效。初始预检缺桥接清单、探针粒度偏差、源签名检查范围修订等失败及派生记录均保留，不覆盖核心或首次业务结果。')
 add();add('## 下一步的受限设计')
 add();add('实际有覆盖的是三路径的边界值投影；有限构造在本池为0，普通写值只在Mall命中一个站点，方法体资格仅Mall具备。是否具有稳定速度收益以上述五轮范围为准，不以记录数或单项改善判整体获胜。没有重跑MT，也不更新旧外部排名；Orders沿用其原专用路径报告，本轮不新增测量。')
 add();add('剩余开销既有业务OAuth／数据库自身执行，也有必要证书、结构、版本和通信核验；这些不能靠目标值投影直接删除。可继续研究的是目标无关值／内部执行证据对编码、解码和状态维护的贡献，但未获得无探针的完整细分CPU比例，不能把事件占比当作端到端优化上限。')
 add();add('最值得下一步验证的公共规则是：把输出字段需求穿过已核验的对象／列表成员转移。规划器给有限转移声明每输出所需输入字段，并纳入后续计算、选择／异常及可达写入；采集器在实际类型／配置守卫成立前不省略，不成立采全；解释器区分有证明的省略与缺证，保持来源实例、版本、selectors和状态。不得给复制结果自动授予私有性，或因当前实参没有目标就忽略未来全局读取。本轮未实现该规则；仍保留所有解释方法必要字段读取及完整有限转换输入，不是最小跨过程切片，也无任意Java完备证明。')
 add();add('## 工件与复核')
 add();add('主目录`artifacts/pruning-contribution-audit-20261106/`。核心冻结`bcdf059`、139项源码核验；诊断／正式与最终验收构建905个全部JAR成员、904个class内容相同，打包SHA分别记录，不冒充同一个JAR文件。实验驱动、协议、矩阵和环境另锁定哈希。全部失败、完整捕获、逐轮CPU／RSS、原始源坐标、控制和根审计保留；完整工件与必要依赖本机备份，不是异地副本。')
 add();add('[小型结果](pruning-contribution-results-20261106.json)、[逐轮CSV](pruning-contribution-rounds-20261106.csv)、[备份清单](pruning-contribution-backup-20261106.json)随Git。')
 add();add('小型结果、逐轮CSV与备份清单随Git；代码提交main，不push。复核应使用新的输出目录，汇总不是重新计时：')
 add();add('```bash\npython3 experiments/sockshop-mirrortaint/summarize_pruning_cost_audit.py \\\n  --home artifacts/pruning-contribution-audit-20261106 --formal --out /tmp/tf2-pruning-summary-new\n```')
 out.write_text('\n'.join(lines)+'\n')

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--home',required=True,type=Path);p.add_argument('--summary',required=True,type=Path);p.add_argument('--out',required=True,type=Path);a=p.parse_args();run(a.home.resolve(),a.summary.resolve(),a.out.resolve())
