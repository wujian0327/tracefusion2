# 构造字段投影、Runnable 与剩余目标回归

**本轮新增正确回答原剩余49个目标中的15个；另外34个仍未回答。** 修复集中在 Cart 已有商品的加购路径。Basic 已进入统一内核，但必要公共契约尚未接齐，不能算新增覆盖。算法冻结为 `b8c432e0739117a7ea816cd0854bed3d33838306`。

本轮不是新版62查询的全量重新部署，不能把旧382个与新15个直接拼成新版397/431正式正确率。旧 `f73fa5f` 的全量结果和成本表继续保留；29个候选没有规划或执行，没有新增性能实验。业务继续使用原版JAR。

## 同一冻结版本的真实部署

10个已暴露开发查询族，full/selective各10次独立业务配置，共20次部署。两个模式各66次查询请求、99个目标实例，分别报告，不能混合成未见查询覆盖率。CPU1、768MiB、堆32m/256m、GC/JIT线程1/2；数据卷和端口隔离，部署可并行，因此不作性能估计。输入、数据库及响应逐项核对原对照工件，独立真值沿用原业务投影、消息及实际调用/对象/字段/版本坐标，不读取TF传播答案。

| 已暴露开发组 | 查询族 | full | selective | 本轮意义 |
| --- | ---: | --- | --- | --- |
| Cart.addToCart：itemId、quantity、unitPrice | 3 | 15正确 / 3unknown | 15正确 / 3unknown | 新恢复15个先前unknown目标 |
| Basic.queryForTravel：trainType的id、economyClass、averageSpeed | 3 | 0正确 / 21unknown | 0正确 / 21unknown | 静态阻断减少，端到端能力未提升 |
| Station两个循环入口 | 2 | 20/20正确 | 20/20正确 | 新Agent兼容回归 |
| Route过滤入口的两个目标 | 2 | 40/40正确 | 40/40正确 | 新Agent兼容回归 |

各组均无错误确定答案、证据无效或分析限制。每模式Cart TP15/FP0/FN3；Basic TP0/FP0/FN21；Station TP20/FP0/FN0；Route TP40/FP0/FN0。目标未生成的请求另计：Basic每模式3个，Station、Route各2个；不将unknown当N/A。full/selective逐查询、逐输入、逐目标状态一致。

新增15个不是MirrorTaint领先反例：这些Cart目标在原对照中也不属于MirrorTaint正确集合。这里衡量的是TF端到端可回答范围的增加，不改写原基线能力表。

## 可复用的语义修订

- **构造器的有限字段投影。** 根据原字节码识别“读取已初始化参数的标量字段或纯getter，再委托同类构造器赋值”。不使用字段名称白名单。新证据记录参数身份、实际类型与类哈希、字段及写入版本、构造前后投影；离线核验来源读取和目标写入版本。未初始化的this不会传入监测器。getter若同时作为别处lambda目标而被插桩，其真实子Frame也必须消费和核验。
- **Runnable调用。** 将标准LambdaMetafactory的`run()V`接入已有lambda捕获、实际调用Frame、共享字段状态和正常/异常完成机制。只创建未执行的Runnable不传播其方法体来源；调用的SAM必须与创建声明一致。这里是实际同步`run()`，不因此支持任意线程调度或共享并发修改。
- **Optional.isPresent。** 使用固定JDK契约及实际Optional成员核验存在性，避免将这项只读查询当作全局不透明效果。
- **必要数值与状态修正。** 支持I2D及有限DMUL，合并实际操作数来源，零结果不抹去来源；非有限结果记分析限制。primitive字段的监测装箱身份不再误作业务字段身份，String及其他对象仍保留身份核验。补充IndexOutOfBoundsException分派；固定List.get的越界只能在实际实现、成员及下标证据一致时视为只读异常，其他不透明异常仍保守处理。

