# Sock Shop / MirrorTaint 预检结果

2026-10-12。**没有本场景的字段准确率，也没有跨服务还原或性能结果。**

本页保留最初环境的历史预检证据。后续用户报告主机两种模式业务均 15/15 通过，
来源追踪受异步线程状态和日志覆盖阻塞，见 [主机状态](HOST-STATUS-20261012.md)。

## 主机真实运行与第一轮日志校准（2026-10-12）

此前 Docker 不可用的阻塞已解除：主机 Docker/Compose 可用，访问 socket 需要提升执行权限。
用户授权停止原有 `laomeng` 的 5 个容器后，使用两个独立项目完成原版服务运行。
原有容器和数据卷保留；plain 项目停止，MirrorTaint 项目继续运行。

| 检查 | 实际结果 |
| --- | --- |
| plain 真实 API 负载 | 15/15 场景业务通过，14 个成功订单 HTTP 201，1 个支付拒绝 HTTP 406 |
| 固定原版 MirrorTaint 负载 | 同样 15/15 业务通过，JAR SHA-256 与 sources.json 一致 |
| 查询契约 | 98 个有目标查询（Java 42、外部来源 56），7 个无目标检查；仍缺实际上游 RPC oracle |
| Orders 汇总 sink.log | 14 条可解析 JSON 记录，按唯一 customerId 可对应全部 14 个成功场景 |
| Orders JSON 查询覆盖 | 14 个 total 记录为空来源；另 84 个查询字段未记录。缺失不等于空来源 |
| Orders 文本查询覆盖 | 12 个文件覆盖 84 个查询，均为 `no sources`；另 14 个查询因两个并发场景文件缺失而不可读 |
| 并发文件名碰撞 | 3 条不同 customerId 记录共用 `20261012.071502.216`、同一 owner/method/group 路径；最终文件只包含 1 条文本记录 |
| Shipping 正向标签检查 | 14 条 JSON 记录，28 个字段有 `FACADE_REQUEST` 标签；此路径不在首批评分范围 |
| agent/runtime 错误日志 | 三个 Java 服务的错误日志为空，不能替代传播正确性检查 |
| Java 8 独立线程校准 | 主线程 startup 后 available=true，新线程 startup 前 available=false，手动 startup 后为 true |

固定源码的 `AsyncGetService` 对 User/Carts 的读取使用 `@Async` 与
`RestTemplate.exchange(RequestEntity, ParameterizedTypeReference)`。实际保存的转换后
RestTemplate 字节码对该重载包含 `TaintCollector.collect` 和 `TaintTagger.tagDbQueryResult`，
所以不能把当前空标签解释为 getForObject/getForEntity 未被覆盖。

公开 JAR 的 `TaintHeap` 使用普通 `ThreadLocal`；collect/tagDbQueryResult 在
available=false 时直接返回。`HeapThreadProbe.java` 在本次 Orders 容器的 Java
1.8.0_111 环境独立复现了线程状态隔离，没有修改 agent 或业务应用。
**这支持异步线程状态作为原因候选，但尚未测量应用实际 worker 的状态，也未排除
对象转移、Mongo save 后对象变化等其他标签丢失点。不能据此宣布唯一根因。**

### 后续：实际异步 worker 状态已确认

为验证上述原因候选，使用全新项目 `tf2-rpc-diag-3afa094c17`，追加只读的
`RpcStateObserver` Java agent，仅在 RestTemplate.exchange 入口/返回处读取
`TaintHeap.available()`、线程名、HTTP 方法与 URI。原版 MirrorTaint JAR、业务源码
和传播规则不修改；观察器没有 startup/clear/标签写入行为。这轮诊断明确单列，
不能当作未经额外观测的原版基线或性能结果。

一个独立 single 订单业务通过 HTTP 201。User 的 customer/address/card 三次 GET、
Carts 的 items GET、Payment 和 Shipping 的两次 POST 共 6 个 RPC，在实际
`SimpleAsyncTaskExecutor-1` 到 `-6` 工作线程中，入口和返回处均为
`available=false`，12 条观察记录完整。由原版已保存的 collect/tagDbQueryResult
字节码可知，这个状态会使两者直接返回。**本诊断场景的异步 RPC 来源打标被跳过，
已从独立线程候选推进到实际应用路径证据。** 仍未排除其他传播限制，也未测完整 15
场景的每个工作线程，不能推广到论文方法整体或其他 JAR/部署。

