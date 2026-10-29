# Apollo / Mall：两个冻结 TF 版本的直接迁移结果

本批保持 `ae7fe8d`、`78a9534` 的核心、Agent 和公共契约不变，按固定顺序执行 Apollo 五 API、Mall 五 API。全部 40 项总清单继续保留。本报告只描述本批十 API，不能称为完成全部 40 API 的共同任务能力对照。没有性能实验或 push。

**本批原版共同任务有 299 个实际入口返回字段目标。`78a9534` selective 已认证正确 0 个；MT＋B0 已认证正确 88 个、确定错误 5 个，另 5 个确定输出尚无充分真值。** 拒绝、无效和未回答保留在分母，不能由旧 Account40 或旧 62 查询结果抵消。这些数字限定本批环境与目标范围，不是完整 40 API 正确率。

第一次高层路由没有把已封存的显式来源声明传给 TF 计划。原计划、首次捕获及评分全部保留于 `audit-final-01`，接入缺口单列；不能用它掩盖必要来源未观测的问题。主表使用单列 **C1 配置校准**：经同一个冻结路由选择 profile，再使用该快照已有 `plan_response(source_calls=...)` 接口传入原声明，并调用同版后处理。全十 API、59 个候选／义务、输入、来源边界与逻辑来源规则不变；目标归属另按下文事后澄清。没有逐字段传播规则、增加库模型或放宽检查。可运行的 C1 TF 配置使用新部署；必要运行时条件已证明不成立的配置保留拒绝证明，不伪造捕获或重复触发同一失败。原版和 MT 的输入、二进制及来源配置未变，复用其原捕获。

来源正确必须同时满足实际目标绑定和独立实例真值。规划接纳、HTTP 200、原生标签或保存参数快照分别只是准备或事实，均不直接计作来源正确。

| API | 查询族 | 无 Agent 请求 | MT B0 字段状态 | TF ae7 full | TF 78 full |
| --- | ---: | --- | --- | --- | --- |
| apollo-1 | 14 | 200×5, 404×1 | unknown 70 | instrumented_business_failure 60；planning_rejected 10 | evidence_invalid 60；planning_rejected 10 |
| apollo-2 | 12 | 200×6 | unknown 60 | evidence_invalid 55；planning_rejected 5 | evidence_invalid 55；planning_rejected 5 |
| apollo-3 | 1 | 200×6 | evidence_invalid 6 | target_binding_unsupported 6 | target_binding_unsupported 6 |
| apollo-4 | 1 | 200×5, 400×1 | 无实际字段目标 | 无实际字段目标 | 无实际字段目标 |
| apollo-5 | 10 | 200×6 | unknown 60 | instrumented_business_failure 60 | evidence_invalid 60 |
| mall-swarm-1 | 6 | 200×6 | known_correct 32 | runtime_contract_rejected 32 | runtime_contract_rejected 32 |
| mall-swarm-2 | 2 | 200×6 | known_correct 4；unknown 4 | runtime_contract_rejected 8 | runtime_contract_rejected 8 |
| mall-swarm-3 | 7 | 200×6 | known_correct 30 | runtime_contract_rejected 30 | runtime_contract_rejected 30 |
| mall-swarm-4 | 3 | 200×6 | known_correct 12；known_wrong 5；unknown 1 | runtime_contract_rejected 18 | runtime_contract_rejected 18 |
| mall-swarm-5 | 3 | 200×5, 500×1 | known_correct 10；known_unchecked 5 | runtime_contract_rejected 15 | runtime_contract_rejected 15 |

表内保留冻结驱动的状态；细分诊断在逐实例 CSV 和逐配置原始事件中。`evidence_invalid` 不全部等于日志损坏：包括未建立响应字段绑定、库投影不支持，以及真正的监测失败。正式请求未执行与原版未生成目标分开。

字段对照分母来自原版共同任务；TF 拒绝或插桩失败时，不把原版已生成目标删掉。原版空容器、正常返回的实际 null 叶、异常 handler 输出和没有进入方法的输入分别记录。C1 的运行时拒绝不意味着发生了新 TF 部署或生成了 TF 物理目标。

