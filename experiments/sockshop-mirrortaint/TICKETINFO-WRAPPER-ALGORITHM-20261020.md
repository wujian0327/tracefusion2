# HTTP 包装与实际 Map 来源绑定

本阶段把有限的 Spring HTTP 包装契约接入统一执行内核。规划器、Agent 和离线解释器继续分开：规划器生成候选调用与必要证据清单，Agent 记录实际身份和执行事实，离线端建立依赖。没有按 TicketInfo 字段名称提供传播规则。

## 请求包装与类实例

`HttpEntity(Object, MultiValueMap)` 只在具体类、原始库哈希、null headers、实际 body 身份及空 headers 均满足时接纳。该契约不概括非空 headers 的复制或任意包装子类。构造器完成证据中的 body 必须与实际实参相同；不能把未初始化的 this 传给监测器。

JVM 的 Class 常量有单独的动态事件：记录实际 Class 对象、描述符和被指类的原始字节码哈希。离线端核对冻结模型及实际调用实参。声明 `Response.class` 只决定本次解码的外层类型，不证明 `Response.data` 的实际内容是 TrainType 或 TravelResult。

## RPC 返回契约

首版仅接纳原路径使用的 `RestTemplate.exchange(String, HttpMethod, HttpEntity, Class, Object[])`，要求空 varargs 数组、具体 RestTemplate 与 ResponseEntity、空拦截器列表、固定请求工厂及已固定的转换器类。Spring Boot 允许的原版 JAXB 转换器也按类哈希固定；不是放行任意转换器。完整清单见 [公共契约](framework-wrapper-contracts-20261020.json)。

交换调用具有明确的 collection call-id 和正常或异常完成。正常返回时还需唯一匹配调用区间中的 RPC 开始、实际 JSON 响应读取及 RPC 完成，核对 URL、HTTP 方法、父请求及具体消息 span。返回 ResponseEntity 的 body 必须就是该次实际解码对象，字段、对象身份及版本投影须与读取时一致。`getBody` 再按确切包装实例取回该 body。

这不是 RestTemplate 的通用只读摘要。离线端先保守失效请求参数及可能全局别名的既有状态，再仅从该次合格的实际响应读取引入来源。返回 body 不能与已声明的输入/全局来源对象直接混同；后续不透明调用仍使可触及的响应状态失效。旧的入口或仓储来源不能仅因发生了一次 RPC 就重新取得确定性。

不满足完整证据下的有限前提时，保留 unknown。必要的 Class、库版本、消息、body 身份或完成证据缺失、歧义或矛盾时，拒绝该证据。异常调用不产生正常返回契约，继续按既有调用生命周期处理。

## 动态 Map 目标与字段实例

原版 TicketInfo 使用原始 `Response.class`，其 `data` 及嵌套内容实际是 LinkedHashMap。查询仍使用预先声明的响应路径；新绑定允许该路径落到经过核验的实际 Map 条目，并保留真实的 `@map:key` 坐标、容器身份和内容阶段。不伪造一个 TrainType 对象，也不因声明 DTO 中有同名字段就自动连接。

HTTP 读取记录增加实际解码根对象身份和类型。离线来源叶来自读取事件中的字段坐标；目标则来自实际返回对象以及默认序列化路径的核验。两者可能指向同一个物理字段，但证据时间、消息和用途不同：**返回快照只证明目标绑定，永远不创建来源。**

从发送到接收的跨服务边仍由具体 RPC 消息、方向和 JSON pointer 连接；同 trace 或同值不足以配对。本轮能力评分在预先声明的实际 RPC 响应读取边界停止，不扩展到 Basic 内部票价计算或数据库历史。

## 支持边界

新契约只覆盖固定库和当前形态的响应转发。自定义 RestTemplate、任意转换器或拦截器、非空 headers 的效果、保存、异步、Date 投影及任意共享修改没有因此获得支持。接收到的 Map/List 继续受已有只读保护；应用试图修改它们会使采集失败，不能把这种失败计作正确来源答案。

full/selective 使用相同契约和核验要求，保守保留必要观测。本阶段没有查询切片收缩或成本结论。

实现入口：[规划与路由](plan_application_calls.py)、[框架事实](FrameworkCallHooks.java)、[Class 与构造证据](ExecutionKernelHooks.java)、[实际解码对象](SpringTransportAgent.java)、[目标绑定](ResponseBindingHooks.java)、[统一解释](infer_application_execution.py)及[图来源连接](infer_distributed_fields.py)。原字节码和冻结后的业务结果见 [实验报告](TICKETINFO-WRAPPER-REVISION-20261020.md)。
