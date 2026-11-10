# 通用观测语义与冻结复用核验

**规则控制通过；同执行离线兼容通过；新应用直接复用没有通过。** Petclinic 两个固定入口均在目标 `@JsonProperty` 序列化模式处规划拒绝。原版七次请求产生十个目标义务，两模式分别保留十项拒绝；没有 TF 业务部署或可认证的物理来源答案，不把它们计作十次传播错误。

参照为完整提交 `bcdf0590d1b22ea13717afded657a062f070e1df`。139 项清单中 138 项原样；审阅新发现一项版本矛盾未拒绝的问题，独立最小修复提交 **`e01f954`**：离线写版本校验增加实际根退出快照作为最终版本见证。在线 Agent 与 30 份公共契约全部未变。候选在 Petclinic 首次规划前冻结；后续只增加实验驱动、配置、评分和报告，没有为该应用增加规则。未进行性能实验或 push。

实际 Agent SHA256：`367cbb2300e507e5db4716c4e2fcbed1a39898c5e6c6f5f23583c4c1487e2764`。下文的“新采集”均直接使用这个冻结二进制，没有重新编译 Agent。字节码工具及原 JAR 元数据另存。

**规则一：容器成员身份转移。** 已共享的是状态转移原语，不是一个统一的“操作证明／成员映射”对象接口；没有仅改名或强行合并不同效果。所述条件是当前有限实现的保持条件，没有形式化完备性结论。

| 项目 | 实现及边界 |
| --- | --- |
| 原操作 | 普通 `List.get`、顺序回调、原地 `ArrayList.removeIf`，以及受限 `JSONArray.toList` 的成员身份复制。筛选和复制各自先验证实际输入到输出的成员对应，再调用公共转移。不能按内容相等配对。 |
| 规划与钩子 | `plan_application_calls.py:190` 附加 removeIf 契约；`plan_json_list_copy.py:5` 按实际依赖选择复制契约，要求 JSON 树观测许可。`CollectionServiceHooks.java:100` 在原调用开始记录身份／成员阶段，`:103` 在原调用正常完成后记录结果；异常完成亦保留原异常。`RemoveIfHooks.java:9`、`:15` 与 `JsonListCopyHooks.java:16`、`:20` 分别核验其操作事实，不额外执行谓词或未知集合方法。 |
| 必留证据 | 接收者、成员身份和顺序、epoch、字段版本、实际调用区间、Frame／调用点／call-id、实现／加载器／运行时。筛选另保留 SAM、捕获参数、实际谓词次序、modCount、原异常和回调写入；复制另保留空 feature 数组、实际 reader 缓存命中、已初始化实现、前后相同成员、新 ArrayList 及完成证明。 |
| 公共状态转移 | [member_state_transfer.py](member_state_transfer.py)：`:4` 定义容器／槽位／阶段坐标；`:7` 对标量及 null 经真实来源坐标查询；`:16` 复制已有 origins／selectors／unknown／allocation；`:20` 安装成员与阶段，默认 `local=False`；`:26` 登记引用可达关系。`infer_remove_if.py:36` 在核验后按原顺序保留成员并补入谓词选择依赖；`infer_json_list_copy.py:6` 核验缓存／身份分支后在 `:28`／`:29` 转移，在 `:30` 安装。`infer_application_execution.py:1172` 为复制结果登记可达关系。新列表不产生新来源或私有性。 |
| 省略资格 | 公共转移本身没有授予新的采集省略许可。`toList` 只能在实际已类型化成员复用等有限分支成立时解释；这些完成证明不能倒用来省略更早的 Redis 来源快照。本轮没有实现盒装载荷省略或通用需求切片。 |
| 失败处理 | 合法但契约未满足时保留完整观测、依赖保守 unknown；必要快照无法安全取得时仍留 problem／粘性无效。缺失、重复、错成员／回调／顺序／完成等矛盾拒绝认证。Java 8 筛选异常前未提交删除，但已发生回调写入或追加不能回滚。 |

