# Galette接入与TF静态观测机制基线校准

**TF static已形成可执行的配置基线，固定MT及三种TF各39/39正来源正确；Galette尚未形成共同业务任务，因此没有进入正式计时。** Galette官方构建及8u504类库插桩成功，标签API小程序通过，但原high业务JAR在查询和来源适配器执行之前遇到JVM验证错误。不能把这个接入阻断记成传播错误或TF的性能胜利。

原`c8918bf`成本和“不支持selective额外在线CPU增长更慢”的结论不变；`c866d67`仍是其后单列的离线版本保护修复。本轮不重新归属旧数字，不更换任务，不增加unknown取得成本优势，不push。

## 冻结与工具准备

开始main为`a6193944b698a579149c0de31e3bdaccbfb8a443`。140项核心源码及其中30份契约／运行时JSON未改，Agent未重编译，SHA256仍为`367cbb2300e507e5db4716c4e2fcbed1a39898c5e6c6f5f23583c4c1487e2764`。新增的只是配置基线、实验驱动、独立控制和汇总。原计划逐字节复用，所有TF配置使用同一Agent、同一计划和传播语义。

协议在业务校准前封存于`artifacts/galette-static-baselines-20261111/protocol-before-calibration.json`。入口、原JAR、六组输入、来源、目标、各任务固定MT组件和正式门槛均有文件哈希；精确来源描述符另存`source_calls_exact`。命名含`contracts`的公共清单子集为25份，完整核心清单已同时封存全部30份，后补索引没有改协议或契约。

