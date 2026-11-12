# 首批运行时状态退役：持有关系与边界

在修改退役实现前审查当前5b3daa2的实际状态。每个“引用”均指Java强引用；字符串身份/纯事件元数据不等于原业务对象引用。现有全局Recorder锁与事件序号不改。

| 状态 | 当前键→值及间接持有 | 结束条件／跨请求需求 | 本轮策略 |
| --- | --- | --- | --- |
| IDS | 业务对象→String ID；键强持有对象，值不回指 | 任意活对象可跨请求/线程复用 | 弱身份查找+Phantom队列确认最终退役；单调ID，不按size编号 |
| VERSIONS | owner-ID:声明字段→Integer；字符串不持有对象，但条目永不消失 | owner存活时版本必须延续 | owner索引，owner确认退役后分预算删除其字段条目 |
| ACTIVE | ID字符串→Frame ID集合，无原对象 | 读取域结束；可能多个域共享owner | Scope.close/rollback对称释放，非空域阻止其ID/字段状态退役 |
| ARRAY_VERSIONS / ARRAY_SLOTS | 数组→Integer/int[]；值不回指数组 | 活数组跨请求必须延续 | 弱身份键、最终队列证明后退役；槽版本与数组版本同步核验 |
| READ_ONLY | 容器强身份集合 | 活容器的只读限制跨请求保持 | 弱身份集合，不在请求结束清除 |
| CONTENTS | 容器→观测列表；列表只含String ID、标量和安全Map，不含活业务容器；自引用表示为ID | 活容器的前态/epoch必须延续 | 弱身份键；入表前校验safeEvent，避免不支持的Number子类等反向强引用 |
| EPOCHS | 容器→Integer | 与CONTENTS同寿命 | 弱身份键 |
| ExecutionKernel STREAMS | stream→实际source List、观测快照、predicate；predicate可能间接回指stream | filter/findFirst移交/消费；未消费或异常边界可能保留 | 保留强状态，明确未纳入退役；不把有值回边的表机械改弱 |
| Async FUTURES | Future→Task→delegate，delegate可间接回指Future或整个调用图 | 存活Future允许多次get/cancel，不能首次get删除 | 值缩减为独立Long任务ID；弱身份Future键；活动Task/delegate仅由执行/业务侧与ACTIVE保留 |
| INITIALIZED / LIBRARY_HASHES | Class→纯Map/hash；Class强持有定义加载器 | 同一类多次见证应一致，类初始化资格不能重置 | 保留，类卸载不在范围 |
| CHECKED_CLASSES | 受计划约束的内部类名String集合 | 跨请求变换覆盖证明 | 保留，不包含业务实例 |
| TemporalDate WIRE | Date→[Long time, String/Long/Integer wire]；值不回指Date | 存活Date跨序列化验证 | 弱身份键；仍只接受原固定Date/安全wire类型 |
| JSON FIELDS/LOADED、WRAPPER_CLASSES、RequestScope CHECKED、JsonListCopy INITIALIZED | Class或ClassLoader→Field/元数据；Field能回指Class | 类型/库匹配跨请求 | 保留并报告计数；不宣称解决类卸载 |
| Feign COMMANDS/INPUTS | command/body→Token→command/body，是值回边 | complete/worker/end及Scope.onClose release | 保留原显式清理，审查正常/异常拒绝回滚，不改为弱表 |
| SourceEvidence CAPTURES | proxy message→Capture（含流/decoder状态） | read/abort移除，活动网络读取必须保持 | 保留活动域策略；未闭合网络读取不在本轮退役许可 |
| Recorder STACK/PENDING/ABORT、Collection CALLS、Execution CONSTRUCTORS | ThreadLocal Frame/调用Map含_receiver_ref/_args_ref/构造参数；活动调用强持有属必要 | exit/abort、end/throw/catch及Scope checkpoint恢复 | 保留活动持有；ABORT finally.remove，检查作用域清理 |
| Async ACTIVE | ThreadLocal Task→delegate | Task.call finally恢复先前任务或remove；拒绝不设置；未启动取消不设置 | 保留，Future表不再旁路持有Task |
| ReadEffect STACK/STREAMS/OPTIONALS/COUNTS | ThreadLocal状态含source List、element[]、optional成员，可回指键 | 方法Scope checkpoint恢复；嵌套保留外层活动状态 | 保留原边界，不机械全局clear |
| Sequence PIPES/COLLECTORS、Save/Conversion/SQL/SourceLocality ACTIVE | ThreadLocal Map/Token，部分持有真实对象，token图可能有环 | Scope checkpoint/onClose及对应complete退出 | 保留活动域，正常/异常都以原finally/Scope退出；未解决的非闭合边界单列 |
| Transport RPC/SPANS/ASYNC/DECODER、Communication ACTIVE、RequestScope ACTIVE、MonitorSafety SCOPES | ThreadLocal上下文/检查点，可能间接持有活动参数 | 对应finally、Scope恢复；嵌套不能清外层 | 保留原协议；诊断当前线程，不把shutdown线程空表当工作线程证明 |

设计：仅WeakReference清除不能证明对象不会通过finalizer复活。因此用弱引用按==查找，另外的PhantomReference/ReferenceQueue作为最终退役证明；值与队列节点不得持有referent。弱引用清除后、phantom尚未确认的同identity-hash新查找无法认证原对象，明确拒绝捕获，不分配新ID。含复活/极少见identity-hash未决碰撞的路径是明确边界，不宣称支持复活后的身份恢复。活对象的真实引用仍能查到原节点，不受请求结束或时间影响。

清理必须有每次预算；上限针对当前登记（含待确认/活动域阻止的条目），不针对累计分配。ID退役不修改日志。此表是范围与持有证明，实际实现/GC计数/未通过项在METHOD-LIFECYCLE-20261112.md与新工件报告。

实现补充：各弱状态节点保存纯String owner-ID，故即便终止证明先于IDS表到达，ACTIVE域非空时也不提前删关联状态。OwnerVersions使用受控Map接口，putAll也经过归属索引，不暴露可修改entry；每次只清有限字段项。默认每个弱表当前登记上限100,000，字段总条目1,000,000，事件上限不变。资源与未决证明不足时明确拒绝，未用LRU、请求边界或时间回收。
