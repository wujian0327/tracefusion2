# 通信消息身份与 Mall 能力修订

**Mall full/selective 各 68/103 正确、35 unknown、0 无效／错误确定答案；逐项保持历史 MT 正确的 58/88，其中正来源 32/62、已知空来源 26/26。** 原 TF 正确的 43 项全部保持。相比上一版新增 25 个已知空来源答案，尚未增加正来源保持数，剩余 30 个 MT 正确的正来源目标仍未回答，不能验收为能力对齐。

源码冻结为 `59dbdf82ec6a1e586c04c415d34ba3e95dd2c757`。同版历史 62＋29＋15 新部署及来源签名审计通过，Account40 也重新部署通过。不做性能实验，不 push。原首次迁移、C1、`8168ab7` 修订及本轮失败候选均独立保留。

## 协议与实现

通信 v2 区分服务端接收请求、客户端发送请求、客户端接收响应、服务端发送响应。根请求是父上下文，不能被用作客户端响应的消息身份。Feign `executeAndDecode` 的每次实际调用有独立调用 ID 与 W3C 子上下文；其正常／异常完成分别闭合。Feign 重试与嵌套调用分别记录。

实际 Request、负载均衡重建后的 Request、网络客户端返回的 Response、`toBuilder/build` 派生 Response、Spring 解码适配器与包装器按真实对象引用连接。核验固定 Feign 11.8、Spring 5.3.20／OpenFeign 3.1.3 的相应实现和运行事实，不以 URL、JSON 路径或数值相等选择对象。16 份类反汇编及哈希位于 `communication-library-review/`。

真实 Mall 会员登录启用了带重试支持的负载均衡客户端，管理员登录没有这一依赖差异。本轮增加的是其精确 `buildRequest` 派生事实；**一次物理 Client 调用内部的重定向／重试，以及同一 Feign 调用中多次物理 Client 执行，仍未获得逐网络尝试认证**。未支持的消息载体留为 `http-json-unbound`，不冒充入站消息，不创建认证来源边。

编解码关联实际消息与方向；同一消息、同一方向及阶段的第二次观测仍拒绝。增加事件序号或换包装对象不能绕过唯一性检查。旧捕获缺少必要坐标时不补造。原始 HTTP 审计字节不完整仍不认证 wire 投影；本任务的来源边界继续是原声明的调用返回字段。

来源调用事实新增精确静态调用者／PC 核验（`source_occurrence_protocol: 2`），避免未计划嵌套调用仅因 callee 相同而借用外层 call-id。来源声明、实际开始／完成及 Frame 必须共同吻合。

## 有限执行语义

- LCMP：精确处理两个有符号 JVM long，保留依赖与选择证据，并核对后续实际分支。没有经 double 转换比较。
- 字面量枚举状态：通用字节码证明要求 private int／long／String 字段、精确 Enum 初始化与实参赋值、字面量常量及 values 数组初始化、没有额外普通字段／静态写入或构造调用。运行时另核对类、常量身份、实际字段、初始化写入版本和字面量。
- 可变枚举、初始化回调及证明不足的形态继续拒绝该证明。反射／native 修改和共享并发修改仍超出声明保证。

没有为 Mall 字段名、状态码、保存、缓存、mapper 或日志上下文增加只读白名单。枚举字段的已知空来源来自受核验的初始化，而非输出值相同。

## 开发控制及保留的失败

默认客户端、OkHttp、重试型负载均衡 Request 重建路径分别在 full/selective 验证。每配置 5 个根请求、13 次 Feign 尝试、10 次实际客户端发送／返回，包含同值多次调用、重试、嵌套、异常后正常请求。四个正常目标按实际返回的那次源调用核验，不能替换成同值的较早／嵌套调用。错误响应、换序号重复、缺完成、错父上下文、复用尝试身份、缺旧协议坐标及断载体链均拒绝。

实际错配响应的三次连续业务结果及线程状态保持，捕获仍粘性无效。正式离线入口的 12 项保护确认：原负捕获及移除 problem、重排序号的派生副本都拒绝，后者由失败 footer 拒绝。原文件哈希不变。

