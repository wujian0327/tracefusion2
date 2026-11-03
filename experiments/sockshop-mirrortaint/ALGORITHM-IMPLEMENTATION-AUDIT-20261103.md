# Java观测闭包：实现与论文措辞核对

参照为`1308589`，本轮核心候选为`d69f54a`。本轮不宣称实现最小跨过程切片，也没有任意Java程序的完备性证明。旧算法报告和正式成本表保留；这里核对当前代码实际做了什么。

## 三种义务不能混为一个数据切片

| 部分 | 实际来源及位置 | 作用 |
| --- | --- | --- |
| 目标数据需求 | [plan_execution_closure.py:18](plan_execution_closure.py#L18)：目标字段、所有解释方法的GETFIELD、getter及构造输入字段 | 这是保守字段需求集合，不是仅从目标反向得到的最小集合 |
| 操作数与效果／路径义务 | [plan_execution_closure.py:50](plan_execution_closure.py#L50)：以返回、全部调用、写入、分支及handler为种子，再沿方法内操作数依赖反向扩张 | 当前种子覆盖整个已计划方法的效果和路径，不能描述成只保留目标所需指令 |
| 公共传输与认证义务 | [plan_target_observation.py:11](plan_target_observation.py#L11)：加入decoder全部投影字段；转换协议未声明更细输入需求时，保留完整原来源字段集 | 这些是解释器／契约的保守需求，不全部是已证明的目标数据依赖 |

别名、发布、对象身份、字段版本、容器阶段、实际调用、分支及异常另行保留。来源仍是原声明入口和实际仓储／RPC读取出现；返回快照只用于绑定。RuoYi的有限Map包装许可也只用于观测，不是传播摘要、来源或局部性证书。

```text
plan(bytecode, query, deployment):
    choose under declared applicability checks; retain pending runtime conditions as conditional
    D = target + all interpreted field/getter/constructor value inputs
    D += full decoder projections + conservative conversion inputs
    I = backward_operands(all return/call/write/path/handler seeds)
    E = identities + versions + aliases + publication + container effects
    C = source calls + communication + target binding + finite contracts + integrity
    permit omission of snapshot scalar values outside D only at checked scopes/types
    permit effect-body cuts only at statically qualified forwarding regions
    emit permissions, retained reasons, runtime guards and pre-omission fallback

observe(actual execution):
    if a static or runtime qualification fails normally: collect the full region
    else: omit only the licensed value/read/branch observations
    always retain E and C
    if necessary evidence is missing or contradictory: mark invalid, never certify

reconstruct(complete capture):
    validate C and recompute omission permissions
    interpret required execution, applying conservative opaque effects
    bind target; return status, instance sources, versions and selection evidence
```

这里的`I`是多种义务的保守并集；伪代码没有把它冒充最小目标切片。

## 两类实际省略与第三类已有写值省略

1. **边界标量值投影。** [ResponseBindingHooks.java:112](ResponseBindingHooks.java#L112)在具体根、实际调用、字段类型和需求许可成立时省去标量取值或Map叶记录。引用遍历、版本及效果事实仍保留。Map叶省略不等于省去了Map迭代或已有值读取。
2. **受守卫的效果方法体收缩。** [plan_body_observation.py:57](plan_body_observation.py#L57)要求候选及转发祖先的后缀只能转发引用；[plan_constructor_prefix_guard.py:11](plan_constructor_prefix_guard.py#L11)拒绝可能提前传出来源引用的构造前缀。[BodyObservationHooks.java:17](BodyObservationHooks.java#L17)在调用开始之前，根据实际来源岛、接收者／实参、发布及修改状态决定是否进入省略模式。只省略许可区域内的读取值／分支记录，不把日志、缓存或保存链声明为只读。

当前方法体收缩还受很窄的调用形态限制：候选必须是计划内、非构造器的直接`invokespecial void`或同owner的`invokestatic void`；相关转发祖先的调用后缀只允许受限的引用转发，拒绝handler、回边和后续目标计算。一般虚调用、未知advice和任意方法体不能因此收缩。调用开始／完成、实参身份、写入版本、发布和必要契约事实继续保留；不能把方法体省略写成“删除了整个调用”。

此外，`plan_execution_closure.application_write_sites`及`ExecutionKernelHooks.omitWrite`已有有限标量写值省略，保留真实写入版本；不能把该机制的收益也重复算成本轮边界投影的新贡献。

| 情况 | 检查位置／控制证据 | 结果 |
| --- | --- | --- |
| 后续还要读取全局／容器或计算目标 | `forwarding_suffix`及全部转发祖先；既有future-state控制 | 静态不生成该体内省略，实际采全 |
| 构造可能传出来源引用 | `eligible`；保留的同对象构造发布反例 | 省略前取消候选 |
| 来源岛尚未闭合、已发布、实参可触及或守卫不成立 | `BodyObservationHooks`的调用进入决定；直接／间接／lambda发布及守卫false控制 | 在区域开始前采全，必要不透明效果仍可产生unknown |
| 当前对象／字段／位置不满足值投影条件 | `SnapshotPolicy`；原Map值类型、作用域及位置控制 | 先保留原值观测，不把普通不适用输入变成漏采后拒绝 |
| 已省略期间出现与许可矛盾的修改或证据损坏 | [infer_body_observation.py:26](infer_body_observation.py#L26)、[infer_target_observation.py:9](infer_target_observation.py#L9)和粘性失败标记 | 拒绝认证，不能事后恢复已丢的记录或伪造回退成功 |

较早SQL回调的时间本身不是独立性证明。原工厂、handler及映射配置检查和早回调留下状态的严格反例继续保留；不能由“分配前已结束回调”推出后续对象私有。

## 保持条件与本轮验证方式

同一捕获的新旧解释器必须保持完整内部答案：状态、来源发生、对象／字段／版本、selectors和根执行审计。本轮将公开查询答案／独立评分比较与内部完整重放分开，后者由`audit_zlt_selection_replay.py`逐项比较；公开查询接口本身不导出selectors。

Agent变化后的业务保持使用新部署。跨JVM不比较对象编号，而按各JVM自己的原始调用与物理字段坐标独立评分，并比较逻辑来源签名。数值只作一致性核对；同值不能合并来源，同值覆盖也不能保留旧版本依赖。已知空来源、unknown、analysis_limited和evidence_invalid分别保留。

## 论文可用措辞

- 可写“以目标和执行／效果／认证义务组成保守观测闭包，在有限条件下省略边界值与效果区域内部观测”。不写“实现了最小跨过程切片”。
- 可写“效果区域允许修改其他对象，受保护来源的保持依赖有限可达性证书和前后续静态条件”。不写“未作为实参传入就不会受影响”。
- 可写“在披露的固定任务上检查来源、选择证据及状态保持”。不把同值响应当作来源保持，也不把开发修订当作冻结后的直接迁移成功。
- ZLT初始化索引是full/selective共享查找优化，不是观测减少。旧在线CPU、延迟和字节保持原表；本轮离线复算不能改写那些列。

`docs/paper-draft.md`仍是明确标注2026-10-09的Go工作稿；其中的路径不可区分性条件及Go实验不等于Java内核已实现相应最小化。本文没有将新的Java结果回填为该历史稿的实验，也不将条件性论证改写成一般完备性证明。

支持仍限于声明的对象、标量、字节码与库语义。反射／native、任意可变标量及未建模的并发共享修改没有由此获得保证；静态或离线预算耗尽保持analysis_limited，必要效果不透明保持unknown，必要证据矛盾仍拒绝认证。
