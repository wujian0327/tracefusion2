# RuoYi／TeaStore：冻结后首次复用

本轮固定算法 `130858947f3eabc1dbee8693f11c926f37f289e9`，新入口首次规划及运行后没有修改核心、Agent 或公共契约使其通过。只评价封存的两个应用、各六个查询族；原 40 API 及其未完成任务继续保留，不合成全 API 正确率。

RuoYi 使用[官方 springboot2 固定提交](https://github.com/yangzongzhuan/RuoYi-Cloud/tree/86527f4da8448a11630ea8dcd03a585cdd6565c6)，没有使用 master；TeaStore 使用[官方固定提交](https://github.com/DescartesResearch/TeaStore/tree/34b37f7e7be433ce72d5f9455e66922a13116749)，原版 Java 11／Tomcat 10 部署。实际原始 JAR／WAR、依赖、JDK及镜像 digest 保存在本批清单。源码和环境已审阅，不称第三方盲测。

六查询族／应用的选择及来源规则先封存，包含非空正来源、重复值、集合选择及副作用。v1／v2 在核心修改前保存；SysConfig 声明类坐标的 v3 修正发生在核心开发后、首次工具规划前，原协议完整保留。原源码提交先固定，但完整JAR／WAR及依赖清单在核心开发期间完成，02:13 UTC保存构建回执；没有满足“全部构建工件均在首次核心修改前锁定”的严格顺序。这不是完整坐标和工件均事前注册的盲测。输入未按工具成功更换，封存新查询未用于核心调试。

评分前发现原 SQL 用 `sysdate()` 初始化 create_time，各独立数据库的 createTime 不同。跨 JVM 业务对比仅将这些非查询时间字段规范化，原始完整响应是否相等另存；已关闭部署缺少的自身 DB 时间事实不补造。此澄清发生在捕获后，单独保存。它不参与所选字段的实例来源真值，也不能证明所有未查询时间字段正确。

| 查询 | 原版所选目标 | TF full | TF selective | 固定 MT B2.2 |
| --- | ---: | --- | --- | --- |
| ruoyi-1 | 5 | evidence_invalid 5 | evidence_invalid 5 | known_correct 5 |
| ruoyi-2 | 43 | evidence_invalid 43 | evidence_invalid 43 | known_correct 43 |
| ruoyi-3 | 12 | evidence_invalid 12 | evidence_invalid 12 | known_correct 12 |
| ruoyi-4 | 5 | evidence_invalid 5 | evidence_invalid 5 | oracle_or_target_unavailable 5 |
| ruoyi-5 | 24 | evidence_invalid 24 | evidence_invalid 24 | known_correct 24 |
| ruoyi-6 | 6 | target_binding_unsupported 6 | target_binding_unsupported 6 | known_correct 6 |
| tea-1 | 9 | runtime_contract_rejected 9 | runtime_contract_rejected 9 | oracle_or_target_unavailable 9 |
| tea-2 | 9 | runtime_contract_rejected 9 | runtime_contract_rejected 9 | oracle_or_target_unavailable 9 |
| tea-3 | 5 | runtime_contract_rejected 5 | runtime_contract_rejected 5 | oracle_or_target_unavailable 5 |
| tea-4 | 5 | runtime_contract_rejected 5 | runtime_contract_rejected 5 | oracle_or_target_unavailable 5 |
| tea-5 | 12 | runtime_contract_rejected 12 | runtime_contract_rejected 12 | oracle_or_target_unavailable 12 |
| tea-6 | 6 | runtime_contract_rejected 6 | runtime_contract_rejected 6 | generated_state_unpaired 6 |

拒绝、业务变化、证据无效和真值不足均保留在原版共同所选目标的分母。目标没有绑定或实例事实不足时，不以图、标签或同值匹配生成真值；不填完整关系 FP／FN 为零。导出成功也不直接计作来源正确。

各工具业务比较、目标绑定、来源调用完整配对和 oracle 充分性在逐实例表中分别保存。TeaStore 原版成功不能证明工具适用；独立 Java 11 控制中，TF 保持业务输出但运行时核验拒绝，固定 MT 原生控制启动成功也不能证明其完整 Jakarta／JPA／JAX-RS 接入。

| 查询 | 其他实际 null／handler 义务 | TF 首道条件／阻断 | MT 首道条件／阻断 |
| --- | ---: | --- | --- |
| ruoyi-1 | 1 | Raw capture incomplete or explicitly invalid; do not use it to certify instance truth | captured |
| ruoyi-2 | 0 | Raw capture incomplete or explicitly invalid; do not use it to certify instance truth | captured |
| ruoyi-3 | 0 | Raw capture incomplete or explicitly invalid; do not use it to certify instance truth | captured |
| ruoyi-4 | 0 | Raw capture incomplete or explicitly invalid; do not use it to certify instance truth | captured |
| ruoyi-5 | 0 | Raw capture incomplete or explicitly invalid; do not use it to certify instance truth | captured |
| ruoyi-6 | 0 | Dynamic AjaxResult Map leaf /code, not an actual declared Java field. If the frozen query interface cannot express it, keep target_binding_unsupported; do not fabricate a field. | captured |
| tea-1 | 0 | Independent Java 11 control preserved business but frozen offline runtime check rejected: Application runtime pin differs. | captured |
| tea-2 | 0 | Independent Java 11 control preserved business but frozen offline runtime check rejected: Application runtime pin differs. | captured |
| tea-3 | 1 | Independent Java 11 control preserved business but frozen offline runtime check rejected: Application runtime pin differs. | captured |
| tea-4 | 0 | Independent Java 11 control preserved business but frozen offline runtime check rejected: Application runtime pin differs. | captured |
| tea-5 | 0 | Independent Java 11 control preserved business but frozen offline runtime check rejected: Application runtime pin differs. | captured |
| tea-6 | 0 | Independent Java 11 control preserved business but frozen offline runtime check rejected: Application runtime pin differs. | captured |

原版实际 null 祖先字段、空容器及异常 handler 输出另外列义务；它们不因所选成员叶缺失而计成功或整 API N/A。所选返回叶不是整个 HTTP API、更不是保存／消息 sink 的完整范围。

本批所选目标合计 141。TF 两模式均没有认证来源答案；固定 MT 已独立匹配 90 项，其中 84 个正来源、6 个已知空来源。未完成共同接入的任务不用于完整关系 Recall 或工具排名。

RuoYi 的 TF 捕获有实际来源记录，但监测退出失败留下 problem／粘性无效标记；仍拒绝整批，不将其说成传播算错。RuoYi config 查询的封存边界是 selectConfigById，而原入口服务实际调用 selectConfig(SysConfig)，固定 MT 没有这次已声明来源事实，因此 5 项未评分。这是首次任务接入缺口，本轮不移动边界补成成功。

TeaStore 的固定 MT 记录仅有 export-start／closed，native_available 为 false，缺少所选目标与实际来源事实；独立控制可启动没有转化为应用接入成功。生成 ID 的 6 项还缺配对生成器状态：原版顺序执行全部 API，工具逐查询新部署，返回 ID 不同不能直接归因于插桩。继续保留生成事实和真值缺口，不猜空来源。

第一份派生评分误把容器 nobody 用户文件的读取权限失败归为 evidence_invalid。仅增加读取权限后，全部首次运行文件 SHA256 逐项相同，02／03 在新目录重算；原评分和原始文件保持。03 另将生成状态未配对与已证明的业务变化区分，未重跑业务或修改工具。

查询族级适用性为：RuoYi 五项 conditional、一项目标接口不支持；TeaStore 六项 TF 运行时必要条件不满足。实际执行10份TF配置和12份MT配置；部署前拒绝没有伪造捕获。规划有条件接纳不等于端到端可回答，不能只报告接纳率。

RuoYi 六份 MT 运行另核对实际 ObjectMapper 类定义与原业务 JAR 一致；TeaStore 仍缺完整框架接入，不能把控制程序启动等同于原生传播能力校准。逐实例表另保存 [CSV](target-external-first-instances-20261103.csv)。

需要新增通信绑定、运行时／库适配、动态返回接口或完整复制／生成事实时，只记录迁移需求。本轮不开发 Gson、动态 Principal、新 sink，也不扩大 TeaStore 框架适配。没有回答的一方不能计为性能获胜。

工件：`artifacts/target-closure-revision-20261103/external-first-01/`；独立评分：`/home/wujian/tracefusion2/artifacts/target-closure-revision-20261103/external-first-audit-03`。原版环境失败、Java 11 探针的首次类路径失败及修正、全部首次工具日志均保留。正式输入、版本、配置、实际字段／调用坐标及逐实例缺口见 JSON／CSV。
