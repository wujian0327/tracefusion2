# Java 字节码采集原型

这是 TraceFusion 的**新增 JVM 采集前端试验**。使用标准 `-javaagent` 和固定 ASM 9.7.1，在类加载时自动插入记录逻辑；业务方法没有手写探针或答案。无需 Intel PT、eBPF 或 root。**现在已接入受限 Java 来源还原器，见 [PROVENANCE.md](PROVENANCE.md)。不是 FlowDist 对比，也不是通用 Java 支持声明。** 以下保留采集阶段的范围与历史验证记录。

## 运行

最新的完整/稀疏观测对照与成本入口见 [OBSERVATION-COMPARISON.md](OBSERVATION-COMPARISON.md)：`python3 experiments/java-collection/compare_observations.py --jdk /path/to/jdk`。以下 `run.py` 保留原有全步骤采集实验。

需要完整 JDK 17 或以上（`java`、`javac`、`javap`）和 Python 3.10+。首次构建会从 Maven Central 下载约 175 KiB 的固定 ASM 依赖并核对 SHA-256。

```bash
git pull --ff-only origin perf/payment-steady-state
python3 experiments/java-collection/run.py
```

如有多个 JDK，显式指定根目录：

```bash
python3 experiments/java-collection/run.py --jdk /path/to/jdk
```

运行入口构建 javaagent、编译受控程序，然后以默认 JVM 模式和 `-Xint` 各执行 7 个正常用例，同时运行 7 个边界拒绝用例和 8 项离线日志故障检查。插桩进程启用 `-Xverify:all`。每个正常用例都有独立的未插桩 JVM 结果及手工指定输出检查。所有原始日志、原始/插桩 class、字节码位置计划、`javap` 输出、命令、源码、验证结果保存在打印的 `artifacts/java-collection-*.zip`。失败包也会保留；工具链启动失败会直接报告。

已有采集可复核，不必重跑 JVM：

```bash
python3 experiments/java-collection/verify.py artifacts/java-collection-YYYYMMDD-HHMMSS-xxxxxx
```

运行后也可复用生成的 agent 采集自己的、满足下述契约的类。将路径与类名替换为实际值；`MyStaticMethods` 是被观察的静态业务方法所在类，`Main` 可以只负责输入准备和输出：

```bash
java -Xverify:all \
  -javaagent:/path/to/tracefusion-java-agent.jar \
  -Dtracefusion.classes=example.MyStaticMethods \
  -Dtracefusion.output=/path/to/new-capture-directory \
  -cp /path/to/application.jar example.Main
```

这只是采集入口；仓库中的夹具评分入口不能直接用作任意应用的正确性判定。

## 2026-10-10 本地真实 JVM 结果

在 Corretto 17.0.20.1（build 17.0.20.1+12-LTS）上构建并运行，没有用模拟器替代 JVM。当前沙箱需显式将独立 JDK 的 `lib` 目录加入进程 `LD_LIBRARY_PATH` 以加载 `libjli.so`；没有修改系统 JDK。

| 检查 | 结果 |
| --- | --- |
| 7 个受控场景 × default / `-Xint` | 14/14 采集通过，业务输出与未插桩版本一致 |
| 原始正常采集记录 | 310 条，其中原始字节码步骤 174 条 |
| 字段访问 | 24 次读、2 次写；同值对象/别名/写版本符合夹具 |
| 调用与分支 | 20 个调用实例、20 条条件方向记录 |
| 真实 JVM 拒绝场景 | 7/7 为 unknown，原因符合预期 |
| 离线日志故障 | 8/8 拒绝，包括重新编号后的步骤/字段事件缺失 |
| 完整包的再次离线复核 | 通过 |

两种执行模式并非 14 个独立业务用例。结果仅支持本原型的采集协议与受控证据；无性能、通用语义或外部工具比较结论。公开摘要与依赖/源码/回传包摘要见 `local-validation-20261010.json`。

## 此轮观察内容

| 事件 | 记录内容 |
| --- | --- |
| `class` | 被变换类名与原始 class 的 SHA-256 |
| `enter` / `exit` | 方法签名、调用实例、父调用、参数和返回值 |
| `step` | 执行的原始字节码位置，静态计划提供 opcode/操作数 |
| `branch` | 条件跳转实际 taken/not-taken；控制证据不作为数据来源标签 |
| `call` / `call_return` | 范围内静态调用的位置与完成边界 |
| `read` / `write` | 成功的 int 实例字段访问：对象编号、声明字段、值、观测写版本 |
| `finish` | 范围内事件完整性状态 `complete` 或 `unknown`，以及原因 |