最终 Mall 正捕获另作 12 项来源保护：错误 callsite、call-id、调用者及丢失调用完成均拒绝，缺失来源及歧义来源均保持 unknown。每种模式先确认原始同路径正控制为已知，再扰动派生副本；没有用路径不匹配造成的拒绝冒充来源保护。早期驱动路径错误的记录另存，不计入这些通过项。

另在默认客户端及 OkHttp 中主动断开真实服务连接；每模式 6 个根、16 次 Feign 尝试、13 次 Client.execute、11 次正常客户端返回及 2 次客户端异常完成。两类客户端的原异常原因对象、业务响应与后续线程状态均保持，异常根不计入返回目标。该控制只认证客户端调用的开始／完成，不把底层重试次数冒充已认证网络尝试。

long／枚举控制每模式 27/27 正确，其中 9 个正来源、18 个已知空来源，覆盖 long 极值、相等和超过 2⁵³ 的整数；每字段六项实际捕获扰动保护通过，另七项派生静态证明保护通过。应用调用控制各 26 已知匹配／8 必要 unknown，另 2 个异常根及预算保护保持。监测混合异常控制各 27 项业务一致、5 项父作用域检查及 RPC／异步控制保持。

上述控制使用的构建与最终业务 Agent 的 **876 个 class 字节逐项相同**，不同 JAR 打包哈希分别保存，不把控制结果当作真实应用覆盖。

通信单独修订曾先把管理员登录的一个既定查询从每模式 5 个无效变成 5 个 unknown，均无监测 problem、10 次声明来源读取完成配对。此中间结果没有计作新增正确答案。

`5f677e7` 首个全 Mall 候选暴露会员登录 Request 派生漏记：两模式各 36 正确、35 unknown、32 无效，原 32 个正来源回退。42 份捕获、评分和复现控制保留于 `final-mall-01/`／`audit-candidate-01/`，没有被后续结果覆盖。`59dbdf8` 补齐该精确派生关系后才重新冻结和部署。驱动字段错误、评分读取错误等失败也分别留档，不冒充算法成功。

## 最终业务验收

同一候选 21 个既定查询、两模式共 42 次独立新部署，先完成全部 full 再运行 selective。来源边界、输入和独立逻辑真值规则不变；本 JVM 的具体来源实例分别独立评分，不跨 JVM 比对象编号。公开字段／入口均已暴露，属于开发回归，不称未见迁移。

| API，每模式 | 目标 | 正确 | unknown | 无效／错误确定答案 |
| --- | ---: | ---: | ---: | --- |
| 会员登录 | 32 | 32 | 0 | 0／0 |
| 注册 | 8 | 8 | 0 | 0／0 |
| 管理员登录 | 30 | 0 | 30 | 0／0 |
| 密码更新 | 18 | 18 | 0 | 0／0 |
| 管理员更新 | 15 | 10 | 5 | 0／0 |
| 合计 | **103** | **68** | **35** | **0／0** |

可回答且正确比例 **68/103＝66.02%**；已知答案条件匹配 **68/68**。68 个正确答案含 32 个正来源、36 个已知空来源。两模式的 103 个目标状态逐项一致；历史 MT 正确的 58 项、MT unknown 的 5 项和 MT 错误的 5 项分别记录。后两类新增正确答案不抵消剩余 30 个历史基线能力缺口。

35 个 unknown 中，管理员登录 30 项有独立实际源实例真值；另外 5 个管理员更新行数目标仍为 `Independent logical rule unresolved`，工具 unknown 与真值不足并存。这 5 项不删出 103 的任务分母，也不据此填写完整关系 FP/FN 为零。原 7 个 handler 输出义务继续单列。

源码、Agent 及计划在业务捕获前锁定；Agent SHA256 为 `9f95c829970e238e18b6562baccfc937eee93ef36ccd5949ec25435bfa159f2f`。复核保护清单：旧首次 2322、本批外部首次 16862、C1 7248、前修订 1746 个文件哈希均未改变。逐实例结果见[配对表](communication-identity-paired-20261029.csv)。

同一冻结候选的新部署及最终审计如下，两模式分别得到相同结果，不合并成总体准确率：