第一次诊断项目因 Docker 默认地址池耗尽而没有启动容器；检查现有子网和主机路由后，
第二次用独立 `10.254.231.0/24` 子网成功，不删除已有网络。诊断项目已停止，保留
容器、卷、原始日志与 `artifacts/sockshop-rpc-diagnostic-20261012-second/result.json`。

观察器构建与诊断复查（`--release 8` 使用支持该参数的较新 JDK；MirrorTaint JAR 必须固定）：

```bash
mkdir -p artifacts/rpc-observer-classes
javac --release 8 -cp artifacts/external-tools/mirrortaint/mirrorTaint.jar \
  -d artifacts/rpc-observer-classes experiments/sockshop-mirrortaint/RpcStateObserver.java
jar cfm artifacts/rpc-state-observer.jar \
  experiments/sockshop-mirrortaint/rpc-observer-manifest.mf \
  -C artifacts/rpc-observer-classes .
python3 experiments/sockshop-mirrortaint/diagnostic_rpc.py \
  --agent artifacts/external-tools/mirrortaint/mirrorTaint.jar \
  --observer artifacts/rpc-state-observer.jar \
  --out artifacts/sockshop-rpc-diagnostic-new
```

诊断默认使用 18180/18181/18182；地址池耗尽时可用 `--subnet` 显式指定经检查空闲的子网。

校准结果仍为 `accuracy_eligible=false`：文本日志覆盖损失、JSON 字段省略、来源标签为空、
实例连接与来源边界未校准，均不能用内容相等或时间分组补齐；也不能报告 0% 字段准确率。
Shipping 标签的存在只构成原版 agent 局部正向对照。

可复查输出位于仓库 artifacts（通常被 Git 忽略）：

- `artifacts/sockshop-plain-20261012-first/result.json` 与同名 ZIP。
- `artifacts/sockshop-mt-20261012-first/result.json` 与同名 ZIP，保留完整原始日志。
- `artifacts/sockshop-mt-calibration-20261012/calibration.json`：逐查询覆盖状态、身份关联、日志摘要。
- 同目录保存 javap、固定源码以及 `heap-thread-probe-java8.txt`。

复查命令：

```bash
python3 experiments/sockshop-mirrortaint/calibration_audit.py \
  --run artifacts/sockshop-mt-20261012-first \
  --out artifacts/sockshop-mt-calibration-20261012/calibration.json
```

下一步原计划验证线程间对象标签转移；后续同步对照新增阻塞，见下一节。
若增加线程状态/连接适配，需要单列为适配版本，不能覆盖原版结果。

## 原版 JAR 同步标签对照（2026-10-12）

使用已锁定 Orders 镜像中的 Java 1.8.0_111，固定原版 agent，网络隔离运行受控 DTO
夹具；没有运行 Sock Shop 业务或安装适配器。独立 driver 在声明的源边界调用公开
`TaintTagger.tagDbQueryResult`，通过只读 heap 查询与原版 collector 保存标签。
被测操作单独位于 `taint.app` 包内，由原版 agent 插桩；driver 不在该包内，不写目标标签。
源标记中的 `DB_QUERY` 类型沿用公开 RestTemplate 转换器调用的 API，并非真实数据库读取。

最终运行在请求之前冻结 `query-contract.json`，来源按声明的 fixture record/field 身份比较，
不按同值或时间关联。四个 Item 内容相同、记录身份独立，分别覆盖公开字段与私有字段
getter/setter 形式。24.99 的业务值计算正确；本地 4.99F 不计入上游显式来源。

| 控制／查询 | 结果 |
| --- | --- |
| 输入源字段标签 | 12/12 通过（4 个 Item 的 name/quantity/unitPrice） |
| 原字符串对象的直接引用复制及引用替换 | 3/3 通过；保留的是同一引用上的原标签，不能单独证明新字符串计算传播有效 |
| primitive 字段复制／替换 | 6/6 未恢复目标标签（含 getter/setter 路径） |
| 两组数值多来源计算 | 2/2 未恢复 total 标签 |
| 新字符串拼接的两来源合并 | 1/1 未恢复 combined 标签 |
| 未写入字段空来源控制 | 2/2 通过 |
| 业务值／异常日志／插桩 | 值符合契约，错误日志为空，被测 operations 转换后 class 存在 |

