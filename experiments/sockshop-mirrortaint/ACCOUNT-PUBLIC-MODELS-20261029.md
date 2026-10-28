# Account 修订的公共语义与效果协议

本文件说明 `78a9534` 的有限模型。它们接入已有 Value、Frame、对象字段版本和调用状态，不提供 Account 字段的手写来源答案。查询仍只声明入口、目标与来源边界；模型由字节码形态和依赖清单选取，并在执行中检查实际实现与配置。

## 从入口到响应

1. 规划器读取原版 JAR，生成应用方法调用计划、默认初始化证明及适用的公共契约。只有兼容的库清单才附加相应协议；单独增加类哈希不代表模型成立。
2. Agent 记录实际 Frame、实参、分配、读写版本、子调用、任务与完成状态。监测失败隔离沿用可靠性检查点的作用域回滚；实际业务写入版本不回滚，失败标记保持粘性。
3. 离线解释器按实际执行建立依赖。已解释的赋值改写具体字段版本；尚未解释的调用仍保守失效可能受影响状态。
4. 有限效果证书只保留**调用前已经建立**的依赖。它不能把 unknown 变成空来源，不能把前后同值当作没有写入。
5. 返回对象与真实序列化位置核验目标。Number、枚举、Date 的投影仅证明物理值如何对应 JSON，不创建来源边。

## 基础值与默认字段

`Boolean.valueOf(boolean)` 返回值依赖本次实参，即使 Boolean 缓存复用了同一个对象，也不合并两个输入出现。`BigDecimal(int)` 只为本次分配 token 和已完成构造建立状态；不能把不透明调用返回的同值 BigDecimal 重新绑定为已知。

默认字段规则要求被核验的构造器在空 Object 构造完成后提供实际新对象、构造调用、完整字段及版本 0 证据。引用默认 null、基本类型默认零/false 可以具有已知空数据来源；构造器后续赋值和调用屏障仍覆盖它。没有为 `note`、`incomes` 或 `expenses` 添加专用规则。

Assert 仅支持经审阅的 `isNull(Object,String)` 重载及其正常/异常效果，不把 Supplier 重载或其他 Assert 方法视为无效果。枚举要求固定的闭合初始化与构造字节码、实际常量身份、name/ordinal 一致；自定义初始化、实例字段或转换不自动获得支持。

## Feign / Hystrix：本地输入保持

此协议支持本次出现的同步 void 客户端方法和单个平坦 String 字段 DTO。它解决的是本地输入经过客户端后能否继续保留依赖，不是远端 Auth 保存 sink 的来源还原。

实际依赖固定 Feign 9.5.1、Hystrix 1.5.12、相应 Spring Cloud 2.0 与 Jackson 2.9.6。必须核验实际 HystrixInvocationHandler、SynchronousMethodHandler、SpringEncoder、已审阅 HTTP 包装与拦截器，没有 fallback、未知 expander 或自定义序列化效果。

运行证据必须闭合以下关系：

`实际调用 → 捕获的参数数组 → Hystrix 命令 → worker → encoder → converter → mapper/生成器/实际属性 serializer → 正常完成 → 同命令 Future → join 完成`

每个阶段携带任务、调用、对象与线程坐标，核验身份、次数及顺序。相同参数值、成功 HTTP 或相同最终响应均不能替代这些证据。序列化核验还包括实际 Bean/String/Null serializer、直接 getter、默认生成器和相关配置，不能用默认 serializer 的存在代替本次 contextual serializer。

只保留调用前已建立且完整字段版本保持的本地输入依赖；可能的其他全局/逃逸效果仍按保守规则处理。fallback、自定义 encoder/serializer、缺失 Future 或错配命令，均不能获得有效保持证书。监测工作线程 finally 恢复自身原上下文，不冒充通用异步来源模型。

## MongoDB 保存：当前版本和给定 ID

协议固定 Spring Data MongoDB 2.0.8、Commons 2.0.8 和 Spring 5.0.7 的实际实现及配置，限定给定 String ID、无 version、自身实体返回、直接字段映射和默认转换/driver。自定义 `Persistable.isNew`、转换器、属性访问器、编码器等不由此获得支持。

保存前检查注册监听器的完整集合，包含已经初始化的 bean、父/委托 multicaster 和实际分派实例。类型筛选、排序、相等性本身也可能执行代码，不能只看最终被选中的回调。有限的框架筛选实现单独核验；未知筛选、尚未解析的 bean、实际应用回调或集合不闭合均不能认证。

不为检查配置而额外创建未知 bean，不先调用未知转换器再判断其类型。返回实体身份仅是条件之一；证书还需要前后字段版本、metadata、转换、实际保存调用及完成配对。保存不把实体重新当来源，也不修复此前丢失的依赖。

Document/Date 编码另外核验默认 DocumentCodec、DateCodec、registry、实际 Date 对象及 epoch 的编码开始/完成。它只保护已有 Date 依赖。保存前 unknown、保存后同值 `setTime` 和自定义 codec 仍不能得到确定来源。

## 输出投影与真值

本次 Number 投影限于已建模的 BigDecimal 整数构造、scale 0 与相应范围、实际默认 NumberSerializer。枚举要求实际默认 EnumSerializer 和 name 投影，索引/toString 配置不混入。Date 同时核验序列化实现、配置、对象及实际输出的时间表示。自定义配置保持业务输出，但不能生成被认证的捕获。

独立评分依据原业务代码、实际输入、数据库事实及原始字段坐标，不调用 TF 传播或 MT 标签决定预期来源。Account 的 `name` 连接本次入口 User.username；固定初始化、默认 null 等为已知空数据来源。`lastSeen` 的本地时钟事实单列：当前查询边界不把时钟生成调用计为入口/仓储/RPC 数据来源，不能将这一空来源结论扩展成任意时间生成都无来源。

## 迁移边界

新增的是七组可复用机制，详见[迁移台账](account-source-migration-ledger-20261029.json)。固定版本和配置减少了需要解释的范围，也意味着换 JDK、框架版本或自定义回调后需要重新核验。49 份 javap 审阅文件和锁定类数是可检查的迁移材料，不是人工工时或已证明规则数。

Recipient 枚举 Map 的完整来源、动态 Principal、保存 sink 查询、远端 Auth 保存及 MT 导出仍单列后续任务。此协议不支持任意 Feign、Mongo、异步或 Jackson 行为。完整业务结果见[修订报告](ACCOUNT-SOURCE-REVISION-20261029.md)。
