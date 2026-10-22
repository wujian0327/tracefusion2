# Jackson依赖隔离与原版运行时回归

> 本页保留该阶段的原版本与口径。最新算法、能力和性能请看[截至2026-10-22完整进展](PROGRESS-20261022.md)及[隔离版三任务成本](ISOLATED-COST-20261022.md)。

**Jackson依赖覆盖已修复。最终冻结版`76d2050de6634c52db6583832aefa1e6892454c9`重新部署全部62查询，full/selective各428/431正确（99.30%）、3unknown、0错误确定答案；126个观测配置的业务Mapper哈希均与原包一致。** 这是隔离后新运行结果，没有直接沿用旧428/431。业务继续使用原版JAR，29个候选保持封存，没有新成本实验或Cart模型扩展。

## 原问题与修复

旧Agent直接打包`com.fasterxml.jackson`，由父加载器提供给业务。Sock Shop本身使用2.8.6，而Train Ticket原包使用2.8.11.3；旧运行中后者实际加载了Agent携带的2.8.6。原报告及原始证据保留，见[旧配置结果](LIBRARY-GAP-REVISION-20261022.md)。

本轮分开处理两类用途：

| 用途 | 隔离后实现 |
| --- | --- |
| Agent读计划、写事件及解析旁路原始JSON | `tracefusion.internal.jackson`，仅供Agent内部使用 |
| 业务HTTP、DTO转换、日期及UUID等实际序列化检查 | 通过业务实际对象及其加载器访问原业务Jackson |

构建器对内部JSON使用者及Jackson依赖重定位；CP索引与指令不变，只调整类文件常量池中的包名。业务检查器不再通过Java类型链接到Agent的ObjectMapper、JsonSerializer等类，而用明确的API调用桥检查实际对象。原Spring调用描述符与业务类名保持原包名；不能把业务对象强转成私有Jackson对象。

每次构建检查Agent不含`com/fasterxml/jackson/`类文件，并拒绝残留的原包直接类型链接。业务没有Jackson时，Agent自身仍能读写JSON；它不会向业务补出原包Jackson。使用两个独立加载器加载原版2.8.6和2.8.11.3的控制程序均通过。

公共契约仍是有限的人工库模型。为原业务2.8.11.3核验既有默认转换、UUID契约，保留两个独立固定哈希配置，按整组匹配；不按类自由拼接版本，也不把哈希匹配等同于对任意库行为的证明。未建模效果仍保持unknown，目标与来源边界不变。

## 实际业务版本证据

运行事件`jackson-isolation`记录实际ObjectMapper定义、类加载器身份、类字节码哈希、位置以及Agent私有Mapper。审计直接从各原业务JAR内嵌依赖取出字节，与运行时事实逐项比较。

| 原业务服务 | 原包Jackson databind | 原版ObjectMapper SHA256前缀 |
| --- | --- | --- |
| Orders、Carts | 2.8.6 | `c9d931c46efb…` |
| Shipping | 2.8.1 | `56240417490a…` |
| Station、Route、Train、Price、Basic、TicketInfo | 2.8.11.3 | `1a33365556ca…` |

Shipping由历史跨服务路径实际验证；其余8个服务也进入62查询任务。仅保存原包清单不足以证明加载正确，最终验收要求每个被观测配置均有实际加载证据。Agent内JAR中的全部854个class定义与各语义控制核对一致；归档ZIP时间戳可不同，class、清单和包结构必须相同。

元数据记录只读取类与包信息，不调用用户重写的`ObjectMapper.version()`或类加载器`toString()`。支持范围外的自定义Mapper不能因为记录版本而额外执行这些回调。

## 版本与首次失败保留

| 阶段 | 版本 | 处理 |
| --- | --- | --- |
| 原未隔离配置 | `223ea07` | 原428/431及依赖覆盖披露保留 |
| 首隔离候选 | `78a1707` | 代表业务与历史回归通过；新保护程序发现元数据调用用户version覆盖方法一次 |
| 修复后冻结版 | `76d2050` | 不再调用用户元数据回调，在新目录重新构建、捕获及审计 |

首候选的全量运行在8个已完成Orders配置后主动中止，部分捕获与清理记录保留。不能把它算作完整431结果，也不把其成功部分拼入最终版。反例位于`observer-purity-first/`，中止原因和时间在`logs/18-stop-initial-candidate.json`。

最终版使用`candidate-v2/`：控制程序、历史路径和全量业务均新运行。最终核心源码62个文件的哈希保持固定；独立实验驱动与审计代码另行保存，不修改核心来覆盖首轮结果。

## 回归结果

最终版语义控制包含统一内核、应用调用、接收集合保护、旧集合、真实Mongo/Date，以及分别在2.8.6和2.8.11.3下运行的转换和UUID控制。已知来源与预期unknown分别计数，缺失证据、自定义serializer等负控制保持拒绝。

