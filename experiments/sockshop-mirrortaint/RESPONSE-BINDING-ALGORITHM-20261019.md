# 有界响应目标绑定算法

冻结版本：`803b92f15653dd570bd6b2b21acb14b69da594ce`。本页描述本轮实现，不替代 [修订与封存测试报告](RESPONSE-BINDING-REVISION-20261019.md)。原版业务 JAR 未修改。

## 输入与明确分类

配置固定入口、声明目标字段、响应 JSON pointer 和原有来源边界；列表使用通配查询族，Map 使用明确字符串键。设置 `response_path` 后进入 [统一规划入口](plan_response_binding.py)，而不是依次尝试三个规划器。

先对整个根方法执行有界控制流/定义合并分析，再依据目标的直接 setter 或构造写入分类：局部标量交给 bounded-scalar，局部 Map 交给集合 profile，已识别的构造复制交给 copy，已有数值归约交给 reduction。没有根方法写入时，不再仅因此拒绝：生成 response-forward 计划，要求运行时证明实际返回值与响应字段的关系。接纳计划不等于已知来源答案。

这不是完整的 Java 类型/别名分析，也不保证最小观测。必要的未建模调用会在运行还原时保留 unknown；不支持的根方法指令或循环仍可直接拒绝。`Target type unsupported` 与字段不存在/歧义已分开报告。

## 来源读取与返回绑定是两个事件

来源记录只在既定边界产生：入口业务对象参数、显式 Spring Data read-return 调用以及实际下游 RPC 响应读取。库模型把仓储读取返回视为本次调用的实体输入，不声称恢复数据库历史。对于返回已有实体的查询，即使源字段和输出字段属于同一对象/字段/版本，源读取调用及时间点与最终输出仍是不同证据点；不能把输出快照直接当成来源。

根调用退出时，记录实际返回对象、相关字段/元素/Map 键、写入计数版本及请求上下文。序列化时，目标路径必须唯一对应到此前同一请求的返回记录，并且对象、字段、版本一致。数值只作一致性检查。返回记录再向前连接实际输入或已解释的局部计算；无提供者或必要调用效果未知时，答案仍为 unknown。

普通 DTO 需要冻结类哈希及运行时实际类型核验。已知 `Response.data` 包装与直接 DTO/列表返回分开处理；默认 Jackson 的选中属性、直接 getter、serializer、Map 键和已覆盖配置约束会核验。当前依赖冻结的默认序列化契约，这些检查不等于证明任意 Jackson 自定义配置正确。HATEOAS、任意自定义 DTO/容器和未覆盖转换仍可能缺少必要字段证据。

## 对必要调用效果保持保守

直接 accessor、已验证的纯构造器及少量公共库契约可以透传身份。其他调用若接收或返回了与目标有关的字段实例，就记录不透明效果；即便最后数值没有变，也不能仅据同值确定来源。这会保守地把部分日志、保存、Supplier、异步调用路径留作 unknown，本轮不靠添加业务专用摘要消除它们。

新增公共契约包括 HttpEntity/ResponseEntity.getBody、Resource.getContent、Collections.singletonList/emptyList，以及支持运行时类型上的 List/Collection/ArrayList 只读方法。它们是人工声明的框架/库模型，不能称为任意库行为的自动证明。RabbitTemplate 发送不修改消息、JsonUtils 默认 Jackson 转换沿用已有契约。每个新查询无需手写传播规则或业务公式；入口、字段/路径和边界仍需声明。

## 局部标量与异常路径保护

bounded-scalar 复用定义合并和实际路径重放，不再要求目标存在 Map.put。实际 setter 写入通过调用区间、接收对象、字段与版本核对；同一字段多次写入分别建图，返回时绑定实际版本。常量覆盖即使值相同，也不能沿用旧版本来源。

调用结果不流入目标，也可能因抛异常改变目标写入。因此，原异常保护区内的非构造调用及其操作数定义被纳入证据闭包。只有实际失败调用、原异常表和实际 handler 一致，才沿该路径重放。未覆盖的必要指令或异常证据不被静默跳过，仍可导致拒绝或证据无效；不声称一般异常分析完备。

## 共用采集器修复

ASM 计算公共父类时，原先通过 Class.forName 可能在转换器重入期间提前加载 DTO，跳过其字段写入插桩。本轮改为读取类层级元数据，不初始化应用类；绑定快照还要求该 DTO 已通过冻结类检查。它保护对象版本证据，不是业务来源推断规则。

## 实现和验证入口

- [统一规划与显式路由](plan_response_binding.py)、[控制流/定义合并](plan_collection_service.py)。
- [身份和来源证据采集](ResponseBindingHooks.java)、[共用 Agent](PlannedServiceAgent.java)、[HTTP/JSON](SpringTransportAgent.java)。
- [实际返回绑定](infer_response_binding.py)、[局部计算重放](infer_collection_service.py)、[统一依赖图](infer_distributed_fields.py)。
- [真实应用驱动与独立真值](run_response_binding_revision.py)、[小程序语义保护](run_binding_semantics.py)、[结果审计](audit_response_binding_revision.py)。

原20个查询已成为开发集。独立覆盖结论只能使用提前封存且在冻结后首次执行的查询；历史性能数不能直接移用于本版。