这些是有限字节码/公共契约能力，没有按查询手写来源或复制基线标签。一般构造器、任意lambda bootstrap、自定义集合和共享并发修改没有因此取得支持。

## 仍未打通的34个目标

**Cart新建商品3个unknown。** 新增Runnable能力已经使添加链进入解释，但保存证据仍包含未核验的`ValidatingMongoEventListener`，且存在接收集合修改、Item/Cart保存等必要效果。不能将验证监听器、保存或接收列表写入统一声明为只读。已有商品返回的副本与后续保存对象按真实身份区分，不能凭同值推断保存保持来源。

**Basic的21个unknown。** 原I2D静态阻断已消除，新计划确实解释了应用方法。真实捕获进一步显示HttpEntity的单参数构造、JsonUtils/Jackson转换、Integer解箱、Map创建与put、部分对象渲染尚未接入这条内核的有限契约。完整证据下这些必要不透明效果仍阻断确定答案。不能只删除旧转发路径的root屏障，也不能将已有JSON转换快照直接注册为来源。

**Price UUID的10个仍规划拒绝。** 本轮没有扩展UUID字段实例到序列化投影，不运行拒绝项，也不借另一字段的成功计划替代。

以上是原开发目标的剩余台账：3 + 21 + 10 = 34。它不是新版全范围的独立测试结果。

## 保护、历史复算与失败保留

- 新JVM契约小程序每模式58个有效目标：50个已知来源匹配、8个必要不透明效果保持unknown，另2个异常根无返回；每模式20项证据扰动均拒绝。含同值对象、构造器参数投影、Runnable执行/不执行/异常、Optional和List越界回退。
- 数值小程序每模式7/7正确、TP14，覆盖零、负数、int边界、重复值及不同输入对象；非有限计算保持analysis_limited。
- 应用调用小程序每模式26个已知来源匹配、8个预期unknown、2个异常根，6项扰动保持。76项既有单元检查通过。
- 原冻结捕获中每模式382个已知正确目标，在新离线代码上逐项复算仍正确，包括原基线正确集合和旧TF正确集合。**使用的是旧Agent、旧计划和旧原始捕获，不是新Agent的全量业务验证。** 原unknown捕获可能缺少新契约必要证据，不宣称其全部状态兼容。

开发失败没有覆盖：`semantics-01/`暴露纯getter子Frame未消费；`numeric-01/`暴露primitive包装身份误判；`semantics-final/`暴露List越界被当作不透明异常。Basic首次开发捕获因异常层次未建模使整个批次analysis_limited，分别影响两个模式各7个目标；后续修复后才冻结并重新部署。`development-01/cart-first/`开发期间源码变化触发哈希拒绝，不能当作冻结验收；其捕获只在独立目录作开发复算。尝试复算旧unknown捕获遇到缺少新增Optional证据的失败也保留，已知答案兼容检查另列目录。

## 工件与复核

原始目录：`artifacts/remaining-semantics-revision-20261022/`。`logs/00…03`保存协议、开发节点和冻结验收；`frozen-candidate/`保存原版9个JAR、源码快照、模型与自动计划；`final-cart/`、`final-basic/`、`final-station/`、`final-route/`保存20次部署的原始事件、输入、真值和预测；`audit-final/`记录哈希与逐组核验。历史已知答案的复算在`historical-known-offline/`。

小型[审计摘要](remaining-semantics-results-20261022.json)和[逐目标CSV](remaining-semantics-instances-20261022.csv)随Git保存。复核使用新目录：

```bash
python3 experiments/sockshop-mirrortaint/audit_remaining_semantics_revision.py \
  --root artifacts/remaining-semantics-revision-20261022 \
  --out artifacts/remaining-semantics-revision-20261022/audit-recheck-new-directory
```

下一步应接齐Basic实际使用的转换与包装契约，再核验Cart的保存监听器和接收集合所有权。新增成功仍需逐实例真值检查，不能以规划接纳替代。所有push由用户完成。