普通列表读取使用 `infer_application_execution.py` 的 `copy_member`；顺序筛选见 `infer_sequence_callbacks.py:41`。removeIf 原地更新自身容器，因此不调用“安装新容器”的函数；toList 安装新容器。因此两者共享转移原语，操作事实、异常和生命周期仍属于框架适配。统一的显式映射证明接口仍是设计，不作为本轮已实现贡献。

**规则二：字段写入值省略。** 这里的省略是监测载荷省略；实际 JVM 写入照常执行，不能写成少执行业务写入或得到最小跨过程切片。

| 项目 | 实现及边界 |
| --- | --- |
| 原操作 | 原 `PUTFIELD` 成功后，记录对象、字段、站点和推进后的版本；抛出业务异常的写入不会产生成功写记录。同值写入也推进版本，不按值比较决定是否写入。 |
| 规划位置 | [plan_execution_closure.py](plan_execution_closure.py):18 汇总目标、所有解释方法的字段读取、getter 和构造摘要输入等值需求；`:33` 只许可非必需标量字段的受限普通写／setter；`:50` 保守保留调用、写入、选择、异常和效果闭包。它保留了很多解释器需求，不能称最小目标切片。 |
| 钩子位置与先后 | `PlannedServiceAgent.java:104` 将钩子置于原成功写入之后。`ExecutionKernelHooks.java:31` 的 `versionOnly` 在省略载荷之前核验策略、实际精确接收类、查询根和当前 Frame／setter 调用；不成立走完整取值分支。`Recorder.fieldVersionRecord`（`:182`）再核验许可、推进版本，保留 ACTIVE 修改保护及 `write-version`。目标字段和其他必要值仍由 `Recorder.field`（`:179`）记录真实载荷。 |
| 必留证据与离线转移 | 实际类／方法哈希、原字段和 PC、调用配对、根归属、对象身份、新版本、目标／必要字段值、异常、别名及完整性照常保留。`infer_execution_closure.py:6` 核验许可、站点、调用和版本；`infer_application_execution.py:490` 消费成功 PUTFIELD，在值已省略时将该非必要字段状态保守设为 unknown，不捏造常量或空来源。声明目标的状态、来源及选择证据应保持。 |
| 构造器边界 | 构造器省略另使用 `omitWrite`、`fieldVersion` 和所属来源调用完成上的 `execution_closure.elided_writes` 计数。它仍推进实际版本，但不为每次省略输出普通 `write-version`。两条路径共享闭包依据，协议表示尚不统一；不能把“计数证明”写成每次都具有相同的逐写记录。 |
| 失败处理 | 静态不许可则不省；运行守卫未成立时先采全；必要证据矛盾、ACTIVE 修改或监测失败仍拒绝／保持粘性无效。未知效果照旧 unknown。新增修复用已有 `exit.fields` 核对最终写版本，不增加事件、不更改版本计数、不减检查。 |

**新反例与最小修复。** `controls-02/write-values` 中首条无关字段 `write-version` 的实际版本为 2，改为 3 后，bcdf059 仍接受：投影后的 binding-return 不含该字段，已有验证只检查这些投影返回。实际根 exit 保留版本 2。修复让最终版本核对同时消费根 exit，现拒绝 `Application final write version differs`。原失败、旧代码接受结果及新拒绝结果均保留；新独立单元测试以字面版本事实判定，不从 TF 图生成真值。它是核验修复，不是新框架语义或公共成员重构。

**分层验收。** 下表均按单模式统计。完整逐项见[验收 CSV](generic-observation-acceptance-20261110.csv)。规则控制的真值来自事先指定的 fixture 分支和本 JVM 原始来源调用／字段／槽位；预测来自还原器，两者分离。

