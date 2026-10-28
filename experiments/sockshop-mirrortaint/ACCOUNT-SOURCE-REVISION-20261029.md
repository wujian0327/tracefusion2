# Account 来源语义修订：40 目标与历史能力保持验收

**冻结版本 `78a95343c127fcc5732174b783e9d528b354a9d7` 的 Account full/selective 各 40/40 实例来源正确，其中各 4 个正来源、36 个已知空来源，历史 MT 正确的 36 项逐项保持。** 同版新部署的 62＋29＋15 查询已完成状态与来源签名保持验收，未新增错误确定答案，原 3＋12 个 unknown 保持。没有性能实验或 push。原 ae7fe8d 首次结果不改写，2322 个受保护文件哈希再次一致。

开发从 main 的可靠性检查点及说明提交 `667e2b2` 继续，最初基点 `6873a48` 和可靠性检查点 `b1380a6` 保留。[改动前协议](account-source-development-protocol-20261028.json)及工件中的原始时间记录早于本轮核心修改。Piggy 查询全部已暴露，仅作开发回归。

## 公共机制

- `Boolean.valueOf` 按实参出现传递依赖，缓存对象身份不合并来源。`BigDecimal(int)` 按真实分配与构造建立值状态，不按同值对象重挂来源。
- 空 Object 构造返回后的默认字段需要精确构造器、真实分配、字段覆盖及版本0证据；后续写入和不透明效果仍覆盖默认状态。note没有逐字段补丁。
- Assert仅覆盖固定String重载；枚举要求闭合的构造与初始化字节码。其他初始化继续不透明。
- Feign协议限定同步void、单个平坦String字段DTO和固定库。实际命令、捕获参数、worker、join Future、encoder、converter、mapper、生成器和Bean/String/Null序列化必须闭合。只保留调用前已建立且版本不变的输入字段；fallback、自定义效果或缺失证据不能认证。
- Mongo2保存限定给定String ID、无版本、自身实体返回、直接字段访问、默认转换和driver配置。完整注册监听器的类型筛选/相等性及实际分派实例也核验；未知筛选、执行应用回调、转换器子类或自定义isNew等阻断保持。检查配置先确认实现，不额外调用不认可的实现或构造器。
- Document/Date编码协议只保持已有Date依赖。保存前已unknown不能恢复；保存后同值改写仍unknown。Number、枚举和Date的JSON投影分开核验具体实现、上下文配置与实际值，不创建来源。

新增模型由实际库清单和统一策略选择，未在核心中使用Account字段名或独立真值。入口、目标和原来源边界仍由查询声明；来源不移到保存或输出。

详细条件见[公共模型与协议](ACCOUNT-PUBLIC-MODELS-20261029.md)。以下来源结论限定在原查询边界及这些固定版本/配置条件内，不代表完整 PiggyMetrics 五 API 已对齐。

## 冻结版 Account 首次完整验收

冻结后共 20 次新部署，每种模式 10 个字段计划、各 6 组原输入。没有使用旧捕获代替新 Agent；评分由原业务逻辑、实际输入/DB 事实和原始实例坐标独立生成，不依赖 TF 传播或 MT 标签。

| 指标 | ae7fe8d 首次 full/selective，各模式 | 78a9534 full | 78a9534 selective |
| --- | ---: | ---: | ---: |
| 实际目标 | 40 | 40 | 40 |
| 已知且实例正确 | 0 | **40** | **40** |
| 正来源 / 已知空来源 | 0 / 0 | 4 / 36 | 4 / 36 |
| unknown | 16 | 0 | 0 |
| 首轮拒绝/无效状态 | 16 | 0 | 0 |
| 目标未绑定 | 8 | 0 | 0 |
| 错误确定答案 | 0 | 0 | 0 |
| 关系 TP / FP / FN | 0 / 0 / 4 | 4 / 0 / 0 | 4 / 0 / 0 |
| 历史 MT 正确目标保持 | 0/36 | 36/36 | 36/36 |

`name` 的 4 个实例连接本次入口 User.username。固定初始化、默认 null 等提供 36 个已知空来源答案；不把它们说成 36 条正来源关系。`lastSeen` 的本地时钟生成事实单列，仍按原入口/仓储/RPC 数据来源边界评分，没有为了成功改变边界。首轮 MT 的 currency 4 个 unknown 不改写。

实际 null 的 `/incomes`、`/expenses` 各 4 个实例均保留为字段目标，并已得到正确空来源。它们不等同于空列表通配查询没有元素。旧 8 项目标清单遗漏仍作为首次失败记录保留。

独立评分位于 `final-candidate-01/account-score-first/`，20 份原始捕获位于 `account-final/diagnostics/collector-preservation/`。[新旧逐实例表](account-source-paired-20261029.csv)保留两模式共 80 行；本轮查询均已暴露，只称开发回归，不称未见查询。

每模式 60 次查询请求包含 40 次正常 200 与 20 次非法输入 400；这不是 40 个独立 API。正常响应除跨部署时钟外与无 Agent 原版相同，Date 在各部署内又与其实际 DB 核对。相关读取状态已校准，不声称全库、盐、令牌及时间逐字节相同。

## 同一冻结版的历史能力保持

| 集合，每种模式分别统计 | 查询族 | 实际目标 | 已知且实例正确 | unknown | 错误确定答案 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 原开发集 full / selective，各模式 | 62 | 431 | 428 | 3 | 0 |
| 已启封字段 full / selective，各模式 | 29 | 244 | 232 | 12 | 0 |
| Route/Price 写入口 full / selective，各模式 | 15 | 96 | 96 | 0 | 0 |