因此 `synchronous_control_passed=false`；runner 返回 1 表示能力控制未通过，不是进程崩溃。
该结果不能换算为 Sock Shop 或论文的准确率，也不能假定日志、线程适配就足以修复全部问题。
转换后字节码显示 primitive GETFIELD/PUTFIELD 的 StackFrame hook 传入类名 `-instance`
字符串，而输入字段标签绑定实际对象实例；这是需继续核查的实例身份不匹配点。
尚未通过变更传播规则验证其为全部失败的唯一原因，字符串拼接也需要单独核对规则。

复现：

```bash
python3 experiments/sockshop-mirrortaint/probe_sync_labels.py \
  --agent artifacts/external-tools/mirrortaint/mirrorTaint.jar \
  --out artifacts/sockshop-sync-labels-new
```

最终逐字段记录：`artifacts/sockshop-sync-labels-20261012-final/result.json`；同名 ZIP 不含
JAR/class。目录包含原始日志、JVM 版本、冻结契约、fixture 源码摘要、转换后字节码审查。
早期探索与增加 accessor 的各轮证据分别保留，未覆盖。

另外更正 collector 重载说明：单 Object 重载按时间字符串分组；Object[] 重载生成随机
UUID。均不能自动当作跨服务 tracing 的请求实例身份。

## 早期受限环境预检（以下为此前结果）

| 检查 | 实际结果 | 可支持的结论 |
| --- | --- | --- |
| 5 个原版应用 Git 提交与源码摘要 | 通过；tracked 源码未修改 | 源码版本与标注依据固定，不证明发布镜像对应源码 |
| orders 0.4.7 原生构建 | Maven 返回 0 | 原版源码可在本轮 JDK/Maven 构建，测试未运行 |
| carts 0.4.8 原生构建 | Maven 返回 0 | 同上 |
| shipping 0.4.8 原生构建 | Maven 返回 0 | 同上 |
| 固定 MirrorTaint JAR 加载 | 返回 0，premain invoked | agent 可加载，不证明字段传播正确 |
| 原版 Orders 原生启动，无 agent | 返回 1，HTTP 尚未就绪 | 环境缺失 `/proc/self/fd` 导致原有 Prometheus 启动失败 |
| 原版 Orders 原生启动，有 agent | 同一启动失败；生成控制器/RestTemplate 插桩记录 | 不是已测得的 MirrorTaint 传播失败；业务正例未执行 |
| 真实 Docker/API 负载 | `blocked`：Docker 不可用 | 0 次实际工作负载、0 个实际准确性评分查询 |
| 原有 Sock Shop 响应校验测试 | 6/6 通过（unittest） | 原有响应判定回归检查，不是来源引擎准确率 |
| 新部署/输入静态检查 | 通过 | 预运行配置与源码预期一致，不是运行结果 |

构建使用 Amazon Corretto 8.504.04.1 / JVM 1.8.0_504-b04、Maven 3.9.9。
原系统 Java 无法加载 libjli，因此使用独立 JDK。最初 Maven 直连 DNS 失败；
随后用仅转发公共 Maven Central 的 loopback mirror，未改依赖版本或业务源码。
首次逐次建连下载超时，复用 HTTPS 连接后三个构建成功。下载路径、内容摘要和最终日志保存。
这是构建 transport 适配，不是被测业务的外部服务 mock。

原生启动两种模式均未经过任何有效 HTTP 请求。没有通过删改 Prometheus 配置或替换业务
绕过环境故障，因此没有把裁剪后的启动冒充原版完整启动。
agent 的 error 日志为空也不能证明传播完整；这一运行在初始化阶段就终止了。

## 公开 agent 的实证与未决问题