Galette固定官方提交 **`bc6002cc5ee4d6eaa30518b2d176a9831d77cb1a`**。按[官方构建与运行说明](https://github.com/neu-se/galette/tree/bc6002cc5ee4d6eaa30518b2d176a9831d77cb1a)执行`mvn -DskipTests install`，用instrument JAR生成独立Java安装，运行时使用其Java、bootclasspath及javaagent。官方源码Git状态干净，未修改或禁用校验。

| 准备项 | 实际结果与边界 |
| --- | --- |
| 构建环境 | Maven3.8.6／Temurin17.0.5+8；镜像digest `sha256:5092873778f0495464c1151df8f5c2e01a09ba37d931be719cbc1fc0f4559a07`；完整image ID、Java及modules哈希另存 |
| 官方构建 | 首次242秒后失败：补丁临时JAR跨挂载点rename失败。仅将Java临时目录设在源码同一文件系统，第二次88秒成功；两次含依赖下载，不是纯编译成本；构建CPU未测 |
| 业务基础JDK | 恢复原归档OpenJDK8u504。宿主机已变成8u512，早期预检另保留，未混入最终校准；所有最终配置挂载同一恢复版及配置 |
| 类库插桩 | 官方内部11.404秒；完整进程墙时11.47秒，user18.57秒、system7.43秒，GNU time最大RSS779516KiB。仅为准备诊断 |
| 字节变化 | 原rt.jar的19896个class中19895个改变；原业务JAR不改。不能称工具运行字节相同；工具及完整JDK文件清单另存 |
| Galette API控制 | 同值双标签求和、常量覆盖、发布后别名修改三项断言通过；仅证明API与这些控制，不是实际业务来源校准 |
| 官方测试边界 | 构建使用skipTests；没有把它写成官方完整测试套件通过 |

工具产物收据见[版本与准备收据](galette-static-tool-receipt-20261111.json)。固定MT原生SHA256仍为`e4c679206993b45c6727a4ace1d4dcff6df0ded2b80b56b27b8c86741be63fe7`。受控程序与Mall使用原B0 bundle；ZLT使用原隔离B2.2／`mt-class-build-04`，分别锁定，不混用。MT不能关闭的多字段标签、实例、调用、运行时导出及native诊断完整保留，只评分声明目标。

## TF static的定义与实际差异

这是受静态选择性插桩思想启发的**JVM机制配置基线**，不是SelectiveTaint原工具复现，也不是新的静态污点分析器。实现见[tf_static_baseline.py](tf_static_baseline.py)。

| 配置 | 固定许可与执行策略 | 必须保留的运行事实 |
| --- | --- | --- |
| full | 原完整观测模式；不启用这些值／方法体省略 | 来源、身份、版本、调用完成、异常、局部性、通信绑定及完整性全部保留 |
| static | 使用现有保守规划器的固定读站点、边界标量／成员、构造及普通写值许可；也保留既有绑定响应的持久化投影 | 原实现／哈希／JDK、精确类型、根与实际调用作用域等前提仍在省略前检查；不成立采全 |
| selective | 同一静态基础，再允许现有实时局部性、别名／发布及影响范围证书选择效果方法体收缩 | 仍保留同样的必要认证；省略后事实矛盾拒绝，不补造数据 |

static用原Agent的`service.mode=selective`加显式`service.body.observation=false`实现；目录、策略收据和CSV始终标为static，不冒充新Agent模式。两者的固定许可完全相同。没有仅为拉开差距削弱静态许可，也没有关闭来源局部性认证：**用于保持来源的局部性证书，三种TF都需要；用于额外少采方法体的动态资格，只有selective消费为省略许可。**

`plan_execution_closure.application_write_sites`及`plan_target_observation.obligations`生成固定需求／站点集合；`PlannedServiceAgent`使用固定读站点，`ExecutionKernelHooks.versionOnly/omitWrite`、`ResponseBindingHooks.SnapshotPolicy`在省略前核验原前提。`BodyObservationHooks.observe`还需要本次来源岛、实际别名／发布状态及调用实参不相交，当前没有静态证明来替代它。未增加静态指针／逃逸分析，不能将本基线解释成静态方法的能力上限。

冻结Agent在关闭body选择时仍计算并记录body资格；保留共同证书和审计。故**没有额外省略不等于没有判断工作，相同省略次数也不证明判断成本相同**。本轮没有为改善该基线速度另删核验。

## 固定任务校准

最终30份独立短部署，各六次原请求，都是新采集。完整业务响应逐项核对，物理真值在每个JVM内由实际来源调用、对象、字段和版本建立；标签／TF图仅是预测。Mall每配置登录日志均新增六条。主评分只比较共同显式数据来源；选择证据另存，不要求MT／Galette提供隐式流。

| 任务 | 原版目标 | 固定MT | TF full | TF static | TF selective | Galette |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 8非目标字段 | 6 | 6正确 | 6正确 | 6正确 | 6正确 | 未运行／6义务未评分 |
| 64非目标字段 | 6 | 6正确 | 6正确 | 6正确 | 6正确 | 未运行／6义务未评分 |
| 256非目标字段 | 6 | 6正确 | 6正确 | 6正确 | 6正确 | 启动阻断／6义务未评分 |
| related-high | 6 | 6正确 | 6正确 | 6正确 | 6正确 | 未运行／6义务未评分 |
| Mall expiresIn | 6 | 6正确 | 6正确 | 6正确 | 6正确 | 未运行／6义务未评分 |
| ZLT User原六输入 | 9 | 9正确 | 9正确 | 9正确 | 9正确 | 未运行／9义务未评分 |

表内已评分配置均业务保持、目标绑定和来源事实充分，错误确定／unknown／拒绝无效各为0；原版只作业务参照，不运行来源预测。Galette39项义务都未评分，不能写成39次传播错误。逐项分类、首道阻断及事实路径见[36行配置校准表](galette-static-calibration-20261111.csv)和[逐目标表](galette-static-targets-20261111.csv)。

related-high每个目标都匹配257个实际来源出现，不能按相同数值去重，边界载荷省略为0。三TF模式的39个声明目标在各JVM独立评分后，又按逻辑读取出现、字段路径和版本比较：答案状态、来源及selectors一致，没有跨JVM比较对象编号。本批目标selectors均为空，不能据此声称复杂选择依赖或隐式流已经充分验证；非空selectors转移由既有公共原语单测覆盖。

原六组User实际都非空，原有Client组才有空页。另在工具运行前封存`/users?page=1000000&limit=1`空页控制，没有替换六组输入。无Agent原版六次均HTTP500：后续角色查询拼成`…WHERE ru.user_id IN`，由Druid报EOFParserException。保留原始SQL错误，不修改业务、不再挑另一个成功输入；其他工具的该空页控制未运行，**空页验收未通过，不增加正来源分母**。

## 实际观测工作：统计不是速度

以下均为完整六请求短捕获（含启动），不是正式成本或测量期专属数据。构造写值省略在全部固定任务中为0，明确保留零触发。

| 任务 | 字段hook full→static→selective | 边界标量省略 static＝selective | 容器值／普通写值省略 static＝selective | selective额外body读／分支省略 |
| --- | --- | ---: | --- | --- |
| 8字段 | 108→54→54 | 48 | 0／0 | 0／0 |
| 64字段 | 780→390→390 | 384 | 0／0 | 0／0 |
| 256字段 | 3084→1542→1542 | 1536 | 0／0 | 0／0 |
| related-high | 4632→3090→3090 | 0 | 0／0 | 0／0 |
| Mall | 1140→552→522 | 270 | 36／6 | **30／36，六次具资格调用** |
| ZLT User | 951→473→473 | 759 | 0／0 | 0／0 |

static没有使用动态body资格但仍记录六次Mall资格。Mall完整事件为2491→2293→2227；其他任务static与selective事件数相同。完整协议字节及计数见[工作量CSV](galette-static-work-20261111.csv)。独立JVM的启动、对象ID、响应及元数据宽度可能造成微小字节差异；例如related-high几乎没有字节变化，不将其记成额外剪枝收益。

边界标量判断在`ResponseBindingHooks.java:186`的反射取值之前，可省该次监测字段读取及载荷构建；容器值36次的决定发生在成员值已取出之后，只少构建／持久化记录，不称少读成员。普通写值仍执行原PUTFIELD并记录新版本。字段hook降幅还包含固定读站点选择；响应持久化投影也保持相同策略，不能把所有full/static差异都归给边界载荷或body收缩。related-high少了附加hook，但257个必要来源及计算输入全部保留。

针对性控制包含同值不同来源、同值常量覆盖、新版本、别名及发布后修改、必要不透明效果unknown和守卫不成立采全。body控制static/selective各八例保持六known／二必要unknown；selective仅三例实际收缩。共享写值控制各模式8/8，必要写保留载荷；许可关闭后版本省略1→0，答案保持。每模式四类损坏证据拒绝，原语8项、写版本6项及配置2项单测通过。没有把这些小程序当成新应用覆盖或Galette业务验收。

## Galette首道阻断与停止

原high JAR按官方命令在插桩8u504上启动，Spring Boot2.7.0的JavaBeanBinder创建caller-sensitive MethodHandle时触发：

```text
java.lang.BootstrapMethodError: java.lang.VerifyError: Bad type on operand stack
java/lang/invoke/MethodHandleImpl$BindCaller$T.finalize(TagFrame)V
```

独立[非Spring反例](GaletteCallerSensitiveProbe.java)调用`MethodHandles.lookup().findStatic(Class.class,"forName",...)`：原版成功，Galette复现同一个VerifyError；[标签API控制](GaletteRuntimeProbe.java)仍成功。没有改Galette源码、忽略类库、关闭字节码验证、换JDK或换任务来通过。此结论仅限固定提交／8u504组合，不是Galette普遍不可用的证明。

失败发生在查询和业务来源适配之前。因此Galette实际mapper／RPC标记、物理调用事实与目标标签导出**尚未接入及校准**，没有伪造适配器或用TF图填标签；其他任务未机械重复相同预检。两项正式任务仍是high及Mall，门槛明确为false，正式部署数0，逐轮成本表为N/A，而不是0开销。不能比较TF／Galette共同正确任务成本，也不能从短审计进程的偶然计时推断在线或离线优势。

准备阶段还保留了容器产物权限问题、错误缺失挂载的首次preflight、驱动缺少协议副本及短采样窗口不足等失败。错误挂载不是Galette失败；真实兼容性结果使用`galette-boot-high-02`，最终校准只用`short-504`／`short-business-504`。不把初始8u512或失败结果混入本表。

## 可以据此写的结论与复核

1. 固定静态许可已经贡献了三档受控路径、ZLT和Mall的一部分观测省略，保持本批声明目标答案；不能将全部selective收益归给动态资格。
2. 动态资格在Mall上另省30次读和36次分支，在其他固定任务上没有额外省略。当前没有新正式CPU／p95／离线成本数据证明成本下降。
3. Galette基础标签API可运行，但共同业务接入受JVM验证阻断，尚不能给出双方传播能力或成本取舍的共同任务结论。
4. 原负面增长结果保留。下一道外部比较义务是解决并重新冻结Galette兼容性，再做真正的来源标记／目标导出校准；不是改变评分、删除失败或改TF核心。

主目录`artifacts/galette-static-baselines-20261111/`保留原协议、版本及完整JDK清单、官方构建、插桩Java、独立控制、30份成功校准、所有早期失败、原版空页失败及独立原始事实。最终复核为`delivery-audit-01/`；`paired-roots-01/`是同批声明目标复核，不是新部署。

```bash
python3 experiments/sockshop-mirrortaint/audit_galette_static_baselines.py \
  --out /tmp/tf2-galette-static-audit-new
python3 -m unittest discover -s experiments/sockshop-mirrortaint \
  -p test_tf_static_baseline.py -v
TF_CALIBRATION_FIXED_RUNTIME=1 python3 experiments/sockshop-mirrortaint/run_galette_static_calibration.py \
  --task high --baseline galette-preflight --out /tmp/tf2-galette-high-preflight-new
```

输出必须使用新目录。第一条仅复核已有证据，不重新计时；第三条会新建隔离部署，预期保留固定版本兼容性失败。官方准备复跑入口为`prepare_galette_baseline.py --stage build|instrument --out <新目录>`。完整数据、新构建镜像及外部二进制按[备份收据](galette-static-backup-20261111.json)保存，为本机副本；小型[结果摘要](galette-static-results-20261111.json)及版本收据随Git。分阶段代码在main提交，未push。
