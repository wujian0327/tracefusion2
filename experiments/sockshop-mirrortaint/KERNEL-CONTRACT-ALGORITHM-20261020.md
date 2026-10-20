# 公共契约与对象数组接入统一执行内核

冻结版本 `ade72a8` 将有限的顺序流、Optional、Supplier 和对象数组语义接入已有 Value、Frame、State、Container。来源仍由实际入口、仓储读取返回和声明的 RPC 读取边界提供；运行快照、相同数值与调用只读性均不能单独建立来源。真实业务结果和36个剩余反例见[阶段报告](KERNEL-CONTRACT-REVISION-20261020.md)。

## 预先选择调用处理方式

统一路径使用已有 `execution_kernel: true` 和 `application_calls: true`，自动生成版本3计划；本轮查询统一采用该策略，没有逐字段传播摘要或事后更换成功profile。旧复制、归约、集合、响应绑定和read-forward路径保留，本轮不把全部旧查询迁移到新策略。

规划器根据冻结字节码和类层级建立非递归应用调用候选，识别允许的LambdaMetafactory站点，保守保留必要调用、读取、写入、构造结果、分支与异常证据。每个实际调用只走一条依赖解释路径：已解释的应用Frame、明确公共契约或不透明屏障。应用方法返回后不再用公共契约重复生成来源。

接口候选中可能递归的实现不会自动取得解释资格；直接递归仍拒绝。lambda体若需要递归或未支持语义，创建可以被记录，执行效果仍不透明。规划接纳不等于全部运行都可回答。

## 顺序流与Optional

运行端与离线端共同核验以下有限契约，相关JDK指纹固定于[kernel-contract-runtimes](kernel-contract-runtimes-20261020.json)。该清单合并原read-forward与执行内核已固定的库类指纹，并固定各Java运行版本。只允许列明的ArrayList、Arrays ArrayList、SingletonList和EmptyList；任意集合实现没有由此得到支持。

| 调用 | 运行核验 | 离线状态 |
| --- | --- | --- |
| List或Collection.stream | 实际列表、内容阶段、成员；返回确为非并行ReferencePipeline Head | stream实例绑定实际Container与阶段 |
| Stream.findFirst | 未经过其他pipeline的已记录stream；来源列表内容及阶段不变；实际Optional与首对象一致 | Optional实例绑定实际首成员Value，空时记录不存在成员 |
| 非空Optional.orElseGet或orElseThrow | 具体Optional实现、非空状态、返回对象与已有成员身份一致 | 返回该成员Value，不执行或合并回退Supplier来源 |
| 空Optional.orElseGet | 实际进入受支持的Supplier实现Frame，完成结果与原调用一致 | 由实际执行的方法体给出依赖；不透明回退仍unknown |

这些运行核验记录附在原调用完成事件中，复用同一个call-id，不另造第二套调用序列。stream来源容器或捕获对象受不透明效果影响时，依赖保守失效；内容数值相同不能撤销屏障。普通List读取和已有元素、字段及版本状态继续共用同一内核。

Object.getClass另有窄JVM契约：核对返回的确是实际接收对象的Class。它用于方法引用创建时的原始非空检查，不建立业务字段来源，也没有开放一般Class常量投影或反射执行。

## Supplier创建与实际执行

只接纳固定的 `LambdaMetafactory.metafactory`、规定的Supplier或Predicate SAM描述及支持的实现handle类型。Agent在原invokedynamic完成后记录静态站点、完整指令、bootstrap参数、实际lambda对象、捕获参数与接收对象。离线逐项核对冻结计划；有状态实例不能被另一个捕获集合重绑定。无捕获实例允许JVM合法复用。

执行Supplier时，接收lambda实例必须对应已记录站点。实现handle决定静态参数或捕获接收对象的绑定；实际进入的方法、父Frame、调用位置、参数身份及正常或异常完成都须相符，再通过现有Frame机制执行。控制程序覆盖静态捕获、两个捕获参数、绑定方法引用及私有实例lambda。只创建但未执行的回退不产生实际数据来源。