| 工具 | 共同目标上的工具状态 | 具有本工具原始实例真值 |
| --- | --- | ---: |
| MT-B0 | evidence_invalid 6；known_correct 88；known_unchecked 5；known_wrong 5；unknown 195 | 223 |
| ae7fe8d-full | evidence_invalid 55；instrumented_business_failure 120；planning_rejected 15；runtime_contract_rejected 103；target_binding_unsupported 6 | 0 |
| ae7fe8d-selective | evidence_invalid 55；instrumented_business_failure 120；planning_rejected 15；runtime_contract_rejected 103；target_binding_unsupported 6 | 0 |
| 78a9534-full | evidence_invalid 175；planning_rejected 15；runtime_contract_rejected 103；target_binding_unsupported 6 | 0 |
| 78a9534-selective | evidence_invalid 175；planning_rejected 15；runtime_contract_rejected 103；target_binding_unsupported 6 | 0 |

- MT-B0：已核验正确 88，其中正来源 62、已知空来源 26。
- ae7fe8d-full：已核验正确 0，其中正来源 0、已知空来源 0。
- ae7fe8d-selective：已核验正确 0，其中正来源 0、已知空来源 0。
- 78a9534-full：已核验正确 0，其中正来源 0、已知空来源 0。
- 78a9534-selective：已核验正确 0，其中正来源 0、已知空来源 0。

双方逐项状态及差距见 [配对表](external-transfer-paired-20261029.csv)。基线导出和独立事实不足时，不填完整关系 FP/FN 为零，也不由“未发现基线领先项”推断能力相等。当前未完成完整 API 的返回＋保存／消息 sink 验收。

一个已独立核验的基线反例是 Mall.updatePassword：正常分支在保存和缓存删除后执行原代码 `return 1`，本任务的数据来源应为空；MT 在五次返回中却连到本次 UmsAdminMapper.selectByExample 的 `/0/status` 字段。预测关系来自原生标签解码，真值来自原代码和具体读取坐标，没有按数值相等补来源。本轮未另行证明缓存装箱等具体内部成因，不把表现当作完整根因结论。

## 主要诊断

Apollo 原业务配置使用 GsonHttpMessageConverter；冻结 TF 与 B0 的实际响应字段记录没有为这些 Gson 路径建立足够绑定。Apollo1 还暴露了未支持的 Map 监测路径：旧 Agent 可改变业务完成，新 Agent 保持业务执行后仍用 problem／失败 footer 拒绝损坏批次。早期因插桩准备请求 500 而未发出正式请求的捕获原样保留，另列准备失败；环境驱动后来识别该具体错误并尝试正式输入，没有修改算法。

独立 B1 Apollo 诊断观察到实际 Gson 对象代码来自 `file:/tf2/mirrorTaint.jar`，与应用声明的 Gson 2.10.1 不同。这个依赖差异需要后续隔离或语义校准，不能直接算作 MT 原生传播错误。B0 已有标签不能替代缺失的 wire 字段实例；本轮不加入 Gson 来源规则使其通过。

Apollo3 的原始 long 返回与 Apollo4 的方法 null／空 HTTP body 另列。空 body 不是 JSON null 字段；空列表没有元素目标，实际 null 字段则仍是字段目标。原静态候选、实际 wire 叶及持久化义务分开保存，没有因工具不支持而删除 API。

Mall 选择的 read-forward 契约只列两个 8u111 运行时，当前固定 8u504 不满足必要版本条件。第一次已实际运行：旧 Agent 可将正常请求变成 500，新 Agent 隔离监测异常后可返回 200，但捕获仍无效。C1 为每查询、每模式保存必要条件拒绝证明，未新增运行时登记或切换策略。通过这项检查也不会自动打通来源：计划仍列服务调用为必要不透明调用，部分实际源调用者未纳入 Frame。

Apollo2 的具体后续阻断包括 Env.valueOf 的外部静态初始化，以及 ReleaseAPI.findActiveReleases 的数组 Class 字面量不在当前支持形态；实际 RestTemplate 调用者 RetryableRestTemplate.doExecute 没有进入计划 Frame。C1 虽补声明，捕获仍无对应 binding-source；Gson 绑定亦未具备。三个布尔字段在静态目标序列化模式处拒绝。完整 [支持缺口清单](external-transfer-support-gaps-20261029.json) 保留这些首道阻断，不承诺补一个指令便恢复整组。

## 共同任务与独立观测适配器

原先仅在应用服务接口处停止的来源扫描不适合评价 DB 来源。本批实验清单沿实际应用实现审阅，声明具体仓储／mapper／RPC 读取边界，业务 helper 不重新当来源。逻辑真值规则在新工具运行前封存；评分 Python 实现随后编写，二者时间分别保留，不宣称完整评分代码预注册。