| 最终版真实历史路径 | 匹配 | 来源关系TP / FP / FN |
| --- | ---: | --- |
| Sock Shop原选定路径 | 198/198 | 258 / 0 / 0 |
| Train Ticket原Station跨服务路径 | 31/31 | 30 / 0 / 0 |

两个路径使用原输入、原业务JAR及新Agent重新部署，没有复用旧Agent捕获。原版默认/自定义序列化控制、两个独立原库加载器及用户回调计数为0的保护也通过。33项针对执行、实例来源、绑定、集合规划和状态的单元检查通过。

最终冻结版首轮业务全部完成，没有失败配置或成功复验替换。每模式388次查询请求、431个目标实例，另85个查询请求没有目标，单列N/A；8个查询族始终未产目标，54/62个查询族至少有已知正确答案。

| 最终隔离版指标 | full | selective |
| --- | ---: | ---: |
| 规划接纳 / 拒绝 | 62 / 0 | 62 / 0 |
| 正确 / unknown / 错误确定答案 | 428 / 3 / 0 | 428 / 3 / 0 |
| 证据无效 / 分析限制 | 0 / 0 | 0 / 0 |
| 整个固定范围的正确回答率 | 99.30% | 99.30% |
| 已知答案来源实例完全匹配 | 428/428 | 428/428 |
| 关系TP / FP / FN，unknown计漏检 | 397 / 0 / 3 | 397 / 0 / 3 |
| 原MirrorTaint正确实例保留 | 368/368 | 368/368 |
| 原TF正确实例保留 | 213/213 | 213/213 |
| 两者联合正确实例保留 | 382/382 | 382/382 |

431个目标的full/selective状态逐项一致；每模式Sock Shop为128正确/131目标、3unknown，Train Ticket为300/300正确。条件匹配率100%不等于整体431/431。31个正确目标的本边界数据来源为空，故关系TP不是428。

126个观测配置包括Orders40、Carts22（含补充创建/再次读取）、Price8、Station12、Train12、Route18、Basic8、TicketInfo6。每个均验证原业务包中的Mapper定义，Shipping另由历史路径验证2.8.1。被观测JVM继续使用1CPU、768MiB、堆32m/256m、GC/JIT线程1/2；Orders的5秒Future期限未改。部署可并行，不作性能估计。

剩余3个仍是Cart首次创建商品的itemId、quantity、unitPrice，涉及未闭合的监听器、保存与容器效果模型，未因依赖隔离变成错误的确定答案。本轮不打开29个封存候选，不把开发回归作为新的未见查询泛化证据。

本轮没有重新部署MirrorTaint等外部基线；原正确集合的保留检查不等于对隔离后配置重新进行跨工具排名或成本比较。

## 工件与复核

原始目录：`artifacts/jackson-isolation-20261022/`。`logs/00…`记录协议、原包清单、初候选、负控制、中止和最终版节点；`candidate-v2/final-capability/`保存最终9个原JAR、源码快照、冻结计划及完整业务捕获；`candidate-v2/frozen-controls/`保存11组控制；`candidate-v2/legacy-live-first/`为历史真实路径。

`candidate-v2/audit-final-first/`保存逐实例独立复算、原包/运行时哈希、资源与证据收据；`candidate-code-76d2050.tar.gz`保存冻结源码。小型[审计摘要](jackson-isolation-results-20261022.json)和[逐实例CSV](jackson-isolation-instances-20261022.csv)随Git保存，原始数据与首次失败另行备份。附加缓存检查的14,400次并发哈希读取、双加载器、不可变见证及5002条事件顺序检查均通过，不并入业务准确率。

```bash
python3 experiments/sockshop-mirrortaint/audit_jackson_isolation.py \
  --root artifacts/jackson-isolation-20261022/candidate-v2/final-capability \
  --out artifacts/jackson-isolation-20261022/audit-recheck-new-directory
```

复核使用新目录，避免覆盖首轮工件。实现入口：[打包](build_distributed_plans.py)、[重定位与链接检查](isolate_agent_jackson.py)、[业务库调用桥](BusinessJackson.java)、[隔离探针](run_jackson_isolation_probe.py)、[回调保护](run_jackson_observer_purity.py)。

隔离会改变Agent实现与开销，不能直接沿用旧成本表。恢复成本比较前，仍需对最终配置重新测量；本轮不提供新的在线延迟或CPU结论。完整工件与Docker镜像不随Git同步，所有push由用户完成。

本机校验备份入口为`artifacts/jackson-isolation-backup-20261022/START-HERE.txt`。这是同盘副本，不是异机冗余，不含Docker镜像层；迁移后按digest另行准备镜像并在新目录重新构建，不复用旧绝对路径。