| 集合，每种模式分别统计 | 实际目标 | 已知正确 | unknown | 已有状态／来源签名变化 |
| --- | ---: | ---: | ---: | ---: |
| 原 62 查询 | 431 | 428 | 3 | 0 |
| 已启封 29 字段 | 244 | 232 | 12 | 0 |
| 原 15 写入口查询 | 96 | 96 | 0 | 0 |
| Piggy Account 返回 | 40 | 40 | 0 | 0 |

62 查询继续逐项保持历史 MT 的 368 个正确实例及旧 TF 的 213 个正确实例；关系 TP397／FP0／FN3，FN包括3个unknown阳性目标。29 字段的 12 个 unknown 仍缺独立完整真值，不填写完整关系 Recall。Account 每模式 4 个正来源、36 个已知空来源，保持该任务历史 MT 正确的 36 项。已有 unknown 没有变成未受证明的 known；本次不是用旧捕获冒充新 Agent 部署。

Apollo Gson 绑定和 MT Gson 依赖校准、全 40 API 及保存／消息 sink 的完整验收均仍未完成，不用本轮成功替代。

管理员的 30 个 RPC 目标均已逐项将独立真值坐标与状态追踪对齐，两模式共 60 项的**首次依赖失效**均落在 `UmsAdminExample.createCriteriaInternal` 的 PC2：`UmsAdminExample$Criteria.<init>()V`。该构造器走父类构造链，当前通用构造 Frame 仍要求直接空 Object 初始化，因而执行不透明构造屏障。这个屏障使先前已建立的 RPC 字段依赖失效；不能把它简单标成通信缺失，或凭值相同恢复来源。

原追踪器只跟踪有普通 `call` 的失效调用，漏了构造器，因而曾把稍后的 `RequestContextHolder.getRequestAttributes()` 说成 RPC 的首次失效。逐目标独立坐标校验揭示该诊断错误；原日志保留，修正的 `all-admin-target-loss-02/summary.json` 对全部 60 项通过。上下文调用仍是更晚的独立屏障，原来它首次影响的是另一些仓储字段。本次只修诊断驱动，没有更改评分、核心或 68/103 结果。

后续仍须解释必要的父类构造、列表所有权及日志路径效果；仅支持一个构造器不能保证恢复全部 30 项。诊断只读取还原器状态，不充当真值，不据此把未知效果改为只读。

## 工件

主目录为 `artifacts/communication-identity-revision-20261029/`。`development-protocol-before-change.json` 记录改动前协议；`source-5f677e7.tar.gz`、`source-59dbdf8.tar.gz` 保存源码；各候选分别锁定 Agent、原业务 JAR、计划、输入及来源边界。`controls-07-*`、`final-long-enum-controls/`、`official-communication-guards-02/`、`final-control-Agent-equivalence.json` 保存控制及构建一致性。

最终 Mall 目录为 `final-mall-02/`，历史目录为 `final-historical-02/`，审计为 `audit-final-mall-02/`、`audit-final-historical-02/`，Account 为 `final-historical-02/account-score-first/`。来源保护为 `actual-source-guards-03/`，逐项首次失效核对为 `all-admin-target-loss-02/`。小型[结果快照](communication-identity-results-20261029.json)和[迁移台账](communication-migration-ledger-20261029.json)随 Git 保存；台账不把类数／文件数当成人工工时。

复核应指定新目录，避免覆盖先前审计：

```bash
python3 experiments/sockshop-mirrortaint/audit_communication_identity_revision.py \
  --stage mall --root artifacts/communication-identity-revision-20261029/final-mall-02 \
  --out /tmp/tf2-communication-mall-recheck-new
python3 experiments/sockshop-mirrortaint/audit_communication_identity_revision.py \
  --stage historical --root artifacts/communication-identity-revision-20261029/final-historical-02 \
  --out /tmp/tf2-communication-historical-recheck-new
python3 experiments/sockshop-mirrortaint/audit_communication_identity_revision.py \
  --stage source-guards --root artifacts/communication-identity-revision-20261029/final-mall-02 \
  --out /tmp/tf2-communication-source-guards-new
```

完整原始工件和镜像需另行备份，Git 只保存源码及小型摘要。Station 继续保留 403，不做鉴权后复验。
