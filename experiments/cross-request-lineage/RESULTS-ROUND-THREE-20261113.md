# 第三轮：限定 A→B 通信与历史来源闭环

在已声明的阻塞 HTTP/1.1、每 RPC 新连接、默认扁平 JSON DTO、顺序进程内缓存范围内，原六组 **32/32 检查点来源正确、32/32 历史版本正确**，来源均追到 A 的真实外部输入。五个正常控制的最终查询各两次，来源与版本分别 **10/10**；第六组完整证据两个最终查询另计正确。没有启动 CVE，也没有发现这些来源查询相对已校准 MirrorTaint 组合配置的优势。

起始 main HEAD 为 `dbb813ad81b789149b90b403a52b6700e2f0588d`，首次 git status 为空；initial-state 收据稍后记录的 worktree 包含刚创建的新增预期，不是用户已有修改。原 Cache、Server、workload、前两轮预期／报告／原始捕获保持。新增预期先封存并提交 a059c95；后述有写入证明的同 trace 校准另在 spec-02 封存、提交 6c2cfcb，未改先前预期。通信与历史核心提交 27b4a42，最终引用一致性保护为 5f70099。运行时仍为既有获准的 8u504，依赖与 native／构造许可未改。

| 原控制，每组两次 | 预期 A 外部来源与共享版本 | 最终来源 | 最终版本 | 当前实际／首次限制 |
|---|---|---:|---:|---|
| R1 写入、R2 命中 | R1/value；同 c1.text@1，Cache.cell@1 | 2/2 | 2/2 | 新通信证据与 B 历史写闭环 |
| 同对象同值覆盖 | R2/value；同 c1.text@2，旧 @1 保留 | 2/2 | 2/2 | 同值不复用旧来源 |
| 同值新对象替换 | R2/value；新 c2.text@1，Cache.cell@2 | 2/2 | 2/2 | 身份替换分别保存 |
| 公开常量覆盖 | 空集合；c1.text@2，覆盖前 @1 已知 R1/value | 2/2 | 2/2 | 前后均验收，不以碰巧空标签证明清除 |
| miss 当前 fallback | R2/fallback；无 Cell.text 读取，原缓存 @1 保持 | 2/2 | 2/2 | 原缓存来源与历史未改 |
| 第六组完整副本，另计 | R2/value；同 c1.text@2 | 2/2 | 2/2 | 完整副本与合成删证分开 |

端到端链来自真实事实：A 外部请求字段→同进程同对象／声明字段／版本的实际发送快照→实际 TCP 连接与具体 wire invocation→B 接收字段→重放验证的历史写版本→后续确切版本读→B 真实输出→A 实际接收→同对象字段的 A 响应。同 JVM 转发还要求引用一致；未记录写入却换成同值新引用会 unknown，跨 JVM 则不比较对象号。op/key 仍为控制选择，数据来源只计 value/fallback；不把全部历史输入混入当前 providers。字段链、原 seq/path、namespace、建立写的 Frame/site/descriptor、正常完成与支持事实保存在 graph 和 local_results.B.session_history 中。

新增 `http_exchange.version=1` 核验实际 I/O 完成、定向连接四元组、Socket／HttpExchange 本地 carrier、实际 traceparent、方法路径、方向、原始 bytes/hash、状态及适配器／服务类哈希。先按端点、具体消息、操作、方向连接，再按冻结默认 JSON schema 选择属性，最后做字节／值一致性检查；跨 JVM 不比较对象号。A 的普通 HTTP 包装器是新增的 RoundThreeServer，Cache 字节码不变；这不是原 HttpURLConnection 或任意框架的覆盖证明。

session history v1 保持 direct-B 规则及 outbound RPC 拒绝。v2 明确把 B 入站作为局部 HTTP 中间依赖，最终图只能以声明 external 的 A 请求作为 source；即使调用者把 B 设置成查询边界，也不能把 intermediate 提升为外部来源。B 本身不发 RPC，请求级 State、不可变确切版本索引与未知效果屏障沿用第二轮。没有新增任意 native／构造许可，也没有补造默认初始化。

同 trace 校准单列：最先冻结的两个无缓存 op=0 请求有相同 trace、不同实际 span／连接、同值 value/fallback，TF 的 **4/4 检查点仍 unknown**。原因是未观测到 Cache.cell@0 的初始化证明，控制选择不能被核验；没有把“默认应为 null”当作证据。该限制与通信错配分开保留，也不计 unknown→unknown 保护通过。另冻结有实际写入的同 trace 控制（先 replace，再 miss），TF **4/4 来源及版本正确**。因此 TF 总体 36 正确、4 unknown，来源和版本分别报告，未隐藏这四项。

| 已知正确答案上的派生义务 | 数量 | 结果 |
|---|---:|---|
| 删必要历史写（miss 删实际 Reply.text 写），保留序号／重编号各一份 | 28 | 拒绝 28：原序列缺口或必需实际写缺失 |
| 删必要 A send I/O，原序列／重编号 | 28 | 拒绝 28：序列损坏或缺实际 I/O 与 codec 配对 |
| 删必要 B receive I/O，原序列／重编号 | 28 | 拒绝 28，同上 |
| 删 A 实际发送字段快照，原序列／重编号 | 28 | 拒绝 28，同上 |
| 删必要历史入口绑定，原序列／重编号 | 28 | 拒绝 14、unknown 14 |
| 删必要 A 外部输入 I/O＋快照，原序列／重编号 | 28 | 拒绝 14、unknown 14；不能把 A 发送或 B 接收升成 source |
| value/fallback 同值而交换 B 字段映射 | 14 | 拒绝 14：属性与冻结 schema 不一致 |
| 用另一个实际消息的连接替换当前请求连接 | 14 | 拒绝 14：同一消息的 request/response carrier 关系不成立，包含同 trace 控制 |
| 混入另一进程 namespace | 14 | 拒绝 14 |
| 整个 B 换为另一真实捕获，实际对象号确有碰撞 | 14 | unknown 14：没有当前 A 的通信连接；donor 原事件／哈希保留 |
| 额外错误包装：同值 value 谎报为 fallback | 2，另计 | 独立来源预期检出 2，物理版本仍正确 |

