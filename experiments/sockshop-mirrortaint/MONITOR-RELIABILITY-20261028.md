# 监测异常隔离修订：可靠性已验收，Account 来源尚未验收

**本次完成了监测可靠性的开发验收，尚未完成 Account 40/40 来源及最终 62＋29＋15 查询验收。** 不把业务恢复、目标绑定和来源正确合并为一个成功指标。原 `ae7fe8d` 首次 40 目标评分、失败与同线程泄漏记录保持不变；复核了原清单中的 **2192 个文件哈希**。没有性能实验或 push。

开发基点为 main `6873a487d4af1dc3c629f20db24d572660dff0fa`。改核心前保存了[开发协议](monitor-development-protocol-before-change.json)和[验收输入](monitor-acceptance-inputs-before-change.json)，包括现有 Piggy 输入、可靠性场景和历史回归范围。它们是已暴露查询的开发协议，不是未见查询封存。

## 修复机制

[MonitorSafety.java](MonitorSafety.java) 为每次实际方法进入分配独立作用域令牌，保存进入前的 Frame、待配对调用、效果检查及相关线程状态。进入失败时回滚本作用域，失败后相关监测不再消费该调用内的语义证据；业务方法继续执行。嵌套调用返回正确父状态，不清空整个线程，也不误弹父 Frame。

ACTIVE 登记按本 Frame ID 撤销，保留父 Frame 和其他线程的登记。对象身份、实际字段写入版本等语义事实不因回滚而复原成旧值：业务已经发生的写入仍然发生，损坏捕获仍然不可用。正常退出、异常退出和清理使用同一令牌，重复完成无效；清理阶段失败也留下失败标记。

插桩生成的安全包装只包围 Agent 自己的 hook，原业务 invoke 不在监测 catch 内。原方法的 Throwable 保存在独立局部槽，监测异常处理后重新抛出同一个业务对象，仍经过原 handler/finally。进入失败后返回失败令牌，禁止原来的“监测异常重抛替换业务返回”。包装也覆盖字段/分支、调用完成和框架注入位置；Java 8 接口的静态包装采用其合法调用形式。保证针对普通监测异常，VM 致命错误及 ThreadDeath 不在此恢复保证内。

HTTP 字节旁路的 read/abort 在失败作用域中仍释放对应输入捕获，释放后停止取证，不删除其他请求的捕获。RPC 开始和结束另使用自身令牌，即使没有应用 Frame，也能在开始/结束失败后恢复本次 RPC 之前的父上下文；不再按当前栈顶无条件 pop。异步 worker 的开始、返回、异常观测与业务委托调用分开，监测失败不替换委托结果或原异常，finally 恢复原父任务。

[PlannedServiceAgent.java](PlannedServiceAgent.java) 保留 problem，并增加进程内粘性 `capture_invalid`、关闭 footer 和失败 sidecar。两个离线入口均拒绝这些标记。即使在**派生保护副本**中移除 problem 行，footer 仍使其拒绝；没有伪造成功闭合或把后续状态恢复解释成证据恢复。处理仍按整批规则，不增加请求级损坏豁免。

## 可靠性结果

最新开发构建为 `artifacts/monitor-reliability-account-20261028/reliability-build-04/`，Agent SHA256：

`d7bfbe0f125dd7ee86e10599d4716f159169bd14e3f020fc1f57ad7fc63776e5`

可靠性源码检查点提交为 **`b1380a62a0189bc9991368d18757602d19995565`**，归档与来源哈希见 `artifacts/monitor-reliability-account-20261028/reliability-checkpoint-freeze.json`。补充保护清单锁定 2322 个首次捕获、评分、泄漏诊断和保存事实文件。

这是已核对源码/二进制的可靠性开发检查点，**不是完成来源扩展后的最终算法冻结**。

| 检查，每种模式单独验收 | full | selective |
| --- | ---: | ---: |
| 独立小程序业务结果与无 Agent 相同 | 27/27 | 27/27 |
| 嵌套失败后父 Frame/ACTIVE 保持 | 5/5 | 5/5 |
| 异步监测失败下返回/原异常及父任务保持 | 8/8 | 8/8 |
| RPC 失败及重复完成后父上下文保持 | 4/4 | 4/4 |
| 原版 Recipient：两类原失败计划，各 6 输入 | 12/12 | 12/12 |
| Recipient 合法响应 / 非法响应 | 10×200 / 2×400 | 10×200 / 2×400 |
| Recipient 后续根 parent 均为空，且各部署同一工作线程 | 10/10 | 10/10 |

