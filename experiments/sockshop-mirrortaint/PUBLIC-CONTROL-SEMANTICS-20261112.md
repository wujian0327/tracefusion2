# 公共控制语义修订与组合验收

**原选择反例已修复；两条解释路径共用控制规则。原66项组合仍只有60项完整可答、6项unknown，本轮完整验收门槛未通过，性能实验继续暂停。** 预分配原异常、隐式异常正常完成及接口分支调用的补充控制分别为12/12、12/12、3/3。没有把这些正例替换原66项，也没有将其6项独立预期改为unknown。

起点为main `f68115e31646961eb15b7eed44c9e9ae83d99631`；最终离线核心为 **`4d29ba6`**。修改前的[规范](PUBLIC-CONTROL-SPEC-20261112.md)、[冻结协议](public-control-protocol-20261112.json)、原失败、原计划及独立预期均保留。Agent仍为`367cbb2300e507e5db4716c4e2fcbed1a39898c5e6c6f5f23583c4c1487e2764`，未重编译；30份公共契约／运行时JSON及原Java钩子源码未改。无新增框架、应用、业务部署或正式计时，未push。

新控制程序使用恢复的OpenJDK8u504；冻结元数据工具的提取进程使用宿主8u512，不将其写成业务运行JDK。实际命令、二进制、各控制JAR和计划哈希见[运行时收据](public-control-runtime-20261112.json)。

## 已实现的公共规则

| 状态／步骤 | 实际规则与证据 | 实现位置 |
| --- | --- | --- |
| 数据来源 | 保留已有origins；常量不会因为受条件控制而获得条件的数据来源。来源仍是原声明的实际读取出现。 | `control_dependencies.selection/selected` |
| 选择依赖 | 将条件的origins和已有selectors放入受控定义的selectors；保留值、分配身份及原数据来源。查询未声明的内部argument坐标不自动注册为新字段来源；原值已有选择状态继续保留。 | 同上；`ControlledStack/ControlledLocals` |
| unknown | 必要条件或效果不确定，结果仍unknown；数值和taken已知不能恢复依赖。缺失／歧义字段事实与错误调用身份分别沿原协议处理。 | `Control.branch`、`field_selection` |
| 作用范围 | 由已锁定、已核验的原字节码建CFG、唯一出口及立即后支配点；实际分支进入作用域，汇合时为可能被定义的局部槽位和可解析字段建立选择状态，再结束活动控制。 | `ControlFlow`、`Control.at/branch` |
| 循环与短路 | 同一动态Frame内对实际循环条件合并；退出时处理循环携带状态，零次循环也有选择。只使用已执行读取，不给短路未执行部分造来源。 | `Region`、局部槽位合流 |
| 字段及调用效果 | 实际写保留原身份、声明字段和版本，同值覆盖仍新版本；未执行备选中的已闭合写效果也参与合流。经现有`call_targets`枚举具体实现，不仅查接口名。复制／合流均不授予私有性。 | `Control._field_effects/write_value`；原`State.field_write` |
| 不透明备选 | 计划已标为不透明的备选效果不能当只读。对旧堆版本保持不确定性；较晚实际写入／声明来源可重新建立状态。不会因此把汇合后独立的新常量计算永久污染。 | `State.control_barriers`、`field_selection` |
| 调用／异常 | 每次调用独立Frame，继承调用者的活动控制，finally恢复。原异常对象、handler、次序和完成继续核验；正常完成与异常完成的选择也跨调用传递，在handler汇合后结束。 | `normal_operation/normal_completion/normal_outcome/caught`；原异常分派 |

两条入口分别为`infer_application_execution.execute`与`infer_execution_kernel.infer_execution`的v1路由，均调用同一`Control.branch`，原重复条件求值已移除。v1以独立协议单测验证真实入口调用；新JVM组合控制使用当前v8路由，不把单测写成v1新业务部署。

公共正常完成规则覆盖已支持操作中的空引用、数组条件和调用结果：例如被调用方法读取nullable并调用String.length，即使返回值被丢弃，正常返回还是进入catch仍可能选择后面的字段。该选择作为异常完成条件传递，不把整个Frame所有历史读取永久并入每个值。模块预留的除法守卫分支**不等于**求值器已支持相应opcode，本轮不计除法能力。

```text
进入Frame：验证原计划／字节码，建立本次控制上下文
到达PC：关闭在此汇合的作用域，合并相应槽位／效果状态
执行条件：核验Frame、PC、操作数与taken；进入至后支配点的范围
产生值／写入：保留数据来源，加活动选择及必要unknown
执行调用：核验实际调用；子Frame独立，传递值、效果及完成选择
异常分派：核验原异常与原异常表，转换作用域；处理后清理
退出Frame：保留已产生状态，恢复调用者；下一根请求使用新State
```