目标归属另有事后澄清：注册失败和 admin-login 缺失用户名的 HTTP 200 是原异常 handler 输出，并非声明控制器的正常返回。原输入不改，handler 叶作为未绑定义务另列；全部 API、候选及负例请求仍保留，不算来源成功。admin-login `/data` 候选只在该 handler 响应中是 null 叶，在其余正常返回中是对象，故没有本批声明入口的标量／null 目标。原三项 target-absent 诊断保留，最终范围解释单列。该澄清发生在部分首次运行之后，不能称完整预注册的目标归属验证。

其中 7 个 HTTP 200 handler 叶另存为未绑定义务，未包含在 299 个声明入口返回目标中，也没有记成正确或业务 N/A。299 的统计不能覆盖这部分义务或全部 HTTP 错误响应，更不能当作完整 API 正确率。

B1 在首次矩阵封存后另行采集实际源调用与保存／删除参数的开始、正常或异常完成、对象和字段坐标。它只补原始事实，不输出来源答案，也没有实现 TF 保存 sink 查询。原生 MT JAR 与 B0 二进制不变；新增插桩的透明性仍按下表的实际检查范围陈述，不宣称任意库写入覆盖或原生传播等价。

下表调用数覆盖整批准备与正式请求；JSON 另列按实际消息配对的正式请求调用数。不能把准备阶段的调用数当成评分目标。

| B1 API | 整批源调用 | 整批 sink 调用 | 参数完整快照 | 调用配对 | 失败标记 |
| --- | ---: | ---: | ---: | --- | --- |
| apollo-1 | 30 | 0 | 0 | True | False |
| mall-swarm-2 | 18 | 5 | 5 | True | False |
| mall-swarm-4 | 6 | 11 | 11 | True | False |
| mall-swarm-5 | 6 | 12 | 12 | True | False |

旧 Piggy 保存前事实另外审计：每模式 36 项可定义为具体 save 调用前实参字段目标，五项错配保护通过，不需要为这 36 项重新采集。冻结 TF 缺少保存 sink 查询入口，MT 旧捕获缺相应完整导出，因此仍不把返回字段答案代作保存答案。另四项 currency 事实缺口保留。

## 迁移工作量与剩余环境

本批新增 TF 公共模型 0、TF 核心与 Agent 修改 0；新增的是任务配置、环境驱动、独立评分与单列的 B1 原始事实观测器。迁移台账记录入口、审阅方法、边界和阻断；文件数不等于人工工时，没有虚构工时。必须分别记录“模型在计划中出现”“运行时调用发生”和“帮助产生经独立核验答案”，不能用前两项宣称复用成功。

ZLT 的两个无 Agent 原版服务已在本地原 SQL／MySQL／Redis 集群／Nacos 配置下启动，四个 GET 路由得到 HTTP 200。列表接口已有列表响应，缺失 mobile 返回空内容；当前用户接口的响应未证明正常认证上下文。该预检不提供来源答案，没有调用写接口，也没有伪造身份；正式输入和独立真值仍待封存。FEBS 归档替代、goodsKill、SuperMarket 的其余环境阻断继续保留；Sock Shop 本批整 API／sink 任务仍待执行。它们不记 TF 失败或业务 N/A，不用历史 62 查询填入本批。Station 403 的既定决定不变。

## 版本与工件

原应用使用已封存历史候选，不是已确认的论文原版本；源码、反射、旧静态规划和环境诊断已经暴露，不称第三方盲测。

- 算法：`ae7fe8d8b9e23d8ce197870ff0069c7f1bee84eb`、`78a95343c127fcc5732174b783e9d528b354a9d7`。
- 源码校验：旧 68 项、新 87 项，均未改动；旧首次 2322 文件及本批 B0 首次 16862 文件哈希保持。
- 新 TF Agent SHA256：`b20ba71e568672a0a91be3c113b4e6db44686d9967ddb1ca4d5f95c8ca70a45a`。
- 原生 MT JAR SHA256：`e4c679206993b45c6727a4ace1d4dcff6df0ded2b80b56b27b8c86741be63fe7`。
- C1 实际新部署 132 份 TF 配置，清理退出均正常；另 84 份配置在部署前按运行时必要条件拒绝，没有伪造结果文件。15 项独立评分保护、6 项冻结配置组合等价检查通过，详见 [校验摘要](external-transfer-validation-20261029.json)。
- 主工件：`artifacts/external-frozen-transfer-20261029/`。首次输入／逻辑真值、计划、镜像、独立网络和 DB、调用日志、源事件、B0／B1 版本和失败尝试均保留；C1 位于独立 `source-config-C1/`。

完整工件和 Docker 镜像需另行备份；Git 仅保存代码及小型结果。原 Account40 和旧成本结果不改写。本轮不据这些能力捕获主张性能优势。