27 个业务场景包含正常→进入失败→正常→业务异常→正常、ACTIVE 登记后失败、嵌套进入/退出/清理失败、原 checked exception/Error 对象、重抛、原 catch/finally、只读保护触发但业务写入保持和 Java 8 接口。每个根结束后核验 Frame、scope、pending、调用、效果、构造器、保存、转换及 ACTIVE 无本次残留。

Recipient 继续使用原版 JAR、合法 OAuth 测试身份及原输入，包含非空枚举 Map、空 Map、非法 email。选取原 read-forward 运行时检查失败计划与原 Map 快照失败计划，两种模式各独立部署。响应和完整 Recipient 保存内容与无 Agent 一致；时钟只在跨部署比较时归一化，各部署自己的 Date 仍与其实际 DB 值逐项核对。非法请求的前后 DB 完全相同。

**四份 Recipient 捕获均仍为整批无效，不是来源正确。** 原 JDK/枚举 Map 的必要证据限制没有在本次被放宽。原首次 HTTP 状态与新状态见[逐请求表](monitor-recipient-paired-20261028.csv)。原第一批与后续单线程诊断使用各自目录，未覆盖为新成功结果。

新 Agent 的应用调用保护程序再次通过：每模式 34 目标中 26 已知匹配、8 必要不透明效果 unknown，另 2 个异常根；6 项实际捕获扰动及 analysis_limited 状态保护保持。新增跨服务回归使用与第四版全部 Agent class 哈希相同的新构建，原五服务票价 full/selective 各 **38/38 匹配、TP92、FP/FN/unknown0**，另各 2 目标 N/A；同源模板只作可靠性回归，不作新查询证据。原 62＋29＋15 的 **106 份静态计划完全不变**，这不是 106 查询的新业务验收。另 24 项契约适用性、绑定、状态和 alias 单元检查通过。预期 unknown 不并入来源匹配率。

旧语义控制也已用当前 Agent 重新采集：绑定 full/selective 各 54 项中 48 已知匹配、6 必要 helper unknown；旧调用生命周期各 11 目标中 7 已知匹配、4 unknown，另各 2 异常根；旧集合各 10/10 匹配，indexOf 篡改、接收集合修改及虚调用保护保持。只读组合控制每模式 48 项中 18 已知匹配、30 unknown，另各 1 类自定义列表契约拒绝。预期 unknown 与拒绝不并入来源匹配率。

旧自定义 serializer、集合修改/虚调用负控制曾把“业务被监测异常中止”当作拒绝标准，首次兼容失败目录保留。测试修订为：业务输出必须与无 Agent 一致，problem/footer 必须存在，正式离线入口必须拒绝整批。没有把不支持行为改为已支持，也没有删除拒绝保护。相关独立测试调整不改变业务 JAR。

## Account：已定位断点，尚未实现所需效果模型

针对原 name 查询，保持还原语义不变，沿首次捕获跟踪进入保守失效的位置。以下是 `AccountServiceImpl.create` 的实际字节码 PC，不是按字段名称新增的传播规则：

| PC | 调用或构造 | 当前阻断与所需核验 |
| ---: | --- | --- |
| 16 | `Assert.isNull(Object,String)` | 首次保守失效；尚无当前库的精确调用效果解释 |
| 20 | `AuthServiceClient.createUser(User)` | 不透明远端客户端调用，可能影响实参；不能凭调用前后同值保持来源 |
| 29、38 | `BigDecimal.<init>(int)` | 当前构造器效果不支持，需固定 JDK 的有限数值构造语义 |
| 32 | `Currency.getDefault()` | 当前拒绝外部应用类静态初始化；需通用枚举初始化/常量读取证明，不能为 USD 写来源补丁 |
| 42、46 | `Boolean.valueOf(boolean)` | 尚未接入当前执行路径的精确装箱语义 |
| 67 | `AccountRepository.save(Object)` | 当前 Spring Data 版本没有已审阅保存契约，保存后必要字段依赖失效 |

四个目标的第一次状态也已分别追踪，而非都笼统归为 save：

