# 有限 Date 投影与效果保护

本阶段在已有执行内核和响应绑定中增加有限的时间值模型。原版业务JAR不变；Date来源由字节码与实际执行证据推导，没有按 `CustomerOrder.date` 手写空来源规则。真实Orders的目标仍因必要效果未解释而保留unknown，见[结果报告](DATE-PROJECTION-REVISION-20261020.md)。

## Date 引用与毫秒值

规划器依据目标描述符及已纳入执行的方法调用，自动附加 [Date公共契约](date-runtime-contracts-20261020.json)。当前只接纳确切 `java.util.Date`，记录实际Date对象身份、逻辑epoch毫秒，以及持有它的DTO字段对象和写入版本。同一毫秒的不同Date或不同输入字段不能合并。

`date_epoch_ms`是内容投影，不是完整的Date内部写入版本。模型没有把可变Date当作任意情况下的不可变标量：尚未解释的修改调用必须使相关Date及其别名来源不确定。反射/native和并发共享修改继续超出保证。

在统一执行路径中，Date复制、`Date(long)`、`Date.getTime`与DTO字段写入使用同一Value/Frame/State。`Date(long)`继承实际毫秒实参的依赖；复制一个Date引用保留被读取字段或入口参数的来源。新对象身份与时间相同也不替代实际参数、字段和构造完成的核对。

## 环境时间与字段来源

无参 `Date()` 和受支持的默认 `Calendar.getInstance().getTime()` 产生环境时间。在当前声明的输入字段边界内可以没有字段来源，但不能把它们说成常量或完整来源为空。执行审计另存时钟/Calendar产生事件、调用坐标、对象及毫秒值；当前未实现一般环境状态的完整来源图。

Calendar只对新建默认GregorianCalendar链提供有限模型，并核对已固定JDK的Calendar、Builder、provider及Date类字节码与实际provider类型。传入的任意Calendar、已被未解释调用影响的Calendar、任意自定义运行时环境不由此获得保证。`Calendar.setTime`与Date各类修改方法本阶段没有来源传播模型，仍施加不透明屏障。

## 序列化是另一个核验阶段

Date字段绑定需核对实际返回Date对象与字段版本，再核对默认Jackson `DateSerializer`、`DateTimeSerializerBase`、`StdDateFormat`及ObjectMapper的实际类哈希。当前拒绝自定义Date序列化器、DateFormat和字段格式覆盖。

保存两种默认编码证据：epoch毫秒数字或带毫秒和时区的标准日期字符串。离线端独立解析日期字符串，按UTC时间差核对原毫秒，避免浮点时间戳舍入。当前字符串解析范围受Python datetime所支持年份约束，不能据本组结果声称任意long时间值均可按ISO格式处理。

Date序列化事实只验证值与目标绑定，不创建输入来源。返回快照、输出ISO字符串和相同毫秒都不能替代来源边界与计算证据。

## 两条路径的保守处理

统一执行内核按已解释指令建立字段和参数依赖。Date或包装DTO流入未解释调用时，可能受影响的状态继续unknown；即使修改前后时间相同也不恢复确定性。一个已解释的后写常量可以在对应新版本上得到空字段来源，这与未知修改不同。

旧响应转发路径没有完整的Date可变内容分析。Date目标因此强制启用有限读取效果核验，且要求根方法满足静态前提、实际执行子调用全部通过核验。只比较方法前后时间或DTO字段版本不足以认证Date内容未被改写。该策略可能保守阻断无关不透明调用；没有把它包装成字段敏感的一般效果求解器。

补测入口Date及毫秒参数时，还修复了统一图中参数叶节点与执行结果节点复用变量名导致的冲突。入口Date和原始毫秒参数均保留真实参数实例来源；helper实参不被重设成新的根来源。

## 实现与保证范围

实现入口：[条件与计划](plan_date_projection.py)、[Date运行事实](TemporalDateHooks.java)、[运行与编码核验](infer_date_projection.py)、[统一执行](infer_application_execution.py)、[有限转发效果](ReadEffectHooks.java)、[图与参数节点](infer_distributed_fields.py)。

这些公共契约覆盖本轮控制程序中的读取、复制、构造和默认投影。保存、异步、Date修改传播、任意Calendar/Date子类、自定义序列化和完整环境溯源没有因此获得支持。full/selective沿用相同模型与核验要求，本轮没有减少观测量或成本优势的结论。