## 支持范围与停止线

| 形态 | 本轮状态与边界 |
| --- | --- |
| 标准整数／布尔条件、可核验引用比较、直接返回、局部赋值、三元、嵌套、短路 | 新JVM控制通过；真实值、引用身份／null及分支事实必留。两个缺失ID不能被当成相同对象。 |
| 有限循环零次／一次／多次、调用者分支中的调用、非入口递归 | 已验证，遵守原深度／步数预算；不是任意非终止程序支持。 |
| 字段写与简单别名、同值覆盖 | 已验证。字段合流接收者需可解析、调用效果需闭合；不改变物理写版本，不按值配对。 |
| 接口调用 | 条件支持：冻结计划中的候选目标及其效果闭合，实际执行仍由原目标／Frame证据核验；不据此开放任意代理/advice。 |
| catch/finally、跨方法显式异常、隐式空引用及其正常完成 | 对原有可核验异常分派和本批操作通过；不声称任意库内部异常／跨线程控制完备。 |
| 跨汇合后才使用的、未闭合may-alias写地址 | 不支持：`control-write-address`的AnalysisLimit，不能仅凭当前owner发证。含隔离拒绝控制，未称新业务覆盖。 |
| switch、jsr/ret、缺少身份的字面引用相等、未提供完整效果的任意库调用、并发／反射/native、类重定义 | 不新增支持。须保留能力限制或必要unknown；不能把本批结果推广为完整Java隐式流。 |

所有解释方法的必要字段读、完整转换输入及原合同核验继续保守保留；没有实施新的剪枝或最小跨过程切片。库模型必须提供其真实操作、效果和返回值状态；本公共规则不自动补齐所有容器结构或库内部的选择语义。

## 新采控制：全部分母分别报告

最终使用同一冻结Agent，新采full、固定许可／body-off、selective，六组各三份JVM捕获。最终离线类型保护补丁另以同批完整捕获复算；不是重新部署Agent。每JVM先以预定程序规则和原始调用／字段／版本判分，再规范化比较，三配置答案一致。

| 控制，每模式分别统计 | 目标 | 完整正确 | unknown | 结论 |
| --- | ---: | ---: | ---: | --- |
| 原`b.id != choice.index` | 4 | 2 | 2必要opaque | 两个正例有选中成员的独立来源及完整3项selectors；缺条件源为unknown |
| 原直接布尔返回 | 4 | 2 | 2必要opaque | 保持2项真实Flag选择证据，不替换原反例 |
| 原66项组合 | 66 | **60** | **6** | **原正例门槛false**，未删除未回答项 |
| 查询前构造的同一原异常对象，catch/finally及跨调用 | 12 | 12 | 0 | 原对象／业务保持，缺callee条件源时unknown |
| 正常完成选择：返回值未使用、二级调用、来源null／常量null、汇合后常量 | 12 | 12 | 0 | 选择依赖未因正常完成或丢弃值而丢失 |
| 接口条件调用，含不调用的分支 | 3 | 3 | 0 | 先前0次分支漏selector的失败保留；从2/3修到3/3 |

原66项按程序字面规则独立给出数据／选择预期，覆盖比较返回、局部改写、三元、嵌套、&&/||、循环0/1/2次、条件写、同值覆盖、别名、调用、无关分支及后续同线程正常请求。原数据来源、目标及输入未为通过而改变。54项规范化改写比较一致；不宣称任意语义等价程序的溯源答案恒等。

**剩余6项是原scenario14/16各三个输入。** 它们在查询内包含未解释的`IllegalArgumentException(String)`构造。实际调用时原不透明效果保守失效；未执行备选也缺少影响范围证明，不能认定与旧来源对象无关。具体字段值仍为7，不构成无修改证明。汇合后的独立常量9仍known，说明没有把历史分支永久并入Frame。没有为异常构造新增只读摘要，没有将原六条金标准改成unknown或从66中移除。预分配原异常的12项是另封存的组合控制，只隔离控制语义，不抵消原六条未回答。**因此不宣布本轮完整验收通过，也不恢复正式计时。**

隔离公共规则16项通过；三配置合计186项证据扰动均未产生错误确定答案。原始字段真值及独立字面预期先保存，预测只用于评分。来源为null仍是实际读取，常量null不产生新来源；同值不同来源不合并，常量覆盖的数据来源清空但保留选择及新版本。