| 目标，每族 4 实例 | 第一次具体状态 |
| --- | --- |
| name | User.username 在 PC16/20 的屏障后失效，PC55 调 setName 时写入的依赖已是 unknown；保存后仍 unknown |
| note | 无 setter 写入，实际 version0/null；当前还原器没有为该分配建立默认字段的已知状态，不能说它曾有已知依赖后又丢失 |
| deposit | PC42 装箱未解释，PC43 setter 写入时已 unknown；PC67 保存另有屏障 |
| capitalization | PC46 装箱未解释，PC47 setter 写入时已 unknown；PC67 保存另有屏障 |

逐目标诊断见 `account-first-loss-per-target-01/` 和[小型断点快照](monitor-account-first-loss-20261028.json)。诊断读取还原器的状态用于查错，不参与独立真值。

这是执行中出现的屏障序列。不能仅凭第一处次数推断修复收益，也不能宣称去掉 Assert 屏障就能回答 name 或另外 12 个目标。完整逐调用记录在 `account-first-loss/poison-trace.json`。

NumberSerializer、当前 Date 序列化库和枚举投影仍待有限模型；没有以补哈希代替语义审阅。16 个原 unknown 和这些投影限制仍不能算已修复。

另外，使用现有通用规划器增加了 `/incomes`、`/expenses` **字段**查询，并用第二版开发 Agent 真实部署 full/selective。每模式 **8/8 实际 null 字段已绑定，仍 8 unknown，0 已知来源**。它们没有变成 N/A；空容器的 `/*` 没有成员，才没有元素目标。这一结果未冒充最新第四版 Agent 的重新部署验收。它说明原候选清单遗漏可以补齐，但没有解决默认值和保存效果的来源证明。

为避免猜测客户端模型，另加**独立诊断 Agent**，在新目录记录真实配置类型，不生成来源边或参与真值评分。实际 authClient 是 `feign.hystrix.HystrixInvocationHandler`，fallbackFactory 为 null，dispatch 为 SynchronousMethodHandler，编码器为 SpringEncoder，并有 Sleuth 客户端与 OAuth2 interceptor；它不是简单的直接只读 helper。由此不能套用已有 Spring AOP 异步契约。诊断原字节码及 16 个依赖类的 javap 审阅文件单独保留；它们尚不构成已完成的效果证明。

## 未完成的验收与保留范围

- Account full/selective 各 40/40 以及历史 MT 正确 36 个目标保持：**未完成，不报告修复版正确率**。首次仍是 MT 36/40，TF 两模式各 0/40 已知正确。
- 原 62 查询、29 字段及 15 写入口的同一最终冻结版新部署及来源签名比较：**尚未执行**。当前小程序兼容检查不能替代这三组业务回归，旧捕获也未冒充新 Agent 部署。
- Recipient 完整枚举 Map 来源、动态 Principal、保存 sink 查询及 MT 导出校准未扩展；原 36 项已有保存前事实和其余任务缺口继续保留。
- 其他应用的冻结首次工具运行仍须使用未改的 ae7fe8d。新增 [冻结运行入口](run_frozen_portability.py) 从改动前源码快照加载原工具，并核验全部 68 项原源码、原任务、原 native JAR 和原 Agent，仅处理文件位置迁移。

## 工件与复核

主目录：`artifacts/monitor-reliability-account-20261028/`。最新证据为 `fixture-07/`、`recipient-03/`、`reliability-audit-05/`、`application-compatibility-03/`、`null-binding-audit-01/` 及 `configuration-probe-02/`。早期构建、驱动竞争/编译失败和原始日志均保留；未删除失败后只留成功。

[小型结果快照](monitor-reliability-results-20261028.json)含二进制及捕获哈希。完整原始工件和镜像不随 Git 保存。

```bash
python3 experiments/sockshop-mirrortaint/run_monitor_reliability_fixture.py \
  --build artifacts/monitor-reliability-account-20261028/reliability-build-04 \
  --out /tmp/tf2-monitor-fixture-new
python3 experiments/sockshop-mirrortaint/audit_monitor_reliability.py \
  --root artifacts/monitor-reliability-account-20261028 \
  --recipient-subdir recipient-03 --out /tmp/tf2-monitor-audit-new
```

输出应使用新目录。可靠性检查点通过后，下一阶段仍按原协议完成有限调用/保存与序列化语义，再冻结最终候选并运行全量能力保持验收；本文件不将这个后续阶段记作完成。