JAR SHA-256：`e4c679206993b45c6727a4ace1d4dcff6df0ded2b80b56b27b8c86741be63fe7`。
首次 native audit 创建 6 个日志文件，实际目录为 `AgentLogs/ShadowTaint/tf2-preflight`。
原版 Orders 初始化过程中还生成 `FacadeRequestSourceTransformer`、
`FacadeResponseSinkTransformer`、`RestSourceSinkTransformer` 等插桩输出。
这些类文件只说明转化器触发，未证明目标方法的传播规则经过执行校准。

对固定 JAR 的 javap 审查显示：`TaintCollector.collect` 单 Object 重载把格式化当前时间
`hhmmss MM-dd` 作为分组/trace 参数，随后将该值用于 sink 文件路径和记录构造；
Object[] 重载使用随机 UUID（后续完整审查更正了此前两个重载均为时间的表述）。
常量池检查未在 agent 自身 class 中发现 Sleuth/MDC/Tracer 引用。
这不等价于证明完整公开工具没有其他连接机制，也不等价于论文方法失效。
**当前跨服务请求实例连接尚未获得可复现校准证据**；不能按时间或值相等补上连接后仍称
“原版完整 MirrorTaint”。实际字段标签、来源边界、并发连接与异步线程传播是下一项资格验收。

## 已冻结但未执行的 API 工作负载

15 次订单请求预计包含 14 个有目标订单、1 个支付拒绝无目标订单；
98 个有目标字段查询（Java 服务边界 42、外部来源边界 56），另有 7 个无目标检查。
这 98 个预计目标中，空购物车 total 的显式来源集合为空；其余为单来源复制和多字段总额计算。
目标对象身份、Carts 项记录 ID、读取版本、实际 RPC 实例不得依赖内容相等确定。

源码查询契约在目标 API 请求前冻结，来源集合不从任一引擎生成。
当前还缺运行级 oracle、第二研究者人工审核、镜像与源码对应核验以及双方引擎输出。
PATCH/重复添加只覆盖当前读取版本，不声称覆盖数据库历史写入来源。
有真实 Go 服务参与业务不等于已证明跨语言前端可迁移性。

## 可复核材料

- [source-audit-20261012.json](source-audit-20261012.json)：原始源码提交与摘要。
- [preflight-validation-20261012.json](preflight-validation-20261012.json)：构建、agent 和两个原生启动结果。
- [native-evidence-20261012.zip](native-evidence-20261012.zip)：原始构建日志、下载摘要、javap、agent 日志及启动日志；不含 JAR/class。
- [evidence-20261012.json](evidence-20261012.json)：ZIP 摘要及文件数。

证据 ZIP 共 563,004 字节，SHA-256：
`5970feaa04cb6a330dce7ced54b814ce70d40ee41aff44651df49484087f4340`。
复核应从可信固定源码构建，不执行上传材料中的脚本或二进制。
完成主机实际运行与资格校准后，再进入来源准确性评分、选择性采集及同负载成本比较。

## 主机适配校准完成（2026-10-12 后续）

前面的原生启动阻塞、预计工作负载和原版 JAR 结论均为历史记录。
主机 plain 与原版 JAR 的业务运行均已独立完成 15/15；原版 Orders 标签为空、文本文件覆盖
与 JSON 字段缺失仍保留在 `artifacts/sockshop-mt-20261012-first`，不由适配结果改写。

本轮完成 companion agent，以原版公开标签／堆／栈 API 为基础，补上插桩、StringBuilder／顺序流
库规则、空 primitive 来源槽处理、异步任务状态和有界日志通道。原版 JAR 字节没有修改。
最终适配 JAR SHA-256 为 `fba378a5a4fa61f63c290d102ed4da4fcf857eeed35c11c271527fe90e44d2d0`。
配置名称必须包含全部适配类别，不能标成原版工具或“仅线程／日志修复”。

| 材料（仓库 artifacts/ 下） | 实测 |
| --- | --- |
| sockshop-sync-final-adapter-20261012/result.json | 来源 12/12、目标 13/13、负控制 3/3，最终 JAR／日志启用 |
| sockshop-async-final-adapter-20261012/result.json | 来源 18/18、目标 20/20、生命周期 11/11，日志启用 |
| sockshop-mt-adapted-20261012-final/result.json | 15/15 业务；14 个 HTTP 201、1 个预期支付拒绝 |
| sockshop-mt-adapted-20261012-final/adapted-calibration.json | 98 个字段契约全部一致；7 个无目标检查通过 |

