# Date 有限语义与真实 Orders 阻断

**有限Date读取、复制、生成和默认序列化已经通过控制程序验证，但原版Orders的Date查询仍为full/selective各0/6可回答、6个unknown。** 本轮新增修复真实基线差距为0，开发台账仍是累计96、剩余73。不能把类型接纳或小程序成功记成真实应用反例已修复。

最终算法冻结为 `882497c339f833ccb6148ebec1f49fd97a1605c7`。本轮没有保存/异步模型、性能实验或未见查询验证，29个候选继续封存。[算法说明](DATE-PROJECTION-ALGORITHM-20261020.md)给出公共契约与实现入口。

## 固定范围与原业务事实

[协议](date-projection-protocol-20261020.json)在核心改动前以 `d736969` 保存。目标仍是原能力对照中的 `OrdersController.newOrder → CustomerOrder.date → /date`，没有移动入口或来源边界。

原业务调用 `Calendar.getInstance().getTime()`，将结果传入CustomerOrder构造器；构造器还先执行字段初始化，随后用参数再次写date。本轮每次原始执行都观察到同一订单对象的两个字段版本，最终使用版本2，且其Date对象是根方法实际产生的那个，不能误选构造器初始化的另一个Date。

在本协议的**输入字段来源边界**内，正常路径的预期字段来源集合为空；实际时间来自环境时钟，不能说成常量或完整来源为空。独立真值依据原字节码、实际Calendar调用、Date身份、两次字段写入及客户端ISO日期的独立毫秒换算，不调用TF传播或图连接算法决定答案。

业务继续使用九个哈希不变的原版JAR；实际Orders验证使用原Sock Shop服务。六种输入结构、购物车条目及数值沿用原能力对照：单条目、同值双条目、空购物车、零单价、修改数量及重复结构。合法重新注册产生新的用户/地址/卡片ID，日期和订单ID也自然变化；不声称与历史运行逐字节相同。两种配置则共用本轮一次准备并冻结的实际输入及消息，只有Orders观测配置与输出数据库重建。

## 冻结后的真实业务结果

| 指标 | full | selective |
| --- | ---: | ---: |
| 查询族 / 入口 | 1 / 1 | 1 / 1 |
| 实际生成Date目标 | 6 | 6 |
| 已知答案 | 0 | 0 |
| unknown | **6** | **6** |
| 证据无效 / oracle unavailable | 0 / 0 | 0 / 0 |
| N/A请求 | 0 | 0 |
| 实际目标可回答率 | **0/6** | **0/6** |
| 已知答案来源匹配率 | N/A，空样本 | N/A，空样本 |

目标、Date对象和默认序列化现在能够绑定，独立真值也全部可核验。失败仍在必要效果：每个目标的首批未解释触及包括 `CustomerOrder.toString`、`CustomerOrderRepository.save`及后续 `StringBuilder.append(Object)`。根方法的完整效果证明未成立，因此不能把产生时间与返回时间相等当作来源保持。

本轮不把关系TP/FP/FN全为零包装成成功：这6个预期字段来源为空的目标仍全部未回答。逐实例状态见[CSV](date-projection-instances-20261020.csv)，具体调用断点见原始审计的 `date-blockers.json`。

## 控制程序验证的实际能力

控制程序与真实应用分别报告，不合并分母。

| 控制套件，每配置 | 已知且来源匹配 | 预期unknown | 异常根 |
| --- | ---: | ---: | ---: |
| 统一内核，默认ISO编码 | 22/22 | 10 | 2 |
| 同一套件，数字时间戳编码 | 22/22 | 10 | 2 |
| Date及毫秒入口参数 | 4/4 | 0 | 0 |
| 有限响应转发路径 | 2/2 | 6 | 0 |

每配置包括full和selective分别执行。输入覆盖同毫秒但不同对象、左右字段选择、`Date(long)`继承毫秒输入、Date值复制、默认环境时间、无关字段写、常量覆盖、null、异常后回退以及后续正常调用。Date修改、未解释保存/helper和已受影响Calendar维持unknown。预期unknown是保守处理检查，不与已知匹配合成“准确率”。

