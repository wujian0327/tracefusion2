#!/usr/bin/env python3
"""Publish audited repository summaries, preserving each configuration's failures."""
import argparse,csv,shutil
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save

def write(root):
    first=load(root/'audit-frozen-final/audit.json');limited=load(root/'audit-quota-jvm-first/audit.json');full=load(root/'quota-all62/audit-qualified/audit.json');assert not first['all_targeted_checks_passed'] and limited['all_targeted_checks_passed'];assert full['all_passed']
    modes=full['modes'];assert all(r['states']=={'known_correct':382,'unknown':39,'planning_rejected':10}for r in modes.values())
    text=f'''# 采集开销修订、JVM线程对照与全量能力复验

算法源码冻结 `{full['algorithm_commit']}`。本轮修复固定元数据的重复读取/哈希与逐事件强制刷盘；**原 JVM 参数下仍出现超时**。另行限制 JVM 工作线程后，先通过固定72请求验收，再用同一 Agent 重新部署全部62个开发查询。新条件下 full/selective 均为 **382/431 正确，39 unknown、10规划拒绝、错误确定答案0**；所有基线正确实例和旧TF正确实例逐项保留，主轮业务验收通过，没有以成功重试替换失败。

这次通过有明确运行条件：每个被观测目标 JVM 为1 CPU、768MiB，堆32m/256m，`-XX:ParallelGCThreads=1 -XX:CICompilerCount=2`。新旧运行条件分别保留。没有延长原版 Orders 的5秒 Future 期限，没有增加业务预热，没有修改业务JAR；未做新成本比较。

**修订机制。** JDK摘要按实际 bootstrap Class 缓存，公共库摘要按实际 Class/定义加载器隔离；补齐 RequestEntity 完整不可变摘要表的缓存写入。摘要来自实际字节，不用配置中的预期哈希替代；事件仍携带原来的实现哈希。不缓存对象值、来源集合、调用结果、字段版本或保存/序列化有效性结论；这些运行事实仍逐次核验。缓存只覆盖固定进程内、固定JAR/JDK的定义，不支持类重定义或运行中替换资源。缓存锁不跨越类加载或字节读取，避免与变换器/采集器形成额外嵌套锁。

事件继续同步编号、校验和序列化，使用有界 BufferedWriter/编码器，保留全部正常捕获事件及顺序；在start、metrics、problem、abort处刷出。离线仍要求关闭标记、连续序号和必要调用闭合，缺失数据不作为完整捕获。可选时间戳/线程栈旁路默认关闭，未参与全量验收或来源计算。没有更改依赖传播语义、来源边界、profile选择或逐字段规则。

**两个目标的固定验收。** `newOrder → /customer/lastName`、`/address/postcode`，各使用原6组输入，full/selective各3轮。每配置重新创建原版Orders JVM并重置订单数据库，每轮重新建立项目和输入数据卷。两阶段各预先固定72次请求，失败之后未执行的请求继续留在分母。

| 条件 | 计划请求 | 完成 | 业务超时 | 未执行 | 已生成目标的实例来源匹配 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 新采集器，原JVM线程默认值 | 72 | 67 | 2 | 3 | 67/67 |
| 同一采集器，GC/JIT线程1/2 | 72 | 72 | 0 | 0 | 72/72 |

原参数的两次失败均为full、customer.lastName查询：第一轮第6个请求等待shipping POST结果；第三轮第3个请求等待初始GET结果。第一轮此前5个、第三轮此前2个成功目标独立复核正确；没有把失败批次的成功部分删掉。原参数full为31完成/2超时/3未执行，selective为36完成。新参数两模式各36/36完成、TP36/FP0/FN0。

独立探针确认：原Orders镜像JDK8u111在1 CPU配额下默认仍设置23个GC线程和15个JIT编译线程。另行GC日志诊断的4个配置均完成6/6；最长暂停包含启动阶段，不能误称为业务停顿。全程最大暂停约4.492秒，包含启动阶段。启动日志中的JVM运行时长只用于粗略分界，不等于精确请求或Future窗口；本组日志也不是原失败的同一次执行。线程过度并行和暂停是具体运行风险；**没有证据证明它们是历史每次超时的唯一原因**。1/2线程的新配置在本批固定验收中消除了观测到的失败，不证明超时概率恒为0，也不由此给出正式性能提升百分比。

**全量能力复验。** 72请求新配置通过后，按[事先提交的协议](quota-capability-protocol-20261021.json)运行62个原开发查询、18个入口、固定431个逻辑目标。61个接纳计划和1个UUID拒绝逐字节复用；源码、模型、库摘要及9个原版业务JAR固定。Orders的40个配置顺序部署；其余独立端口/数据卷的worker可以并行，整批不用于性能估计。符合参数的捕获共124个被观测目标JVM，包含122个主查询部署及2个Cart创建/再次读取补充部署。本轮没有采用成功业务重试来替换失败。首次参数审计发现补充驱动沿用了旧64m/G1预设；原两份来源均正确的捕获永久保留，按事先保存的修正协议重跑这两组为32m/default GC。总实际部署126个，不宣称全部126个一次就符合协议。

| 指标 | full | selective |
| --- | ---: | ---: |
| 固定目标实例 | 431 | 431 |
| 已知且来源实例完全匹配 | 382 | 382 |
| unknown | 39 | 39 |
| 规划拒绝所对应的参考目标 | 10 | 10 |
| 错误确定答案 | 0 | 0 |
| 目标级正确回答率 | 88.63% | 88.63% |
| 已知答案条件匹配率 | 382/382 | 382/382 |
| MirrorTaint正确目标逐项保留 | 368/368 | 368/368 |
| 旧TF正确目标逐项保留 | 213/213 | 213/213 |
| 两者并集逐项保留 | 382/382 | 382/382 |
| 关系TP / FP / FN（unknown及拒绝计入漏检） | 351 / 0 / 49 | 351 / 0 / 49 |
| 首次主轮的预期业务结果全部满足 | 是 | 是 |

**100%只适用于上述两个逐项保留条件，以及已知答案条件匹配率；不是431个目标全部可回答。** 剩余39个unknown为Cart.addToCart的18个和Basic.trainType的21个；UUID的10个目标仍在规划阶段拒绝。未产列表元素、预期业务负例、分析限制、证据无效各有独立状态，不把规划拒绝或业务失败算为N/A。两模式431个参考目标状态一致。

真值继续依据原业务逻辑、实际数据库/原消息及调用、对象、字段版本坐标；不调用TF传播/图连接或复制MirrorTaint标签。原版本MirrorTaint对本任务为368正确、35错误、28无法回答，仍不称其整体100%。本轮没有重新测量外部工具成本，也未增加未见查询泛化证据；29个候选一直封存。

**保护与工件。** 76项单元检查通过。新JVM运行应用调用、HTTP解码/异步、Future依赖、接收集合修改、Date/Mongo及旧集合控制；预期unknown单列。摘要控制完成14,400次并发独立字节摘要检查、不同定义加载器隔离和不可变共享表检查；5,002条缓冲事件顺序/内容一致，关闭刷出和I/O失败传播通过。两份72请求审计各有36项缺失footer、尾部截断、内部丢事件检查，均拒绝。

原始根目录：`artifacts/orders-availability-20261021/`。`diagnostic-core/`、`candidate-core/`、`buffered-core/`与source-snapshot保存开发源码和哈希；`diagnostic-first/`、`diagnostic-cached/`、`frozen-validation/`、`gc-diagnostic/`、`quota-jvm-validation/`保留全部尝试；`quota-all62/`保留本轮全量捕获、输入、真值、预测、命令及环境；初次参数审计失败位于`audit-final/`，修正后位于`audit-qualified/`；`logs/`记录重要节点。`audit-frozen-final/`是失败结果，`audit-quota-jvm-first/`和`quota-all62/audit-qualified/`是新条件结果，不能互相覆盖。

[新配置逐实例CSV](quota-capability-instances-20261021.csv)、[逐查询CSV](quota-capability-queries-20261021.csv)、[原参数72请求CSV](orders-availability-original-20261021.csv)、[线程受限72请求CSV](orders-availability-quota-20261021.csv)及[小型审计快照](orders-availability-results-20261021.json)随Git保存。完整工件与Docker镜像需另外备份；同盘归档不是异机冗余。推送由用户完成。

```bash
python3 experiments/sockshop-mirrortaint/audit_orders_availability_revision.py \\
  --root artifacts/orders-availability-20261021 \\
  --validation quota-jvm-validation \\
  --out artifacts/orders-availability-20261021/audit-quota-recheck-new-dir
python3 experiments/sockshop-mirrortaint/audit_quota_capability_acceptance.py \\
  --root artifacts/orders-availability-20261021/quota-all62 \\
  --out artifacts/orders-availability-20261021/quota-all62/audit-recheck-new-dir
```

审计输出使用新目录，保留原始文件；迁移后先按冻结源码在新目录重建，不能直接信任旧绝对路径。旧`2cefacd`的[来源核验及复验](CAPABILITY-ACCEPTANCE-20261021.md)、本轮原JVM失败和旧成本表均保留各自版本/条件。

下一步先在这个冻结实现上启封29个候选做首次覆盖验证；后续恢复成本时，原版、TF full/selective和拟比较基线必须固定并披露相同JVM参数，重测受影响任务。当前不把旧成本收益套给缓存/缓冲或新线程配置。
'''
    (HERE/'ORDERS-AVAILABILITY-20261021.md').write_text(text)
    for source,target in [(root/'audit-frozen-final/requests.csv','orders-availability-original-20261021.csv'),(root/'audit-quota-jvm-first/requests.csv','orders-availability-quota-20261021.csv'),(root/'quota-all62/audit-qualified/source-union/instances.csv','quota-capability-instances-20261021.csv')]:shutil.copyfile(source,HERE/target)
    query_rows=[]
    for q in load(root/'quota-all62/audit-qualified/source-union/queries.json'):
        query_rows.append({**{key:q.get(key)for key in ('mode','application','query','entry','requests','targets','N/A_requests')},'known_correct':q['states'].get('known_correct',0),'unknown':q['states'].get('unknown',0),'planning_rejected':q['states'].get('planning_rejected',0),'FP':q.get('fp'),'FN':q.get('fn')})
    with (HERE/'quota-capability-queries-20261021.csv').open('w',newline='')as stream:
        writer=csv.DictWriter(stream,fieldnames=list(query_rows[0]));writer.writeheader();writer.writerows(query_rows)
    small={k:v for k,v in full.items()if k not in ('raw_receipts','all_source_hashes','builds','raw_hashes','primary_business_failures')};small['qualified_observed_deployments']=124;small['actual_total_observed_deployments_including_invalid_configuration']=126;small['original_parameters_72']={k:first[k]for k in ('business_states','target_states','modes','all_targeted_checks_passed')};small['limited_threads_72']={k:limited[k]for k in ('business_states','target_states','modes','all_targeted_checks_passed')};save(HERE/'orders-availability-results-20261021.json',small)
    readme=ROOT/'README.md';old=readme.read_text();assert old.startswith('# TraceFusion 2\n\n');prefix='''2026-10-21完成[采集修订、JVM线程对照及全量复验](experiments/sockshop-mirrortaint/ORDERS-AVAILABILITY-20261021.md)，核心冻结 `f73fa5f`。
原JVM默认线程下72请求仍有2次超时、3个未执行；GC/JIT线程限制为1/2、CPU/内存/堆/5秒期限保持后，固定72请求全部完成且来源正确。
同一冻结Agent重新部署全部62查询，full/selective各 **382正确 / 39 unknown / 10拒绝 / 0错误确定答案**；首次业务验收通过，未替换失败。
新条件下逐项保留MirrorTaint正确368/368、旧TF正确213/213；整体正确回答率仍为88.63%，不是所有目标100%。
124个符合条件的部署均审计；另保留并披露Cart补充两组初次参数错误及修正重跑。29候选仍封存，无新性能结论；旧失败和成本继续按版本单列。

以下保留历史版本快照。

'''
    if '完成[采集修订、JVM线程对照及全量复验]'in old:old='# TraceFusion 2\n\n'+old.split('以下保留历史版本快照。\n\n',1)[1]
    readme.write_text('# TraceFusion 2\n\n'+prefix+old[len('# TraceFusion 2\n\n'):])
    return small

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();write(a.root.resolve())