| 新采控制 | full | selective | 保护与限制 |
| --- | --- | --- | --- |
| removeIf | 8 正确、2 必要 unknown | 同左 | 7 正来源、1 常量覆盖空来源；同值不同读取，谓词原异常、CME 追加；每模式 6 类扰动拒绝。未知子类业务保持且捕获无效。 |
| toList，已初始化 | 5 正确、3 unknown | 同左 | 只复用已核验身份分支；每模式 7 类扰动拒绝，未知转换不被当作复制。 |
| toList，根内首次初始化 | 4 正确、4 unknown | 同左 | 首次初始化条件不满足继续 unknown，没有加业务预热来掩盖此条件。 |
| 普通应用写入 | 26 正确、8 unknown，另 2 异常根 | 同左 | 目标字段 26 次写入均保留载荷；selective 有 4 次版本记录无载荷。4 次同值目标覆盖版本分别 5→6、13→14、25→26、33→34，依赖按实际另一实参读取判分。 |
| 关闭写省略运行许可 | 26 正确、8 unknown | 同左 | 同计划，省略前 `service.write.observation=false`；selective 的版本记录 4→0，确实采全，不以更多 unknown 换取低成本。 |
| 本地列表的 null／标量成员 | 4/4 | 4/4 | 一项来源 null、两个同值不同来源出现、一项常量 null；来源 null 有真实来源，常量 null 才为空来源。 |

普通写另有 7 类证据保护，含错 owner／版本、缺记录、额外载荷、冒充目标、full 模式冒充省略及禁用许可；原有 6 类调用／构造／异常保护保持。两模式的不支持子类捕获在派生保护副本中取消 problem 语义、也不携带失败 sidecar，正式入口仍因原粘性 footer 拒绝。缺失／歧义来源与 selectors／unknown 转移另有独立原语控制；它们属于隔离验证，不冒称新增业务覆盖。真实新控制的 full/selective 在各 JVM 独立判分后，按来源边界及实际调用出现次序规范化比较，目标版本、来源和 selectors 一致；没有跨 JVM 比对象编号或随机消息 ID。

第一版额外控制尝试直接从 `List<String>` 读取边界取得来源；虽有调用区间，当前声明字段模式未产出所需 scalar-list 来源字段事实。`member-slots-01` 原样保留，不凭内容补坐标。第二版明确以三次 `Store.read(int)` 的 DTO 字段为来源，再进入本地标量／null 列表，4/4 独立通过。两版是不同控制范围：后者不证明前者的来源接入已经支持。

**同执行离线保持与在线省略不合并。** 十二份完整新控制捕获在旧／新离线核验器上复算，全部 replay 结果逐项相同，含答案、版本、来源、selectors 和根审计。这证明此次核验增强没有改变这些有效执行的答案。

“把 full 捕获的 write 直接改成 write-version”不具备现有许可：full 头明确禁止省略，也没有记录该次 selective 的省略前守卫成功。关闭运行许可的完整捕获同样不能伪装成守卫成功。因此**正向派生投影检查标为不可测试**；没有改 mode、补造许可，或把后续完成证明倒作前置证据。反向控制证实这种无许可派生会被拒绝。十二份旧／新复算不能替代这项缺失的正向投影证明；真实在线省略则由独立新采 full/selective 控制验证。