Orders 共 192 个唯一事件（89 个请求、89 个响应、14 个订单目标）；全部 capture_complete、
available 为 true，无 adapter error 或非空运行时 error 日志。8 个并行订单各有独立 trace。
多商品总额包含两项的 quantity/unitPrice 共 4 个来源，空购物车实际响应集合 size=0，
其 total 来源显式为空，未把采集失败当空集合。

`audit_adapted.py` 读取预先冻结的 query-contract，按实际响应项 ID 或唯一 HAL self URI 解析
来源记录身份，来源坐标为实际响应事件 UUID＋字段路径；目标按订单 ID、客户 ID、itemId、trace
核对。来源标签仅以精确 token 识别，不按时间、数值或字符串内容连接；未知、歧义、缺失仍留在分母。
User 的 HAL DTO 的 id 为 null，因此使用响应中的 self URI，与该次请求 URI 一致后才能解析记录 ID。
这项日志结构事实在审计中显式处理，没有从预期答案填入响应身份。

失败尝试完整保留：第一次真实适配遇到未初始化 receiver 的 VerifyError 及 Spring submit
数量校验失败；第二次原版 collector 沿类型元数据进入 Spring 对象图导致堆耗尽；第三次
业务通过，但多商品 stream.sum 仅保留最后一项标签。目录分别为
`sockshop-mt-adapted-20261012-first/second/third`。受控同步失败与修复过程也保留，不能择优覆盖。

受控异步测试涵盖输入上下文捕获、worker 产生的新来源返回、两个同值请求实际并发隔离、
任务正常／异常／取消后的 worker heap 与返回寄存器清理、父线程不受污染及错误上下文取 Future。
Spring 接入只覆盖固定版本 Future/void 的两处 submit，未宣称 Completable/Listenable 路径。
顺序流规则从实际 callback 返回寄存器折叠来源；并行流报告 unsupported，不能获得资格。

校准完成不等于 RQ1 完成。当前 accuracy_eligible、performance_eligible、
cross_service_join_validated 仍为 false。后续须完成调用方到实际被调服务的实例连接、独立
oracle／第二研究者审核、镜像源码对应核验，以及我们的真实 Java 服务传播接入，再进行正式比较。

## 后续独立 HTTP 与 Java 控制器实例校准

已在相同原版业务镜像、相同传播适配 JAR 上完成被调端独立观测。最终证据目录是
`artifacts/sockshop-rpc-handler-20261012-complete`。再次执行 15 个真实业务场景，全部通过。

89 次真实 HTTP 调用均由被调容器 namespace 的 pcap 观测：Carts 15、User 45、Payment 15、
Shipping 14；每次按 TCP stream＋request frame＋response back-reference 确定实例，
并按实际 B3 child/parent、method、URI 唯一连接到 Orders pre-call 和 consumed-response 事件。
全部 98 个来源查询与独立 HTTP 响应体中的记录 ID／字段路径一致，四个抓包 socket 均无 drop。

独立 Java HTTP 入口／派发／退出探针还核对了 29 次实际 MVC 执行。Servlet UUID 绑定收到的
请求头和 dispatch owner/method/span；控制器返回事件按实际 trace/span/thread/method 唯一对应。
29/29 均通过，探针没有创建污点标签、改写请求头、输入或输出。
Go User/Payment 仅以实际外部 HTTP 请求／响应作为来源边界，不声称有 Go 内部执行 span。

Carts 返回日志的 15 个污点堆均 inactive，而 Shipping 14 个为 active。
完整日志可以在 inactive 时记录真实字段值，不能因此认为内部来源传播通过。
本轮的来源标签仍是 Orders RPC 消费点的原版打标；没有把 Carts 的 null 标签改成真值。

`verify_rpc_audit.py` 在临时证据副本中注入五类故障，全部正确拒绝：错误 wire parent、
wire／consumer 响应字段分歧、丢失 wire 响应、重复 MVC 派发、capture socket drop。
源码语法检查、原有 Sock Shop 六项测试、host check、git diff --check 均通过。

