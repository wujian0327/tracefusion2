# 目标相关观测闭包：算法与保持条件

本轮以 `7e4ad0b900a64871259a5fac008968128cc5ec28` 为能力和成本参照。当前是开发及验收中的算法说明，正式冻结、业务保持和成本结果分别报告。没有任意 Java 程序完备性证明。

输入是原字节码模型、具体入口、物理目标字段及响应路径、显式来源调用集合，以及部署实现与配置。输出是观测计划：必要证据、可省略值、静态资格、实际执行守卫和省略前的完整观测回退。来源定义和对象实例坐标不因收缩而改变。

## 闭包的组成

| 义务 | 本版实现 | 仍保留的证据 |
| --- | --- | --- |
| 目标及其计算 | 跨方法操作数依赖；目标、全部已解释字段读取和 getter／构造投影；有限解码协议的全部投影字段 | 实参、返回、实际实现和来源调用 |
| 后续计算 | 候选效果调用及其全部转发祖先的后缀只能转发引用；存在后续字段／容器读取、计算、调用或 handler 时不剪该方法体 | 完整路径及读取观测 |
| 修改与可达性 | 独立维护对象、字段版本、容器阶段、别名和发布；构造器也属于可能传出来源引用的调用 | 所有写入、版本、引用、发布和契约事实 |
| 路径及异常 | 保守保留分支、循环、调用及异常；仅在受限效果区域内允许原有局部性守卫支持的省略 | 实际调用与正常／异常完成 |
| 来源与通信 | 显式调用边界和实际 source-call-id；输入／输出及消息角色分开 | 来源调用区间、字段坐标、绑定、完整性和失败标记 |

字段闭包目前仍作保守扩张：解释方法中的非目标读取也保留，有限解码投影也整体保留。它不是最小切片。没有因“当前还原器未读取这条记录”就认定记录无用。

```text
plan(model, query, deployment):
    P = select_applicable_strategy(model, query, deployment)
    assert every_declared_source_is_preserved(P)
    D = backward_operand_and_field_dependencies(P, query.target)
    D += all_interpreted_field_reads_and_verified_transfer_projections(P)
    E = writes + aliases + publication + membership + selection + exceptions
    C = source_occurrence + binding + finite_contracts + capture_integrity
    V = original_scalar_snapshot_fields(P) - fields(D)
    B = directly_forwarded_source_effect_regions(P)
    B = regions_with_reference_only_continuations(B)
    B = regions_without_unresolved_constructor_transfer_before_cut(B)
    return P with (D, E, C, V, B, reasons, guards, fallback)

observe(boundary, actual_state):
    if query_scope/type/actual_call/demand_qualification_not_met:
        collect_original_values_before_omission()
    else:
        skip_only_permitted_scalar_value_extraction()
        traverse_references_and_record_versions_and_effects()
        record_policy_identity_and_actual_omission_counts()

enter_effect_region(call, actual_state):
    if static_qualification_and_unexposed_island_guard_hold_before_call:
        omit_only_authorized_internal_read_values_and_branches()
        retain_call_completion_and_all_required_effects()
    else:
        collect_full_region()

reconstruct(capture, P):
    reject_problem_sticky_failure_or_incomplete_capture()
    recompute_static_permissions_and_verify_runtime_witnesses()
    interpret_required_execution_and_conservative_effects()
    bind_target_and_return_original_instance_source_coordinates()
```

## 两类实际省略

**边界快照值投影**在反射取值、标量装箱及字段事件构建之前执行。仅可省去闭包之外的受支持标量字段值；引用遍历继续执行。当前有限的 Map 叶投影还要求来源对象直接转发、路径为确定的单叶、没有后续已计划 Map 消费；不省未知可变值、Date、枚举或任意 Number 实现。当前元素／类型／作用域不适用时，先采全，不把合法输入变成漏采后拒绝。