**冻结后新应用：固定两个入口，保留首道失败。** 选择官方 [Spring Petclinic REST v2.6.2](https://github.com/spring-petclinic/spring-petclinic-rest/tree/517a399cabe4dd7a40c07a81facd599df3cbf9cd)，原提交 `517a399cabe4dd7a40c07a81facd599df3cbf9cd`。首次 TF 规划前封存[完整协议](generic-observation-freeze-20261110.json)：原 JAR、完整应用类和生成代码、全部依赖清单、两个入口、输入、字段目标、仓储来源及独立实例评分条件。源码和环境在本轮已审阅，不称第三方盲测。没有以静态／运行成功结果替换入口。

运行环境为原版 HSQLDB／Spring Data JPA 配置、OpenJDK 8u504，镜像实际 ID 为 `sha256:efeab1ce0ab9219386bc7138b8389149a9b7849e868632ca09340e4039a58982`。原公开配置禁用安全认证，没有伪造身份。第一次原版构建因 JDK truststore 挂载失败保留，修正环境后原源码构建成功；这是构建环境修正，不是 TF 接入校准。

| 固定入口与目标 | 原输入及实际目标 | full／selective 首次结果 | 首道阻断及改动分类 |
| --- | --- | --- | --- |
| `SpecialtyRestController.getSpecialty`，`/name` | id 1、2、1；3 次 200，3 目标 | 各 3 planning_rejected | 业务是固定 name→DTO 字段转发，但 DTO 的 `@JsonProperty` 被当前公共序列化模式拒绝。需要通信／映射契约及其规划、绑定实现适配，不是补查询字段名或类哈希。 |
| `OwnerRestController.getOwner`，`/pets/*/name` | id 1、3、6、6；4 次 200，7 个非空成员目标 | 各 7 planning_rejected | 同一目标 DTO 注解先阻断。JPA 关联集合和 MapStruct 成员映射是后续审阅义务，尚未运行到，不能把它们写成已确认唯一根因。 |

来源边界分别保持 `SpecialtyRepository.findById(int)` 和 `OwnerRepository.findById(int)` 的实际返回。原生成 MapStruct 代码确认固定字段赋值及列表成员映射，但 SQL 种子和 wire 值不能证明本 JVM 的来源出现／对象／版本。因为规划拒绝，没有启动 TF JVM，**物理真值不充分、FP/FN 留空**。逐目标[独立评分状态表](generic-observation-petclinic-targets-20261110.csv)保留每个原版目标义务、来源声明、拒绝和缺证，未伪造成功评分。没有额外配置校准结果，也没有声称新应用直接复用成功。

这说明：成员转移原语可以在不同已有模型间复用；支持一个新入口仍先受通信和来源证据的适用性限制。本轮结果不足以断言只补框架证据便可支持 Petclinic，更没有证据要求改动依赖传播核心。应先解决最早的公共通信模型义务，再判断后续是否需要新效果契约或核心执行语义。

**复核及停止范围。** 主工件为 `artifacts/generic-observation-rules-20261110/`。最终控制为 `controls-03/`、`write-guard-off/`、`member-slots-02/`，完整再现驱动验证在 `reproduce-controls-01/`；最终含粘性保护的同捕获审计为 `audit-final-01/`，另保留 `audit-04/` 和 `reproduce-audit-01/`。中途元数据工具缺依赖、旧版本反例、首次标量列表来源失败和随机消息 ID 不能跨 JVM 对比的派生审计失败均保留。

```bash
python3 experiments/sockshop-mirrortaint/audit_generic_observation_rules.py \
  --home artifacts/generic-observation-rules-20261110 \
  --out /tmp/tf2-generic-rule-audit-new
python3 -m unittest discover -s experiments/sockshop-mirrortaint \
  -p test_write_version_exit_witness.py -v
python3 experiments/sockshop-mirrortaint/run_generic_observation_rules.py \
  --out /tmp/tf2-generic-controls-new
python3 experiments/sockshop-mirrortaint/run_generic_frozen_petclinic.py --stage plan \
  --protocol experiments/sockshop-mirrortaint/generic-observation-freeze-20261110.json \
  --out /tmp/tf2-petclinic-plan-recheck-new
```

输出必须使用新目录。第一条是同捕获复核，第三条是真实新 JVM 控制，第四条是封存声明的静态复核，都不是性能测量。原版构建、隔离部署及请求命令见工件 `commands.json`。备份见[清单](generic-observation-backup-20261110.json)，为本机副本。

本轮未重跑无关历史矩阵、未改旧成绩、未开发 RuoYi 盒装载荷省略。证据支持“有限公共规则控制通过”及“这些新控制的 selective 保持答案”；不支持“同执行派生投影已全面验证”或“冻结后 Petclinic 直接复用成功”。论文第三章尚未改写。