106 个查询族、两模式全部使用本轮新 Agent、新部署捕获；没有复用旧 Agent 捕获冒充新部署。逐项保持前版状态与规范化来源签名，没有把旧 unknown 改成 known。实际实例正确性由每个 JVM 自身的独立真值判定，不跨 JVM 强行比较对象编号。

62 查询继续保持历史 MT 正确的全部 368 项及旧 TF 正确的 213 项；每模式关系 TP397/FP0/FN3，FN 包括 3 个 unknown 阳性目标。29 字段每模式 190 次请求，其中 41 次没有目标；12 个 unknown 仍为 oracle unavailable，不计算完整关系 Recall。写入口各 96 项与前版状态和来源签名相同。Station 不在这 15 项中，继续保留原 403。

这三组与 Account 都属于开发/兼容回归，分别报告，不合成未见查询准确率。综合审计为 `final-candidate-01/audit-final-02/summary.json`；[小型结果快照](account-source-results-20261029.json)随 Git 保存。

## 最终可靠性与保护

同一冻结 Agent 的混合正常/异常控制每模式 27 项业务结果与无 Agent 一致，5 项嵌套父状态保持，另 8 项异步业务和 4 项 RPC 上下文检查通过。业务原异常对象、handler/finally 与清理保持；损坏证据仍有 problem、sidecar 与粘性 footer。

Recipient 两类原失败计划各 6 组输入，full/selective 各 12/12 响应与保存一致（10 次 200、2 次 400）。同一工作线程中的后续根 parent 均为空。四份捕获仍整批无效，不计来源正确；没有扩展 Recipient 枚举 Map 语义。

真实 Account 捕获的 22 项派生证据扰动通过，包含缺失/错配 Feign Future 与命令、缺失监听器集合、缺失保存或默认字段事实，以及数值/枚举/Date 投影冲突和粘性失败标记。每组先核验未扰动捕获可回答，再验证损坏副本不能认证；原捕获不改写。

## 同版语义控制

基础值每模式66目标：51项预期已知匹配，15项必要不透明效果unknown，另3个异常根。Feign原库控制每模式10目标：7项已知匹配、3项unknown，另1个异常根；覆盖fallback和同根重复调用。保存控制每模式文字22目标中10已知、12unknown，Date22目标中6已知、16unknown；未知筛选和转换器子类、保存前后同值修改及缺失证据保护单列。预期unknown不是正确空来源。

数值、枚举与Date原生Jackson投影的正负控制，以及正常/异常业务输出保持均有原始捕获。自定义序列化配置保留业务完成，损坏捕获仍拒绝。小程序不替代Account或历史业务验收。

这些语义控制均以冻结后重新构建的 Agent 执行，34 个构建的全部 Agent class 字节码与冻结 Agent 一致。旧绑定两模式各 54 项中 48 已知匹配、6 预期 unknown；应用调用各 34 项中 26 已知匹配、8 预期 unknown，异常与预算分类保护保持。缺失、歧义消息与来源保护、旧集合修改/虚调用保护，以及 18 项相关单元检查通过。预期 unknown 单列，不并入准确率；早期不同开发捕获的局部成功不拼入最终 40 目标分母。

## 工件及剩余范围

工件根目录 `artifacts/account-semantics-20261028/` 保留改动前协议、逐阶段失败、构建、原始事件、独立评分和配置审阅。`account-name-score-01/` 是 name 的独立开发评分；旧16unknown、16无效及8未绑定的首轮40目标仍留在原首次目录。

框架安全包装的 StackMap 重算缺陷也在本轮接入时暴露并修正，原启动失败保留。早期控制的工具类路径及评分驱动问题同样保留。最终审计的首次失败是旧集合审计仍读取“业务中止”的旧字段；只修正审计为业务保持且捕获拒绝，核心与捕获未变。Date 控制的首次依赖路径错误、守护审计的参数修正亦保留。派生审计可写入独立新目录，不覆盖首次证据。

[迁移台账](account-source-migration-ledger-20261029.json)列出公共模型、核心改动及49份可用字节码审阅文件。哈希覆盖的类数是兼容性足迹，不是人工证明条数；未虚构人工工时。

Recipient 枚举 Map 的完整来源、动态 Principal、保存 sink 查询、MT 导出校准及其余 361 项任务仍未完成。原 36 项已有保存前物理事实与缺口清单保留；本轮返回目标成功不等于保存 sink 已获来源答案。其他应用后续的冻结首次工具实验仍须通过 `run_frozen_portability.py` 使用原 ae7fe8d，不混入本轮修订。Station 保持 403，不做鉴权后复验。

## 冻结与复核入口

冻结记录锁定 87 项核心源码/契约和 10 个原版业务角色 JAR，最终哈希复查全部一致。Agent SHA256 为 `b20ba71e568672a0a91be3c113b4e6db44686d9967ddb1ca4d5f95c8ca70a45a`；冻结清单 SHA256 为 `4d29ce7414f732615cbcc49bc3b9803cac55068b876106a3f13f4c404bb3c70d`。源码归档、综合审计及完整哈希见小型结果快照和工件中的 `algorithm-freeze.json`、`source-archive.json`。

```bash
python3 experiments/sockshop-mirrortaint/audit_account_candidate.py \
  --root artifacts/account-semantics-20261028/final-candidate-01/account-final \
  --out /tmp/tf2-account-score-new --require-complete
python3 experiments/sockshop-mirrortaint/audit_account_semantics_revision.py \
  --root artifacts/account-semantics-20261028/final-candidate-01 \
  --out /tmp/tf2-account-final-audit-new --stage final
```

使用尚不存在的新输出目录。Git 保存代码、小型快照及配对 CSV；完整原始捕获、源审阅、源码包和 Docker 镜像仍需单独备份。当前结果只证明这一个 PiggyMetrics 入口及原有回归范围；没有新增未见查询或成本优势证据。
