# Java 查询入口绑定与稀疏观测对照

本文保留 v1 两组实验。后续已完成统一 v2 快照的三组实验，见 [BOUNDARY-COMPARISON.md](BOUNDARY-COMPARISON.md)，不可将两轮不同快照协议的数字直接合表。

此轮完成**同一原始字节码、同一来源语义下，full 与 sparse 两组真实 JVM 采集、独立还原及完整命令成本比较**。没有新增业务函数，只增加调用原有 `Subject.sum` 的负载驱动。Java Agent/ASM 采集，不使用 eBPF；不是 FlowDist/MirrorTaint 的复现或比较，不是实际 Java 应用适用性证明。

## 算法和边界

`observation.py` 从用户声明的入口签名出发，独立解码原始 class，计算静态调用可达方法闭包。现仅支持同一应用类内的闭包。入口签名需要显式配置，因为根调用序号不能在执行前唯一定位方法。查询内容和原始 class 摘要绑定进 `observation.properties`；采集端核对类摘要，还原端重新解码和核对闭包、查询与日志摘要。

- `full`：在相同查询入口闭包内，记录每条原始指令的 step，并记录全部字段、分支、调用和返回事件。
- `sparse`：使用相同闭包，保留全部字段读写、分支方向、调用前后、实参和返回证据，不插入 step 记录调用。这是真正减少插桩，不是先完整采集再过滤文件。
- 还原端从方法入口或上一观测后开始，按原始字节码补出确定的指令步骤，遇到第一个必须观测的位置就停下匹配事件。不能为了迎合下一条日志而跳过缺失的字段/调用事件。普通跳转由静态目标恢复；条件跳转由观测方向推进，再由语义引擎按实际操作数独立核对方向。
- 派生步骤只存在于内存中，带 `derived` 和对应原始序号。原始文件不补写、不改序号；统计事件数只算真实采集行。每次展开有指令上限，异常、不闭合或证据不足返回 unknown。

这是**方法入口粒度的查询范围绑定＋可重建步骤省略**，尚未根据具体目标字段执行细粒度反向切片，没有省略任何字段或分支观测，也没有证明探针全局最少。来源标签选择本身不会进一步改变该闭包。两组使用相同闭包，因此性能差异衡量 step 省略，不把未执行方法的静态裁剪计成动态收益。

原有无隐藏修改、字段 owner、单应用线程、强引用对象身份、受限字节码等契约继续适用。闭包之外的方法可能不插桩，因此要求它们不修改范围内相关状态；没有自动证明所有权。根序号指该采集范围中实际记录的根调用；若其他调用者直接调用闭包中的辅助方法并形成不同根入口，推断拒绝。初始字段来源仍止于第一根调用的对象初态，不是数据库或远端来源。

## 运行和复核

Linux、完整 JDK 17+、Python 3.10+、C 编译器 `cc`；ASM 仍固定 9.7.1 并校验摘要。

```bash
git pull --ff-only origin perf/payment-steady-state
python3 experiments/java-collection/compare_observations.py --jdk /path/to/jdk
```

默认同一 JVM 模式下比较 full/sparse，正确性包含 default 和 `-Xint`；成本使用 default，每次执行 200 次原有 sum，1 个准备块＋6 个正式配对块，每块 native/full/sparse 顺序按固定种子打乱并记录。构建、离线入口规划在计时外。

程序打印 `artifacts/java-observation-*` 目录，包含原始事件、原始/插桩 class、计划、查询、完整依赖图、运行命令、原始测量、源码快照和摘要清单。复核不重新启动 JVM：

```bash
python3 experiments/java-collection/verify_observations.py \
  artifacts/java-observation-YYYYMMDD-HHMMSS-xxxxxx \
  --output artifacts/java-observation-verification-new
```

若成本阶段失败，可用 `--reuse-correctness <原目录>` 复用已完成的 28 份对照记录与 12 项检查；会核对文件摘要和采集/还原源码。它不是跳过正确性要求或接受失败结果。

单独生成配置示例：

```bash
python3 experiments/java-collection/observation.py \
  --classes /path/to/fixture-classes \
  --entry 'demo/Subject.choose(Ldemo/Cell;Ldemo/Cell;I)I' \
  --query experiments/java-collection/example-query.json \
  --output /path/to/query.properties

java -Xverify:all -javaagent:/path/to/tracefusion-java-agent.jar \
  -Dtracefusion.scope=/path/to/query.properties -Dtracefusion.mode=sparse \
  -Dtracefusion.output=/path/to/new-capture \
  -cp /path/to/fixture-classes demo.Driver right
```

随后使用原有 `infer.py --query ... --output ...`。默认 full、无 scope 的旧日志和旧查询仍可读取。

