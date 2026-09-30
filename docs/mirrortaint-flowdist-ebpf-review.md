# MirrorTaint、FlowDist 与 eBPF 动态溯源：论文及实现核查

日期：2026-09-30。本文区分论文设计、公开代码观察和本项目建议。已下载原始仓库、阅读论文与关键实现；没有完成两套工具的构建、部署及完整实验复现。当前项目的真实 uprobe 验证另见 [uprobe-assignment.md](uprobe-assignment.md)。

## 1. 材料和版本

| 材料 | 固定版本与实际阅读范围 |
| --- | --- |
| [MirrorTaint，ICSE 2023 论文](https://lingming.cs.illinois.edu/publications/icse2023d.pdf) | 重点阅读 IV-A–E 的状态、传播和跨服务机制，以及 V 的评估 |
| [MirrorTaint 仓库](https://github.com/MirrorTaint/MirrorTaint/tree/54fcbfc5bb3a0d7cd30309098355d999553a861b) | `54fcbfc5bb3a0d7cd30309098355d999553a861b`；README、指令列表、传播规则、部署配置、输出样例；用 CFR 0.152 阅读核心 JAR 的反编译结果 |
| [FlowDist，USENIX Security 2021 论文](https://www.usenix.org/system/files/sec21-fu-xiaoqin.pdf) | 重点阅读 §3 两阶段算法、Algorithm 1/2、§5 限制、§6 评估 |
| [FlowDist 原始 Bitbucket 仓库](https://bitbucket.org/wsucailab/flowdist/) | `9a683606aa42289e045cdbfa9391b55e79a3ac05`；实际分析入口为实验脚本调用的 `disttaint.*` |
| [FlowDist GitHub 镜像](https://github.com/baltsers/FlowDist/tree/14491152666feaf4a6b2c2f3f833e7c59b73dd57) | `14491152666feaf4a6b2c2f3f833e7c59b73dd57`；逐文件核对原始仓库的 4284 个跟踪文件，仅 README 不同 |

下载文件的 SHA-256、大小和来源见 [mirrortaint-flowdist-sources.json](mirrortaint-flowdist-sources.json)。本文的 FlowDist GitHub 代码链接指向上述已核对版本。

MirrorTaint 的 `Instrumenter/` 主要是为 Phosphor/FlowDroid 基线准备的改造工具，不能当成 MirrorTaint 核心源码。其核心以 `mirrorTaint.jar` 发布，部分符号混淆；下文保留可识别类名与方法名，反编译结果不等于作者原始源码。

## 2. MirrorTaint：在线维护来源标签

### 算法与状态

MirrorTaint 的“non-intrusive”指避免修改类字段、方法签名等元数据及 JVM/JDK 运行时；它仍通过 javaagent/ASM 改写应用字节码。它在同一个 JVM 的堆中维护影子状态，不是启动另一个 JVM 重放业务。

关键状态可抽象为：局部槽位标签 `L[i]`、操作数标签栈 `S`、对象身份标签 `H[o]`、基本类型字段标签 `F[o,f]`，以及调用之间暂存参数/返回标签的 register。这里的公式是对实现的说明性归纳，不是论文原文算法。

| 业务操作 | 实现中的对应动作 |
| --- | --- |
| 读取局部变量 | `StackFrame.visitVarInsn` 把 `L[i]` 压到标签栈 |
| 写入局部变量 | 从标签栈弹出标签，替换 `L[i]` |
| 二元算术等操作 | `StackFrame.visitInsn` 取两个操作数标签，构造新标签并合并来源；归纳为 `T(z)=T(x)∪T(y)` |
| 读写基本类型字段 | `visitFieldInsn` 调用 `queryPrimitiveFieldTaint` / `recordPrimitiveFieldTaint` |
| 调用方法 | `preVisitInvokeInsn` 将实参标签放入 register；被调用方初始化影子帧，返回时传回标签 |
| 库函数、native 边界 | `TaintPropagator` 和规则配置提供传播摘要，不是自动分析任意库内部 |

上述方法位于 JAR 中 `com.shadow.taint.agent.model.StackFrame` 和 `com.shadow.taint.agent.runtime.*`。`TaintHeap` 使用 `IdentityHashMap`，按对象身份而非值相等关联标签；其两张表在此公开版本中放在 `ThreadLocal` 内。跨线程、异步任务继承不能凭“全局标签表”这一概括默认成立，仍需单独验证。

`TaintTagger` 为 API 参数、RPC 返回、数据库查询结果等建立来源，再递归进入复合对象。`TaintCollector` 收集出口字段关联的来源。标签内部保留来源集合，并能携带传播位置/操作说明，输出中确有 `source trace`；因此它不只是一个“是否敏感”的布尔值，也不能被概括成“完全没有路径”。但这些来源记录不等同于每一次机器指令、每次字段写入都具有独立版本的完整执行历史。

### 跨服务与公开版本的差距

论文 IV-E 的方案是：各服务独立做输入到输出的污点分析；输出附上调用链上下文，之后按同一 trace 内的调用关系、匹配的输入/输出标识拼接。跨服务 trace 是关联辅助，服务内部来源关系仍由污点传播产生。

公开实现有两个必须保留的核查结论：

1. `TaintCollector.collect(String,String,Object)` 的反编译结果用格式化时间生成传给 `SinkRecord.traceId` 的值；数组重载使用新生成的 UUID。在这两个收集路径中没有看到读取分布式 tracer 上下文。因此，不能声称这个公开 JAR 已复现论文完整的跨服务关联。这里是对固定版本的观察，并非断言作者的其他版本没有相关实现。
2. [Sock Shop 部署配置](https://github.com/MirrorTaint/MirrorTaint/blob/54fcbfc5bb3a0d7cd30309098355d999553a861b/Benchmarks/microservices-demo-mt.yml) 只为 `carts`、`orders`、`shipping` 三个 Java 服务设置 `-javaagent`。它没有证明 Node.js 前端、Go 服务、队列消费者内部的字段传播都被覆盖。

可借鉴的是字段/对象身份建模、影子状态、库函数摘要和服务边界关联。不能直接继承的是任意语言覆盖、任意异步通信下的完整来源链，以及完整的历史版本追踪。论文也明确不支持隐式流；已有对象共享和模型缺口仍影响精度。

## 3. FlowDist：用执行证据逐步筛选依赖图

### 两阶段的实际含义

FlowDist 输入 Java 字节码、运行输入、指定的 source/sink，以及消息收发 API 列表。它不是纯静态分析，也不是对每个值在线维护污点标签。

**第一阶段先缩小方法范围。** 静态控制流分析限制插桩范围；运行时记录方法 entry、returned-into（从被调用方回到调用方）、消息事件与分支覆盖。方法级预分析用首次进入、最后返回到该方法的时间范围，以及进程间消息时序，保守保留可能连接 source/sink 的方法。时间先后只是筛选条件，不能单独证明数据依赖。

**第二阶段构造和细化语句依赖图。** 在保留的方法上建立静态数据/控制依赖，再用执行事件激活依赖边、按语句覆盖情况剪枝。参数和返回依赖要求相应调用事件相邻，堆定义—使用等依赖允许较晚发生。方法执行过并不表示其所有静态依赖都真实发生，因此覆盖剪枝之后仍可能存在多余边。

Algorithm 2 将跨进程路径拆为 source→发送点、中间进程接收点→发送点、最终接收点→sink 三类片段，按通信及事件时序拼接。这是依赖图可达性和片段连接，不是“最短路径就是来源”，也不要求输入输出值相等。默认方案在一次被分析的执行上做两个分析阶段；需要多次运行的是另一个 `FlowDistmul` 设计。

### 代码证据

以下路径均在固定版本的 `code/src/disttaint/` 下：

| 文件/入口 | 已确认的作用 |
| --- | --- |
| [OTAnalysisAll.java](https://github.com/baltsers/FlowDist/blob/14491152666feaf4a6b2c2f3f833e7c59b73dd57/code/src/disttaint/OTAnalysisAll.java) | 读取方法首次/末次事件和首条进程间接收记录，计算方法候选范围 |
| [OTMonitor.java](https://github.com/baltsers/FlowDist/blob/14491152666feaf4a6b2c2f3f833e7c59b73dd57/code/src/disttaint/OTMonitor.java) | 运行时监测；`packClock` / `retrieveClock` 写入/提取 Lamport 时钟，部分模式附带发送进程标识和长度 |
| [OT3Inst.java](https://github.com/baltsers/FlowDist/blob/14491152666feaf4a6b2c2f3f833e7c59b73dd57/code/src/disttaint/OT3Inst.java) | 读取 `methodList.out`、`coveredMethods.txt` 等，构造缩小后的静态图；不能仅凭类名认定默认第二阶段重新采集一次 |
| [DynTransferGraph.java](https://github.com/baltsers/FlowDist/blob/14491152666feaf4a6b2c2f3f833e7c59b73dd57/code/src/disttaint/DynTransferGraph.java) | 从静态边和方法事件构建动态图，提供覆盖/对象 ID 剪枝相关代码 |
| [OT3AnalysisAll.java](https://github.com/baltsers/FlowDist/blob/14491152666feaf4a6b2c2f3f833e7c59b73dd57/code/src/disttaint/OT3AnalysisAll.java) | source/sink 节点、前后向遍历、通信片段及结果输出；`findPathMsgToNode` 用工作集合和 visited 集合扩展，找到目标便返回 |

由此可确认：FlowDist 的分布式时序并非被动观察机器时钟，通信双方要配合处理额外元数据。不能把这部分直接替换成“eBPF 看见一次 send/recv”就视作等价。

还有一个与我们目标直接相关的实现细节：`DVTNode` 具有变量、方法、语句和时间戳字段，但 `equals/hashCode` 的节点身份未包含时间戳。`applyDynAliasChecking` 初值为 false，是否启用还取决于运行参数。这不等于工具没有动态信息，而是表明不能默认它将每次请求、每次写入都展开为独立的值版本节点。

公开脚本仍依赖旧 Java/Soot 环境，并含作者机器上的硬编码路径。论文提出线程依赖处理、复用 Indus；本次没有完成对每种线程边在默认脚本中的端到端验证，不把它写成已复现能力。

## 4. 两者能回答的问题

| 维度 | MirrorTaint | FlowDist |
| --- | --- | --- |
| 主要证据 | 执行时同步更新的来源标签 | 静态依赖及方法、分支、消息执行证据 |
| 主要结果 | 输出字段/对象关联哪些已标记来源，可带传播记录 | 指定 source/sink 之间的语句级信息流路径 |
| 反向溯源 | 从出口标签查来源，再拼接服务关系 | 从 sink 沿依赖图查可达 source 与路径 |
| 控制依赖 | 明确不支持隐式流 | 依赖图包含控制依赖；不表示所有语义和并发情况都精确 |
| 部署 | JVM agent，应用字节码插桩 | Java 静态插桩，运行监测与离线分析 |
| 不能默认的能力 | 任意语言、所有异步边、完整写入历史 | 每次请求的独立值版本、完整精确动态切片、自动识别净化 |

二者都能为“溯源”提供依据，但正确性单位不同。来源字段对、语句路径、请求实例级字段版本不能混为同一种指标。

### 评估给我们的启示

MirrorTaint 在八个开源微服务应用上选择每个应用五个耗时 API，沿具体测试执行路径人工核对数据关系。其 97.9% precision / 100% recall 是该评估范围内的结果；Phosphor 的兼容性影响了跨应用汇总，不能把汇总数简单理解为纯传播算法优劣。Sock Shop 也不是全语言覆盖。

FlowDist 使用十二个 Java 分布式系统，包括 Thrift、ZooKeeper、RocketMQ、Netty 等，输入来自集成、负载和系统测试，部分框架配有作者构造的应用。precision 人工检查路径，数量较大时抽样最多二十条，并避免同一 source/sink 对重复取样；recall 只在三个可人工建立真值的对象上检查。它报告的完美结果不代表所有系统、所有路径均已穷尽标注，且实现不自动检查 sanitization。

因此我们的实验应先约定结果单位，再建立对应真值。无需给生产程序的每个字段增加编号；可以只在专用评估夹具中独立记录少量选定操作的预期关系，不能将这些真值输入推断器。

## 5. eBPF 能替代哪些部分

Linux [uprobe 文档](https://docs.kernel.org/trace/uprobetracer.html) 和 [BCC API](https://github.com/iovisor/bcc/blob/master/docs/reference_guide.md) 支持在用户态可执行文件的选定位置挂接探针并读取寄存器/用户内存。这里的 uprobe 本身是一种动态插桩机制；可以不修改磁盘上的业务源码/二进制，但不等于运行时零干预或零开销。

| 目标 | 可行程度与所需补充 |
| --- | --- |
| 记录函数进入、参数和特定内存状态 | 可行，需要正确的 ABI、地址/结构布局和读取时机 |
| 记录选定赋值、复制、变换 | 可行，需要确定机器指令语义和覆盖范围；现有实验仅验证一个很小的子集 |
| 复现 MirrorTaint 的传播 | eBPF 负责取事件；另实现影子寄存器/内存标签、调用状态、对象生命周期、规则摘要，不能由 map 自动产生 |
| 复现 FlowDist 的分阶段图算法 | 思路适合借鉴，但仍需静态/二进制依赖建模、足够执行证据和跨进程消息配对 |
| 任意 JVM/Node.js 业务字段赋值 | 不能从普通 native 函数探针直接获得；JIT、对象布局和 GC 需要运行时适配 |
| 不增加任何运行时语义信息却完整跨语言追踪 | 目前没有依据支持这种承诺 |

Java 的动态编译生命周期可参见 [JVMTI CompiledMethodLoad/Unload](https://docs.oracle.com/en/java/javase/11/docs/specs/jvmti.html)。Go 也有专门的 [内部 ABI](https://go.dev/src/cmd/compile/abi-internal)，不能将 C 参数布局照搬过去。“最终都执行机器码”不会消除对象布局、指令优化、栈移动和运行时语义的适配工作。

额外存储的作用是保存已经观测到的证据及传播历史，不能补回未观测的决定性动作。例如两个不同来源的字段值恰好相同，出口根据一个未记录的分支选择其中之一：仅凭两个输入值和最终输出值，无法唯一判断选中了谁。若记录选择对应的加载地址、分支或等价的可靠语义证据，才可能区分。

我们现有六次赋值实验正是后一种情况：从实际加载地址及指令语义区分同值的两个来源，并验证 XOR 后的传递。它证明了局部动作可观测，不证明任意字段传播都已解决。

## 6. 建议的研究范围与算法接口

建议先研究“基于选择性运行时观测的敏感数据传播重建”，目标仍是聚合 API 敏感字段暴露，但先覆盖一种可稳定分析的运行时及少量关键转换。借鉴 FlowDist 的范围缩减和图细化，借鉴 MirrorTaint 的影子状态与传播摘要；eBPF 承担事件采集。这里是设计建议，尚不是已验证创新点。

可以按下列接口拆分，避免只有一段无法验证的伪代码：

1. **静态/二进制规划器**：输入 source/sink 和目标程序版本，产出可能依赖图、探针位置与位置对应的传播规则。若图分析不完备，必须记录由此带来的覆盖限制。
2. **动态事件采集器**：记录进程实例、线程/执行上下文、位置、局部顺序、必要地址/值和读取状态。应用请求不能只用线程 ID 代替。
3. **影子状态与版本图**：复制继承标签、变换合并依赖、常量覆盖清除旧依赖；为地址重用/多次写入建立不同内部版本。编号保存在分析器，不必写进业务字段。
4. **跨服务连接器**：使用现有 span/消息 ID 或明确验证的通信配对规则，加上序列化字段映射。仅相同 trace、时间邻近、值相同，都不足以独立建立字段依赖。
5. **反向查询器**：由某次出口字段版本沿已建立的边查来源。每条边区分“完整观测并由规则支持”“摘要规则支持”“仅候选”；存在缺事件/未建模操作时不能输出确定的唯一来源。

一个可用的分析器内部节点是 `(进程实例, 分配/对象实例, 字段或内存区间, 写入版本)`，局部变量还需执行帧身份。它不是要求业务代码给所有字段附加追踪编号，也不能仅用裸地址实现：地址可能被复用。

目前原型只支持 x86-64 直线式 32 位 load/[xor]/store。下一步更有价值的验证是同值来源、连续覆盖、分支选择、指针别名、字符串复制/拼接中的一小组真实转换，再逐步扩展到两个服务。每增加一种转换都必须明确传播模型与漏事件处理。不要立即宣称完整支持 Sock Shop 多语言链路。

### 需要衡量的结果

- 在预先声明的范围内，依赖边 precision/recall 与出口来源 precision/recall 分别是多少；不能靠拒绝全部结果获得虚假的高精度。
- 给出范围内已支持操作、范围内漏报、明确范围外操作、证据不足拒答的数量及比例。候选集合正确率不能冒充唯一来源正确率。
- 并发请求、相同值、覆盖及消息重复/重试是否混淆来源。
- 对延迟、吞吐、CPU、存储量和事件丢失的影响；eBPF 不天然保证比 JVM agent 更轻量。缓冲区满可能采集失败，见 [BPF ring buffer 文档](https://docs.kernel.org/bpf/ringbuf.html)。
- 只有当语言、source/sink、控制依赖范围及结果单位可对齐时，才把 MirrorTaint/FlowDist 当作直接数值基线；其余情况分别做方法参考和受控子集比较。

## 7. 复核入口

```bash
git clone https://github.com/MirrorTaint/MirrorTaint.git MirrorTaint
git -C MirrorTaint checkout 54fcbfc5bb3a0d7cd30309098355d999553a861b
git clone https://bitbucket.org/wsucailab/flowdist.git FlowDist
git -C FlowDist checkout 9a683606aa42289e045cdbfa9391b55e79a3ac05
```

MirrorTaint 核心 JAR 的本次阅读方式：从 [CFR 官方地址](https://www.benf.org/other/cfr/cfr-0.152.jar) 下载工具后执行 `java -jar cfr-0.152.jar MirrorTaint/mirrorTaint.jar --outputdir MirrorTaint-decompiled --jarfilter '.*taint.*' --silent true`。依赖类的反编译警告、混淆命名和未运行验证的路径需要保留，不能将反编译代码当成已运行正确的证明。

FlowDist 先读 `code/shell/Thrift/` 的 `OTBetterInstr.sh`、`OTAnalysisAll.sh`、`OT3Instr.sh`、`OT3AnalysisAll.sh`，再按入口追到上表源码。仓库中还有同名/变体实现及空占位类，不能仅凭搜索到的文件名判断默认算法。

本次只提交阅读笔记和版本清单，不将第三方仓库、论文 PDF 或反编译结果复制进本项目，也不修改现有实验程序。