| 扰动 | 实际处理 |
| --- | --- |
| 条件字段缺失、歧义、没有匹配版本 | unknown，不能用具体taken恢复known |
| 错来源call-id／PC、物理写版本倒退／重复 | 拒绝 |
| 分支缺失／重复／结果矛盾、错Frame／PC、错父调用 | 拒绝 |
| sticky无效标记 | 拒绝；后续正常状态不能恢复认证 |
| 被调用者条件源缺失，含正常／异常两种完成 | unknown |
| 操作数缺失、非法整数位宽／类型、引用ID同时缺失 | 隔离保护拒绝；字面引用身份尚无合同的合法形态为能力限制，不按值认定相等 |

## 旧执行的针对性复算

固定14份完整旧捕获，在独立进程比较`f68115e`与最终核心，没有过滤记录、重采业务或更改旧捕获。全部数据来源和字段版本不变；根审计亦逐项相同，selectors和known变化单列。

| 旧捕获 | known，旧→新 | 选择变化及评分边界 |
| --- | --- | --- |
| 原选择反例，三配置 | 各2→2，另2 unknown | 各2个正例补齐selectors，原字面预期保留 |
| 直接返回正例，三配置 | 各2→2，另2 unknown | 来源／版本／selectors保持 |
| 原removeIf控制，两模式 | 各8→6／10 | 4项selector变化；原case4的2个known改unknown：catch比较依赖未解释的静态ORIGINAL状态。不是业务损坏，不撤销新规则追求旧全图相等 |
| RuoYi部门详情，两模式 | 各5→5 | 无选择变化；无独立完整选择真值，不扩张结论 |
| RuoYi部门列表，两模式 | 各39→39／43 | 43项selectors变化，原4项冷启动unknown保持；**选择部分尚未充分独立评分** |
| RuoYi字典，两模式 | 各12→12 | 无选择变化；旧显式正确不替代选择正确证明 |

RuoYi各结果仍归原在线执行，只是新离线语义复算；不能拼成新Agent全量成绩。未机械重跑Mall、Account、ZLT及62＋29＋15。MT和Galette继续仅按共同显式来源评价，未参加本轮selectors排名。修改版Galette39/39的六份原始捕获和评分文件，共18文件，与本轮之前的封存归档逐项一致。

## 版本、工件与复核

分阶段提交：`a559773`规范／冻结，`a03ca64`公共范围及合流，`3c8b81f`未闭合效果保护，`67e57c8`正常／异常完成与写地址边界，`b1a6aca`接口候选效果，`bf2ce9f`及`4d29ba6`补齐操作数／引用身份与JVM整数保护。代码不含业务类或字段传播公式。

主目录`artifacts/public-control-semantics-20261112/`。最终新控制为`frozen-*`，最终原始捕获复算为`old-capture-comparison-final-core`。早期61/66、62/66、接口2/3、异常9/12及所有驱动失败均保留。隐式异常补充控制的JSON封存首次因登记脚本语法失败，修正登记晚于首次启动；字面规则已先写在源码中，**不称该补充控制预注册**。首次分支扰动误选声明来源内部、非计划解释的分支；修正为当前计划的必要分支，原结果保留，未删除源内部原事件。

最终复核见`delivery-audit/`；机器可读[逐目标控制表](public-control-targets-20261112.csv)、[证据扰动表](public-control-guards-20261112.csv)、[旧捕获清单](public-control-old-captures-20261112.csv)、[支持范围及代码映射](public-control-support-20261112.csv)、[结果快照](public-control-results-20261112.json)随Git。完整原始事实、各次候选、独立预期、源码和必要运行时另按[备份收据](public-control-backup-20261112.json)保存，是本机副本。

```bash
python3 experiments/sockshop-mirrortaint/audit_public_control_semantics.py --out /tmp/tf2-public-control-audit-new
python3 -m unittest discover -s experiments/sockshop-mirrortaint -p test_control_dependencies.py -v
python3 experiments/sockshop-mirrortaint/check_public_control_old_captures.py --out /tmp/tf2-public-control-old-new
```

第一条以最终离线核心复算本轮完整控制捕获并核对预期／版本／selectors／状态，不是新JVM或性能测量；第三条复算旧执行。新采入口为`run_nonempty_selection_control.py --revision-protocol <candidate-4d29ba6.json> --out <新目录>`及其`--direct-predicate`，以及`run_public_control_semantics.py --out <新目录>`和`--exception-controls|--implicit-controls|--interface-controls`。输出一律用新目录。审计进程完成不表示完整语义门槛通过，`revision_full_acceptance_passed`仍为false。代码与小型报告提交main，不push。