## 2026-10-10 正确性结果

Corretto 17.0.20.1+12-LTS，本地实际 JVM 执行。7 个原有场景 × 2 个 JVM 模式 × 2 种采集方式，共 28 份正常采集。每组 16 个返回值查询，含 GC 请求场景的两个返回；不是 16 个独立应用。

| 指标 | full | sparse |
| --- | ---: | ---: |
| 正确来源查询 | 16/16 | 16/16 |
| 原始事件 | 310 | 136 |
| 原始 step 事件 | 174 | 0 |
| 离线补出的 step | 0 | 174 |

事件减少 **56.13%**；同一场景的完整依赖图、来源结果、别名和条件操作数来源全部逐项一致，而非仅比较最终数值。两组字段来源均对应独立夹具真值。

另外，10 项日志/绑定故障＋2 次真实 JVM 拒绝场景（null、第二应用线程），以及复核时新增的 6 项写入/调用故障，全部 unknown，共 **18/18**。包括重新编号后删除字段/分支/写入/调用/返回事件、同值对象替换、错误分支、写版本、实参、scope/原始 class/查询绑定改变。此数不与此前实验拒绝检查累加为新覆盖。

## 本地诊断成本结果

最终采集目录：`java-observation-20261010-092411-937152`。正确性复用此前本轮已通过的采集，成本另行测量。公开记录见 `observation-validation-20261010.json`，包括配对原始测量和离线复核摘要。

**这些是完整命令测量，包含 JVM 启动、类加载、运行时 ASM 变换和日志写出；不是业务请求延迟或稳态性能。** Java Agent 在业务进程内，因此在线 CPU 是业务和采集合计，未分离出单独采集进程。离线包含 Python 启动、字节码核对、稀疏步骤展开、依赖图构建、查询和完整 JSON 写出。端到端时间/CPU 为每次在线和离线测量之和；不包含人工整理、构建或静态入口规划。缓冲写入不等于 fsync 持久化。

每次调用原有 sum 200 次，输入及循环次数相同；检查总输出及第一、最后根返回的来源。准备块运行于独立 JVM，只作为文件缓存等准备，不能声称预热了后续 JVM 的 JIT。未固定 CPU、未控制共享宿主负载，不能外推为生产性能。

| 指标（6 次正式运行的中位数） | 无插桩 | full | sparse |
| --- | ---: | ---: | ---: |
| 在线完整命令耗时 | 65.07 ms | 266.07 ms | 239.37 ms |
| 在线进程 CPU | 73.90 ms | 477.73 ms | 370.05 ms |
| 离线完整命令耗时 | — | 178.30 ms | 164.83 ms |
| 在线＋离线耗时 | 65.07 ms | 446.33 ms | 404.78 ms |
| 在线＋离线 CPU | 73.90 ms | 653.44 ms | 531.91 ms |
| 原始事件数 | 0 | 10,003 | 2,003 |
| 原始日志字节数 | 0 | 1,186,524 | 259,442 |

合计中位数来自每对实际合计，不要求等于各列中位数之和。Java 多线程可能使总 CPU 大于墙钟时间。

相对 full 的**逐块配对降幅中位数**：事件 **79.98%**，日志体积 **78.13%**，在线耗时 **11.20%**，在线 CPU **23.58%**，端到端耗时 **8.00%**，端到端 CPU **18.69%**。这些百分比不是两个组中位数相除。在线耗时降幅范围 **−0.71%～20.18%**，6 对中有 1 对 sparse 略慢；端到端降幅 **2.70%～16.99%**。

两种采集都明显慢于无插桩基线。结果只能支持本地受控负载上省略 step 降低了诊断成本，不支持低绝对开销、强基线优势、真实服务性能或论文级普遍收益。

### 内存和计时限制

计时使用阻塞等待＋独立超时计时器，避免 `Popen.wait(timeout)` 的轮询量化污染短进程墙钟。CPU/RSS 由新 exec 的轻量 C 监督进程 fork 后调用 wait4 记录，避免直接继承 Python 分析器的大堆。

当前环境不暴露 `/proc/self/statm`，无法核对监督进程的实际内存下限。**RSS 原值保留，但 `memory_measurement_qualified=false`，不报告内存降幅或方法胜负。** 后续主机测量需继续核验内存统计机制，不能把不可用信息填成零或当作无内存开销。

## 研究含义

此轮证明受控 Java 子集可以省略确定性执行步骤并保持来源答案，提供了方法入口绑定和完整成本的可复现起点。它没有实现字段查询驱动的观测充分性算法或成本自适应选型，也没有与完整边界快照重放等更强自实现方法比较。下一阶段需在统一来源语义下加入这些控制组并扩展真实 Java 路径，再决定论文主张。