字节码位置是**原始方法中可执行 opcode 的序号**，不是字节偏移、源码行号或 JIT 机器码地址。编号在插桩前生成，原始 class 与计划一起保留。`step` 在指令执行前记录；字段事件只在访问成功后记录，未完成执行不能假装成一次成功读取。`complete` 仅表示在声明契约下采集结构完整，不表示来源正确性已经证明。

对象编号由 `IdentityHashMap` 按 `==` 引用身份分配，不依赖字段值，不调用应用的 `equals/hashCode/toString`，不同对象不会因 `identityHashCode` 碰撞而合并。编号 0 表示 null。采集期间持有强引用，因此可保持对象身份，但会延长对象存活时间，**当前不适合内存开销或生产性能比较**。GC 用例只验证显式 GC 请求前后编号一致，不证明此轮实际发生了对象搬迁。

写版本只统计**已观测**的写入；版本 0 是观测范围开始前的状态，不是对象生命周期内从未写入。字段原始声明 class 也会保存；继承 owner 别名、volatile/static 字段不在此轮契约内。

## 固定边界与拒绝策略

默认仅变换 `demo.Subject`，可用 `-Dtracefusion.classes=包名.类名,另一个类名` 指定精确类白名单。只接受系统类加载器首次加载。方法必须是无同步的具体静态方法；支持经白名单审核的 int 运算、int/引用局部变量、条件分支、范围内静态调用、int 实例字段读写和返回。完整集合以 `Agent.audit` 为准。**默认 full 模式记录范围内全部支持的字节码步骤；后续 sparse 模式省略可重建的 step，仍没有字段级最优选点。**

不支持数组、long/浮点运算、对象分配、实例/虚方法调用、外部调用、异常处理器、反射、JNI、监视器和并发业务访问等。类中非构造方法发现不支持内容时，整个类拒绝插桩，并将此次采集标为 unknown。Java transformer 抛异常可能被 JVM 忽略，所以拒绝被明确写入日志；业务可继续执行原始代码，不能把该次执行算成采集成功。

构造和输入准备在观察边界之外；构造方法不插桩。当前试验契约要求：边界内不存在未观测的外部线程、反射、native 或其他 agent 对相关对象的修改；对象跨多次根调用也不能在间隙被外部改写。采集器检测进入范围的第二条应用线程，但**不能自动证明进程里没有其他线程修改对象**。这里的声明契约与 C/Go 原型一样，不能省略。

同一进程内的对象 ID 与写版本贯穿所有根调用。首次读取可记录边界初态；采集器不会自动把这些值认定为用户指定来源。事件上限默认 100,000（`-Dtracefusion.maxEvents=N`）；上限触发、类拒绝、空采集或未闭合调用都标为 unknown。写失败退出 74；进程被强杀、没有完成行或日志缺失必须由复核器拒绝。输出目录不能覆盖已有事件文件。

## 验证与下一步

受控正常用例：同值不同对象的左/右选择、两个参数互为别名、同值覆盖写入、嵌套调用、循环累加、GC 请求前后身份。它们验证采集证据，**不是七个已实现的 Java 来源查询**。负例覆盖 null 中断、第二条应用线程、数组参数、事件上限、外部调用、异常处理器、volatile 字段。

`verify.py` 检查序号、类摘要、按原始计划执行的控制流、嵌套调用配对、字段版本和值的一致性、独立夹具的实际对象/访问/返回结果。它不执行通用 JVM 污点传播，不把正常用例的答案输入采集器。default 模式的短程序也不能证明热点方法已被 JIT 编译。

后续已实现这一字节码子集的操作数栈/局部变量及字段写版本依赖传播，并提供用户指定源/目标查询，详见 [PROVENANCE.md](PROVENANCE.md)。可加 `--with-inference` 一次执行采集和还原。最新本地诊断成本与稀疏采集结果另见 [OBSERVATION-COMPARISON.md](OBSERVATION-COMPARISON.md)。尚未扩展真实 Java 程序或运行与 FlowDist 的共同任务；没有跨进程消息关联或外部工具胜负结论。

实现依据：[Java Instrumentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html)、[ASM](https://asm.ow2.io/)。依赖不提交到仓库；ASM 使用其上游 BSD 许可证。