**效果方法体收缩**沿用局部性证书，不把方法宣告只读。方法可更新日志对象、缓存或数据库；仅受保护来源岛能保持依赖。后续目标计算若还读被该调用修改的全局或容器状态，静态后缀条件直接取消候选。此前只检查返回对象身份会导致正常可回答输入退化为 unknown，已保存这类完整反例。

Map 叶省略发生在叶记录及值编码之前，迭代、引用遍历及已有值读取仍保留，不能将其计作省去一次 Map 读取。

构造器是单独的前缀义务：未知构造可接收来源对象并发布它，不能因没有普通调用事件而忽略。新反例中 full 为 unknown，而旧候选 selective 触发损坏拒绝；该失败已保留。本版对前缀构造可能传递来源引用的情况直接采全，包括部分已解释的构造。资格检查必须在省略前阻止此类收缩，不能仅依赖事后的无效标记。

## 认证与边界

| 条件 | 检查位置 | 实际控制证据 | 条件失败时 |
| --- | --- | --- | --- |
| 后续不再计算目标值 | `plan_body_observation.forwarding_suffix` 及全部转发祖先 | 同值全局字段覆盖后读取；容器更新后读取 | 运行前不生成该体内省略，采全 |
| 前缀构造未传出来源引用 | `plan_constructor_prefix_guard.eligible` | 未建模构造器将同一个来源对象发布到全局 | 保守取消候选，不能等写入保护事后使捕获无效 |
| 实际来源岛未暴露 | `BodyObservationHooks`，离线同构核验 | 直接发布、Map 包装发布、lambda 捕获／发布、同对象解码泄露 | 在进入效果区域前采全；必要未知效果继续 unknown |
| 未知分支与 handler 不参与省略 | 静态后缀资格及原异常表 | 正常／原异常对象／catch 回退／finally | 采全，保留原业务行为 |
| 省略字段不供解释或公共转换使用 | `application_value_fields`、解码投影及有限转换输入义务 | 原 Mall／ZLT 目标及转换配置核对 | 不能列出更小输入需求的转换，保留其完整原来源字段集 |
| 当前实例符合值投影资格 | `ResponseBindingHooks.SnapshotPolicy` | 根作用域、实际调用、字段类型及 Map 位置 | 在反射取值或叶记录省略前保留原观测 |
| 早回调没有留下后续映射影响 | SQL 原有实际工厂／元数据／handler 检查 | 分配前回调留下泄露工厂、替换实际 handler | 证书无效，结果 unknown；不按时间早来放行 |
| 证据完整且无矛盾 | 采集粘性标记及正式离线入口 | 必要来源／模式／策略／完成缺失、错配和 sticky invalid 扰动 | 拒绝认证；检测到损坏的批次不因后续状态恢复而重新有效 |

新增资格检查只分析字节码与已记录坐标。运行时新增值选择只检查已有作用域、实际调用、已核验字段元数据与精确的标量类型；没有为检查调用未知应用方法、getter 或 `toString`。原有限契约的受支持库调用及其实现／配置检查继续保留。

离线端重新计算计划中的许可并核对策略摘要、实际模式、作用域及省略计数；这些许可不创建来源。必要证据缺失、歧义、错误坐标及粘性失败继续拒绝。未知效果仍保守失效；前后同值或版本未变不构成局部性证明。

SQL 结果局部性继续核对实际工厂、元数据、type handler、缓存及受支持映射。新增严格控制在分配之前完成回调，但留下泄露工厂或更换实际 handler；两种模式均保持 unknown。早回调的结束时间本身不能证明后来对象独立。

本轮未新增 SQL、Feign、Spring、MyBatis 或 JDK 公共契约。通用部分是依赖义务、字段值许可、调用后缀／前缀资格和观测前回退；框架新鲜对象和有限传输仍依赖各自已审阅公共契约。新应用配置、元数据提取和独立评分属于实验接入。Gson、动态 Principal、新 sink 及任意调用切片不在本轮范围。