合计 **224：182 拒绝、42 unknown、错误 known 0**。全部先有正确 known；常量的 source 删除针对清除前已知来源检查点，必要常量写删除针对最终空集合。原始捕获不动，修改副本有 synthetic 标记、原始哈希及修改收据。检查后原始正例重新评分仍正确。没有再用较早 control-write-address 或无初始化证明遮蔽这些义务。

MirrorTaint 分开核验。论文 [IV-E](https://zhangyuqun.github.io/publications/icse2023c.pdf)描述先得到各服务局部输入输出关系，再依据 trace 和接口数据标识离线连接；它不要求原始标签在线穿过网络。固定[公开提交](https://github.com/MirrorTaint/MirrorTaint/tree/54fcbfc5bb3a0d7cd30309098355d999553a861b)的 64 项完整 tree、JAR 内容和 javap 收据已保存，未找到独立公开后分析入口；没有声称运行了作者后分析器。

| 基线配置／能力 | 实测 | 解释 |
|---|---|---|
| 固定原版 JAR，只有 A 外部 source，在线原生 API | A 的 40 个在线 sink 标签为空；完整通信未贯通 | 原始导出单列 unconnected_online，不将其计作论文跨服务机制的 FN；常量空标签也不计校准成功 |
| 同一原版 JAR＋披露的局部接口 API 标识／输出查询＋独立实现的 IV-E 组合 | **40/40 外部来源正确** | 所有进程内依赖来自原生 IDs，B 缓存来源仍由 native 传播；组合只连真实消息和对应字段，不读取 TF 图、预期或业务传播模型 |
| 严格历史版本／离线缺证查询 | N/A | 公开原生查询 API 不提供，不计错误或 TF 优势 |
| 第二轮 direct-B 原有成绩 | 32/32 来源保持 | 未覆盖、未替换历史结果 |

论文式配置的 B 请求、A RPC 接收标签仅代表各自局部接口坐标，最终外部 source 仍只在 A；不传输源标签，不向 B 搬正确标签，也不为 native 实现缓存传播。新增无初始化证明校准上，组合配置正确而 TF unknown，必须保留这一对照结果。因此本轮没有证明一个基线缺少的来源能力，更没有创新或性能结论。

完整采集 complete-05 有 64 组进程对、128 个业务 JVM、160 次外部请求；各组内持续处理全部请求。TF／两种 MT 与 plain 响应、异常和最终缓存一致。TF 共 1,808 条事件、200 个跨 JVM 属性边、62 个正常根完成，80 次真实工作线程清理均无残留。188 项单测（旧 170＋新 18）全部通过。第一轮 12 份 direct-B、12 份 process 捕获在当前核心下答案／状态变化 0；第二轮原始捕获复算仍来源 32/32、版本 32/32，90 缺证控制和两个错标签再次通过。没有改变 ACTIVE、退役或 GC 实现，未声称新增 GC／异步历史支持。

首次失败均保留：development-01 的薄适配错误继承 final 类导致编译失败，改为委托；development-02 的 HTTP 收据误覆盖 RPC 端点，图实际通信证据正确，另存修正收据和采集；最初无缓存校准 unknown 保留。acceptance-04 在 MT 常量组的第二次请求连接超时，未见进入 A handler，整批不作为正式完整验收；原因未确定，不归因于 native 传播。complete-05 使用显式直连回环驱动并记录客户端实际端点后全部完成，这不证明原超时必由代理引起。final-audit-01 因离线源码收据早于最后错误消息调整而拒绝，另存 current-replay-07、current-score-07、current-negatives-07 和 final-audit-04；没有改旧收据。

可复算命令、Git 内精简原始证据见 [README-ROUND-THREE.md](README-ROUND-THREE.md)，完整逐项评分、证据及归档收据见 [results-round-three-20261113.json](results-round-three-20261113.json)。精简包保留原始文件字节并已解包自检，第二轮 32／90 和第三轮 40／224 均可不启动 JVM 复算。它们明确排除运行时、依赖和 Agent 二进制，不冒充完整归档。当前宿主不能创建 `/mnt/data`，工具没有通用附件上传接口，因而没有声称完整包已附到会话；精简包随 Git 提交，完整包仍在 artifacts，有逐文件 hash。

仍不覆盖原 process 条件写、原 HttpURLConnection 适配、无初始化证明的默认状态、并发／异步、持久化存储、网络复用／重试／代理／TLS、嵌套／自定义 JSON、GC 复活、性能或剪枝。没有启动 CVE。本轮推进了有通信证明的历史来源底座；是否有论文贡献仍需具体未被对照正确完成的任务与独立审查。


最终完整原始证据包：[raw-evidence.tar.gz](../../artifacts/cross-request-lineage-round-three-delivery-20261113-02/raw-evidence.tar.gz)，11,030 文件、32,082,912 字节，SHA-256 `3086bb79c6972f0046e878432e18bdd4f7a1c540519f3d513812577081b88319`；逐文件 manifest 与流式回读校验收据在同目录。delivery-01 保留，delivery-02 为最终包。归档源码快照中的最终摘要明确标记封包待完成，当前摘要补充本段最终归档元数据，避免归档自身哈希递归。