Predicate目前只支持创建记录；本轮没有解释一般 `Stream.filter`、任意pipeline或Predicate执行。Cart单项GET恰好还需要这些语义，因此不能由Supplier创建成功推出整个GET查询已支持。

不透明回调可能再次进入已插桩的方法。内核会核对这段调用的父子范围、嵌套生命周期和闭合完成，将其作为**整段不透明效果**处理，失效可触及的接收对象、参数、捕获引用、关联容器和全局别名。该子树不用于产生确定依赖；必要完成缺失或范围矛盾仍拒绝。它不是对未知子调用逐个跳过后保留原来源。

## 一维对象数组

本轮支持一维引用数组的分配、默认null、AALOAD、AASTORE、ARRAYLENGTH，以及同一State中的跨方法参数和返回传递。保留原JVM指令，只在其前后记录证据，并在原业务异常保护范围内记录同一异常后重抛；不以返回Object的替代调用破坏原数组的静态类型。

数组由实际对象身份区分；状态保存顺序元素Value、整体内容版本和每个位置的写入版本。成功写入仅更新实际下标及其新版本；相同字符串数值的覆盖也必须按真实写入更新依赖。读取返回对应位置的Value，索引来源另存选择证据。默认null和已解释常量覆盖有已知空数据来源，未知输入不是空来源。

Agent记录分配后的实际元素、组件类型、读写前状态、成功写入后的整体及元素版本、实际读出值。写入还记录实际组件类型兼容性。离线要求身份、位置、前后版本、内容、返回值和原始异常路径一致；缺失写入、错误对象或矛盾版本不能继续给出确定答案。

支持的数组异常包括空引用、负长度、越界与引用类型不兼容，并交给原异常表和现有Frame异常机制处理。完整证据下超出分析预算仍为analysis_limited；必要证据损坏为evidence_invalid。

原始外部数组的元素来源没有仅凭数组快照自动注册为边界来源；未建立依赖的外部元素保持unknown。本阶段不支持基本类型数组、多维数组、数组直接序列化目标或任意native修改。当前声明的数组能力主要用于已解释的本地数组和跨方法传递。

## 字段效果与来源边界

旧的字段写入版本和有限构造器核验继续生效。新容器状态没有减弱不透明屏障：可达性遍历增加stream关联列表、Optional成员、lambda捕获引用和数组成员。已解释且未逃逸的本地复制值可以保留；通过捕获或容器传给未知效果的对象需要失效。

Cart首次GET仍进入创建、保存和再次读取；第二次GET直接读取已有实体。本轮独立真值分别锚定前者的第二次仓储读取和后者的第一次读取，不把入口customerId或最终输出快照替代真实来源。首次请求unknown、后续读取known是模型边界的预期结果。

保存、异步、Date、一般构造器和一般框架类型转换继续留待后续。新对象数组语义不会自动证明HttpEntity构造器、Class常量、RestTemplate返回包装和动态Map投影，因此TicketInfo仍须逐层核验。

## 实现入口

- [计划与有限lambda站点](plan_application_calls.py)、[根计划及构造器限制](plan_execution_kernel.py)、[定义不动点](plan_collection_service.py)。
- [公共契约及数组和lambda证据](ExecutionKernelHooks.java)、[唯一调用序列](CollectionServiceHooks.java)。
- [统一状态](execution_dependency_state.py)、[跨Frame解释及别名屏障](infer_application_execution.py)。
- [独立语义输入](KernelContractFixture.java)、[独立实例坐标评分及扰动检查](run_kernel_contract_semantics.py)。

本轮仍保守多采，没有查询切片收缩或新成本主张。固定的构造器和公共模型边界使36个真实差距继续拒绝；这一结果与小程序数组、lambda正确性分别报告。
