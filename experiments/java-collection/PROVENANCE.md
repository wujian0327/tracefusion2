# Java 来源还原：第一版

当前已实现**真实 JVM 事件 → 原始字节码核对 → 依赖图 → 用户指定来源查询**，范围仍限定于采集原型的受控子集。不是 FlowDist 对比，不是跨进程或任意 Java 程序支持，也没有性能结论。

## 运行

已有上一轮完整采集目录时，直接离线还原，**无需重跑采集**：

```bash
python3 experiments/java-collection/check_inference.py \
  artifacts/java-collection-20261010-084036-762537
```

将目录替换为自己实际的采集目录。程序对先前 14 份正常记录构建查询、还原并与独立真值核对，同时验证 7 份真实 JVM 负例、8 份旧日志故障和 6 项新语义故障。输出在 `artifacts/java-inference-*`，包括每份用户查询、完整依赖图、结果与总报告。

如果还没有采集目录，可以一次执行采集与还原（完整 JDK 17+、Python 3.10+）：

```bash
python3 experiments/java-collection/run.py --with-inference
# 指定 JDK 时加 --jdk /path/to/jdk
```

单个查询不依赖夹具评分，可直接指定来源及目标：

```bash
python3 experiments/java-collection/infer.py \
  artifacts/java-collection-20261010-084036-762537/default-right \
  --query experiments/java-collection/example-query.json \
  --output artifacts/java-right-inference.json
```

此例指定两个根参数对象的 `value` 初态为来源、第三个整数参数为选择条件来源、第一次根调用的返回值为目标。结果应是值 17、直接来源 `right.value`；`selector` 单列在 `branch_observations`。源/目标由用户声明，不会自动从业务含义中发现。声明文件不包含真值。

## 算法与事件使用

1. `classfile.py` 独立读取原始 class 的常量池、方法 Code 和操作数，规范化短局部变量指令、宽索引、跳转偏移及常量引用。解码过程不调用 ASM，也不使用采集计划或夹具答案；然后与采集器保存的计划逐项核对。不支持的字节码、类版本或格式报告 unknown。当前解码类版本上限为 Java 17 的 61，构建入口用 `--release 17`。
2. `infer.py` 为每个调用维护操作数栈和局部变量，为每个 `(对象编号, 声明字段)` 保存最新定义及写版本。每个值携带类型、具体值和依赖图节点。加载、存储、整数运算及参数/返回传递建立数据边；新写入替换旧定义。
3. 对象身份用于定位内存。字段读取的数据父节点来自该字段最近一次写入或范围初态；对象引用通过**独立地址边**保存，不混入字段值的数据来源。不同对象的相等字段值不会被合并。
4. 对照日志验证计算出的分支方向、被访问对象、方法实参、写入值和返回值。即使修改日志后最终数值碰巧相同，只要与实际操作数或原始字节码不符，也拒绝给出来源结果。
5. 从目标返回节点沿数据边反向遍历，输出匹配用户来源的 `direct_sources`，以及不依赖来源命名的 `direct_origins`。图中的 `branch_predicate` 不接入返回值数据边；分支观察单独提供。

还原器不导入 `check_inference.py` 中的答案，不调用 `verify.check_fixture`。共享的 `verify.validate` 只检查日志结构、控制流顺序与观测一致性。评分器在推断完成后检查业务语义真值。

## 来源与精度口径

- `initial_field`：首次根调用的引用参数所指对象，在**整个采集范围开始时**的指定 int 字段，写版本为 0。源字段的声明 owner 必须与该参数的声明类相同；不支持继承路径的来源绑定。其数值在首次成功读取时获得，依赖原有无外部隐藏修改的契约。它不是任意后续方法入口快照，也不是远端/数据库来源。
- `argument`：指定第几次根调用的某个 int 参数。对象参数作为身份/地址证据，不作为标量数据来源；目前不支持任意中间指令注入来源标签。
- `return`：指定根调用的 int 返回值。void 返回明确为 no_sink，其他目标类型尚不支持。
- 未配置为来源的初始字段和整数参数仍保留在 `direct_origins` 中，不能假装成常量或消失；`direct_sources` 仅返回本次配置的来源名称。
- 两个来源名称若绑定同一个物理字段初态，会列入 `source_aliases`，查询结果可以同时含这两个名称，底层只有一个物理来源。不能声称能够把同一物理位置人为拆成两个不同来源。
- 此版采用**指令操作数的直接数据依赖**：算术节点依赖其输入操作数；不是最小语义依赖、逐位精确依赖或反事实因果分析。例如 `x & 0` 或 `x ^ x` 不会因为数值恒定就删除所有输入依赖。整数溢出、截断、除法和移位的具体值按 JVM 32 位 int 语义验证。
- `branch_observations` 是执行中条件操作数的来源记录，**不是针对某个输出完成了控制依赖分析**。没有通过后支配关系判定每条分支对目标的控制影响。

