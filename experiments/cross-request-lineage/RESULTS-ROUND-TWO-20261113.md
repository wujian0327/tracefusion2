# 第二轮结果：单 JVM 历史来源闭环与缺证退化成立

审查基线和实际起始 HEAD 均为 `e48832dc171357c614912d8795c17e186eabd0c1`，main，工作区干净。本轮只推进 direct-B：外部 HTTP 直接进入 B，使用原 Cache 业务和原 workload，多请求共享同一个 JVM／工作线程。没有修改第一轮预期、workload、报告或原始捕获，也没有修改业务源码。独立新增检查点在实现前冻结；miss 检查点“缓存仍为 @1，但不读取 Cell.text”的澄清另存 spec-02，早于核心实现，spec-01 保留。

最终五个正常控制、各两次独立重复的 **10 个最后查询，来源 10/10、版本 10/10 分别正确**。第六组完整证据副本的两个最后查询也分别正确，另计；全部逐请求检查点为 **32/32 来源正确、32/32 版本正确**。在这些正确 known 正例上，90 项缺证／身份检查得到 **34 unknown、56 明确拒绝、错误 known 0**，另有两个故意复用旧来源的同值包装错误被独立预期检出。原始正例在负例之后重新评分，仍全部正确。

| 控制，两次重复分别验收 | 最后数据来源 | 实际共享对象／读取版本 | 来源评分 | 版本评分 |
|---|---|---|---|---|
| R1 写入，R2 命中 | R1/value | 同 c1；读取 c1.text@1，Cache.cell@1 | 2/2 | 2/2 |
| 同对象同值覆盖 | R2/value | 同 c1；c1.text@2，Cache.cell@1；旧 @1 保留 | 2/2 | 2/2 |
| 同值新对象替换 | R2/value | 新 c2 != c1；c2.text@1，Cache.cell@2；旧 c1.text@1 保留 | 2/2 | 2/2 |
| 公开常量覆盖 | 空数据来源集合 | 同 c1.text@2；覆盖前 @1 已 known R1/value，覆盖后 known 空集合 | 2/2 | 2/2 |
| miss 使用当前 fallback | R2/fallback | 不读 Cell.text；Cache.cell/key 均 @1；缓存 text@1 的来源仍为 R1/value | 2/2 | 2/2 |
| 第六组完整证据副本，单列 | R2/value | 同 c1.text@2 | 2/2 | 2/2 |

op/key 按已冻结范围作为控制选择事实，保留 selectors，不混入 text 的显式数据来源。Cache.key 写入记录可以定位到 HTTP key 控制来源；Cache.cell 右值通过真实分配／构造和对象身份解释；Cell.text 通过实际输入读取／参数／常量指令解释。没有按字符串相同推断来源。

以前缺少什么，现在采到什么：第一轮 direct-B 只给 read 规划根，写操作在根外只递增版本，没有写值及可重放 RHS。新计划明确纳入真实 `replace/overwrite/publish/read`，用原应用调用规划器审核它们及现有构造协议。实际采到了 Cache.key、Cache.cell 引用、Cell.text 的写入和方法入口／参数／读写／构造开始与完成／正常或异常边界。本轮两次重复中，新增并还原 **14 次 Cache.key、14 次 Cache.cell、20 次 Cell.text 写入**；另有 32 次原有 Reply.text 写，共 80 个不可变版本记录。52 个实际顶层调用均正常完成。它们来自真实字节码执行，没有伪造 Frame、构造完成或业务标签。

State 与历史如何隔离：每个真实根调用仍新建 State，局部变量、操作数栈、异常、临时容器和分配 token 不跨根复用。一条 HTTP 请求可能先写、再读，两个方法的状态也分开。只有已重放核验的字段版本进入捕获级 `SessionHistory`，位置为 `(capture_session, process_instance, object, declared-field, version)`。记录中的观测被复制为不可变 JSON，来源和 selectors 为不可变集合，分配 token 已物化成真实对象 ID；历史查询返回新的 Value，后续写入不能回改旧版本。

每条版本记录保留真实写事件、Frame、site、descriptor、根完成状态、依赖／效果完整性和支持事件；读取记录指向确切写版本。来源仍是较早 HTTP source 事件的原 seq/path 和 namespace，可定位原请求与字段；多次入口观察绑定到同一个实际 HTTP 字段。没有把历史输入混入当前 providers，没有把缓存／方法返回重新打 source。缺 v2 就 unknown，不回退到同值 v1。未知调用沿当前 State 与已发布历史引用传播屏障；后续有证明的强写才能建立新的 known。ACTIVE、只读域、WeakIdentityMap、OwnerVersions 的退役机制没有改动，历史也不持有 JVM 业务对象。

新协议仅在计划显式 `session_history.version=1`、full、顺序根调用时启用。头、每条事件带 capture/process 身份，footer 带事件数；冻结计划哈希、原字段／方法／异常协议继续验证。方法返回仅在该协议下按其实际 Frame 的描述符核验；旧格式保持原规则。没有增加 native、构造或运行时许可。v1 显式拒绝 method-return source_calls 和 outbound RPC 计划；没有字段绑定的顶层标量输入保持 unknown。