环境生成的空字段来源与已知常量分别保留产生证据。Date修改未建模时，即使写回相同毫秒也不能恢复确定性；统一内核保守失效Date及别名，旧转发路径则要求根静态前提与全部实际子调用闭合通过。

ISO与数字编码套件各有11项运行时、Date身份/毫秒、Calendar必要调用与provider、序列化身份/库版本/值/缺失证据扰动，全部被拒绝。同值自定义Date序列化器和自定义DateFormat单独拒绝；真实Orders每配置另有5项必要证据扰动通过。

## 修复的实现缺陷与保留的首次失败

入口参数补测暴露统一图把参数叶节点键覆盖到执行结果键，导致Duplicate evidence node；同时入口Date不能按普通对象忽略其参数来源。现在Date参数与原始毫秒参数均连接实际入口实例，helper参数不重设边界。

旧转发检查还可能在Date接收者没有DTO字段快照、时间值又未变时漏掉必要不透明调用。首轮保护测试的确定答案没有证明调用效果已解释；本轮增加Date路径的实际子调用闭合条件，并补入同值常量改写，要求unknown。这个开发失败不被冒充已经完成的业务错误率实验。

其余开发记录保留：主机ISO解析不接受 `+0000` 的初次失败、Date不透明修改后把过期毫秒比较误判为证据损坏、最初扰动误选额外诊断而非必要调用事件，以及过期构建在业务请求前被中止。修复均发生在882497c冻结前；原始捕获、构建和失败说明未覆盖。

## 兼容回归

同一冻结新Agent重新部署，原版Cart单项GET的full/selective各15/15、旧Cart读取各6/6、Station/Route各60/60、TicketInfo各21/21保持来源匹配。

构造器控制各20已知匹配/4unknown，数组与lambda各38已知匹配/6unknown，应用调用各26已知匹配/8unknown；这些套件各另有2个异常根。旧绑定48已知匹配/6unknown、旧调用生命周期各7已知匹配/4unknown继续通过。原能力对照301个捕获在新离线代码上保持213正确、88unknown；后者是原Agent/计划捕获复算，不是213个目标的新部署。

同版本重新执行全部62查询、覆盖原368个基线正确目标与原213个TF正确目标的联合验收仍未完成。小程序增加支持不能减少真实反例台账，旧成本表也不对应本次候选配置。

## 工件与下一步

原始根目录：`artifacts/date-projection-revision-20261020/`。`algorithm-freeze.json`保存61份源码/配置及9个原JAR的哈希，源码包保留冻结代码。`orders-frozen/`保存新部署、共享冻结输入、独立真值、事件及预测；`semantics-frozen/`、`arguments-frozen/`、`forward-frozen/`保存控制程序。

`loop-frozen/`、`cart-gaps-frozen/`、`cart-restore-frozen/`、`ticketinfo-frozen/`保存业务回归；`legacy-offline-frozen/`明确标注历史捕获复算。总审计、逐实例、断点与原始哈希在 `audit-frozen-final/`，JDK探针和环境资料随原始根目录保存；重要节点在 `logs/00…06`。小型[审计快照](date-projection-results-20261020.json)随Git保存。

```bash
python3 experiments/sockshop-mirrortaint/audit_date_projection_revision.py \
  --root artifacts/date-projection-revision-20261020 \
  --out artifacts/date-projection-revision-20261020/audit-recheck-new-directory
```

审计写入新目录，不覆盖原始事件。完整工件需要单独备份，本机入口为 `artifacts/date-projection-backup-20261020/START-HERE.txt`；这是同盘副本，不含Docker镜像层，迁移需在新目录重建。推送由用户完成。

后续优先级应转向**Cart首次创建的有限保存效果**，再逐步处理Orders的格式化、字段效果与异步链。Date6也依赖这些效果核验，不适合继续孤立增加类型规则以追求成功数。73个缺口及29个封存候选保持原口径。