## 已验证结果

复用上一轮 310 条真实 JVM 原始记录，不新增采集：7 个业务场景、两种 JVM 模式共 14 份记录；GC 请求场景各含两次根返回，因此总计 16 个返回查询。

| 场景 | 直接来源结果 |
| --- | --- |
| 同值对象选择左侧 | `left.value` |
| 同值对象选择右侧 | `right.value` |
| 两个参数互为别名 | 两个来源名称均返回，并标注同一物理来源 |
| `left.value = right.value` 后返回左字段 | 仅 `right.value`，旧左来源被覆盖 |
| 选择右字段后嵌套乘二 | `right.value`，返回 34 |
| 从左字段起始，循环累加右字段 | 两者，返回 68；循环次数只在分支观察中 |
| GC 请求前后两次选择 | 依次左、右，对象编号一致 |

**16/16 查询正确，来源名称关系 TP=20、FP=0、FN=0；对应物理来源关系 18 条。** 这不是 16 个独立应用用例，也不能与先前 C/Go 实验直接相加当作统一评测。7 份原始拒绝采集、8 份旧故障、6 项新语义故障全部产生 unknown，且不返回部分来源结论。新故障包括：同值对象接收者替换、嵌套实参篡改、字节码计划局部槽修改、同值分支路径伪造、不存在的源字段、未观察到的目标。

另外，用同一个已验证 javaagent 对 `semantics/calibration/IntOps.java` 做**整数语义校准**：22 组边界输入 × 两种模式，共 44 项，未插桩 JVM、插桩 JVM、离线计算结果一致。覆盖溢出、负数除法/余数、MIN_VALUE、移位距离屏蔽和窄化转换。该程序只校准还原器，不是新增真实应用或性能优势证据。

```bash
python3 experiments/java-collection/check_integer_semantics.py \
  --jdk /path/to/jdk \
  --agent artifacts/java-collection-YYYYMMDD-HHMMSS-xxxxxx/tracefusion-java-agent.jar
```

公开报告见 `inference-validation-20261010.json`，包括独立字节码绑定、来源结果、故障原因和校准结果摘要。原始采集链保留在 `local-validation-20261010.json`。

## 当前限制与下一步

后续三组统一 v2 快照实验已验证完整边界重放，见 [BOUNDARY-COMPARISON.md](BOUNDARY-COMPARISON.md)。当前受控查询不要求内部观测；尚无真实 Java 应用或自动成本选型结论。

上述历史结果使用全步骤诊断采集。后续已增加查询入口可达方法绑定、稀疏观测还原和本地完整命令成本试验，见 [OBSERVATION-COMPARISON.md](OBSERVATION-COMPARISON.md)。不是字段级最小探针优化，也不是稳态性能结论。强引用对象表会延长对象生命周期。采集端仍不支持数组、虚调用、反射/JNI、异常处理、并发业务访问和跨进程通信；不在支持范围或证据不完整都报告 unknown。hash 和内部一致性复核不能证明远端主机或上传日志真实。

接下来应选定双方真正共同支持的正常 Java 业务查询，再扩展必要的 JVM 语义与运行时契约。当前结果只能支持“受控 Java 子集已完成采集到来源查询的闭环”，不能写成已支持 ZooKeeper/任意 Java，或已经优于 FlowDist。

语义依据：[JVM 指令集](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html)、[class 文件格式](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html)。