历史失败材料保留：`sockshop-rpc-wire-20261012-first` 是仅 NET_RAW capability 下证据目录
权限导致观测器启动失败（未执行业务）；second 的业务和抓包完成，但日志回收参数冲突导致
runner 标记错误，之后已回收日志、删除临时容器，没有拿它作为通过结果。
wire-final 是完整通过的网络边界运行；handler-final 是入口／退出观察的中间版本，
handler-complete 才包含实际 MVC dispatch。没有复用失败目录覆盖结果。

**通过标志限定为 `scoped_orders_http_join_validated=true`。** 完整 Go 内部传播、数据库历史、
消息后续配送、同 trace 内不可区分的重复调用仍未验证；full_cross_service_join_validated、
accuracy_eligible、performance_eligible 均保持 false。还需独立人工审核、镜像源码对应
核验，以及我们的真实服务传播结果，才能正式对比。

## 2026-10-13 暂停后恢复：TraceFusion 独立校准完成

2026-10-12 暂停时，独立前端仅通过 15/15 业务和首版离线还原，尚未核对 98 个查询。
当时材料在 `sockshop-tracefusion-20261012-first`，不追记成首版已有完整资格。
恢复后重建独立 Java 8 agent，新增实际集合成员身份快照，校验每个 stream mapper 回调的完整覆盖；
新建项目 `tf2-mt-1c28784a55`，仅运行本轮需要的 11 个业务组件及 4 个临时独立网络观测器。
临时观测器运行后已停止删除，容器和业务数据卷保留。

本轮结果：15/15 业务通过，98/98 来源查询一致（Java 服务边界 42、外部来源边界 56），
7/7 支付拒绝无目标检查通过，89/89 真实 RPC 由独立被调端网络记录连接，所有 socket_drops=0。
8 个并行订单的 enter/exit 事件区间两两重叠（共 28 对），按实际身份隔离，没有按同值串连。
这是事件级执行区间重叠证据，不是 CPU 同时运行或稳态性能指标。

前端及模型均独立于 MirrorTaint：固定 ASM 9.7.1，--release 8，原版 JVM 1.8.0_111 镜像；
agent SHA-256 为 `6ab6db6ec6d63ac9f93aea6d26654945ecf9d6b85740dcdc8d2f6b2bc9635b7c`。
来源锚点来自实际 RPC 消费对象，字段通过实际 owner／field／version 定位；运行时仅记录，
不传播来源标签。离线模型从实际原始字节码导出 scalar/getter/stream/构造参数规则并校验摘要。
引擎不接收预期关系、MirrorTaint 输出或 wire 正文；独立评估才将来源坐标连接到实际 wire 记录。

原版 calculateTotal 的实际零回调补充测试包含两个商品、其中一项乘积为 0。
未插桩和插桩都返回 14.99。去掉该零回调全部事件并重新编号，数值仍可相同，但还原器按实际集合
成员快照拒绝遗漏。这验证来源完整性不是只靠输出数值相等判断；此探针本身没有 HTTP 来源评分。

9 项离线检查全部通过：去 trace/span 答案不变、最小输入目录及伪造 oracle/wire 不影响答案，
字段版本断裂、错误 callback parent、漏 operand read、重复 RPC 响应、同值跨请求来源替换、
wire drop 及漏登记场景均被识别。原有 Sock Shop 六项测试、host check、语法和 diff 检查通过。

材料：`artifacts/sockshop-tracefusion-20261013` 下的 service-model、inference、service-calibration、
service-regressions JSON，以及 `artifacts/sockshop-zero-callback-20261013/result.json`。
MirrorTaint＋适配器与独立 TraceFusion 在相同预登记工作负载上的校准符合率均为 100%，
两个配置的运行及夹具实例不同，不将它表述为原版 MirrorTaint 的准确率或性能排名。

当前还原器明确限于已审查的只读 DTO 别名、有限 float 运算、顺序流和金额构造绑定。
未审查的字段覆盖／反射写入、一般 Future／集合、任意 Java 方法不会被宣称已支持。
完整镜像源码对应及第二研究者审核尚未完成，accuracy_eligible、performance_eligible 仍为 false。
下一阶段是同负载成本测量设计和资格复核，不能仅用这一次短业务执行耗时宣布性能优势。
