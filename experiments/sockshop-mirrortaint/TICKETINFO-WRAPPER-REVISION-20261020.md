# TicketInfo 包装与来源实例修订

**原版 TicketInfo 三个字段的21个基线领先实例，最终冻结版 full/selective 各21/21来源完全匹配，TP21、FP/FN/unknown均为0。** 三个字段来自同一个入口，使用原先暴露的八种输入模板，不是新的未见查询泛化结果。

最终算法冻结为 `19b11b6d4fd1d344550c307a0acabe4dbf7548cd`。本轮新增修复21个暴露反例，开发台账累计修复96个、剩余73个。**尚未完成同一个新冻结版本的62查询全量验收，不能把历史213个成功与阶段修复数拼成新版整体正确率。** 29个未测候选继续封存，没有新增性能实验。

## 固定任务与首次冻结

[协议](ticketinfo-wrapper-protocol-20261020.json)在核心修改前以 `1413f23` 保存，沿用原62查询能力对照中的三个 TicketInfo 查询、原版业务JAR、输入与来源边界。九个原业务JAR的哈希保持一致，实际业务部署使用六个原版 Train Ticket 服务及各自数据卷。

| 阶段 | 版本 | 结果与用途 |
| --- | --- | --- |
| 上阶段 | `3f78922` | TicketInfo21在框架构造器处规划拒绝 |
| 首次核心冻结 | `16abcda` | full21个目标全部unknown，未产生错误确定答案 |
| 最终核心冻结 | **`19b11b6`** | 补齐原Boot JAXB转换器类哈希，随后重新构建、重新部署两种配置 |

首次冻结增加了转换器类核验。原版容器中，Spring Boot 的实际列表比单独 `new RestTemplate()` 控制程序多了 JAXB 转换器，因此有限契约拒绝赋予确定来源。原始三组full捕获及21个unknown完整保留；在确认这一共同原因后中止尚在启动的selective部署。最终版本只补原版类哈希和有限允许集合，没有删除失败查询或放行任意转换器。两个冻结记录、源码包及首轮预测分别保存。

开发首轮还因比较错误响应中的运行时时间戳而中止。后来只排除错误JSON中的 `timestamp` 比较，正常业务响应、其他错误字段、请求和数据库事实仍严格核对。该次七个成功请求及失败日志保留，不充当完整套件。

## 最终冻结后的真实业务结果

入口为 `TicketInfoServiceImpl.queryForTravel`。每个查询独立部署，先完成三个full，再执行三个selective；每个查询使用原八种输入：正常、同值、重排、短距离、缺失Route/Price/Station/Train。前七种实际生成目标，缺失Train时原业务HTTP500，没有所查询字段，单列N/A。

| 固定目标路径 | full已知且匹配 | selective已知且匹配 | 每配置N/A请求 |
| --- | ---: | ---: | ---: |
| `/data/trainType/id` | 7/7 | 7/7 | 1 |
| `/data/prices/economyClass` | 7/7 | 7/7 | 1 |
| `/data/trainType/averageSpeed` | 7/7 | 7/7 | 1 |
| 合计 | **21/21** | **21/21** | **3** |

每配置24个“查询—请求”、21个实际目标、已知21、unknown0、证据无效0，TP21/FP0/FN0。实际目标可回答率与已知答案实例完全匹配率均为100%。N/A的分母是请求，不是目标；三个查询重复使用八种模板，不能表述为24种独立输入。两种配置的42条实例记录见[逐项CSV](ticketinfo-wrapper-instances-20261020.csv)。

原MirrorTaint正确、TF规划拒绝的对应21条实例逐一核对；新部署的请求、数据库文档和客户端业务响应与原任务一致。来源真值来自原方法直接返回 `exchange(...).getBody()` 的业务逻辑，以及本次实际RPC读取、对象、Map条目与版本；不使用TF传播或MirrorTaint标签决定预期来源。

## 这次恢复能力的机制

新增有限的 `HttpEntity` null-header包装、固定 `RestTemplate.exchange` 与 `ResponseEntity.getBody` 契约，并核对Class常量的真实身份和字节码哈希。每次调用只有一种解释入口，不重复消费事件。

实际返回体的 `data` 是LinkedHashMap，嵌套内容也不是声明中的TrainType/TravelResult实例。现在响应路径绑定到实际 `@map:id`、`@map:economyClass`、`@map:averageSpeed`，不伪造DTO字段。返回包装的body身份、具体RPC读取及字段阶段一致，才把目标连接到声明边界处的来源。