| 从正确 known 正例制作的合成义务 | 数量 | 实际退化／检出 | 原因与边界 |
|---|---:|---|---|
| 删必要写事件，保留原 seq | 12 | 拒绝 12 | 事件序列缺口，证据无效 |
| 删必要入口绑定，保留原 seq | 12 | 拒绝 12 | 事件序列缺口，证据无效 |
| 删必要写事件，重新编号及重算总数 | 12 | 拒绝 12 | 必需构造写缺失，或 overwrite/publish 的实际 PUTFIELD 事件缺失 |
| 删必要入口绑定，重新编号及重算总数 | 12 | unknown 12 | 该 RHS 缺外部来源绑定；不会借当前入口重置来源 |
| 删必要外部 HTTP source 字段事实 | 12 | unknown 12 | 实际 HTTP 字段到输入对象的证据缺失，不按同值补出 |
| 将实际读取改为无写证明的版本 | 10 | unknown 10 | 索引没有确切版本；旧版本即使同值也不命中 |
| 引入另一真实捕获的同对象号／版本，capture 身份混用 | 10 | 拒绝 10 | 实际 donor 记录保留；capture namespace 不匹配 |
| 同上，单独混用另一真实进程身份 | 10 | 拒绝 10 | process namespace 不匹配 |
| 包装器在同值覆盖后故意复用 R1 来源 | 2，另计 | 独立评分均检出错误 | 字段版本仍正确，来源错误不能被版本正确抵消 |

miss 最后查询没有 Cell.text 数据读取，不伪造一个必要历史读取来做负例：其必要写是实际 Reply.text 写，必要 source 是当前 fallback。常量清除后的空集合不依赖旧数据 source，因此该组删除 source 的义务针对覆盖前已 known 的检查点，删除常量必要写则针对最后的空集合查询。所有原始捕获不改；每个派生文件有 synthetic 标记、原始哈希和修改收据。没有一个检查以“原本 unknown”作为通过依据，也未再被 `control-write-address` 或不相关运行时限制遮蔽。

基线配对：同样的外部字段粒度和业务下，MirrorTaint **32/32 逐请求来源正确**，12 个最后查询也全部正确；第一轮 direct-B 原有 12 个正确结果保留。公开 queryTaint 导出不提供本轮严格版本和离线删写证据查询，继续 **N/A**，不计错误或 TF 优势。本轮没有创新或性能结论。

是否影响行为、旧答案、清理和退役：36 个新业务 JVM 配置、96 次请求中，TF／MT 与各自 plain 的响应、异常及最终缓存一致；每组进程、线程和不同 trace ID 均核验。每个新 TF 请求结束时，在实际 HTTP 工作线程读取 monitor，帧、scope、calls、构造、ACTIVE 等都清理为零。原 147 项方法／生命周期单测和 23 项新增索引／绑定／覆盖／隔离／缺证测试，共 **170 项通过，失败／跳过 0**。既有方法观测在 full/static/selective 三模式通过；监控故障注入的 27 条业务结果和父域、异常身份／finally、无残留、失效 footer／sidecar 均保持。既有退役组件 10 项及 Map 控制通过，120000 累积注册后 live IDs、字段版本、数组槽均归零，ACTIVE 延迟退役与不支持复活的边界保留。组件中原有线程／Future／GC 控制不是新增的并发或异步历史能力。

旧捕获单列：第一轮 12 份 direct-B 捕获在新核心下的答案与根审计逐项相同，仍 unknown；原 process 的 12 份捕获保持同一个 control-write-address 拒绝。旧捕获未记录的写没有由算法补造。另有既有 current-core 审计的 18 份控制捕获、72 项保护检查保持，14 份旧业务的来源／版本／selectors／根审计变化均为 0。旧审计中 `Agent_unchanged` 指被引用的历史 Agent 工件没有被覆盖，新 Agent 的 SHA 与新观测另列。

所有阶段均新建目录。最初新 Agent 捕获在 `cross-request-lineage-round-two-development-20261113-01`：第一次预测被旧 binding-return 描述符假设拒绝，原文件保留；修正后另存 development-replay-02/03。独立预期只在评分器读取，预测进程的文件审计钩子禁止 expected/workload。正式验收保留 acceptance-02；完整新入口保留 complete-03。构建收据修正为记录实际新计划哈希，未改早期收据。最终离线证据以 `cross-request-lineage-round-two-current-replay-20261113-06`、current-score-05、current-negative-05、final-audit-02 为准。采集 Java 源码和离线 Python 源码分别记录：最终离线完善的完整性元数据、未知效果屏障和计划核验不需要重新启动业务 JVM，实际执行源码哈希在 replay receipt 中，采集 Agent／计划哈希在 build receipt 中，均保留。

局限仍然明确：v1 是 full、顺序、显式应用根、受支持基本类型／引用字段和既有调用契约；未覆盖任意未观测 native／反射写、类卸载或 GC 复活，也未设计历史淘汰。原 process 条件写限制没有消除。没有启动 A→B、CVE、并发／异步业务、Redis／数据库、性能优化或剪枝。复现、离线复算和核验命令见 [README-ROUND-TWO.md](README-ROUND-TWO.md)。本轮完成的是这一限定范围内的历史来源闭环与缺证退化，不宣布创新成立。

逐项机器可读结果与原始归档信息见 [results-round-two-20261113.json](results-round-two-20261113.json)。原始目录与所有中间失败均保留，代码与摘要提交到 main，不 push。

最终原始证据包为 [raw-evidence.tar.gz](../../artifacts/cross-request-lineage-round-two-delivery-20261113-03/raw-evidence.tar.gz)，共 6,397 个文件、22,527,428 字节，SHA-256 `024c779852ecac6b9a0b375de6fd509fa6900a937c03f25b94bf2212b5fc3135`。逐文件哈希与流式回读校验收据在同一 delivery-03 目录；源码快照记录归档时的实现，最终报告／摘要补充归档元数据。delivery-01 的打包校验中断记录和较早的 delivery-02 均保留，不作为最终证据包。