请求及可能全局状态仍按不透明效果保守失效；只有该次合格的新响应读取能引入来源。保存和异步没有被统称为只读。返回快照只用于目标绑定，不能创建来源。有限前提不满足时保留unknown，必要身份或消息证据矛盾则拒绝。详细机制、版本清单与代码入口见[算法说明](TICKETINFO-WRAPPER-ALGORITHM-20261020.md)。

查询继续只声明入口、目标字段/响应路径与来源边界；三个查询统一启用已有execution/application调用策略，没有逐字段传播补丁。新增Spring框架契约是人工审查的公共模型，并不属于完全无需人工库知识的分析。

## 语义保护与兼容回归

| 检查 | full | selective |
| --- | ---: | ---: |
| 原版Cart单项GET回归 | 15/15 | 15/15 |
| 原版Cart列表读取恢复 | 6/6 | 6/6 |
| 原版Station/Route循环回归 | 60/60 | 60/60 |
| 真实Spring HTTP小程序已知来源匹配 | 6/6 | 6/6 |
| 同小程序预期unknown | 6 | 6 |
| 同小程序异常根 / 无目标请求 | 2 / 2 | 2 / 2 |

HTTP小程序两轮混合正常与异常请求，包含连续两个同值RPC并返回第二次结果、默认null条目、空Map，以及非空headers、自定义RestTemplate和必要不透明helper。后面三种按有限契约保持unknown，不合并成来源准确率。每配置12项Class、库版本、body、父消息、读取缺失/歧义及getBody扰动均被拒绝；每个真实TicketInfo查询、每配置另有7项必要证据扰动通过。

尝试修改接收Map的小程序捕获触发已有只读保护并拒绝，保留该失败工件；不把采集失败计作正确来源。历史缺失构造写入见证仍被拒绝。构造器控制各20个已知匹配/4预期unknown，数组与lambda控制各38已知匹配/6预期unknown，应用调用控制各26已知匹配/8预期unknown；各自另有2个异常根。旧绑定48已知匹配/6unknown、旧调用生命周期各7已知匹配/4unknown、旧集合各10/10继续通过。

原能力对照中已执行的301个目标，使用原Agent、原计划和原始捕获在新离线代码上复算，保持213正确、88unknown。**这不是213个目标的新Agent重新部署。** 本轮Cart与Station/Route业务回归则确实使用新Agent重新部署。

构造器及数组/lambda的开发捕获在最终冻结后复算时，逐项证明生成计划相等、全部Agent class字节码哈希相等；它们不算新独立部署。最终JAXB修订只影响framework配置，未使用该契约的Cart捕获同样保留实际构建、计划与哈希证明。一次旧loop套件因配置哈希变化触发保护而中止，最终loop套件已在新目录重建、完整重新部署，不把中止套件冒充成功。

## 当前能力边界

原169个基线领先实例的开发台账为：循环阶段60、Cart单项GET15、本阶段TicketInfo21，累计96，剩余73。余项仍是Orders66、Date6、Cart首次创建1；它们是当前开发缺口，不是保证一次扩展即可恢复的数量。

仍需使用一个统一冻结策略重新部署全部62查询的full/selective，确认原368个基线正确目标及原213个TF正确目标的联合条件，且不新增错误确定答案，才能宣布至少382/431验收通过。本阶段不启封29候选，也不把旧成本表移用于新内核。

## 工件与复核

根目录为 `artifacts/ticketinfo-wrapper-revision-20261020/`。`algorithm-freeze-first.json`、`algorithm-freeze.json`及两个源码包保存首次与最终版本；`ticketinfo-frozen/`保留首冻结unknown，`ticketinfo-final/`保存最终六次部署的原始事件、独立真值与预测。

`loop-final/`、`cart-gaps-frozen/`、`cart-restore-final/`保存真实业务回归；`semantics-final/`等目录保存语义与拒绝检查，`legacy-offline-frozen/`明确标注历史捕获复算。`audit-final-01/`保存总审计、实例及原始文件哈希，`environment.json`和`images.json`保存机器与镜像资料，`logs/00…06`保存重要节点。

```bash
python3 experiments/sockshop-mirrortaint/audit_ticketinfo_wrapper_revision.py \
  --root artifacts/ticketinfo-wrapper-revision-20261020 \
  --out artifacts/ticketinfo-wrapper-revision-20261020/audit-recheck-new-directory
```

审计输出使用新目录，不覆盖原始事件或首次结果。小型[审计快照](ticketinfo-wrapper-results-20261020.json)与代码随Git保存，完整工件需另外备份。本机备份入口为 `artifacts/ticketinfo-wrapper-backup-20261020/START-HERE.txt`；这是同盘副本，不含Docker镜像层，迁移须在新目录重建。推送由用户完成。
