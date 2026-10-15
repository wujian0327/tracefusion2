# Sock Shop / MirrorTaint：真实 API 接入预检

2026-10-12。用户确认先做 Sock Shop，再做 PiggyMetrics。**正式准确率资格尚未完成；2026-10-13 已完成五方法的选定字段校准与首轮开销测量，见文末。**
这一步冻结原版业务、查询契约和外部 agent，准备真实服务的 API 负载；不把预检当成来源还原。

**2026-10-14 当前优先级：**MirrorTaint＋披露适配器与 TraceFusion 做主对比，
Phosphor 先做 Shipping 小范围资格检查；FlowDist 保留为补充，暂停扩展。
已有 166 查询的评分会合并同一请求中同一业务记录字段的多次读取／版本，
不能作为严格字段版本或完整跨服务路径的准确率。见文末“动态基线复核与 Phosphor 接入”。

**后续主机反馈：**plain 和原版 MirrorTaint 业务均 15/15 通过；异步线程污点状态未初始化，
且并发文本日志覆盖，来源追踪仍未通过。主机结果来自用户反馈，原始包尚未在当前分支独立复核。
见 [主机状态与适配校准边界](HOST-STATUS-20261012.md)。

## 原版对象与运行范围

使用 MirrorTaint 作者部署所选的 orders `0.4.7`、carts/shipping `0.4.8`、
user `0.4.4`、payment `0.4.3`，提交与 JAR SHA-256 见 [sources.json](sources.json)。
业务源码不修改、不添加自定义计算函数、不用 mock 代替 payment/shipping/MongoDB。

主机入口复用仓库已有 11 组件部署和真实注册/地址/卡片 API，并直接调用原始
Orders `POST /orders`。客户端构造测试数据属于工作负载，不是重新实现业务。
镜像在主机拉取后锁定到 registry digest，并保留 VCS labels；标签相同不能证明镜像对应源码。
在映射独立核实前，源码标注与镜像执行的对应资格仍未完成。

这是**原始订单同步响应路径的部署子集**，不是整个 Sock Shop 或完整异步配送：
不包含 catalogue/edge-router，不评估 frontend 转发与 queue-master Docker worker 完成。
queue-master 的历史 socket 缺失问题保留，收到任务不等于配送完成。
不把 Go user/payment 实际参与业务运行当成已实现 Go 前端来源传播。

## 预先冻结的查询

来源是**本次 Orders 实际消费的上游 HTTP 响应字段**，目标是其原始 HTTP 响应，
保留上游 RPC 实例、记录 ID、字段及读取版本。客户端额外 GET 仅检查夹具状态，
不能代替 Orders 的实际读取或成为算法来源。

| 查询组 | 来源 → Orders 目标 | 对照资格 |
| --- | --- | --- |
| Java 服务边界 | Carts GET 中各项 `quantity/unitPrice` → `total` 与 `items[*]` 对应字段 | 首批 MirrorTaint 同任务校准候选；数据库到 Carts 输出之前不在来源范围 |
| 外部来源边界 | User GET 中 `firstName/street/longNum/ccv` → 对应嵌套字段 | 上游为真实 Go 服务，但不分析其内部；能否公平配置 MirrorTaint 来源尚需核验 |
| 无目标 | payment 拒绝时没有 CustomerOrder 响应对象 | 单列无目标检查，不增加 TP |

`total` 显式依赖各项数量和单价；4.99F 是本地常量。空购物车的 `total` 是存在目标的
空来源集合。支付授权、客户 URI 和 itemId 的选择/地址影响不并入总额的显式内容来源。
来源相同的数值不能用于关联字段或请求。

[cases.json](cases.json) 冻结 7 个顺序场景，加 8 个独立客户的并行请求：
单项、多项同价、同值不同字段、PATCH 数量、重复 POST、空购物车和支付拒绝。
预计 15 个订单请求，14 个有目标、1 个无目标；成功执行时预计 98 个有目标查询
（Java 服务边界 42、外部来源边界 56），另有 7 个无目标检查。
**字段查询数仍是预期计数；用户报告业务 15/15 通过，不自动等于字段查询已评分。**

PATCH 只替换数量、保留旧单价；重复 POST 对已有项使用旧数量 + 1，不采用新数量和新单价。
在当前读取边界上，这两个场景验证读取当前版本及真实业务行为，**还不能证明从历史写入
恢复旧来源清除**。POST/PATCH → Mongo 写入/读取 → 输出的版本来源属于下一层扩展。

Shipping 返回收到的 Shipment；`shipment.id` 实际由 Orders 的 UUID 构造器生成，
不应标为 Shipping 生成的追踪号。第一批不评分该往返和 UUID 本地来源。

`host.py` 在目标请求之前保存源码推导的逻辑查询契约。当前还缺实际 RPC 实例 oracle、
第二研究者人工审核、来源还原输出以及双方来源/目标配置校准。
夹具核验、同值记录 ID 检查和业务公式检查不能代替这些证据。

## MirrorTaint 资格

使用公开原版 `mirrorTaint.jar`，不重写/提取其传播核心。
启动采用作者 `taint.env=remote`、`taint.app=works.weave.socks`；另设 `user.home`
保存日志，传播规则未修改。JVM 内存沿用现有仓库部署的 256 MB，区别于作者 128 MB，
这里只做兼容性预检，不比较性能。

本地已确认 JAR 的 premain 能加载，日志路径为 `AgentLogs/ShadowTaint`，与 README 的
`AgentLogs/MirrorTaint` 不同。运行时挂载整个新建 home，避免仅挂载错误目录漏掉日志。

公开 JAR 的 `TaintCollector.collect` 单 Object 重载使用
`SimpleDateFormat("hhmmss MM-dd")` 生成记录分组键；Object[] 重载使用随机 UUID。
这两者都不是这里可见的 Sleuth Trace ID 获取。此前对两个重载均使用时间的描述已更正。
对 agent 自身 class 的常量池检查未找到 Sleuth/MDC/Tracer 引用。
这只是该公开构件的检查，**不能推出论文方法无法跨服务分析**；
当前也没有验证公开构件完整实现了论文中的跨服务实例连接。
时间字符串不能用于我们的字段连接。必须通过实际日志和并发校准后，才把原版工具填进
端到端准确性表。若需要我们的连接适配，名称必须改为“原版传播＋适配连接层”。

## 运行

Python 标准库；真实业务运行需要 Linux amd64 Docker Engine/Compose v2。
先从固定提交取原版 JAR，SHA-256 必须与 sources.json 一致。

```bash
python3 experiments/sockshop-mirrortaint/host.py check

# 可选：从固定版本克隆构建原版 Java 服务。目录命名见 source_audit.py --help。
python3 experiments/sockshop-mirrortaint/build_native.py \
  --sources-dir artifacts/external-tools --jdk /path/to/jdk8 \
  --maven /path/to/apache-maven/bin/mvn --out artifacts/sockshop-build-new

python3 experiments/sockshop-mirrortaint/native_audit.py \
  --agent /path/to/mirrorTaint.jar --jdk /path/to/jdk8 \
  --out artifacts/sockshop-agent-audit-new

python3 experiments/sockshop-mirrortaint/host.py run --mode plain \
  --out artifacts/sockshop-plain-new
python3 experiments/sockshop-mirrortaint/host.py run --mode mirrortaint \
  --agent /path/to/mirrorTaint.jar --out artifacts/sockshop-mt-new
```

每次默认新建随机 Compose 项目；指定项目时拒绝复用已有容器。
三个公开端口仅绑定 loopback；已有端口被占用时，通过 `TF2_FRONT_PORT`、`TF2_CART_PORT`、
`TF2_ORDERS_PORT` 设置空闲端口。容器和卷保留，不自动删除数据。
主机输出原始 HTTP 记录、请求前契约、镜像锁、agent 原始日志及错误日志清单；ZIP 不含 JAR/class 可执行构件。
停止仅使用该次输出的项目名和锁定配置：

```bash
docker compose -p <result.json中的project> -f <输出目录>/compose.lock.json down
```

即使 `business-preflight-passed`，`accuracy_eligible` 仍为 false；这里不安装 OTel/我们的来源
采集器，不声称已完成选择性观测或性能实验。8 个并行客户端也不自动等于已证实服务执行重叠。

下一步先完成原版 agent 的实际字段标签/RPC 实例连接校准，再扩展我们 Java 前端对真实 DTO、
引用、集合/lambda、异步任务及序列化的支持。当前 Commons Codec 的整数/数组前端不能直接
宣称支持这些服务。已有 Online Boutique 双进程预检保留为另一个受限组件证据。

本轮构建与阻塞证据见 [PREFLIGHT-RESULTS.md](PREFLIGHT-RESULTS.md)。
`source_audit.py` 检查固定提交与源码摘要；`native_orders.py` 是原版应用的启动/无效请求预检，
不需要 mock，但缺数据库时不能执行正例订单。

2026-10-12 主机后续运行已完成：plain 与原版 MirrorTaint 均 15/15 业务场景通过。
第一轮日志校准发现 Orders 的来源标签为空、并发文本文件名碰撞，以及汇总 JSON 的字段
省略；当前仍不具备来源准确率评分资格。实际结果与独立 Java 8 线程校准见上述预检结果文件。
`calibration_audit.py` 按唯一客户记录身份复查目标日志覆盖，不推断缺失来源或 RPC 连接。

后续同步标签夹具也未通过完整资格：12 个输入字段标签控制通过，12 个目标检查中
3 个字符串引用复制通过、9 个失败（primitive 复制、数值多源计算、字符串拼接）。
私有字段 getter/setter 路径也有相同 primitive 标签丢失现象。`probe_sync_labels.py`
提供冻结契约、原版 agent、Java 8 隔离运行与逐字段证据；它不是真实 Sock Shop 准确率。

## 2026-10-12 自行实现的适配校准

已完成独立 companion agent，配置名称为 **MirrorTaint 原版 JAR＋插桩／库规则／来源／线程／日志适配器**。
原版 JAR 的 SHA-256 保持不变，原版失败证据也保留。适配器调用原版公开运行时 API，
没有提取或重写核心引擎，也不读取查询契约、预期答案或按数值相等生成目标标签。
这里修复了传播插桩和库规则，因此不能简称“原版传播保持不变”。

| 校准 | 结果 |
| --- | --- |
| 同步夹具 | 12 个来源、13 个目标及 3 个负控制通过 |
| 最终适配器异步夹具（启用日志） | 18 个来源、20 个目标及 11 个生命周期检查通过 |
| 真实 Sock Shop | 15/15 业务通过；14 个成功订单、1 个支付拒绝 |
| 冻结字段契约 | 98/98 查询校准一致；7 个无目标检查通过 |
| Orders 日志 | 192 个唯一事件，89 对请求／响应，14 个目标；没有截断或运行时错误 |
| 多商品总额／空购物车 | 分别包含全部 4 个字段来源／显式空来源 |
| 并发 | 8 个独立 trace；夹具验证同值不同来源隔离、线程复用、异常和取消清理 |

`MirrorTaintIntegrationAdapter.java` 启用原版 StringBuilder 规则、修正插入的字段 receiver，
跳过构造函数尚未初始化的 receiver，并在原版来源打标前删除构造插桩留下的空 primitive 槽。
`MirrorTaintStreamAdapter.java` 汇总实际 mapper 返回标签，为顺序 `DoubleStream.sum` 增加规则；
不重新执行业务、不由 expected sources 补标签。`MirrorTaintThreadAdapter.java` 捕获任务提交者状态，
在工作线程绑定并清理，通过 `Future.get` 只合并实际返回对象可达的标签。
`MirrorTaintLogAdapter.java` 替换 collector，记录有界对象图、原始字段标签、MDC trace/span、
唯一事件 ID 和直接 RPC 配对；类型元数据标记为 opaque，循环与截断显式记录。

```bash
python3 experiments/sockshop-mirrortaint/build_integration_adapter.py \
  --agent artifacts/external-tools/mirrortaint/mirrorTaint.jar \
  --out artifacts/sockshop-adapter-new
python3 experiments/sockshop-mirrortaint/probe_sync_labels.py \
  --agent artifacts/external-tools/mirrortaint/mirrorTaint.jar \
  --adapter artifacts/sockshop-adapter-new/integration-adapter.jar \
  --fixture async --logging --out artifacts/sockshop-async-new
TF2_FRONT_PORT=18280 TF2_CART_PORT=18281 TF2_ORDERS_PORT=18282 \
python3 experiments/sockshop-mirrortaint/host.py run --mode mirrortaint \
  --agent artifacts/external-tools/mirrortaint/mirrorTaint.jar \
  --integration-adapter artifacts/sockshop-adapter-new/integration-adapter.jar \
  --subnet <未使用的CIDR> --out artifacts/sockshop-adapted-new
python3 experiments/sockshop-mirrortaint/audit_adapted.py \
  --run artifacts/sockshop-adapted-new --out artifacts/sockshop-adapted-new/adapted-calibration.json
```

当前实际证据在 `artifacts/sockshop-mt-adapted-20261012-final/adapted-calibration.json`，
同步和异步分别在 `artifacts/sockshop-sync-final-adapter-20261012`、
`artifacts/sockshop-async-final-adapter-20261012`。审计按实际订单／客户／项记录身份、HAL self URI
及直接事件 ID 连接；原始标签只用精确 token 解码，禁止按内容或时间补连。
源码、原始日志和最终同步／异步控制合并为
`artifacts/sockshop-mt-adapted-20261012-final-audited.zip`，不包含 JAR/class。

**这仍不是正式准确率或性能结果。** 已观测的是 Orders 消费的 RPC 响应；完整被调服务实例连接、
独立 oracle 审核、镜像与源码对应核验及我们的引擎仍待完成。选定 HTTP 范围的后续连接校准见下节。线程支持限于固定 Spring
Future/void 路径，库汇总规则限于顺序流；并行流明确报错，不能据此宣称支持任意 Java 程序。

## 独立跨服务 HTTP／控制器连接校准

后续已完成真实被调端观测，复用固定业务部署，仅重建 Carts/Shipping 加入独立入口探针。
原版 JAR 和传播适配 JAR 的摘要保持不变。最终运行在
`artifacts/sockshop-rpc-handler-20261012-complete`；`wire-calibration.json` 是逐调用／逐字段结果。

| 检查 | 结果 |
| --- | --- |
| 业务 | 15/15 通过 |
| 被调端实际 HTTP 请求／响应 | 89/89 对应；Carts 15、User 45、Payment 15、Shipping 14 |
| 独立响应体与冻结字段契约 | 98/98 一致 |
| Java 入口、MVC 派发与控制器返回 | 29/29 对应；Carts 15、Shipping 14 |
| 四个网络观测器 | socket_drops 均为 0，已停止并删除 |
| 审计负控制 | 错误父标识、响应体分歧、丢失响应、重复派发和抓包丢失均被拒绝 |

`capture_http_peer.py` 在每个被调服务的网络 namespace 内被动记录指定 Orders／服务 IP
对之间的 TCP/80，不代理、不修改请求，不采集注册凭据或其他应用流量。临时容器只增加
NET_RAW capability，不挂 Docker socket。`tshark` 按 TCP stream、请求 frame 和响应 back-reference
解码真实 HTTP 消息；原始 pcap 与解码 JSON 都保留。

`HttpServerBoundaryObserver.java` 是独立 Java agent，只观察 FrameworkServlet 的入口／退出
和 ServletInvocableHandlerMethod 的实际派发。入口 UUID 记录实际 B3 请求头；MVC 派发记录
真实 controller owner/method 和当前 span。响应返回日志须按 trace、派发 span、线程和方法唯一
匹配。Sleuth 在 RPC pre-call 之后创建客户端 child span，因此 wire 的 parent span 必须匹配
pre-call 的 span；不能只按 trace、时间或响应值相等连接。

**已通过的是选定 Orders 同步 HTTP 范围，未扩展为全链路。**
Go User/Payment 按外部 HTTP 边界观测，未提供 Go 内部 handler span。
Carts 的 15 个 getItems 返回事件 `TaintHeap.available=false`、字段标签为 null；这不影响
实际执行身份及返回记录核对，但意味着 Carts 内部数据库来源传播仍没有通过。
数据库历史写入、RabbitMQ 后续配送、同 trace 内不可区分的重复调用都不在已通过结论内。
`scoped_orders_http_join_validated=true`，`full_cross_service_join_validated=false`，
正式准确率、性能和第二研究者审核资格仍为 false。

```bash
python3 experiments/sockshop-mirrortaint/build_http_observer.py \
  --agent artifacts/external-tools/mirrortaint/mirrorTaint.jar \
  --deployment <已有适配部署目录> --out artifacts/http-observer-new
# 必须沿用该部署原有的三个端口；此处是本轮部署端口。
TF2_FRONT_PORT=18280 TF2_CART_PORT=18281 TF2_ORDERS_PORT=18282 \
docker compose -p <已有project> -f <已有适配部署目录>/compose.lock.json \
  -f artifacts/http-observer-new/compose.observer.json up -d --no-deps carts shipping
python3 experiments/sockshop-mirrortaint/run_rpc_capture.py \
  --deployment <已有适配部署目录> --server-logs artifacts/http-observer-new/server-logs \
  --out artifacts/rpc-observed-new
python3 experiments/sockshop-mirrortaint/audit_rpc_wire.py \
  --run artifacts/rpc-observed-new --out artifacts/rpc-observed-new/wire-calibration.json
python3 experiments/sockshop-mirrortaint/verify_rpc_audit.py \
  --run artifacts/rpc-observed-new --out artifacts/rpc-observed-new/audit-regressions.json
```

HTTP 抓包运行使用已缓存固定 Python 镜像，校验读取已存在服务；不会自动创建整套业务部署。
自定义端口时另传 `--front`、`--cart`、`--orders`。回归审计只改临时副本，原始证据保持不动。
汇总材料为 `artifacts/sockshop-rpc-handler-20261012-complete-evidence.zip`，不含 JAR/class。

## 2026-10-13 TraceFusion 独立真实服务接入

暂停后的工作已恢复并完成本轮字段校准。配置是 **TraceFusion Java 8 DTO／顺序流观测前端＋离线还原器**，
只在 Orders 加载自己的 agent，**没有加载 MirrorTaint 或读取它的标签**。业务镜像保持原版；
支持范围是这次审查过的只读 DTO 别名字段、浮点运算、顺序 mapToDouble/sum 和构造参数到 total 的绑定，
不将 Commons Codec 的受限前端直接宣称为通用 Java 服务支持。

| 相同冻结工作负载的校准 | MirrorTaint＋披露的适配器 | TraceFusion 独立前端／还原器 |
| --- | --- | --- |
| 业务场景 | 15/15 | 15/15 |
| 字段来源查询 | 98/98 一致 | 98/98 一致 |
| 无目标检查 | 7/7 | 7/7 |
| 实际 HTTP 调用实例 | 89/89 对应 | 89/89 对应 |

两个配置使用相同的 case 定义、查询语义和来源边界，但各自新建运行及独立夹具身份。
以上是**校准符合率均为 100%**，不构成通用准确率排名或开销优势。
原版 MirrorTaint 直接运行的来源接入失败仍单列，不由适配后或我们方案的成功反向覆盖。

`tracefusion/ServiceAgent.java` 使用固定 ASM 9.7.1，在真实类加载时采方法边界、对象身份、
字段读写版本、RPC 消费边界和顺序流回调，运行时不创建或传播来源标签。
`ServiceRecorder.java` 用 identity 映射保留跨线程的实际对象身份，按方法调用帧隔离上下文；
本轮采集 3,001 个事件、89 对 RPC 及 14 个成功订单。
`service_model.py` 从捕获的原始 class 经 javap 独立解码 getter、mapper、金额计算、局部变量到
构造参数及 total 字段的赋值，校验 class 摘要；未知调用／操作／覆盖路径不补猜。
`infer_service_sources.py` 在离线图中按对象＋字段＋版本还原只读字段关系，并逐步重放 Java float
及回调汇总关系。它仅读取观测和程序模型；wire 响应与冻结答案只进入独立评估器。

恢复后补上了 calculateTotal 的实际集合成员身份快照：每个 mapper 回调必须与成员逐个对应。
`probe_zero_callbacks.py` 在同一 Java 8 镜像执行原版私有金额方法，包含正常金额项及零金额项；
native／observed 都返回 14.99，两个回调都记录。删除完整的零返回回调并重新编号日志后，
即使总额不变，还原器仍拒绝“回调覆盖不完整”。此补充探针没有 HTTP 来源、没有订单字段准确率。

独立检查还确认：去掉 trace/span 后来源答案不变，只有观测/class 的目录也能还原，
添加伪造契约／无效 wire 文件不会影响答案；字段版本断裂、回调上下文错位、缺读、重复 RPC、
同值跨请求来源替换、抓包丢失和漏登记场景都会被拒绝。原始证据未被故障测试修改。

本轮结果在 `artifacts/sockshop-tracefusion-20261013/service-calibration.json`；
离线图在 `inference.json`，完整性测试在 `service-regressions.json`，
零回调实际执行材料在 `artifacts/sockshop-zero-callback-20261013/result.json`。
汇总包为 `artifacts/sockshop-tracefusion-20261013-evidence.zip`，不含 JAR/class。

```bash
python3 experiments/sockshop-mirrortaint/build_service_frontend.py \
  --out artifacts/tracefusion-service-build-new
TF2_FRONT_PORT=18380 TF2_CART_PORT=18381 TF2_ORDERS_PORT=18382 \
python3 experiments/sockshop-mirrortaint/host.py run --mode tracefusion \
  --tracefusion-agent artifacts/tracefusion-service-build-new/tracefusion-service-agent.jar \
  --wire-capture --subnet <未使用的CIDR> --out artifacts/tracefusion-service-new
python3 experiments/sockshop-mirrortaint/service_model.py \
  --capture artifacts/tracefusion-service-new/tracefusion-events \
  --out artifacts/tracefusion-service-new/service-model.json
python3 experiments/sockshop-mirrortaint/infer_service_sources.py \
  --capture artifacts/tracefusion-service-new/tracefusion-events \
  --model artifacts/tracefusion-service-new/service-model.json \
  --out artifacts/tracefusion-service-new/inference.json
python3 experiments/sockshop-mirrortaint/audit_service_sources.py \
  --run artifacts/tracefusion-service-new --out artifacts/tracefusion-service-new/service-calibration.json
python3 experiments/sockshop-mirrortaint/verify_service_sources.py \
  --run artifacts/tracefusion-service-new --out artifacts/tracefusion-service-new/service-regressions.json
```

host 的 `result.json` 是业务／采集阶段，仍记录 offline reconstruction pending；
完成后以 `inference.json` 的 `provenance_engine_run=true` 和校准文件核对阶段结果。
正式 `accuracy_eligible`、`performance_eligible` 仍为 false：第二研究者审核、完整源码镜像
对应核验及同负载成本测量尚未完成；数据库历史、Go 内部、消息后续与任意 Java 路径仍不在范围内。

## 主要来源

- [作者原版部署](https://github.com/MirrorTaint/MirrorTaint/blob/54fcbfc5bb3a0d7cd30309098355d999553a861b/Benchmarks/microservices-demo-mt.yml)
- [OrdersController](https://github.com/microservices-demo/orders/blob/e97ec6530811c92babbcb4227cf2d77896b5c26d/src/main/java/works/weave/socks/orders/controllers/OrdersController.java)
- [ItemResource.merge](https://github.com/microservices-demo/carts/blob/d0a55c9f483269034ab9f2473c1a738b2d7d422b/src/main/java/works/weave/socks/cart/item/ItemResource.java)
- [ItemsController.addToCart](https://github.com/microservices-demo/carts/blob/d0a55c9f483269034ab9f2473c1a738b2d7d422b/src/main/java/works/weave/socks/cart/controllers/ItemsController.java)
- [MirrorTaint 论文](https://lingming.cs.illinois.edu/publications/icse2023d.pdf)

## 2026-10-13 五方法同负载首轮对比

已补齐论文 Table II 的 `CartsController.get/delete/mergeCarts` 和
`ShippingController.postShipping`，加上原有 `OrdersController.newOrder`。
三种配置使用相同的 11 个原版业务镜像 digest、Java 8、JVM 堆参数及共同测量器。
各配置独立新建数据库和夹具，151/151 业务调用通过，没有前端／适配器错误。
最终共同测量器最后加载，包住追踪器的入口、退出和来源／目标日志开销；一次配置只运行一套部署。

**字段校准：两套方案均 166/166，180 个关系 TP、0 FP、0 FN，8 个无目标检查通过。**
分方法为 newOrder 98、get 18、delete 18、mergeCarts 28、postShipping 4 个查询。
这不是论文的 69 条关系重现；这里冻结了我们自己的多场景字段查询。

Carts 的 HTTP Cart 响应只序列化 customerId；id/items 是实际 Java 返回对象的私有字段。
因此 get 的目标是 Java 返回 DTO，delete 的目标是 CartDAO.delete 的实际参数，
mergeCarts 的目标是最后一次 CartDAO.save 的实际参数；空来源购物车没有 save，单列无目标。
三者来源均为目标调用实际消费的 CartDAO.findByCustomerId 返回字段。
请求前后额外读取 MongoDB 文档及 DBRef item 文档，作为独立夹具身份／业务状态证据，
不能成为算法的来源输入。Shipping 的来源是入口 Shipment 的 id/name，目标是返回 DTO。
不评估 RabbitMQ 后续处理、数据库写入历史或 customerId 的控制依赖。

新增 `boundary/BoundaryAgent.java`／`BoundaryRecorder.java` 为独立 ASM 9.7.1 前端，
采集真实来源、目标、对象／字段／版本、DTO 字段写入以及调用帧。
TraceFusion 在运行时不创建标签，`infer_boundary_sources.py` 仅读观测离线解析只读别名；
同值不生成关系，写入版本变化、未观测的计算／复制保持 unknown。
MirrorTaint 的相同来源边界由原版公开 TaintHeap/model API 打标；只配置来源，不补目标标签。
Shipping 原生 facade 标签未被 recordTaint 替换时，评估器从实际来源快照建立精确 token 索引，
不按标签内的数值、时间或文本相似度连接。配置名称必须包含已披露适配器和字段来源适配层。

下表为 **5 次预热后、每个方法 20 次串行调用的平均值**，属于一次部署的 pilot。
时间是服务控制器包含追踪的墙钟时间；客户端 HTTP 时间、median/p95、每个原始样本也保留。
内存分配是 JVM 所有存活线程 allocation counter 的增量 / 1024，含异步工作线程和背景活动；
不等同于保留堆或论文未进一步明确的 Memory Cost。

| 方法 | 原始时间 ms | MT＋适配 ms | TraceFusion ms | 原始分配 kB/次 | MT＋适配分配 kB/次 | TraceFusion 分配 kB/次 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| newOrder | 16.318 | 87.481 | 19.237 | 120.9 | 12503.7 | 1015.4 |
| get | 1.563 | 3.514 | 2.107 | 59.6 | 1016.0 | 331.5 |
| delete | 2.130 | 3.904 | 2.632 | 76.7 | 855.6 | 352.5 |
| mergeCarts | 5.924 | 13.180 | 7.494 | 314.6 | 4263.3 | 1315.3 |
| postShipping | 0.573 | 2.640 | 1.057 | 27.1 | 459.3 | 181.7 |

另记录每次方法返回后的 JVM `/proc/self/status` VmRSS（kB），表示整个服务的常驻内存，
不是单次请求的占用；它受 JVM 预热、GC、采集器保留对象以及运行顺序影响。
本轮 RSS 没有一致排序，不能把分配量降低等同于常驻内存降低。
TraceFusion 表中的运行时成本**不含离线还原**：离线批次（含原始字节码解码、完整日志还原、
结果写出与评估归一化）时间及 Python 进程峰值 RSS 在 comparison.json 的 offline 中单列，
不能直接摊成单查询延迟，也不能据此声称总成本更低。

`compare_five_methods.py` 统一评估两边的实际输出，缺失／unknown 查询保留并计入 FN；
字段精确匹配率和关系 precision/recall 分开记录。案例登记缺失直接拒绝，
同值外国请求标签替换会产生 FP 和 FN。新增两服务各 7 个故障／独立性回归通过，
原有 Sock Shop 6 个测试通过。实际运行 class 摘要与原版镜像内 JAR 对应，
固定源码提交到镜像构建的完整资格仍未完成。

结果目录：`artifacts/sockshop-five-plain-20261013-final`、
`artifacts/sockshop-five-mirrortaint-20261013`、`artifacts/sockshop-five-tracefusion-20261013`。
汇总为 `artifacts/sockshop-five-comparison-20261013/comparison.json`；所有实验容器测量后停止，卷保留。
早期 plain 首轮因误以为私有字段会序列化而失败的证据保留在 first 目录；v2 是业务预检，
最终成本比较仅使用最后加载共同测量器的 plain-final，避免混用不同观测边界。

```bash
python3 experiments/sockshop-mirrortaint/build_boundary_frontend.py --out artifacts/five-boundary-new
TF2_FRONT_PORT=18480 TF2_CART_PORT=18481 TF2_ORDERS_PORT=18482 TF2_SHIPPING_PORT=18483 \
python3 experiments/sockshop-mirrortaint/five_methods.py --mode tracefusion \
  --tracefusion-agent artifacts/tracefusion-sockshop-frontend-20261013/tracefusion-service-agent.jar \
  --boundary-agent artifacts/five-boundary-new/boundary-agent.jar \
  --subnet <未使用的CIDR> --warmup 5 --repetitions 20 --out artifacts/five-tracefusion-new
python3 experiments/sockshop-mirrortaint/compare_five_methods.py \
  --plain artifacts/sockshop-five-plain-20261013-final \
  --mirrortaint artifacts/sockshop-five-mirrortaint-20261013 \
  --tracefusion artifacts/sockshop-five-tracefusion-20261013 \
  --out artifacts/five-comparison-new.json
```

**当前依然是选定字段校准和首轮成本结果。** accuracy_eligible/performance_eligible 保持 false；
独立审核、数据库 wire 实例 oracle、源码镜像构建资格和多次随机顺序部署尚未完成。
不能据此宣称通用准确率 100%、重现论文的数值或具有统计保证的性能排名。

## FlowDist 候选基线兼容性预检（2026-10-13）

本节保留首轮预检状态。后续已定位启动等待的 DNS 原因，并修复通信时钟关联，见下节；
首轮 socket 模式未完成业务，不能据此断言原版通信协议发生死锁。

使用作者仓库 `https://bitbucket.org/wsucailab/flowdist.git`，固定提交
`9a683606aa42289e045cdbfa9391b55e79a3ac05`。作者源码、例子和工具 JAR 未修改；
`flowdist_preflight.py` 将绝对路径调整为容器挂载，使用固定 Orders 镜像中的 Java 8，
限制堆为 1–3 GiB、容器为 4 GiB，默认阶段超时 240 秒。作者脚本原来配置 100 GiB 堆，
因此本地超时只能说明此次资源配置下未完成，不能推断工具无法完成分析。
现代 javac 无法直接读取作者 Soot JAR 的非法 ZIP 条目 `/.`，编译时仅提取其中 SLF4J 类，
不重写 JAR；保留原始编译失败日志和后续通过的证据。

| 检查 | 实际结果 | 对比较资格的影响 |
| --- | --- | --- |
| 作者 Thrift 例子默认配置 | 来源／出口各 22 个方法；方法范围 1150 个；插桩后四种计算正确且生成两份进程轨迹 | 方法级流程可运行 |
| 默认配置来源 read → 客户端 main | 首次输出 19 个方法，脚本重跑输出 10 个；来源在两进程都存在，展示的路径位于客户端 | 随例子随机执行而变化；不能据此证明跨进程传播 |
| 手工指定服务端 add → 客户端 main | 返回 `There is no flow path!` | 跨进程兼容性检查未通过；不计作准确率 |
| 原版可选 `-socket` | 字节码确有 socket 包装器；20 秒业务等待内无计算结果，运行检查退出码 3 | 尚未查明协议／监视器问题；不能用于开销测量 |
| 作者语句级分支映射配置 | 240 秒超时，无映射输出；容器已清理 | 语句级静态图／精化未完成 |
| 原始 Shipping JAR | 9 个原始应用 class、完整嵌套依赖；默认来源 0、出口方法 1（打印日志）；方法范围 2 | 来源／出口不匹配现有 Shipment.id/name 查询，尚未进行插桩运行 |

源码 `OTBranchInst.run` 在映射输出后调用 `System.exit(0)`，分支探针插桩调用被注释；
本轮没有验证实际动态分支覆盖。不能把退出码 0、文件存在或方法路径直接当作完整
FlowDist 语句级分析成功。可选 socket 模式与默认模式的证据分目录保存，不混合结果。

证据索引为 `flowdist-evidence-20261013.json`，包含日志 SHA-256、原始 JAR 摘要及检查状态。
目录为 `artifacts/flowdist-thrift-20261013`（含历史失败）、
`artifacts/flowdist-thrift-20261013-repro`（脚本完整重跑的默认方法级流程）、
`artifacts/flowdist-thrift-socket-20261013`（可选 socket）及
`artifacts/flowdist-shipping-20261013`。未产生 FlowDist 的 Sock Shop 准确率、Runtime Cost
或 Memory Cost；不追加到已有五方法实测表，也不把未支持查询填成 0% 或 100%。

从空目录复现默认方法级检查（需要 Docker 和支持 `--release 8` 的 javac）：

```bash
git clone https://bitbucket.org/wsucailab/flowdist.git artifacts/external-tools/flowdist-new
git -C artifacts/external-tools/flowdist-new checkout 9a683606aa42289e045cdbfa9391b55e79a3ac05
docker pull weaveworksdemos/orders@sha256:b622e40e83433baf6374f15e076b53893f79958640fc6667dff597622eff03b9
python3 experiments/sockshop-mirrortaint/flowdist_preflight.py prepare \
  --repo artifacts/external-tools/flowdist-new --out artifacts/flowdist-thrift-new
for stage in source-sink scope instrument runtime method-analysis; do
  python3 experiments/sockshop-mirrortaint/flowdist_preflight.py "$stage" \
    --repo artifacts/external-tools/flowdist-new --out artifacts/flowdist-thrift-new || break
done
```

`cross-method-analysis` 单独检查服务端到客户端的方法查询；默认配置当前会失败。
`prepare --socket` 用另一个空目录显式启用原版 socket 开关，之后仍按上述阶段运行。
`branches` 使用作者分支分析选项，`refine` 要求已生成非空分支映射；完整语句查询生成和
最终分析尚未集成。`prepare-shipping --shipping-jar <原始shipping.jar>` 原样提取 Spring Boot
应用 class 和依赖，随后运行 `source-sink`、`scope`；来源空缺会明确记为检查失败。
脚本拒绝覆盖同名阶段日志，超时会清理自己创建的命名容器。

下一步先诊断 socket 模式业务阻塞，验证真实跨进程传播，再对齐 Shipping HTTP／DTO
来源和目标、处理 Spring 入口并完成语句级分析。只有边界和业务正确性通过后，才测量
相同工作负载下的准确率、在线开销及单列离线开销。当前资格标志仍为 false。

## FlowDist 跨进程适配进展（2026-10-13）

原始仓库及 FLOWDIST.jar 未修改。线程栈显示首轮启动等待发生在
`InetAddress.getLocalHost`：`--network none` 容器的主机名没有加入 `/etc/hosts`，
Java 等待不可达 DNS。启动脚本现在给每个容器分配独立主机名并添加本地解析；
这既消除等待，也避免后续多容器的进程 ID 因同名而碰撞。
修复环境后，原版 socket 模式四种计算通过，但 OTMonitor 的轨迹没有对端接收映射，
服务端到客户端查询仍返回无路径。

第二处是运行时引用不一致：OTBetterInstr 的方法事件写入 OTMonitor，
原版两个 socket 包装器却使用 dtMonitor 的时钟和接收映射。
`build_flowdist_socket_adapter.py` 生成独立 JAR，只替换两个 socket 类，将引用统一到
OTMonitor。原版方法插桩输出、监视器和分析器保留；适配 JAR 置于运行时 classpath 前面。
只修复引用就恢复了两端首次接收映射和跨进程候选方法路径。
因此配置名称应为 **FlowDist＋socket 时钟／流契约适配层**，不能称为未经修改的原版。

协议检查随后发现原版读取会跨过帧边界，把下一帧元数据交给业务；其剩余字节状态还位于
共享进程时钟，单字节写入声明长度 4 而实际写入 1，部分头部读取假设一次 read 就读满。
`--robust-framing` 用本仓库 `flowdist/dtSocket*.java` 修复这些问题。
保留作者线格式（总长度、逻辑时钟、发送进程 ID 长度／内容、业务字节），不更改图算法。
接收事件按原版首次接收规则写入 OTMonitor；支持 token 模式，帧上限 64 MiB，
发送者 ID 上限 4096 字节。其他协议／模式尚未验证。

最终适配层通过 `FlowDistSocketProtocolTest.java` 的 10 项检查，涵盖多帧合并、碎片头部／
载荷、多输入流交错、零值字节、单字节写入、零长度读取、EOF、截断头部／载荷、
跳过业务字节和非法帧。只修复时钟引用的早期版本在多帧检查失败，证据仍保留。
作者 Thrift 例子的四种计算再次通过。`FlowDistTraceProbe.java` 直接读取实际 Remote 轨迹，
确认两个不同进程、服务端来源与客户端目标的不同角色，以及相互首次接收映射。

在冻结的最终两端轨迹上，原版 OTAnalysisAll 给出：

| 查询检查 | 实际结果 | 含义 |
| --- | --- | --- |
| 服务端 add → 客户端 main | 213 个候选方法 | 跨进程关联已恢复；候选集合不等于精确路径 |
| 服务端 add → 客户端 recv_add | 21 个候选方法 | 实际接收返回值的跨进程正例 |
| 服务端 add → 未调用的 AsyncClient.add | 无路径 | 实际存在但未执行的目标反例 |
| 服务端 divi → 本次执行中更早的 add | 无路径 | 四次计算、无第二轮调用时的时间倒序反例 |

这些是兼容性／因果次序检查，**不能换算成通用准确率、precision/recall 或字段级正确率**。
`flowdist_query.py` 在新目录运行查询，冻结输入轨迹摘要，明确区分无路径与执行失败，
不覆盖之前的候选方法文件。

完整分支配置以及关闭 wrapTryCatch 的诊断配置均在 240 秒超时；线程栈位于
Soot Spark 的 PropWorklist。单独排除 JDK 库方法体后，分支映射在约 8.1 秒完成。
这一范围限制不是完整作者配置。精化接着遇到原版 P2 模型要求未加载 FileReader 类型；
`FlowDistStaticLauncher.java` 仅预加载原模型使用的 11 个类型签名，没有修改模型定义。
随后生成 2681 节点／8297 边的图，但报告 1735 个未计算 CDG 的方法，全部位于
213 个候选方法范围之外；严格检查仍将阶段标为 failed，保留原始诊断，不自动放行。

该图的语句查询只用于排查。使用 21 方法范围时没有输出路径；使用完整 213 方法范围时，
原版分析器输出 696 段并标为 Local，但来源／目标实测位于不同进程。这一分类及
共享类型的进程边界仍需核实，不能仅凭退出码 0／输出存在认定完整语句重建正确。
截至这一检查点还没有验证动态分支覆盖，不能把静态分支映射当成运行覆盖。

新检查点为 `flowdist-adaptation-20261013.json`，包含修复说明、来源摘要、实际进程信息、
查询检查及所有日志摘要。主要目录：
`artifacts/flowdist-socket-adapted-v3-20261013`、
`artifacts/flowdist-socket-adapter-v3-20261013`、
`artifacts/flowdist-socket-protocol-final-20261013`；静态诊断及失败保留在
`artifacts/flowdist-socket-adapted-20261013` 与 `artifacts/flowdist-statement-*-20261013`。

从空目录复现适配后的方法级流程：

```bash
python3 experiments/sockshop-mirrortaint/build_flowdist_socket_adapter.py \
  --repo artifacts/external-tools/flowdist --out artifacts/flowdist-adapter-new --robust-framing
python3 experiments/sockshop-mirrortaint/flowdist_preflight.py prepare --socket \
  --repo artifacts/external-tools/flowdist --out artifacts/flowdist-adapted-new
for stage in source-sink scope instrument; do
  python3 experiments/sockshop-mirrortaint/flowdist_preflight.py "$stage" \
    --repo artifacts/external-tools/flowdist --out artifacts/flowdist-adapted-new || break
done
python3 experiments/sockshop-mirrortaint/flowdist_preflight.py runtime \
  --repo artifacts/external-tools/flowdist --out artifacts/flowdist-adapted-new \
  --runtime-adapter artifacts/flowdist-adapter-new/flowdist-socket-adapter.jar
python3 experiments/sockshop-mirrortaint/flowdist_preflight.py cross-method-analysis \
  --repo artifacts/external-tools/flowdist --out artifacts/flowdist-adapted-new
python3 experiments/sockshop-mirrortaint/flowdist_preflight.py trace-inspection \
  --repo artifacts/external-tools/flowdist --out artifacts/flowdist-adapted-new
```

后续先验证语句精化的进程边界和实际分支覆盖，再为 Shipping／Orders 明确 HTTP／DTO
来源、目标与 Spring 反射入口。跨服务接入需要选择 Java 对端；不能把 socket 帧附加到
外部 HTTP 客户端、Go 服务、MongoDB 或 RabbitMQ 的原始协议中。
本轮没有新增 FlowDist 的 Sock Shop 准确率、Runtime Cost 或 Memory Cost，资格仍为 false。

### FlowDist 同次执行的真实覆盖与语句诊断（2026-10-13，后续进展）

公开 OTBranchInst 在输出映射后直接退出，原有插桩调用被注释。
恢复调用后又确认：其三参数 instrumentDirect 会排除传入方法，导致候选范围
内的计数全为零。独立 branch-adapter 改为调用作者原有的两参数接口，并让
映射与插桩使用完全相同的候选分支列表。原仓库、分析器 JAR 和分支算法保持原样。
两次 Soot 输出还把类字面量包装为 `LL...;;`，导致 Java 类加载失败；
normalize_flowdist_class_literals 仅为 CONSTANT_Class 克隆规范化名称，保留
原 UTF8 业务字符串、原常量池编号与指令字节，逐文件记录修复摘要。

最终在 `artifacts/flowdist-branch-v2-runtime-20261013` 同次采集方法轨迹和真实覆盖：

| 进程 | 命中分支／候选分支 | 命中语句 |
| --- | --- | --- |
| server | 279／546 | 1075 |
| client | 301／546 | 1055 |

四个原始 Thrift 业务操作、两端时钟关联均通过。覆盖报告的语句集合与命中
分支映射的并集完全一致。19882 条语句与此前诊断静态图逐编号核对通过；
局部变量名变化仅做结构比对，不重排编号、不修改图。
作者覆盖报告的分母 19715 是映射最大编号加一，不是完整 19882 条静态语句总数。

`flowdist_statement_diagnostic.py` 使用冻结的同次轨迹、核验后的真实覆盖，
替换新目录里的静态覆盖文件，运行原版 OT3AnalysisAll 的 stmtcov/postprune。
在 `artifacts/flowdist-measured-statement-v2-20261013`，add 参数到 recv_add 返回值：
合并两端覆盖后输出 521 段、类型仍为 Local；单独服务端缺少已执行的 sink，
单独客户端缺少已执行的 source。两端轨迹与覆盖摘要分别保留。
Local 是原分析器在合并图中找到路径后的分类，不能解释为两个端点实际位于
同一进程；这也尚不能证明所有输出段都是精确信息流。图的 JDK 排除和未计算
CDG 的限制仍存在，正式准确率与性能资格继续为 false。

保留失败目录：branch-runtime 初版类加载失败；branch-runtime-normalized
业务通过但覆盖为零；measured-statement 初版重命名轨迹使原读者无法发现，
不可使用其结果。最终使用 v2 目录，不覆盖这些失败证据。

复现真实覆盖、对齐审计与语句诊断（各输出目录须不存在）：

```bash
python3 experiments/sockshop-mirrortaint/build_flowdist_branch_adapter.py \
  --repo artifacts/external-tools/flowdist --out artifacts/flowdist-branch-adapter-new
python3 experiments/sockshop-mirrortaint/flowdist_branch_preflight.py \
  --repo artifacts/external-tools/flowdist --scope artifacts/flowdist-socket-adapted-20261013 \
  --branch-adapter artifacts/flowdist-branch-adapter-new/flowdist-branch-adapter.jar \
  --socket-adapter artifacts/flowdist-socket-adapter-v3-20261013/flowdist-socket-adapter.jar \
  --out artifacts/flowdist-branch-runtime-new
python3 experiments/sockshop-mirrortaint/flowdist_statement_diagnostic.py \
  --repo artifacts/external-tools/flowdist --runtime artifacts/flowdist-branch-runtime-new \
  --graph artifacts/flowdist-socket-adapted-20261013/work/OT3InstrumentedExcludedJdkPreloaded \
  --query '<CalculatorHandler: int add(int,int)> - i0 := @parameter0: int; <CalculatorService$Client: int recv_add()> - return $i0' \
  --out artifacts/flowdist-statement-new
python3 -m unittest discover -s experiments/sockshop-mirrortaint -p test_flowdist_compatibility.py -v
```

新增检查点 `flowdist-coverage-20261013.json` 冻结本阶段代码和证据摘要。
下一步是处理语句图的进程范围和完整性，再接入 Sock Shop Java Orders → Shipping。

### 扩大静态范围与原始 Sock Shop HTTP 接入（2026-10-13）

CDG 报错来自范围不一致：StaticTransferGraphOT 只为候选方法建立局部 CDG，
InterCDGraphEx.computeAllInterCDs 却遍历所有应用方法。保持原算法，改为使用
stmtids.out 中全部 1948 个方法作静态范围后，原版生成 24440 节点、121314 边，
不再报告缺失 CDG；19882 条语句和真实分支覆盖的编号仍逐项对齐。
该配置扩大了工作范围，关闭候选方法裁剪，因此会改变成本；JDK 方法体排除
仍保留，不能据此宣称全局图已经完整或直接使用为论文性能数据。

`flowdist_expanded_preflight.py` 固定这个范围变更、原版配置及审计过程。
首次证据在 `artifacts/flowdist-expanded-runtime-20261013`；真实覆盖为 server
490／5672 分支、2239 语句，client 470／5672 分支、2042 语句，合并 2888 语句。
对应 `artifacts/flowdist-expanded-statement-20261013` 的原版语句查询输出 570 段、
仍标为 Local；范围错误消除后，该分类仍不能解释为实际进程相同。
这几个长度是原分析器的候选语句输出，不保证逐段有序或字段依赖精确。

HTTP 接入已在 `artifacts/flowdist-sockshop-http-final-20261013` 验证：

- 原始 Orders AsyncGetService.postResource 经真实 HTTP 调用原始 Spring ShippingController.postShipping。
- 客户端请求拦截器传递版本化 `X-FlowDist-Clock`；服务端 Filter 在业务处理前接收，
  ResponseBodyAdvice 在业务返回后、响应序列化前发送。JSON 请求体和响应体不变。
- 使用原始 OTMonitor 的 Lamport 时钟和每个对端的首次接收规则，不使用 traceId/spanId
  或业务字段值关联；客户端只处理明确配置的 Shipping URI。
- 两个 JVM 分别使用各自原始依赖目录，避免 Orders Spring Boot 1.4.4 与 Shipping 1.4.0 混装。
- 普通无时钟头请求返回 201、不同 id/name 值保留，响应不添加时钟头；
  带时钟的同值 id/name 请求也保持业务返回，原版 Remote 轨迹验证双向对端关系。
- 原版 OTAnalysisAll 对 postResource → postShipping 输出 3 个候选方法；
  不能当作完整信息流路径，也不能换算字段级准确率。

这是通信兼容性检查：客户端直接构造原始 AsyncGetService，尚未执行完整
OrdersController.newOrder 或 Spring 异步代理。方法事件由明确的调用／HandlerMethod
分派边界钩子记录，尚未进行 Sock Shop 的 Soot 语句与分支插桩。
RabbitMQ 不可用，原始 Shipping 控制器执行自身的捕获并接受分支；没有验证 MQ 投递。
Java 时钟检查覆盖首次接收不覆盖、较小远端时钟不会倒退、非法报文不修改状态。
业务类和原作者分析器 JAR 均未修改，HTTP 适配是披露的协议传输变体。

保留 HTTP 初版 Spring 依赖混装失败目录与 v2 重复终止／返回事件缺少入口的诊断目录；
最终结果只引用 final 目录。错误检测也已补充没有冒号的 Java 异常行。
新增检查点为 `flowdist-http-20261013.json`，准确率与性能资格仍为 false。

```bash
python3 experiments/sockshop-mirrortaint/flowdist_expanded_preflight.py \
  --repo artifacts/external-tools/flowdist --scope artifacts/flowdist-socket-adapted-20261013 \
  --mapped-statements artifacts/flowdist-socket-adapted-20261013/work/OT3InstrumentedExcludedJdkPreloaded/stmtids.out \
  --branch-adapter artifacts/flowdist-branch-adapter-v2-20261013/flowdist-branch-adapter.jar \
  --socket-adapter artifacts/flowdist-socket-adapter-v3-20261013/flowdist-socket-adapter.jar \
  --out artifacts/flowdist-expanded-new
python3 experiments/sockshop-mirrortaint/flowdist_http_preflight.py \
  --repo artifacts/external-tools/flowdist --orders artifacts/sockshop-orders-original-20261012/app.jar \
  --shipping artifacts/sockshop-five-methods-original-20261013/shipping.jar \
  --out artifacts/flowdist-http-new
```

下一阶段将 HTTP 适配接入完整 Orders.newOrder，恢复真实异步调用与 RabbitMQ，
并解决 Spring 反射入口与跨服务 DTO 的静态分析范围，再冻结跨进程字段查询。

### 完整订单、真实异步 HTTP 与 RabbitMQ 投递（2026-10-13）

`build_flowdist_spring_apps.py` 在原始 Boot JAR 的副本中添加 Spring 配置和作者
运行时。逐项校验所有原始归档内容不变；包括业务类、原依赖及原启动入口。
新增内嵌 JAR 使用 Spring Boot 要求的非压缩格式。两端依赖仍各自隔离。
`FlowDistSpringHooks` 在原始 AsyncGetService 使用的 RestTemplate 安装 HTTP
时钟拦截器，并对 newOrder、Shipping URI 的 postResource、postShipping 添加
Spring 方法 advice。已有异步 advisor 保留，入口事件实际在异步工作线程执行。
这些是披露的运行边界钩子，只有方法入口写入原始 OTMonitor；返回／异常日志
为单独核验数据，不能当作完整作者方法序列、语句插桩或字段追踪。

最终证据目录 `artifacts/flowdist-full-order-final-v2-20261013`：

| 检查 | 实际结果 |
| --- | --- |
| 完整原始 newOrder | 返回 201；用户、地址、卡、商品和总价符合独立预置 fixture |
| Spring 异步调用 | newOrder 在 HTTP 线程，Shipping postResource 在 SimpleAsyncTaskExecutor 工作线程 |
| Shipping HTTP | 原始 Spring 服务执行 postShipping，保留双向 FlowDist 时钟关联 |
| RabbitMQ 入队 | 暂停本项目 consumer 时，shipping-task 从 0 到 1 条 ready 消息 |
| RabbitMQ 送达 | 恢复 queue-master 后 ready/unacknowledged 均为 0；consumer 日志包含该 Shipment 的 name |
| 原版方法查询 | newOrder → postShipping 输出 3 个候选方法，并包含两个查询端点 |

**投递和任务处理须区分**：queue-master 接收后尝试通过 Docker socket 启动
工作容器，当前原部署没有该 socket，日志记录 AFUNIXSocketException。
因此这里只验证入队和送达消费端，**未验证 Shipment 工作容器处理成功**。
消息队列与消费端尚未接入 FlowDist 时钟和语句分析；当前原版轨迹覆盖 Orders／Shipping 两个进程。

该轮使用全新项目、独立数据卷、已缓存镜像的 digest，不进行镜像拉取；
显式实验网段避免已用完的 Docker 默认地址池。RabbitMQ 线程数做资源限制。
先确认项目名没有既有容器，再进入清理范围；只停止／清理本项目。
服务退出时立即失败，不等待完整健康检查超时。
作者轨迹以毫秒时间戳命名，两个进程同步停止可能重名；现在依次停止，
复制轨迹时拒绝同名覆盖。测试覆盖项目名碰撞不清理和启动退出立即失败。

失败记录保持原样：首轮 Compose 变量转义告警误判、v2 默认地址池耗尽、
v3 新增内嵌 JAR 被压缩导致启动失败；final 首轮两个 Remote 文件同名导致
归档少一端，严格轨迹检查失败。v4 的旧 status 用词较宽，已附加
shipment-processing-audit.json 澄清只证明 consumer delivery，不证明工作任务完成。
正式结果使用 final-v2，完整日志及摘要保存为 `flowdist-full-order-20261013.json`。

```bash
python3 experiments/sockshop-mirrortaint/build_flowdist_spring_apps.py \
  --repo artifacts/external-tools/flowdist --orders artifacts/sockshop-orders-original-20261012/app.jar \
  --shipping artifacts/sockshop-five-methods-original-20261013/shipping.jar \
  --out artifacts/flowdist-spring-apps-new
python3 experiments/sockshop-mirrortaint/flowdist_full_order.py \
  --repo artifacts/external-tools/flowdist --apps artifacts/flowdist-spring-apps-new \
  --out artifacts/flowdist-full-order-new --subnet 10.254.243.0/24
python3 -m unittest discover -s experiments/sockshop-mirrortaint -p 'test_flowdist_*.py' -v
```

这一轮没有正式准确率或成本结果，资格继续为 false。下一步将实际执行的
Spring 入口、异步调用和 HTTP DTO 转换纳入静态语句／分支模型，再冻结跨进程
字段查询与多请求反例；MQ 工作容器处理另按所需实验范围处理。

### FlowDist：真实服务的分支覆盖与语句图（2026-10-13）

已对原始 Orders 的 37 个业务类、Shipping 的 9 个业务类生成作者分支探针，
重新部署完成一次真实 newOrder，返回 201，预置业务字段、异步线程、
Orders／Shipping 双向 HTTP 时钟、RabbitMQ 入队和消费端收到 Shipment 均通过。
证据目录为 `artifacts/flowdist-full-branches-final-20261013`。
queue-master 仍因缺少 Docker socket 无法启动任务容器，未证明 Shipment 工作任务完成。

| 服务 | 累计分支命中 | 分支推导语句覆盖 | 静态语句图节点／边 |
| --- | --- | --- | --- |
| Orders | 256 / 407 | 1142 / 1782 | 2131 / 5364 |
| Shipping | 54 / 79 | 310 / 406 | 447 / 1066 |

这些数字包含进程启动、健康检查及一次目标下单，不是单请求隔离覆盖或准确率。
语句覆盖使用作者的分支映射推导，不是每条语句的直接执行探针。
`statement-alignment-audit.json` 验证每个服务的实际覆盖索引与静态图逐项对齐，
只允许局部变量重命名；没有证明跨进程语句路径或图完整性。
方法轨迹仍为三个边界方法的 entry hook，不是完整作者方法事件序列。

本轮明确记录以下适配，作者仓库和原始工具 JAR 保持固定摘要：

- 用原 Soot 内置 ASM 后端输出 Java 8 lambda 字节码；旧 Jasmin 输出会出错并留下无效 class。
- 关闭 `wrapTryCatch`；作者包装涵盖构造函数的 super 初始化之前，导致 JVM VerifyError。
- 独立重算校验帧，修复旧后端把异常类型合并成 Object 的 VerifyError。
  将修复前后类文件去除 frames 并规范化后逐字节比较，确认指令、异常表和类数据不变。
- 独立扩展旧 DUA 不支持的 invokedynamic 引用模型：声明返回类型及已知子类型；
  在已知类型模型内做 may-alias，must-equal 仅接受同一表达式身份。
  原断言继续启用，16 项 Java 8 引用／别名检查通过。
  **没有建立 lambda 捕获变量、回调体依赖或运行时生成的隐藏类型的完整模型**。
- 修复作者 BranchReporter 重复报告的缓存：原版退出时分支已增加，
  语句列表却沿用启动时的值。独立覆盖类每次执行原映射算法重新计算；
  重复报告回归检查通过，审计对每段报告逐项检查分支／语句一致性。

静态图仅分析应用方法体，保留库签名但排除框架和 JDK 方法体。
Spring 反射、JSON／HTTP DTO 转换和 MQ 消费端信息流仍未建模；
该版本应称为 **FlowDist 适配版本**，不能声称完成原版复现或正式对比。
正式准确率、Runtime Cost、Memory Cost 资格仍为 false。
失败的 Jasmin 输出、lambda 断言、两轮 VerifyError、缓存不一致报告全部保留。

下面命令使用新目录重建；Orders 和 Shipping 分别执行静态分析和帧修复：

```bash
python3 experiments/sockshop-mirrortaint/build_flowdist_lambda_adapter.py \
  --repo artifacts/external-tools/flowdist --out artifacts/flowdist-lambda-new
python3 experiments/sockshop-mirrortaint/build_flowdist_reporter_adapter.py \
  --repo artifacts/external-tools/flowdist --out artifacts/flowdist-reporter-new
python3 experiments/sockshop-mirrortaint/flowdist_service_static.py \
  --repo artifacts/external-tools/flowdist --role orders \
  --jar artifacts/sockshop-orders-original-20261012/app.jar \
  --branch-adapter artifacts/flowdist-branch-adapter-v2-20261013/flowdist-branch-adapter.jar \
  --lambda-adapter artifacts/flowdist-lambda-new/flowdist-lambda-adapter.jar \
  --out artifacts/flowdist-orders-static-new
python3 experiments/sockshop-mirrortaint/reframe_flowdist_branches.py \
  --repo artifacts/external-tools/flowdist --static artifacts/flowdist-orders-static-new \
  --out artifacts/flowdist-orders-frames-new
# 同样处理 shipping，使用其原始 shipping.jar。
python3 experiments/sockshop-mirrortaint/overlay_flowdist_branches.py \
  --repo artifacts/external-tools/flowdist --apps artifacts/flowdist-spring-apps-v4-20261013 \
  --orders artifacts/flowdist-orders-frames-new --shipping artifacts/flowdist-shipping-frames-new \
  --reporter-adapter artifacts/flowdist-reporter-new/flowdist-reporter-adapter.jar \
  --out artifacts/flowdist-spring-branches-new
python3 experiments/sockshop-mirrortaint/flowdist_full_order.py \
  --repo artifacts/external-tools/flowdist --apps artifacts/flowdist-spring-branches-new \
  --out artifacts/flowdist-full-branches-new
python3 experiments/sockshop-mirrortaint/audit_flowdist_services.py \
  --runtime artifacts/flowdist-full-branches-new --orders artifacts/flowdist-orders-static-new \
  --shipping artifacts/flowdist-shipping-static-new \
  --out artifacts/flowdist-full-branches-new/statement-alignment-audit.json
```

摘要、源文件及证据摘要保存为 `flowdist-service-statements-20261013.json`。
下一步是建立跨 HTTP 字段转换与异步调用的语句级模型，再用独立正负例评估跨进程路径。

### FlowDist／TraceFusion 首轮共同工作负载对比（2026-10-13）

使用相同原始业务 JAR、缓存镜像 digest 和公共计时器，依次运行 plain、FlowDist 适配版、
TraceFusion。每组 7 个业务校验用例、5 次预热、20 次串行测量，共 32 次 newOrder；
所有业务检查通过，测量样本全部保留。原始记录在
`artifacts/flowdist-tracefusion-pilot-v2-20261013`，字段查询在
`artifacts/flowdist-total-query-pilot-20261013`。

| 部署配置 | newOrder 平均耗时（ms） | Orders JVM 平均 RSS（MiB） | 每调用进程分配增量（KiB） |
| --- | --- | --- | --- |
| 原始服务＋公共计时器 | 16.105 | 502.72 | 121.45 |
| FlowDist 适配版＋公共计时器 | 18.145 | 520.64 | 147.39 |
| TraceFusion＋公共计时器 | 21.961 | 496.66 | 1018.01 |

newOrder 控制器耗时包含等待实际异步 HTTP 返回，不包括离线重建、静态预处理或
进程退出时的轨迹序列化。HTTP 客户端耗时另存。RSS 是整个 Orders JVM 在调用结束后的
常驻内存，不是单次请求保留内存；分配增量包含后台线程，不能与 RSS 混合解释。
这是固定顺序、每配置一次部署的初测，尚无随机化多轮或置信区间。
不能由本轮较低的 TraceFusion RSS 宣称其内存开销更低；其运行时分配量明显更高。
FlowDist 的内存累计／退出写出与 TraceFusion 的逐条事件写出方式也不同。
双方采集范围和分析模型不同，只比较当前部署配置，不能归因于核心算法的稳定成本差异。

本轮 FlowDist 已用**作者原 OTBetterInstr**补全应用方法事件，而非三个 entry hook：
Orders 最终 Local 轨迹包含 136 个方法、5229 次进入和 12201 次返回相关事件；
Shipping 包含 42 个方法、515 次进入和 1129 次返回相关事件。
最后一份 Remote 快照验证两进程互相记录对端；完整审计见
`artifacts/flowdist-fullmethods-trace-audit-20261013`。
方法字节码插桩没有重写图分析算法；Spring advice 在此模式仅安装 HTTP 时钟和审计，
避免再次插入边界方法 enter，也避免再次 initialize 清空原监控器。

生命周期注意：最初 launcher 的 `instrumentTerminate()` 空覆盖并未阻止 EAInst
在 entry-method instrumentation 中直接插入的 main-return terminate。
实际每进程保留了启动和退出两份 Remote，Local 文件在退出时写入后续完整业务序列。
原始快照均保留，最终对端审计只选择退出快照。
源码已移除无效覆盖并纠正声明；不能依赖旧 manifest 的 `terminate_on_main_return=false`。
当前配置保留作者的 main-return／shutdown 行为，没有改变监控算法。

首次成本测试因公共 CostAgent 反射式计算校验帧时重入定义当前类，
没有实际计时 enter／exit，严格样本检查失败，保留在
`artifacts/flowdist-tracefusion-pilot-20261013`。公共观察器现在只读 class 资源计算层级，
拒绝未知类型／未支持的数组合并；6 项不定义类的层级检查通过。
修复后**三组全部重跑**，没有沿用旧 observer 的 plain 样本。

#### 首个共同字段依赖子集：七种字段到 total

预先冻结七个聚合字段类型查询：quantity、unitPrice 应影响 total；itemId、
firstName、street、longNum、ccv 不应影响 total。
独立语义依据为原始公式 `sum(quantity * unitPrice) + 4.99F`。
查询范围是整个串行工作负载的 **Orders JVM 内字段类型依赖**，
没有测试具体请求／对象实例区分，也不是跨进程字段路径准确率。

| 指标 | FlowDist 适配版 | TraceFusion |
| --- | --- | --- |
| 正确查询数／总数 | 5 / 7 | 7 / 7 |
| 正例命中 | 0 / 2 | 2 / 2 |
| 负例正确 | 5 / 5 | 5 / 5 |
| 未回答 | 0 | 0 |
| 正例召回率 | 0% | 100% |

FlowDist 使用真实 Local 序列、实际分支推导覆盖和原 OT3AnalysisAll 的图／剪枝／查询流程；
独立 probe 只读取作者 `isLocal`／`isNoDependency` 决策及端点节点数。
七组的源／汇语句都被覆盖、节点均非空，作者均返回 no-dependency，漏掉两条正例。
另加两条 getter 读取到返回值的正控制，原查询器均找到长度为 2 的 Local 流，
排除了查询器完全未工作的情况；这些控制不加入七条评测的分母。
控制证据在 `artifacts/flowdist-query-positive-controls-20261013`。
TraceFusion 从自己的原字节码、DTO／stream 观测和 RPC 来源记录独立推导，
推断阶段不读取 oracle 标签。该查询将其来源投影为字段类型，未用 oracle 生成答案。
未知／无端点答案仍计入总分母并使 exact 失败，不视为正确负例。

**这一差异包含分析模型支持的差异**：FlowDist 当前扩展仅支持 lambda 引用类型／别名，
没有完整回调体／捕获值及 stream reduction 模型；TraceFusion 有经原字节码校验的
标量／stream 摘要。尚不能把漏检归因于核心重建算法，也不能写成 FlowDist 总体准确率 71.4%。
跨 HTTP DTO／跨进程实例路径、并发同值反例和独立多轮成本对比仍待完成。

独立重算核对了原始计时事件、每组 20 个样本、32 个业务用例、七条查询的完整分母及单位。
13 项 Python 检查通过。结论为“在此限定范围内可分享，需保留限制”，
正式 `accuracy_eligible`／`performance_eligible` 仍为 false。
汇总和摘要在 `flowdist-tracefusion-pilot-20261013.json`。

```bash
python3 experiments/sockshop-mirrortaint/flowdist_runtime_comparison.py \
  --repo artifacts/external-tools/flowdist --apps artifacts/flowdist-spring-fullmethods-20261013 \
  --orders artifacts/sockshop-orders-original-20261012/app.jar \
  --shipping artifacts/sockshop-five-methods-original-20261013/shipping.jar \
  --boundary artifacts/sockshop-flowdist-cost-observer-20261013/boundary-agent.jar \
  --tracefusion artifacts/tracefusion-sockshop-frontend-20261013/tracefusion-service-agent.jar \
  --out artifacts/flowdist-tracefusion-pilot-new
python3 experiments/sockshop-mirrortaint/compare_flowdist_total_queries.py freeze \
  --repo artifacts/external-tools/flowdist --pilot artifacts/flowdist-tracefusion-pilot-new \
  --static artifacts/flowdist-orders-static-lambda-v3-20261013 --out artifacts/flowdist-total-queries-new
python3 experiments/sockshop-mirrortaint/compare_flowdist_total_queries.py evaluate \
  --repo artifacts/external-tools/flowdist --pilot artifacts/flowdist-tracefusion-pilot-new \
  --static artifacts/flowdist-orders-static-lambda-v3-20261013 --out artifacts/flowdist-total-queries-new
python3 experiments/sockshop-mirrortaint/compare_flowdist_total_queries.py positive-controls \
  --repo artifacts/external-tools/flowdist --scored-queries artifacts/flowdist-total-queries-new \
  --out artifacts/flowdist-positive-controls-new
```


### 跨 HTTP 消息实例校准（2026-10-13，尚非完整 FlowDist 准确率对比）

本轮分别运行 FlowDist 适配版和 TraceFusion，使用相同原始 Orders／Shipping JAR、
缓存镜像和业务用例。每组 23 次 newOrder：7 个串行用例、8 个独立客户的同值并发用例，
以及 8 个复用同一客户、同一 Trace ID 的并发用例。每组业务检查均通过，
一例付款拒绝不进入 Shipping，实际 Shipping 调用各为 22 次。两组并发请求的客户端区间
均实测有 8 个请求同时在途；这里不宣称服务器全部同时执行或提供并发性能排名。

TraceFusion 新增 `Shipment` 字段观察、出站 RequestEntity DTO 快照和显式
`X-TraceFusion-Message` UUID 请求头，需设置 `-Dtracefusion.http.instances=true`。
头中只有消息标识，没有污点标签、字段来源或 oracle 信息。接收端在原有 postShipping
观察中读取标识，离线按消息编号连接两个 JVM 的观察，再使用对象、字段、版本的别名关系
连接接收 DTO 与控制器返回字段。Trace ID 和业务值均不参与消息选择；值只校验已选边的一致性。
这是本方法新增的 HTTP 实例采集／模型，不是原有采集方案已经具备的能力。

有限的字符串属性模型核验两侧原始 Shipment 的 id/name getter、setter 及 Jackson 注解；
自定义序列化器不支持。本轮两侧采集到的 Shipment／Controller 原始字节码与未改业务 JAR
逐字节一致，接收对象确实作为原控制器结果返回，源与汇的字段版本及对象身份保持一致。
源从 Orders 即将发出的 Shipment 字段开始，尚未连接更上游的客户响应到 Shipment 构造，
也未连接 RabbitMQ 消费者。

| 本轮限定结果 | FlowDist 适配版 | TraceFusion |
| --- | --- | --- |
| newOrder / postShipping 业务检查 | 23 / 22 次通过 | 23 / 22 次通过 |
| 原始跨进程方法候选查询 | 有候选路径，62 个候选方法 | 此处不比较方法候选数 |
| 显式跨 HTTP 字段返回路径 | 尚未产出同粒度结果 | 44 条，22 个消息实例 |
| 字段／消息实例正负查询 | 尚未评分 | 132/132；TP=44、TN=88、FP=0、FN=0、unknown=0 |

132 条查询由预先冻结的三个模式实例化：同消息同字段为正例、同消息不同字段为负例、
另一消息的同字段为负例。具体消息编号在采集后绑定；此结果属于边界／回显校准，
不属于独立盲测，也不等于整个 Sock Shop 的准确率。对于共用 Trace ID 的 8 个请求，
跨请求负例使用另一同 Trace ID 的消息；它们的 Shipment.name 业务值也相同。
字段模型、采集范围和查询粒度仍不等价，**不能据此给出 FlowDist=0% 或宣称准确率胜出**。
FlowDist 的原始方法查询、构图、剪枝、时钟记录规则未因本轮改变，仍需保留此前 lambda
引用／别名模型扩展等适配说明。实际 Local 原始序列验证 Orders 记录了 23 次 newOrder，
Shipping 记录了 22 次 postShipping，完整业务方法事件并未仅用边界钩子代替。

一次诊断查询误把 NewOrderResource 的包名写成 entities，而实际为 resources；
其“无路径”结果无效，原始目录保留，并在审计中明确排除。重跑使用实际 Spring 采集的方法签名，
并新增查询前验证源／汇存在于作者 Remote 证据的检查；有效查询返回 62 个候选方法。
这是候选方法数量，不是 62 条实际字段或请求路径。

原始证据位于 `artifacts/flowdist-http-instance-pilot-20261013`，离线核验在 `audit.json`，
源文件和证据摘要在 `flowdist-http-instances-20261013.json`。16 个 FlowDist Python 检查、
6 个 HTTP 实例对抗检查通过；还复核了原有 DTO／stream 推断在这批并发数据中完成 22 个订单。
本轮没有预热后计时设计，不替换上一轮 Runtime／Memory 数字，完整准确率／性能排名资格仍为 false。

```bash
python3 experiments/sockshop-mirrortaint/build_service_frontend.py --out artifacts/tf-http-frontend-new
python3 experiments/sockshop-mirrortaint/build_boundary_frontend.py --out artifacts/tf-http-observer-new
python3 experiments/sockshop-mirrortaint/flowdist_http_instances.py \
  --repo artifacts/external-tools/flowdist --apps artifacts/flowdist-spring-fullmethods-20261013 \
  --orders artifacts/sockshop-orders-original-20261012/app.jar \
  --shipping artifacts/sockshop-five-methods-original-20261013/shipping.jar \
  --boundary artifacts/tf-http-observer-new/boundary-agent.jar \
  --tracefusion artifacts/tf-http-frontend-new/tracefusion-service-agent.jar \
  --out artifacts/flowdist-http-instances-new
python3 experiments/sockshop-mirrortaint/infer_http_instance_sources.py \
  --run artifacts/flowdist-http-instances-new/tracefusion \
  --out artifacts/flowdist-http-instances-new/tracefusion/http-inference.json
```

以上采集、推断可直接重跑。审计脚本还需该目录的原生方法查询与 Local 解码结果，
本次对应 `flowdist-native-method-query-validated` 和 `flowdist-method-audit`；
它们的准确命令及输入摘要均保留在 stage JSON。下一步是用原始 statement 查询管线生成
跨服务字段级结果，区分聚合结果与实例结果，保留 unsupported/unknown 后再统一评分。


### 三方同批次五方法运行（2026-10-13）

完成 plain、FlowDist 适配版、MirrorTaint 适配版和 TraceFusion 的独立新部署，
本轮目录为 `artifacts/sockshop-three-five-v3-20261013`。每个配置运行相同的 151 次业务调用：
26 个校准业务场景（含 8 个不同客户的同值并发 Orders 请求）、5 个方法各 5 次预热、
各 20 次串行正式测量。总计 604 次业务检查通过、400 个正式计时样本，三服务共用相同
最终加载的测量器。原业务 JAR、镜像 digest 与基本 JVM 参数在配置间匹配。
此处的“同批次”是同一协议、构件和测量活动，配置逐一部署，不代表同时运行。

五个方法为 Orders.newOrder、Carts.get/delete/mergeCarts、Shipping.postShipping。
FlowDist Carts 现已生成 162 个应用方法、1148 个语句映射、195 个分支的静态图，
包含 1371 个节点、3117 条边。使用原始 OTBetterInstr 记录完整应用方法序列，
加上此前已披露的分支探针恢复、lambda 引用／别名模型、框架体排除、校验帧和 reporter 修复。
Carts 没有新增跨 HTTP 时钟连接；已验证的 HTTP 时钟适配仍限于 Orders→Shipping。

第一次 FlowDist Carts 请求因 Soot 丢失方法参数名字而返回 HTTP 500：Spring 无法绑定
未显式命名的路径参数。`FlowDistParameterNames.java` 从未改业务 JAR 的参数元数据或
LocalVariableTable 恢复 MethodParameters，修复 20 个类的 88 个参数。
移除 MethodParameters 后，修复前后规范化 class 字节逐字节相同，证明指令、帧、注解和
其他 class 数据保持一致。5 项 Java 回归核验宽参数槽位、缺失调试数据、元数据修复及
反射可见参数名。该修复属于框架兼容，不改 FlowDist 图／传播／遍历规则。
失败原始目录及各次恢复诊断保留，首轮 plain 的结果没有混入最终批次。

以下是控制器含在线追踪的平均墙钟时间（ms），每格来自 20 个样本。

| 服务 | 方法 | plain | FlowDist＋适配 | MirrorTaint＋适配 | TraceFusion |
| --- | --- | ---: | ---: | ---: | ---: |
| Orders | newOrder | 15.600 | 17.429 | 94.246 | 20.734 |
| Carts | get | 1.510 | 1.684 | 3.540 | 2.266 |
| Carts | delete | 2.083 | 2.171 | 3.916 | 2.880 |
| Carts | mergeCarts | 5.527 | 5.473 | 12.137 | 8.282 |
| Shipping | postShipping | 0.534 | 0.480 | 2.584 | 1.280 |

只有一轮固定顺序部署，FlowDist 两格略低于 plain 是本轮观测，不能解释成加速或负开销优势。
计时不含静态预处理、离线分析、关闭 JVM 时的事件序列化；FlowDist 缓存事件后序列化与
其他前端逐事件输出的方式不同，必须保留此范围差异。内存分别记录整个服务的平均 VmRSS
（导出 MiB）和 JVM 进程分配量增量（KiB/次），不直接对应论文未明确采样方式的 Memory Cost。
完整时间、百分比、内存及原始样本索引在 `sockshop-three-five-audit-v2-20261013/five-method-costs.csv`
和 `validation.json`。

准确性结果保持三种分母：

| 查询范围 | TraceFusion | MirrorTaint＋适配 | FlowDist＋适配 |
| --- | --- | --- | --- |
| 五方法实际标量字段校准 | 166/166 精确查询；180 TP，0 FP，0 FN | 同左 | 尚未产出相同字段／实例粒度结果 |
| Orders 同一组 7 条聚合字段类型→total 查询 | 7/7；2 TP、0 FP、0 FN、5 TN | 7/7；2 TP、0 FP、0 FN、5 TN | 原报 5/7 已撤回：分析器解码失败，见下方 2026-10-14 更正 |
| Carts 三方法和 Shipping 原生引用控制 | 不据此评分 | 不据此评分 | 原报 4/4 已撤回：静态回退不能证明动态图正确 |

字段校准分方法为 newOrder 98 个查询／112 个正确关系、get 18／18、delete 18／18、
mergeCarts 28／28、postShipping 4／4；两侧各 8 个无目标字段／save 检查通过。
这不是 MirrorTaint Table II 的 69 条关系重现。七条聚合查询投影两侧实际 DTO 来源／标签，
只使用预测来源，不读取 expected 标签生成结果。旧 FlowDist 记录虽然保存了完整 Local
方法序列和语句覆盖，但原分析入口没有正确解码该序列；旧漏报不能归因于回调模型。
引用控制是 CartDAO 结果集合→return/delete/save 引用，
以及 Shipment 参数→返回引用，不能填进另一套标量字段分母。上述均不是完整跨服务路径评分。

独立验证逐一核对了全部 400 个样本与原始计时事件、604 个业务调用分母、各组镜像及基本
JVM 参数、标量关系集合和聚合查询计数。16 个 FlowDist Python 检查及 5 个参数名 Java
检查通过。三服务原生 Local 序列也已解码验证，实验项目容器、网络和卷均已清理。

离线重建／评估重新在每个配置的独立 Python 进程中运行，时间约为 MirrorTaint 输出解码／
归一化 66.6 ms、TraceFusion 字节码解码／重建／归一化 2145.6 ms；整评估进程峰值 RSS
分别为 49028、89312 KiB。它们是整批处理，不是每查询时间，也不是纯算法阶段内存。
最初在部署 runner 同一进程中求得的 ru_maxrss 会累计前序峰值，因此该内存结果明确排除，
旧 JSON 保留作诊断；本轮在线数字与准确性输出经核对完全未变。
FlowDist 的静态构建及四个控制／七个查询的独立 Java 容器命令、耗时和原始输出单独保留，
没有将容器启动包含的单查询耗时与上述 Python 批处理时间混成总成本排名。

检查摘要与源／证据 SHA-256 在 `three-method-five-20261013.json`。
所有 accuracy_eligible/performance_eligible 仍为 false：逐字段三方对齐、独立人工审核、
完整分布式路径真值和重复随机顺序的成本测量尚未完成。

```bash
python3 experiments/sockshop-mirrortaint/three_method_five.py \
  --repo artifacts/external-tools/flowdist --apps artifacts/flowdist-five-fullmethods-parameters-v4-20261013 \
  --orders artifacts/sockshop-orders-original-20261012/app.jar \
  --carts artifacts/sockshop-five-methods-original-20261013/carts.jar \
  --shipping artifacts/sockshop-five-methods-original-20261013/shipping.jar \
  --boundary artifacts/sockshop-http-instance-observer-20261013/boundary-agent.jar \
  --tracefusion artifacts/tracefusion-sockshop-frontend-20261013/tracefusion-service-agent.jar \
  --mirrortaint artifacts/sockshop-five-mirrortaint-20261013/mirrorTaint.jar \
  --integration-adapter artifacts/sockshop-five-mirrortaint-20261013/integration-adapter.jar \
  --out artifacts/sockshop-three-five-new
```

`flowdist_five_statement_controls.py` 提供 freeze/evaluate 两步重跑引用控制；
`compare_flowdist_total_queries.py` 提供同轮三方七条聚合查询；
`audit_three_method_five.py` 验证并导出 CSV。各阶段使用新输出目录保留原始证据。

### FlowDist 与 TraceFusion 的共同字段访问查询（2026-10-14）

本节是单 JVM 字段存储／计算的诊断校准，不作为跨服务主表。跨服务结果见后续“首条跨服务主路径”。

**更正旧结果：** FlowDist 原 `OT3AnalysisAll` 的 `dtDiver` 将运行时写出的 HashMap
强制转换成 LinkedHashMap，捕获异常后仍继续执行；动态图为空时又回退到静态图。
因此旧七条查询的 FlowDist“5/7，TP=0、FN=2”和旧四条引用控制“4/4”均无效，
也不能将旧漏报归因于流计算／回调模型。原始记录和旧 checkpoint 保留作诊断，
由本节更正；方法级 Remote 分析、业务成功检查、计时、MirrorTaint/TraceFusion
既有标量校准不依赖这一错误的语句解析入口。旧入口现在拒绝空事件和解码异常。

新实验 `artifacts/sockshop-field-comparison-20261014` 分别运行两种配置，每种配置的
五个 API 共 31 次业务检查均通过。新增观察只记录实际字段访问的方法签名和字段声明，
继续使用对象身份、字段版本和实际读写推断；不按值相等选来源、不读取真值生成预测。
本轮零预热、每方法一次测量只用于功能验收，不能作为 Runtime/Memory Cost 结果。

共同口径为：**一个 JVM 内，指定字段写／读指令位置之间是否存在显式值依赖，
对该工作负载聚合**。静态端点限制为只引用一个字段的语句，记录原始方法、字段和语句编号。
FlowDist refinement 使用原工具开关关闭控制依赖，避免与标量值依赖混算。
查询冻结在原生预测之前；选择端点时已看过运行观察，因此是校准集，非盲测基准。

20 条查询分为：Carts 的 quantity/unitPrice/itemId 三组 setter→getter 交叉查询（9 条）；
Shipping 的 id/name 两组 setter→getter 交叉查询（4 条）；Orders 的七种 getter 字段读取
到 CustomerOrder.total 构造写入（7 条，quantity 和 unitPrice 为正例）。
前三个 Carts API 都运行了，但九条 DTO 存储查询尚未逐 API／逐请求拆分。
这不是五方法完整路径，也不含跨 HTTP 字段来源准确率。

新配置明确称为 **FlowDist＋完整事件解码／编号适配**：

- 独立解码器读取原 Map，保留所有方法事件的原时间戳、正负方法编号及次序；进程时钟元数据
  与方法索引分开，避免同一整数在两个命名空间中碰撞。绕过原 dtDiver 按方法名覆盖重复事件的入口。
- 仅在原 DynTransferGraph 的四参数查询构图函数中，将运行事件的方法名查回
  `this.method2idx`，修复把运行编号直接当图编号的问题。独立 class 覆盖加载，原作者 JAR 不改。
  逆向撤销这一处修改后，整个规范化 class 与原件逐字节相同。
- 调用原作者的查询动态图构建、语句覆盖裁剪和 OT3AnalysisAll.computeNodes 搜索；
  没有补写字段边或另写路径搜索。保留此前已披露的 Spring/lambda 模型适配。
- 解码失败、端点方法未进入、编号不存在、次序异常或空动态图均报错，禁止静态图回退评分。
  因此这不是“完全未修改的原版 FlowDist”成绩，输入适配和编号修复均单独留证。

最终结果目录为 `artifacts/field-access-query-comparison-v4-20261014`：

| 配置 | TP | FP | FN | TN | unknown | Precision | Recall | F1 | 回答覆盖率 | 全部查询答对比例 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| FlowDist＋适配 | 0 | 0 | 7 | 13 | 0 | 未定义 | 0% | 0% | 100% | 65% |
| TraceFusion | 7 | 0 | 0 | 7 | 6 | 100% | 100% | 100% | 70% | 70% |

FN 包含未回答的正例；unknown 不计为答对，始终留在全部 20 条查询的覆盖率／答对比例分母中。
本轮六个 unknown 都是 Carts 负例：部分数据库／反射写入缺少已观察的 reaching write，
不能凭字段值相同或预期标签将它们补成 TN。因此 TraceFusion 的 F1=100% 不代表完成了全部查询。

| 查询组 | 数量 | FlowDist＋适配答对／unknown | TraceFusion 答对／unknown |
| --- | ---: | --- | --- |
| Carts DTO 存储 | 9 | 6／0 | 3／6 |
| Shipping DTO 存储 | 4 | 2／0 | 4／0 |
| Orders 派生 total | 7 | 5／0 | 7／0 |

FlowDist 三个服务的原生完整日志分别包含 Orders 8679、Carts 18088、Shipping 1078 个事件
（精确计数以 checkpoint 为准）。每条查询都产生了非空的真实动态图，并在裁剪后具有唯一字段端点。
四条独立 getter 字段读取→return 正例全部通过，未计入 20 条查询分母。
七条跨方法字段正例未检出是当前 Sock Shop 模型／配置的现象，尚未定位全部原因，
不能推导出 FlowDist 通常不能分析字段，也不能据此宣称完整分布式重建优于原论文。

8 个 Python 字段回归、5 个 Java 日志解码检查及既有 16 个 FlowDist Python 检查通过。
`audit_field_comparison.py` 独立核对原始日志、查询标签／端点、业务协议、完整事件计数、
动态图非空、控制查询、混淆矩阵和证据哈希；摘要保存在 `field-comparison-20261014.json`。
尚需解决 Carts 反射写入、定位 FlowDist 字段漏依赖、补齐请求实例／跨服务路径真值，
再开展独立测试集和相同最终前端配置的重复成本测量。

```bash
# 使用已采集的共同工作负载，输出目录须为新目录。
python3 experiments/sockshop-mirrortaint/compare_field_accesses.py freeze \
  --repo artifacts/external-tools/flowdist --pilot artifacts/sockshop-field-comparison-20261014 \
  --orders artifacts/flowdist-orders-data-20261014 --carts artifacts/flowdist-carts-data-20261014 \
  --shipping artifacts/flowdist-shipping-data-20261014 --out artifacts/field-compare-new
python3 experiments/sockshop-mirrortaint/compare_field_accesses.py evaluate \
  --repo artifacts/external-tools/flowdist --pilot artifacts/sockshop-field-comparison-20261014 \
  --orders artifacts/flowdist-orders-data-20261014 --carts artifacts/flowdist-carts-data-20261014 \
  --shipping artifacts/flowdist-shipping-data-20261014 --out artifacts/field-compare-new
python3 experiments/sockshop-mirrortaint/audit_field_comparison.py \
  --pilot artifacts/sockshop-field-comparison-20261014 --comparison artifacts/field-compare-new \
  --out /tmp/field-compare-checkpoint.json
```

### 首条跨服务主路径：Carts 响应字段 → Orders.total（2026-10-14）

已用相同的源字段、目标字段和真值跑通第一组**跨服务字段类型聚合查询**。
源从 Carts 实际返回的 Item 字段开始，经 HTTP 响应和 Orders 的计算，到
CustomerOrder.total 字段写入结束，不要求追溯 Carts 数据库赋值。
因此本组不使用上一节 setter→getter 的 DTO 存储查询，也不混入其 20 条分母。

实际接口是 Orders 请求的 `GET /carts/{customer}/items`，由 Spring Data REST 生成，
并非 `CartsController.get`。旧 HTTP 时钟适配仅覆盖 Shipping，不能据此认定已经跟踪此路径。
新增 opt-in `--carts-http` 后，Orders/Carts 都记录了真实 HTTP 关联。
FlowDist 使用原进程逻辑时钟与首次接收规则；Carts 在实际序列化读完字段后才发送回复时钟，
通过缓存响应延迟提交实现，避免将回复时钟打在源字段读取之前。仅选择指定的 Java Carts
GET 路径，未把时钟扩展到 Go、数据库或付款接口。

TraceFusion 为这条 RPC 增加独立消息 UUID，将 Carts 实际 getter 字段读取与 Orders
反序列化的 Item 快照连接。按消息身份、列表位置和默认 JSON 属性选边，值只检验已选的边。
再接入已有对象／字段版本与算术／stream 重建；不以 B3 trace、客户编号或业务值选择来源。
本轮有 15 个成功的 total 目标（含空购物车的常量结果），重建 30 条实际字段来源路径；
48 个 HTTP 字段绑定另含 itemId 负例及没有成功目标的响应，不与主表查询数混用。

FlowDist 需额外披露以下适配与配置，**本表不是未修改原版 OT3 的 socket 级实验复现**：

- 为已有原生 enter 探针的方法，在真实正常调用返回处补原 OTMonitor.returnInto 观察。
  异常返回不发成功事件；方法尚未 enter 时不补事件。移除新探针后，规范化 class 完全复原。
  这修复了框架／异步调用返回后，调用方恢复执行未被完整记录的问题。
- 从 Jimple 的真实 LambdaMetafactory 目标和直接管道结构，生成通用的顺序
  `List.stream().mapToDouble(lambda).sum()` 回调返回摘要，使用原生 VTE_RET 边。
  摘要不引用 quantity/unitPrice、查询标签或预期结果，暂不覆盖 parallel/filter 等其他管道。
  这是新增库模型，不能称为完全没有模型扩展。
- 原按源方法条件匹配配置仍有失败的正例，原始诊断保留。主表采用作者 JAR 已有的
  `DynTransferGraph.buildGraph(DynTransferGraph, boolean)` 全轨迹匹配实现，再用原生语句搜索。
  这里没有替换图搜索／传播规则，也不加载上一节修复编号查找的 DynTransferGraph class 覆盖。
  `build_flowdist_field_launcher.py` 构建可复现的此配置，原作者 JAR SHA 保持不变。
- 跨服务输出组合为：原生进程时钟候选路径、原生 Carts 字段→getter 返回路径、
  明确披露的默认 JSON 属性名／类型模型、原生 Orders 字段→total 路径。
  它是高层框架模型适配后的组合结果，不是直接冒充原 OT3 的底层网络语句路径。
  FlowDist 不读取 TraceFusion 的 UUID 关联或重建结果。

最终 FlowDist 配置的 11 项阶段正例全部通过，包括两边 getter、Orders 回调返回、
sum、调用方恢复、构造传参和 total 写入。前面的默认匹配失败和静态／动态差异证据
保留在 `carts-orders-native-*-controls-20261014` 等目录，没有把它们改计为算法 FN。

主表范围是“该次完整工作负载中，某类 Carts 响应字段是否影响某类 Orders 输出字段”。
TraceFusion 的请求实例路径向此粒度聚合；FlowDist 保留原方法／进程粒度，
本表**不声称双方都已完成请求实例区分**。

| Carts 源字段 | Orders 目标字段 | 真值 | FlowDist＋上述适配 | TraceFusion |
| --- | --- | --- | --- | --- |
| Item.quantity | CustomerOrder.total | 有依赖 | 有依赖 | 有依赖 |
| Item.unitPrice | CustomerOrder.total | 有依赖 | 有依赖 | 有依赖 |
| Item.itemId | CustomerOrder.total | 无依赖 | 无依赖 | 无依赖 |

两边都是 TP=2、FP=0、FN=0、TN=1、unknown=0；Precision/Recall/F1=100%，覆盖率=100%。
**这只有 3 条聚合字段类型查询，属于第一条路径校准，不能据此宣称准确率全面达到 100%
或任一方法胜出。** 真值来自独立业务公式，查询在组合预测前冻结；端点资格检查时已看到
采集观察和阶段控制，因此不是盲测基准，也不是论文 Sock Shop 69 条关系的复现。

最终主表为 `artifacts/carts-orders-main-comparison-20261014/main-table.csv`，
FlowDist 采集为 `sockshop-carts-http-resumptions-20261014/flowdist`，
TraceFusion 采集为 `sockshop-carts-http-20261014/tracefusion`；两边各 31 次业务检查通过，
镜像与冻结工作负载／观察器协议匹配。先前 FlowDist HTTP 版本另有 31 次通过的诊断调用。
实验自己的容器、网络和卷均已清理。

47 项回归检查及 11 个原生阶段正例通过。`audit_carts_orders.py` 独立核对原生查询日志、
时钟进程关系、未覆盖原生图类、字段端点、消息身份、预测与真值分离、计数和证据哈希；
可提交摘要在 `carts-orders-comparison-20261014.json`。新增调用返回探针和响应缓存会影响
开销，**不可把旧配置的 Runtime/Memory Cost 数字拼进本表**；本轮功能采集不构成成本测量。

复用已采集数据的主表生成示例（输出目录须为新目录）：

```bash
python3 experiments/sockshop-mirrortaint/build_flowdist_field_launcher.py \
  --repo artifacts/external-tools/flowdist --out artifacts/all-query-driver-new
comparison_flags=(
  --repo artifacts/external-tools/flowdist
  --flowdist artifacts/sockshop-carts-http-resumptions-20261014/flowdist
  --tracefusion artifacts/sockshop-carts-http-20261014/tracefusion
  --orders artifacts/flowdist-orders-data-20261014
  --carts artifacts/flowdist-carts-data-20261014
  --template artifacts/all-query-driver-new
  --stream-model artifacts/flowdist-sequential-stream-return-model-20261014/model.tsv
  --qualification artifacts/carts-orders-native-all-query-stages-20261014
  --reconstruction artifacts/sockshop-carts-http-20261014/tracefusion/carts-to-total.json
  --out artifacts/carts-orders-main-new
)
python3 experiments/sockshop-mirrortaint/compare_carts_orders.py freeze "${comparison_flags[@]}"
python3 experiments/sockshop-mirrortaint/compare_carts_orders.py evaluate "${comparison_flags[@]}"
```

重新采集时，先用 `build_flowdist_spring_apps.py` 构建新版 HTTP 配置；
`refresh_flowdist_http.py` 将这些配置刷新到已验证的完整方法／分支构件中；
`build_flowdist_resumptions.py` 补正常调用返回观察。
`three_method_five.py --carts-http --modes flowdist tracefusion` 用同一工作负载采集，
`infer_carts_http_sources.py` 重建消息字段路径，`flowdist_stream_model.py` 生成库摘要，
`qualify_carts_orders.py --all-query-matching --stream-model ...` 先完成阶段资格检查。
各脚本 `--help` 列出必需输入，所有原输入与旧实验目录保持不变。

## 2026-10-14 动态基线复核与 Phosphor 接入

采用 MirrorTaint＋披露适配器作为主动态基线，Phosphor 作为待资格验证的第二动态基线；
FlowDist 保留已有结果作为补充，FlowDroid 暂不进入字段实例准确率主表。
不沿用论文工具之间不同粒度的真值或漏报数；执行／接入失败单列兼容性，不计成传播算法 FN。

`audit_dynamic_baselines.py` 独立读取 `sockshop-three-five-v3-20261013` 的原始记录，
检查 plain / MirrorTaint / TraceFusion 三配置的镜像、原版业务 JAR、共同 JVM 参数、
相同负载、453 次业务调用及 300 个原始性能样本，重新计算 TP/FP/FN 和完全匹配率。
该复核不重跑推断，不引用旧 FlowDist 七查询或四参考查询的无效结果。
原始成本被篡改、unknown 被标为 exact 的两个负对照均拒绝。

准确率范围是 **request / business-record / field**。Orders 归一化为请求、服务、路由、
记录 ID、字段；Carts / Shipping 为请求、记录 ID、字段。相同请求中同一记录字段的多次
读取或版本可能合并，不能据此宣称严格字段实例／版本或跨服务路径准确率。
当前两方案各 166/166 查询完全匹配，TP=180、FP=0、FN=0，P/R/F1 均 100%；
另各有 8 个无目标检查通过，未混入 TP。

下表是该轮保存的成本均值，每方法 5 次预热、20 次串行测量。Runtime 为含在线追踪的
控制器墙钟 ms；Memory 为整服务 JVM RSS KiB。只有每配置一轮固定顺序部署，
启动、静态分析、结束写盘和离线还原不在 Runtime 中，不能作为正式性能排名。

| 方法 | plain ms | MT＋适配 ms | TraceFusion ms | plain RSS KiB | MT＋适配 RSS KiB | TraceFusion RSS KiB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| newOrder | 15.600 | 94.246 | 20.734 | 507011.0 | 504335.0 | 519500.0 |
| get | 1.510 | 3.540 | 2.266 | 500056.8 | 522300.4 | 496276.4 |
| delete | 2.083 | 3.916 | 2.880 | 499978.6 | 522250.8 | 496294.6 |
| mergeCarts | 5.527 | 12.137 | 8.282 | 500014.4 | 522409.4 | 496346.2 |
| postShipping | 0.534 | 2.584 | 1.280 | 512527.0 | 509295.4 | 501277.6 |

结果：`artifacts/dynamic-baseline-audit-20261014/{comparison.md,field-calibration.csv,online-costs.csv,validation.json}`。
CSV 还保留各方法 TP/FP/FN、Precision/Recall/F1、完全匹配率、unknown、RSS 和独立的分配增量；
离线还原时间和离线进程峰值 RSS 见 validation.json，未与在线成本混合。

复核命令（输出必须用新目录）：

```bash
python3 experiments/sockshop-mirrortaint/audit_dynamic_baselines.py \
  --pilot artifacts/sockshop-three-five-v3-20261013 \
  --out artifacts/dynamic-baseline-audit-new
```


Phosphor 固定为官方 Maven Central **0.0.3** 发布包（不是论文版本的数值复现），
JAR SHA-256 `12d9613d93baaa3dc64e7727bcfba006147e06b244af80b6b5fd33e1af1fd837`。
下载来源及上游校验和保存在 `artifacts/external-tools/phosphor-0.0.3/manifest.json`：
[官方发布包](https://repo.maven.apache.org/maven2/edu/gmu/swe/phosphor/Phosphor/0.0.3/)。
JRE 来自固定 digest 的原 Sock Shop Orders Java8 镜像，单独插桩到实验目录，
不替换主机 JDK。采用 `-multiTaint`、显式数据流，不开启控制依赖传播。

`PhosphorShippingProbe.java` 直接调用原版 Shipment / ShippingController：
多来源算术、不同 String 对象的同值字段、同一 DTO 的重复请求、字段覆盖、旧引用、
覆盖为无标签值，共 12 项断言通过。**共享同一个 String 对象的 id/name 不能通过：**
当前 `MultiTainter.taintedObject` 给对象设标签，第二个字段打标会覆盖第一个字段标签。
这是本次版本／来源配置的限制，不能据此断言所有 Phosphor 配置都不支持字段分析；
也不能静默克隆字段对象或给目标补标签来掩盖问题。

`PhosphorShippingAgent.java` 仅在控制器入口给两个声明来源打不同标签，
返回时读取原生标签，不按值建立来源关系。它在 Phosphor 之前注册，
提供与插桩 JRE 一致的数组标签转换接口，并预载自身 ASM visitor，避免混合插桩域；
使用 Phosphor 随包的 ASM，不修改 Phosphor 的传播代码或原版业务 JAR。
HTTP 夹具在执行前冻结为不同字段值、同值字段、重复相同输入、相同业务 ID 新 name 四场景。

最终 `artifacts/phosphor-shipping-20261014` 已从头用复现脚本构建并完成：
4/4 HTTP 业务请求、8/8 字段查询，TP=8、FP=0、FN=0，P/R/F1=100%。
这里的目标是控制器返回的 DTO 字段，不能解释为 HTTP 序列化后或跨服务标签已验证。
负对照把一个真实目标标签改成其他来源时，评分变成 TP=7、FP=1、FN=1、F1=87.5%；
注入运行时 VerifyError 时拒绝生成污点指标。结果与逐查询答案见 `qualification.json`。

| 配置／范围 | 业务 | 字段校准 | 当前资格 |
| --- | --- | --- | --- |
| MirrorTaint＋披露适配器，五方法 | 151/151 | 166/166，180/0/0 | 有界记录字段校准；严格版本／共享引用待补测 |
| TraceFusion，五方法 | 151/151 | 166/166，180/0/0 | 有界记录字段校准；严格版本／共享引用待补测 |
| Phosphor 0.0.3＋入口／采集适配器，Shipping | 4/4 | 8/8，8/0/0 | 专项兼容性通过；共享引用限制，主表资格未完成 |
| Phosphor 前两次 HTTP 适配尝试 | 各 4/4 | N/A，无来源／目标观测 | 分析接入失败，不计作 FN |

失败尝试保存在 `phosphor-java8-qualification[-v2]-20261014/attempt-status.json`；
与最终复现环境独立，不覆盖原始日志。完整检查点为 `dynamic-baselines-20261014.json`。

Shipping 专项未部署 RabbitMQ：原版控制器捕获连接异常后仍接受并返回 Shipment。
因此只验证入口／返回字段和 Spring/Jackson HTTP 的兼容性，不代表配送成功、AMQP
跨进程标签传播或第二 JVM 的来源重建，也不测此配置的 Runtime / Memory Cost。
它与 166 查询使用不同场景和分母，不能把二者的百分比直接并排用于排名。

复现（`--work` 为新目录，需要已校验发布包和本地缓存的固定镜像）：

```bash
python3 experiments/sockshop-mirrortaint/phosphor_shipping.py prepare \
  --work artifacts/phosphor-shipping-new
python3 experiments/sockshop-mirrortaint/phosphor_shipping.py http \
  --work artifacts/phosphor-shipping-new
python3 experiments/sockshop-mirrortaint/phosphor_shipping.py evaluate \
  --work artifacts/phosphor-shipping-new
```

容器只属于本次实验，HTTP 阶段完成或失败均保存日志并停止／删除该容器。
执行失败保留启动／业务／分析阶段和原因，字段指标记 N/A，不生成虚假的传播 FN。
后续应先解决／限定共享引用来源定义，再接入 Carts 和 Orders，统一重跑负载后才考虑
把 Phosphor 加入主表；跨 JVM 还需单独披露消息序列化／传输适配与真值。
共享引用、重复读取和覆盖版本的严格查询也必须对 MirrorTaint / TraceFusion 同样补测；
目前只验证了 Phosphor 此配置的限制，不能据此宣称另两个方案优于它。

## 2026-10-14 四工具共同语句级 Shipping 校准

已完成第一轮四工具同口径验证：来源为原版 `ShippingController.postShipping`
的 `@parameter0` 语句，目标为该方法的 `return r1` 语句。
原始 class 的独立反汇编显示直接 `aload_1; areturn`；对应 Jimple ID 为 142 → 152。
这条真值在查询运行前冻结，不从工具的预测结果生成。

四工具使用同一份 Shipping 业务字节码与四个 HTTP 输入：不同字段值、同值字段、
重复相同输入、相同业务 ID 的新 name。MirrorTaint / TraceFusion / FlowDist 新采集，
Phosphor 复用已核验的完全相同四场景专项记录，并核对业务 JAR SHA-256。
每配置业务调用 4/4 成功，RabbitMQ 都未部署，原版控制器捕获队列异常后仍返回入参。
前三者使用同一 Java8 镜像、`-Xms128m -Xmx2g`；Phosphor 使用该镜像派生的插桩 JRE。
这是准确性接入口径校准，不提供这轮配置的开销比较。

共同来源配置仅包含入参 Shipment 的 id/name 内容，目标为返回 DTO 的 id/name 内容。
MT / TF / Phosphor 的实际字段来源统一投影为参数语句，实际返回字段统一投影为返回语句。
**四次调用的八个字段答案去重后只有一对语句，不是八条或四条语句查询。**
FlowDist 原生查询在整个本地轨迹上作聚合，不声称能够区分这四次请求。

| 配置 | 聚合语句查询数 | TP | FP | FN | Unknown | Precision | Recall | F1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| MirrorTaint＋披露适配器 | 1 | 1 | 0 | 0 | 0 | 100% | 100% | 100% |
| TraceFusion | 1 | 1 | 0 | 0 | 0 | 100% | 100% | 100% |
| Phosphor 0.0.3＋来源／采集适配器 | 1 | 1 | 0 | 0 | 0 | 100% | 100% | 100% |
| FlowDist＋披露适配器 | 1 | 1 | 0 | 0 | 0 | 100% | 100% | 100% |

**只有一条阳性关系，没有阴性查询；不能据此评判误报能力或宣布四工具准确率相同。**
它只证明这组来源／目标可以对齐并被四工具分析，不能恢复旧的四条引用控制结果，
也不能替代完整五方法、严格字段实例／版本或跨服务路径准确率。
后续扩展 Carts 与 Orders 时，应冻结更多共同语句对及真实负例，保留不支持／unknown 的覆盖率。

FlowDist 仅读取完整 Local 方法事件及实际语句覆盖，用原作者
`DynTransferGraph.buildGraph(DynTransferGraph, boolean)` 和 `OT3AnalysisAll.computeNodes`。
完整事件解码适配、应用观测及原作者 all-query 模式均披露；未覆盖原引擎 class，
未加自定义图边／路径搜索，不允许空动态图或静态回退。
本轮动态图有 150 个节点、265 条边，来源／目标各有 1 个节点，原生 `is_local=true`。
没有启用 Stream 摘要；并未证明另一种 query-conditioned 原生匹配模式也能得到同样答案。

结果保存在 `artifacts/common-statement-shipping-v2-20261014/` 的
`contract.json`、`comparison.json`、`comparison.md` 和 `main-table.csv`。
改变共同业务输入、破坏原生查询驱动 class 的两个负对照均拒绝评分。
MirrorTaint / FlowDist 中断的采集已保存为 `*-interrupted/`，不计 FN；重试使用干净目录，
本轮专属容器均已停止／删除。源与证据摘要在 `common-statement-20261014.json`。

复现时依赖固定的已构建工具／业务构件和 Phosphor 四场景证据；每个阶段使用新输出，
不要在已有 native-query 工作目录上重复执行 evaluate：

```bash
python3 experiments/sockshop-mirrortaint/common_statement_shipping.py freeze \
  --out artifacts/common-statement-shipping-new
python3 experiments/sockshop-mirrortaint/common_statement_shipping.py collect \
  --mode tracefusion --out artifacts/common-statement-shipping-new
python3 experiments/sockshop-mirrortaint/common_statement_shipping.py collect \
  --mode mirrortaint --out artifacts/common-statement-shipping-new
python3 experiments/sockshop-mirrortaint/common_statement_shipping.py collect \
  --mode flowdist --out artifacts/common-statement-shipping-new
python3 experiments/sockshop-mirrortaint/common_statement_shipping.py evaluate \
  --out artifacts/common-statement-shipping-new
```

## 2026-10-14 五方法双口径结果

已完成 `Orders.newOrder`、`Carts.get/delete/mergeCarts`、`Shipping.postShipping`。
字段表沿用已审计的请求／业务记录／字段真值；语句表使用另行冻结的物理端点与真值。
这不是把 166 个字段查询简单去重成 11 个语句查询：Orders 的语句来源是指定 getter
的字段读指令，字段表的来源则是服务边界字段。两张表的分母不能合并排名。

| 表／配置 | 查询数 | TP | FP | FN | TN | Precision | Recall | F1 | 完全匹配 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 字段：MirrorTaint＋披露适配器 | 166 | 180 | 0 | 0 | — | 100% | 100% | 100% | 166/166 |
| 字段：TraceFusion | 166 | 180 | 0 | 0 | — | 100% | 100% | 100% | 166/166 |
| 语句：TraceFusion | 11 | 6 | 0 | 0 | 5 | 100% | 100% | 100% | 11/11 |
| 语句：Phosphor 0.0.4＋来源／采集适配器 | 11 | 6 | 0 | 0 | 5 | 100% | 100% | 100% | 11/11 |
| 语句：FlowDist＋披露适配器 | 11 | 6 | 0 | 0 | 5 | 100% | 100% | 100% | 11/11 |

语句集包含 Orders 的 7 对关系：quantity、unitPrice → 构造器 total 写入为两条阳性，
itemId、firstName、street、longNum、ccv → 同一写入为五条阴性；Carts 三个方法各一条
DAO 返回引用内容 → return/delete/save 关系；Shipping 一条入参内容 → return 关系。
三配置使用相同场景顺序，独立数据库及随机夹具 ID；每配置 31/31 业务调用通过。
Phosphor 完整部署 11 个服务，包含真实数据库、payment、RabbitMQ 和消费端。
这里评分的是单 JVM 捕获中的聚合语句关系，未验证消息跨 JVM 标签传播。
Carts 的 save/delete 帮助方法在多个 API 及夹具中共享，表中按代表性端点关联方法，
没有按 API 根调用隔离；不能把 11/11 写成逐请求字段实例或端到端路径准确率。

Phosphor 0.0.3 在 Orders/Carts 的 primitive lambda ABI 上失败，原始失败日志保留；
执行失败记 N/A。最终采用官方 `Phosphor-0.0.4` 标签，提交
`6c15c9b2bb609b790cacfc9297d9f18724dcb1d6`，原作者 Java 源码和 POM 未修改，
用 Java8 javac 编译并单独插桩 Java8 JRE；原生 Stream 数值标签探针通过。
来源赋值和目标观测适配器调用原生标签接口，不增加传播算法；Carts 来源配置覆盖引用
内容，未将 primitive 字段内容作为来源。工具源码、发布构件及适配器均保存 SHA-256。
FlowDist 使用原作者 all-query builder 和查询引擎，保留完整事件解码、正常返回观测及
顺序 Stream 返回模型的披露，不覆盖引擎 class、不作静态图回退。

完整逐方法两表、历史字段配置 Runtime/Memory Cost 及限制在
`artifacts/two-grain-five-methods-20261014/results.md`；CSV、逐查询答案、原生查询日志
与冻结契约位于同目录。新增 Phosphor/FlowDist 语句配置没有同口径成本测量，历史
成本不能移用。当前两表结果持平，仅为有界接入口径校准，不支持优越性结论。
字段表可能折叠同一请求中同一业务字段的重复读／版本，另有八个无目标检查单独统计。

计分负对照：给真实目标日志添加一个负例来源，必须计为 FP；去掉实际来源赋值后的
标签，必须把分析标为不可用；更改业务场景列表，必须拒绝评分。原日志保持不变。
检查点 `two-grain-comparison-20261014.json` 保存结果、来源与证据散列。

复评已有固定构件／捕获（只校验缓存输入与日志散列，不重复执行已有原生工作目录）：

```bash
python3 experiments/sockshop-mirrortaint/compare_two_grains.py evaluate \
  --phosphor artifacts/phosphor-004-five-statements-20261014 \
  --out artifacts/two-grain-five-methods-20261014
```

完整重采 Phosphor 时使用新目录及已校验的官方 0.0.4 构件／插桩 JRE：

```bash
python3 experiments/sockshop-mirrortaint/phosphor_five_statements.py build \
  --tool artifacts/external-tools/phosphor-0.0.4 --out artifacts/phosphor-statement-build-new
python3 experiments/sockshop-mirrortaint/phosphor_five_statements.py run \
  --tool artifacts/external-tools/phosphor-0.0.4 \
  --jre artifacts/phosphor-004-jre-20261014/jre \
  --build artifacts/phosphor-statement-build-new --out artifacts/phosphor-five-statements-new
```

新捕获评分使用 `freeze --out <新比较目录>` 冻结端点，然后 `evaluate --phosphor
<新捕获目录> --out <新比较目录>`；TraceFusion/FlowDist 当前固定捕获路径在比较脚本中
明确声明。复现实验需缓存业务镜像、工具与静态图，不能只凭检查点 JSON 启动服务。

## 2026-10-15 字段来源 → 安全规则 → 影响确认

已完成新的两 JVM 受控应用实验与 Log4j2 已知漏洞触发／修复对照，共 37/37 业务调用。
应用夹具为 `SecurityLeakLab.java`，不修改 Sock Shop，也不声称 Sock Shop 存在漏洞。
`SecurityObservationAgent.java` 是 opt-in 新观测前端：只记录对象身份、字段版本／读写、
实际分支、HTTP 消息身份与 JSON、真实 Logger.info 参数及原生 JndiLookup 参数。
不在运行时传播来源标签。`security_field_flow.py` 根据实际原始字节码和分支观测，
离线重建有界引用复制、局部变量覆盖和对象字段版本；不读取夹具预期答案。
这是对既有方法的新实验扩展，不把旧配置的性能数字移用过来。

| 配置／判据 | 查询 | TP | FP | FN（含阳性 unknown） | TN | Unknown | Precision | Recall | F1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 受控敏感字段 → 禁止的日志目的地 | 22 | 9 | 0 | 1 | 12 | 1 | 100% | 90% | 94.7% |
| Log4j 2.14.1：可控日志参数 → 实际 JNDI lookup | 5 | 3 | 0 | 0 | 2 | 0 | 100% | 100% | 100% |
| 同库 + formatMsgNoLookups=true | 5 | 0 | 0 | 0 | 5 | 0 | N/A | N/A | N/A |
| Log4j 2.17.1 修复版 | 5 | 0 | 0 | 0 | 5 | 0 | N/A | N/A | N/A |

缓解版、修复版无阳性样本／预测，P/R/F1 无定义，不写成 100%。受控组覆盖率 21/22
（95.5%），未知 helper 实际复制了敏感值，但当前未支持其调用模型，保留 unknown，
按真实泄露的漏检计入 FN。不能仅在成功重建的查询上报告 100%。

受控组包括直接泄露、公开字段、相同值的敏感／公开字段、局部变量覆盖、对象字段复制
和覆盖、读取但未使用的敏感字段、与敏感值相同的常量、未知调用及 12 个并发请求。
并发组所有字段值与业务 ID 相同；源服务为每个真实 HTTP 响应生成独立 UUID，关联按
消息身份及属性选择，值只校验已选边。同步屏障使 12 个实际业务帧同时存活。
首轮虽然并行发 HTTP，但字段处理帧未重叠，原始记录保留为 `security-leak-20261015`；
最终采用 `security-leak-v2-20261015`，没有用首轮结果声称已验证帧内并发区分。

已知漏洞使用官方未修改 Log4j API/Core 2.14.1 与 2.17.1 的原始 JAR（固定 SHA-256）。
五个场景为直接表达式、经字段复制、被覆盖的表达式、普通消息、公开但用户可控字段
中的表达式。漏洞版三个触发均同时有实际 Logger.info 参数、原生 JndiLookup 参数、
本地 Context.lookup 回调及日志 `LOCAL_LOOKUP_MARKER`；两种防护配置均无触发。
`${jndi:key}` 到 lookup 实参采用明确披露的单字面表达式模型，并校验实际 key；不声称
重建了 Log4j 内部每条语句。仅有 Source→日志关系不会直接算作 JNDI 漏洞触发。

本地 JNDI provider 只返回固定字符串，不联系 LDAP、不加载远程代码。
因此复现的是 CVE-2021-44228 的危险 lookup 求值路径及防护前后差异，未证明 RCE，
也不是复现原生产应用或发现新漏洞。官方依据：
[Apache Log4j 安全公告](https://logging.apache.org/security.html#CVE-2021-44228)。

独立审计用 javap 验证每配置 80 条原始 Flow 指令的 opcode、字段／方法／常量／分支
操作数，核验原应用和原库 class SHA、业务覆盖和进程清理。九个负／扰动对照通过：
缺失消息身份保持 unknown；打乱源事件顺序仍保持来源；重复消息身份、缺失分支、
字段版本破坏、目标参数篡改、HTTP 内容破坏被拒绝；更改请求名称不改变来源；
lookup 参数不符合库模型时保持 unknown。原始采集不修改。

完整报告为 `artifacts/security-leak-v2-20261015/results.md`，同目录保存 JSON、CSV、
逐事件／逐查询证据、应用日志、真实回调、审计与负对照结果。
可提交检查点为 `security-field-flow-20261015.json`。
当前只支持有界无环引用复制、观测分支、线程独占 DTO、默认三 String JSON 和单跳
HTTP；不支持一般隐式流或未知 helper。尚未测量该新配置成本或接入其他比较工具。

复现（使用已有固定 ASM 9.7.1 与 Jackson 2.8.6 缓存；两个 JVM 仅监听 localhost）：

```bash
python3 experiments/sockshop-mirrortaint/run_security_leak.py prepare \
  --out artifacts/security-leak-deps
python3 experiments/sockshop-mirrortaint/run_security_leak.py build \
  --out artifacts/security-leak-build-new
python3 experiments/sockshop-mirrortaint/run_security_leak.py freeze \
  --out artifacts/security-leak-new
python3 experiments/sockshop-mirrortaint/run_security_leak.py run \
  --build artifacts/security-leak-build-new --out artifacts/security-leak-new
python3 experiments/sockshop-mirrortaint/audit_security_leak.py \
  --build artifacts/security-leak-build-new --out artifacts/security-leak-new
```

`run` 无论成功／失败都停止专属进程、保存退出状态；`audit` 重新生成完整报告。
已有最终捕获可直接执行最后一步，不能覆盖已有目录重跑采集。

## 2026-10-15 查询驱动的自动观测计划：首版

新增 `query_observation_planner.py`：输入原始应用 class 模型、固定入口边界与目标字段，
自动追入可确定分派的应用 helper，生成字段来源与覆盖后的表达式、路径区分需求、
边界快照字段及插桩位置。采集器 `QueryObservationAgent.java` 仅消费计划，不包含
quantity/unitPrice/name 的业务配置；`infer_query_observations.py` 用同一个候选一致性
还原器处理 full、selective、fixed 三种证据。业务值与请求名称不选择来源。

本节是第一阶段新增受控 Java 程序的算法验证，**不是原 Sock Shop Orders / Shipment 服务**；
后续真实服务接入见下一节，尚未替换前文跨服务工具主表。入口边界仍需配置，换查询字段后无需
修改采集器、还原器或业务计算模型。原始 class 由 `QueryBytecodeModel.java` 导出，
方法调用、字段读写及数学操作均从指令导出。

规划步骤：

1. 在有界无环应用调用图中构建字段／局部赋值、算术来源和最后写入关系。
2. 以最终目标字段的来源集合、根对象身份和目标版本为查询答案。
3. 固定入口／出口身份和字段版本、所有目标写入，枚举固定证据相同但答案不同的路径对。
4. 贪心保留能区分这些路径对的分支事实，再删除冗余分支；按答案反推快照字段。
5. 输出可重新生成／检查的计划与证书；证据不足返回 unknown，未知外部效果拒绝规划。

证书检查“同选定证据的候选路径有同来源及版本答案”。这是声明模型内的充分性检查，
不是任意 Java 的正确性证明；只保证所选分支按删除意义不可再减，不保证所有观测全局
最少。框架／库摘要仍需要明确支持；不能借此宣布算法新颖性已确立。

| 受控目标集合 | 额外分支点 | 完整／自动完全匹配 | 完整事件 | 自动事件 | 事件减少 |
| --- | ---: | --- | ---: | ---: | ---: |
| Orders.total | 1 | 44/44；44/44 | 748 | 220 | 70.6% |
| Shipment.name | 0 | 44/44；44/44 | 748 | 176 | 76.5% |
| Noise.payload | 0 | 44/44；44/44 | 748 | 132 | 82.4% |
| total + name | 1 | 88/88；88/88 | 748 | 308 | 58.8% |
| 三个字段 | 1 | 132/132；132/132 | 748 | 352 | 52.9% |

完整观测限定于同一入口及可达方法的实例字段／分支集合，非全 JVM 指令追踪。
事件数包含入口、出口、字段和分支；另计原始日志字节、字段／分支 hook 调用次数。
所有模式都为相关字段保留显式写入版本计数，包括入口之外的普通应用赋值，计数开销
没有伪装为零。fixed 保留入口／出口与必要目标写入，比纯边界快照更强。
对 name，fixed 已足够；对 payload，目标写入位置本身已区分来源；对 total，删去
所选分支后 42/44 变为 unknown，仅输入对象实际别名的两个案例仍可确定答案。

44 个输入包含同值异对象、输入别名、覆盖赋值、同对象重复调用、12 个实际重叠并发帧，
以及计划／算法冻结后生成的 24 个新随机输入。评分保留源和目标的对象／字段／版本；
完整／选择答案按入口参数对象规范化后逐项一致，未合并为业务字段类型。
重复对象的目标版本为 2 → 4，来源版本为 1 → 2。
五个查询集合重复使用这批输入，不能声称有 352 个独立案例；也不是第三方独立盲测。

另外验证两个程序变体，无需修改算法或采集器：

- 将计算方法改名，为字段复制加入两层 helper：重新从 class 生成计划，所有答案保持。
- 增加 80 段无关字段操作：total 完整事件 748 → 11308，自动选择仍为 220；完整日志
  318439 → 4021118 B，选择性日志保持 111254 B。

三种程序 × 五组查询 × 三模式共 1980 次业务调用。另有四次原生 JVM 反例执行：
固定输入值、输出值、字段版本和语义观测，仅隐藏选择不同，quantity 分别来自两个对象。
去掉选定分支，两者均 unknown；保留分支后正确区分。证据比较对根对象身份做
alpha 重命名，去掉线程／帧名称及装箱值对象身份，保留字段值、字段版本和写入位置。
三种程序各 13 项审计通过，包括独立 javap 逐指令操作数核验、证书扰动、未知效果及循环
拒绝、缺失证据、版本破坏、字段名整体替换和请求名称无关性。

完整报告与 CSV 为 `artifacts/query-planner-comparison-20261015/results.md`、
`comparison.csv`，摘要为 `summary.json`。实际捕获分别为 `query-planner-20261015`、
`query-planner-helper-20261015`、`query-planner-noise-20261015`；反例为
`query-planner-collision-20261015`，均在 `artifacts/` 下。
可提交证据摘要为 `query-planning-20261015.json`。

复现（复用固定 ASM 9.7.1 / Jackson 2.8.6 缓存，无需 Docker）：

```bash
python3 experiments/sockshop-mirrortaint/run_query_planner.py build \
  --out artifacts/query-build-new
python3 experiments/sockshop-mirrortaint/run_query_planner.py freeze \
  --build artifacts/query-build-new --out artifacts/query-run-new --seed 241016
python3 experiments/sockshop-mirrortaint/run_query_planner.py run \
  --build artifacts/query-build-new --out artifacts/query-run-new
python3 experiments/sockshop-mirrortaint/run_query_planner.py evaluate \
  --build artifacts/query-build-new --out artifacts/query-run-new
python3 experiments/sockshop-mirrortaint/audit_query_planner.py \
  --build artifacts/query-build-new --out artifacts/query-run-new
```

`build --helper-depth 2` / `--extra-work 80` 分别生成迁移／无关工作变体；`audit_query_planner.py
--collision` 使用新输出目录重跑实际歧义反例。对已导出的模型，可直接调用规划器，仅换
`--target Orders.total` 为 `--target Shipment.name`：

```bash
python3 experiments/sockshop-mirrortaint/query_observation_planner.py \
  --model artifacts/query-build-new/model.json \
  --entry 'QueryPlannerFixture.process(LQueryPlannerFixture$Source;LQueryPlannerFixture$Source;LQueryPlannerFixture$Orders;LQueryPlannerFixture$Shipment;LQueryPlannerFixture$Noise;)V' \
  --target Shipment.name --out artifacts/query-name-new.plan.json
```

当前限定根参数对象的最终标量／String 字段、可确定分派、无环路径最多 256、调用深度
最多 12、线程独占 DTO；不支持一般循环、数组、递归、反射、嵌套 heap 别名或隐式流。
ThreadLocal.get / Boolean.booleanValue 采用声明的只读环境输入契约。
本轮衡量记录量和答案保持，尚未完成业务延迟、吞吐、总 CPU、离线耗时及内存的正式
成本比较。运行文件中的 JVM 整体时间包含启动，旧成本数据不能移用。

## 真实服务的自动规划：Orders.total 与 Shipment.name（2026-10-15）

第二阶段使用**原版 Orders 0.4.7 / Shipping 0.4.8 class**，在完整 Docker Sock Shop
的真实 HTTP / Mongo / RabbitMQ 业务执行中比较 full 与 selective。输入编译程序、
入口和目标字段后，`plan_service_observations.py` 从字节码自动生成字段快照、计算摘要、
真实 lambda bootstrap / 顺序 Stream 依赖及目标写入绑定。核心规划器／采集器／还原器
无 Orders / Shipment / quantity / unitPrice 等业务名单；业务真值在评分器中独立声明。
两个服务使用相同 `PlannedServiceAgent` 字节码，计划不同；两个模式共用
`infer_planned_service.py`。

| 真实目标 | 完整／自动完全匹配 | TP / FP / FN（两模式相同） | 完整业务事件 | 自动业务事件 | 减少 | 日志 B：完整 → 自动 |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| CustomerOrder.total | 24/24；24/24 | 68 / 0 / 0 | 4548 | 292 | 93.6% | 1426531 → 89741 |
| Shipping Shipment.name | 29/29；29/29 | 29 / 0 / 0 | 145 | 58 | 60.0% | 50049 → 23043 |

两模式每种均 25 次下单（24 成功、1 支付拒绝）及 5 次独立 Shipping 请求。
29 次 Shipping 调用包含 24 次成功下单触发的内部调用，不能当成额外独立输入案例。
Orders 包含 8 个实际重叠的并发根帧，另有冻结计划后生成的 10 个新业务输入。
来源／目标对象、字段和版本均参与评分；空购物车为合法空来源，支付拒绝另核验无目标。
同值来源及 id/name 同值不会按值合并。trace ID 仅供外部评分匹配请求，不参与来源选择。

**本轮来源边界变窄且明确，不能直接混入旧跨服务工具主表：**

- total 从实际金额计算入口的成员对象字段版本开始，追到新建订单的 total；
  未追到这些对象对应的 HTTP 响应／数据库来源。
- name 从 Shipping 控制器输入对象字段版本开始，追到原样返回对象字段；
  声明 RabbitTemplate.convertAndSend 对 DTO 参数只读，未还原 AMQP 消费路径。

服务规划器支持两个可复用的受限模板：唯一 writer/producer 的标量顺序归约，以及只读
输入对象恒等返回；未知效果、一般循环、无法解析的分派等拒绝规划。它不是任意 Java
的通用规划器，也没有全局最少事件证明。入口外的应用字段写入仍保留版本 hook，计数
没有隐藏；full 字段 hook 为 Orders 7913 / Shipping 406，selective 为 164 / 58。
快照字段记录为 Orders 164 → 94，Shipping 58 → 58，另报告原始字节，避免只看合并事件数。
反射／native 等未建模写入不在保证内。记录量降低不代表已证明 Runtime / Memory 收益，
正式多轮成本实验仍待完成。

完整结果与复现命令：`artifacts/query-service-final-20261015/results.md`；
结构化结果：同目录 `comparison.csv` / `summary.json`。最终构建为
`artifacts/query-service-orders-final-build-20261015` 与
`artifacts/query-service-shipping-final-build-20261015`。
`algorithm-audit.json` 19 项通过，独立 javap 核对 362 条指令及操作数；旧规划器另有
13 项回归通过（在临时副本验证，旧捕获不变）。换 Shipping 目标为 `Shipment.id` 会自动
生成不同字段计划，此项是静态检查，尚未额外做 id 查询的真实部署实验。
可提交证据摘要为 `query-service-planning-20261015.json`。本次实验项目与测试卷已清理。

```bash
python3 experiments/sockshop-mirrortaint/run_planned_service.py evaluate \
  --out artifacts/query-service-final-20261015 \
  --build artifacts/query-service-orders-final-build-20261015
python3 experiments/sockshop-mirrortaint/audit_planned_service.py \
  --out artifacts/query-service-final-20261015 \
  --build artifacts/query-service-orders-final-build-20261015
python3 experiments/sockshop-mirrortaint/summarize_planned_service.py \
  --out artifacts/query-service-final-20261015 \
  --build artifacts/query-service-orders-final-build-20261015 \
  --checkpoint experiments/sockshop-mirrortaint/query-service-planning-20261015.json
```

## 扩大真实跨服务路径并迁移到 Train Ticket（2026-10-15）

第三阶段复用同一个冻结 JVM observer JAR、同一规划／还原代码，新增 Spring HTTP / 默认
Jackson 属性桥接与通用直接字段复制模型，应用于 Sock Shop 和 Train Ticket 镜像版0.2.0。
原始业务 JAR 及插桩前 class 不变，运行时插入观测；没有修改原业务算法。

| 实际字段路径 | 完全匹配 | TP / FP / FN | Precision / Recall / F1 |
| --- | --- | --- | --- |
| Carts.quantity/unitPrice → HTTP → Orders.total | 24/24 | 84 / 0 / 0 | 100% / 100% / 100% |
| Carts.itemId/quantity/unitPrice → Orders 返回商品字段 | 126/126 | 126 / 0 / 0 | 100% / 100% / 100% |
| Orders Shipment.id/name → Shipping → Orders 返回 shipment | 48/48 | 48 / 0 / 0 | 100% / 100% / 100% |
| Train Ticket Station.id → Response.data → Basic → TicketInfo.data | 31/31 | 30 / 0 / 0 | 100% / 100% / 100% |

Sock Shop 合计198个查询来自24个成功订单、42个商品实例；另有1次支付拒绝无目标。
Train Ticket 共31次公开读请求，30个实际记录读取实例及1个不存在站点的常量null结果。
查询发起方向 TicketInfo→Basic→Station，字段回传方向相反。空来源也参与完全匹配评分。
两应用都包含8路并发驱动，另有72条补充字段角色负关系检查，未混入229个目标实例分母。
不能把同一业务请求的多个目标字段当作独立业务案例。

`plan_distributed_fields.py` 自动导出默认JSON属性、直接getter→构造参数→目标写入、
根参数复制和常量杀死；例如不配置Station.id为业务答案，也能从Response.data反推该字段。
`SpringTransportAgent.java` 记录实际消息UUID、JSON位置及对象／字段／应用写计数。
`infer_distributed_fields.py` 用消息／位置跨进程连接，以对象／字段／版本在进程内转发，
连接已有Stream金额还原；值只验证已选边，不选择来源。去掉trace／父消息审计标签不改答案。
原RPC线程上下文另独立核验。不同服务只提供原JAR、入口和目标，不修改这三个核心组件。

迁移仍需查询配置、部署依赖、业务输入与独立真值。通用框架模型是新增工作，不能称为
任意Java／全部框架的零适配迁移，也不能从本轮推断优于MirrorTaint／FlowDist／Phosphor。
运输层当前观察已支持DTO属性，尚未完成最少运输观测；完整观测口径与正式成本继续暂缓。

边界限定：Carts来源从响应字段观测开始，不还原其数据库历史；Shipment从Orders出站
对象字段开始；Station从已解码实体的实际getter读取开始，不还原Mongo存储来源。
对象／声明字段／应用写计数以及具体观测／消息实例均保留，应用计数不冒充全部反射写
或数据库版本。背景中43个Carts Item.id数据库回写观察点因未建模写入保留unknown；这与
已查询的Item.itemId不同，也不属于预先指定的来源边界之后。缺少被查询的quantity消息
证据会使total为unknown，不能靠数值或业务公式补答案。

新审计13项通过，独立javap核对872条指令及操作数；旧受控13项、旧真实服务19项回归通过。
独立原镜像JAR核验6/6一致；Train Ticket对应Git提交尚未反查，以镜像digest/JAR/class SHA
固定身份。本次独立项目与测试卷已清理，原版鉴权未改；站点fixture仅写本次新建Mongo卷。

完整报告：`artifacts/distributed-paths-final-20261015/results.md`；主表 `main-table.csv`；
两应用各自 `inference-graph.json`、`field-results.json`、原始事件、API与DB真值均在该目录。
冻结构建：`artifacts/distributed-plans-final-build-20261015`；可提交摘要：
`distributed-paths-20261015.json`。报告包含完整复现命令，复用本地原镜像／JAR缓存。

```bash
python3 experiments/sockshop-mirrortaint/evaluate_distributed_paths.py \
  --out artifacts/distributed-paths-final-20261015 \
  --build artifacts/distributed-plans-final-build-20261015
python3 experiments/sockshop-mirrortaint/audit_distributed_paths.py \
  --out artifacts/distributed-paths-final-20261015 \
  --build artifacts/distributed-plans-final-build-20261015
python3 experiments/sockshop-mirrortaint/verify_original_path_images.py \
  --out artifacts/distributed-paths-final-20261015 \
  --build artifacts/distributed-plans-final-build-20261015
```

### W3C Trace Context 替换（2026-10-15）

迁移到台式机的代码包、非Git实验输入、镜像清单、完整复现命令和下一阶段成本
实验任务，见 [DESKTOP-HANDOFF.md](DESKTOP-HANDOFF.md)。

当前通信采集器改为传播标准 `traceparent` / `tracestate`，不再注入
`X-TraceFusion-Message`，也不要求响应回显自定义标识。每次实际 HTTP RPC
新建 client span，接收端新建 server span 并记录父关系；内部 `message` 只是
`trace-id/request-span-id` 组合键。字段桥接仍需方向、JSON pointer、两端字段
观测和本地依赖，不能按整条 trace 合并来源。Spring `@Async` 的 Callable
在提交时捕获上下文、执行结束或异常时恢复线程原上下文。

完全复用上一轮冻结的业务案例、六个原业务 JAR/字节码模型及本地字段计划，
重跑56次目标业务请求。Sock Shop 198/198（TP258、FP0、FN0）、Train Ticket
31/31（TP30、FP0、FN0），均与替换前一致；一个不存在站点查询的正确来源为空。
本轮每个应用的目标请求共用一个 trace-id，各次调用使用不同 span，包含8路并发。
两个应用分别先按自身的具体来源观测、对象、字段和写计数评分；跨部署比较再去掉
不可复用的 JVM 对象 ID/事件序号，不能把逻辑来源归一化冒充实例评分。

W3C专项检查13项、原跨服务审计13项通过；Java协议边界及异步线程复用/异常恢复
检查通过，原镜像JAR再次核验6/6一致。缺失中间来源证据返回unknown，错误响应
上下文拒绝。72条补充负关系仍通过；背景43个Carts数据库id回写unknown依然保留，
未计入事先指定的目标查询。实验项目和数据卷已清理。

限制：这是当前Spring/Jackson路径的标准上下文传播适配器，尚未集成OpenTelemetry
SDK/导出器或验证与任意既有tracer共存；也不证明已支持Go、任意线程池、自动重试
及队列。必要的字段证据不按sampled标志丢弃；外部采样造成证据缺失时不能保证
相同覆盖率。本轮不作为正式性能比较。

报告：`artifacts/distributed-paths-w3c-20261015/results.md`；对照表：
`w3c-comparison.csv`；构建：`artifacts/distributed-plans-w3c-final-build-20261015`；
可提交证据摘要：`w3c-paths-20261015.json`。报告包含复现命令，协议独立检查命令
与依赖哈希在`protocol-checks.json`。生成新一轮相同案例可使用：

```bash
python3 experiments/sockshop-mirrortaint/run_distributed_paths.py freeze \
  --out artifacts/w3c-run-new --build artifacts/w3c-build-new \
  --cases-from artifacts/distributed-paths-final-20261015 --seed 151031
```

W3C报告使用`compare_w3c_paths.py`，旧UUID报告使用`summarize_distributed_paths.py`。
旧构建的冻结源码哈希属于当时提交`ce5c182`，当前源码下直接运行旧构建的冻结检查
会拒绝源码变化；查看旧工件无需重跑，复现旧协议应使用对应提交。

## 台式机复现与独立成本驱动（2026-10-15）

本机在新的绝对目录重新构建六个服务的计划，并完成 Sock Shop 198/198、
Train Ticket 31/31 个指定字段查询验收，TP258/30、FP/FN0。13项算法审计、
13项W3C对照检查、协议/异步测试及6个原镜像JAR核验均通过；原始数据与背景
unknown 保留在 `artifacts/desktop-portable-acceptance/`，构建为
`artifacts/desktop-portable-build/`。

`experiment_environment.py` 支持 JDK 8 与 JDK 9+ 的 Java 8 目标构建，按迁移
清单选择原始 digest，并显式设置容器 DNS 搜索域，避免旧 Go 解析器使用宿主机的
搜索域。`prepare_pinned_images.py` 可通过终端代理和临时回环仓库准备全部14个
固定镜像，逐项验证 manifest/config/layer 的 SHA-256、原始 RepoDigests 和
image ID，无需修改或重启 Docker daemon。

`run_sockshop_cost.py` 为专用成本驱动：固定查询/输入模板/JVM/资源限制，预热、
独立部署和数据卷、随机配置顺序、固定到达率和并发上限、稳态 CPU/RSS 采样，
区分 HTTP 耗时与计划到达至响应的延迟。逐请求核验原业务，TraceFusion 对每轮
预热和稳态请求的全部指定字段做实例评分；记录采集事件/字节、离线图构建及
评分导出耗时/峰值内存、响应完成至整批答案写出的延迟。原版来源答案和未验收
MirrorTaint＋适配器为 N/A。固定到达率不测最大吞吐，整进程 RSS 不代表每请求
分配，整批答案延迟不代表流式查询。

命令、前置验收、度量口径及完整输出说明见 [DESKTOP-HANDOFF.md](DESKTOP-HANDOFF.md)。
短试验在 `artifacts/sockshop-cost-smoke/`，不具备正式五轮结果资格。

正式五轮结果：`artifacts/sockshop-cost-formal-20261015/results.md`，可提交摘要为
`sockshop-cost-20261015.json`。每个配置每轮预热30秒、稳态60秒、固定2请求/秒、
最大并发2；11个组件分别限制1 CPU、768 MiB。以下为五个独立部署指标的中位数，
延迟开销为同轮 TraceFusion/原版比值的中位数：

| 指标 | 原版 | TraceFusion 自动选择性观测 | 同轮延迟开销 |
| --- | ---: | ---: | ---: |
| 在线 p50 (ms) | 11.598 | 13.902 | +19.10% |
| 在线 p95 (ms) | 14.858 | 18.727 | +26.04% |
| 在线 p99 (ms) | 20.192 | 22.622 | +17.27% |
| 窗内吞吐 (请求/秒) | 2.000 | 2.000 | — |
| 三个目标 JVM CPU（单核百分比） | 6.994% | 8.659% | — |
| 三个目标 JVM RSS 均值之和 (MiB) | 1530.455 | 1530.958 | — |

每轮 TraceFusion 稳态采集5,898条事件、约4.43 MB日志。独立离线进程的图构建
中位数0.276秒，还原/评分/导出总时间中位数1.727秒，峰值RSS中位数189.47 MiB。
响应完成至整批答案写出的延迟包含剩余稳态窗口和关闭采集器；逐请求记录在各轮
`answer-readiness.jsonl`，不能将该批处理延迟解释为流式响应。

10次部署共1,800次目标业务请求（其中1,200次稳态）全部通过。五次 TraceFusion
共8,325/8,325个指定字段查询完全匹配，TP11,175、FP/FN0；1,875个背景unknown
原样保留。这是当前所选成功订单路径、固定低到达率下的成本结果，不代表最大
吞吐、全应用准确率或其他机器开销。MirrorTaint＋适配器及其他未验收配置为N/A。
原始分位数、吞吐、事件序列/字节、资源限制、字段答案、答案延迟和清理记录已
独立复核，记录在 `independent-validation.json`；所有本轮实验容器已清理。

## MirrorTaint 的 Orders.total 共同查询校准（2026-10-15）

恢复固定公开 MirrorTaint JAR 并验证原 SHA-256 后，重新构建兼容适配器及
`CommonHttpInstanceAgent`。共同来源边界是 Carts 实际序列化的 HTTP/JSON 响应，
目标是 Orders.total；数据库内部写历史、未校准的返回 Item、Shipment 和
Train Ticket 查询均为 N/A。MirrorTaint 核心只在 Orders 加载，Carts/Orders
装载独立实例证据探针；两侧 Shipping 均保持原版。TraceFusion 使用相同原业务 JAR
上的 Orders.total 计划和 Carts/Orders 观测器，重新测量，不复用前一节成本。

MirrorTaint＋披露适配器与 TraceFusion 均通过24/24个指定 total 查询、TP84、
FP/FN0。覆盖同 trace 不同 span、8路并发、同值记录、空总额、购物车更新和支付
拒绝时无目标。双方先按自身实际服务/观测序号/JSON pointer/对象/字段/应用写计数
评分，再验证逻辑字段和写计数一致；不跨 JVM 比较对象 ID，不按数值合并来源。
8项实例审计检查错误来源/目标对象、失效来源/目标版本、缺少远端字段等保持 unknown，
错误调用 span 被拒绝。此处未声称任意共享对象或反射修改已被完整处理。

适配器具体功能和可复现命令见 [DESKTOP-HANDOFF.md](DESKTOP-HANDOFF.md)。
`native_predictions` 只读取实际原生标签与运行时边界证据，实例 oracle 单独评分；
它不调用 TraceFusion 的本地字段依赖图来生成 MirrorTaint 答案。
校准原始证据分别为 `artifacts/mirrortaint-total-calibration-01/`、
`artifacts/tracefusion-total-calibration-01/`，跨运行口径核验为
`artifacts/common-total-calibration-comparison.json`。

成本驱动现在支持 `--query-scope total --modes original tracefusion mirrortaint`，
并校验校准结果、原 JAR、适配器、分析器、应用及输入哈希。负载扫描由
`scan_sockshop_load.py` 实现，保留失败请求和排队延迟；业务失败请求不伪造来源答案。
新增加的 HTTP 503 保留测试与原四项行为测试均通过，三配置短试验也通过。

解释成本时须区分事件格式和数量、标签/调用历史体积、公开 JAR 的默认诊断日志，
以及兼容和通信适配器自身成本。公开 JAR 的原始诊断产物计入采集字节；此配置不是
MirrorTaint 调优后最低成本的证明。MT 没有枚举未查询字段的图注记；其背景 unknown
不应与 TraceFusion 图中数据库 ID 的 unknown 直接比较，未校准字段保持 N/A。
事件数量接近不代表信息量相同，也不能把实测差异直接归因于“少采”。①的严格消融
仍为后续独立任务，本节不将其冒充已完成。

## Orders.total 共同查询五轮成本比较（2026-10-15）

本轮测量实现固定于 `2853a59`（在 `442178f` 上继续）；三配置均重新部署、重新测量，
不复用上一节的开销数据。预热30秒、稳态60秒、2请求/秒、并发2，五轮内随机配置顺序；
每容器1核/768 MiB，三业务 JVM 的堆和GC参数一致。双方各900/900个 total 查询准确，
TP3750、FP/FN0、目标unknown0；原版来源答案N/A。15次部署共2700次业务请求均通过。

| 五轮中位数 | 原版 | TraceFusion | MirrorTaint＋披露适配器 |
| --- | ---: | ---: | ---: |
| HTTP p50 ms | 11.600 | 13.218 | 66.459 |
| HTTP p95 ms | 15.370 | 18.520 | 107.228 |
| HTTP p99 ms | 19.180 | 23.212 | 117.389 |
| 三个业务 JVM CPU 单核 % | 6.590 | 8.258 | 22.375 |
| 三个业务 JVM RSS均值 MiB | 1535.78 | 1530.36 | 1548.00 |
| 采集增量事件数 | N/A | 5298 | 5280 |
| 采集增量字节 | N/A | 4042178 | 69756296 |
| 离线还原/评分/导出总秒 | N/A | 0.621 | 0.917 |
| 离线进程墙时（含启动）秒 | N/A | 0.705 | 0.986 |
| 离线峰值RSS MiB | N/A | 163.30 | 163.17 |
| 响应完成到整批答案可用 p95秒 | N/A | 61.342 | 61.601 |

同轮 TF/MT 成本比的中位数：p95延迟 0.1727，CPU 0.3696，采集字节 0.0579，离线总时间 0.6848。RSS与离线峰值内存接近。
事件数比 1.0034；事件格式不同且原生诊断日志计入字节，不能把这些差异直接归因于少采。
公开 JAR 与披露适配器的当前配置表现更贵，不代表 MirrorTaint 调优后的最低成本。

五轮正式报告：`artifacts/common-total-cost-formal-20261015/results.md`；
探索性扫描：`artifacts/common-total-load-scan-20261015/results.md`；
可提交摘要：`mirrortaint-total-cost-20261015.json`。独立复核覆盖逐请求延迟、吞吐、资源、
实例答案、日志计数、配置/源码哈希和清理；证据见两个结果目录的 `independent-validation.json`。
按用户最新要求，高负载扫描已停止，不是当前比较的必要验收项。已完成点仅保留作补充；
扫描预热失败与稳态错误分别保留，取消/未运行点为N/A，不据此宣称最大容量。
固定2请求/秒的完成吞吐不能证明最大吞吐相同；扫描单点也不是五轮容量估计。
采集增量含请求排空和采样边界；答案等待包含剩余窗口、关闭采集器与整批离线处理。
MT未枚举未查询字段的图注记，背景unknown为N/A，不能将其解释为全部字段无unknown。
少采的因果收益由下方独立的严格消融衡量，不能由这张跨工具成本表直接推断。

## 观测策略严格消融：冻结的比较口径

后续以新主实验机最新main为准，旧迁移包保留为历史快照。共同查询、输入和计划
沿用已验收的 `Carts实际序列化响应字段 -> Orders.total`，在新目录构建同一个
采集器JAR。full、selective、boundary仅改变 `service.mode`；相同原业务JAR、
JSONL序列化/同步flush、W3C/JSON属性采集和离线还原器/独立评分器保持一致。
不混入MirrorTaint默认诊断日志、不同采集格式或旧成本数字。

full沿用现有策略：纳入应用类中的实例字段读写与条件分支钩子，记录限于冻结查询帧；
不是所有JVM/第三方库/本地指令的完整追踪。selective使用自动计划。boundary只保留
相同HTTP/JSON边界及必要的DTO应用写计数，关闭内部帧、读、归约和目标写入记录，
不得根据数值或业务公式补造来源；其total答案必须保留unknown，仅作为功能删减控制。
full与selective必须先通过相同24查询、8路并发校准并逐实例准确，才能比较同能力成本。

入口为 `run_observation_ablation.py`，使用全新build与两应用回归目录，依次执行
`calibrate`、`run`；正式参数沿用五轮、预热30秒、窗口60秒、2请求/秒、并发2、
每容器1核/768MiB。每次独立部署并随机策略顺序，冻结源码/输入/构建/镜像哈希，
逐轮保存CPU/RSS、在线延迟、事件类别/字节、快照字段数、钩子计数、离线墙时与峰值
内存、答案等待、独立真值和unknown。缺失内部证据的boundary不能冒充同准确率方案。
校准和运行中均检查除了策略与输出目录外没有部署差异。

## 严格消融五轮结果（2026-10-15）

测量代码固定于 `5836f0a`，所有数字来自本轮新部署。原业务JAR、六份模型和计划与上一版相同，
采集器增加boundary策略，离线依赖规则不变。两应用回归仍为198/198、31/31，FP/FN0。
五轮内随机策略顺序；预热30秒、采样60秒、2请求/秒、并发2；每容器1核/768MiB。
15次部署共2700次业务请求均通过。full与selective各900/900查询准确、TP3750、FP/FN0；
boundary为900个unknown、TP0、FP0、FN3750，按缺失能力控制报告，不参与同准确率收益比较。

| 五轮中位数 | full | selective | boundary控制 |
| --- | ---: | ---: | ---: |
| 在线p50 ms | 14.335 | 13.612 | 13.166 |
| 在线p95 ms | 19.710 | 18.190 | 18.461 |
| 在线p99 ms | 25.122 | 22.309 | 25.432 |
| 三个业务JVM CPU单核% | 7.862 | 8.725 | 8.523 |
| 三个业务JVM RSS均值MiB | 1538.95 | 1540.30 | 1532.09 |
| 采集事件数 | 26988 | 5298 | 3720 |
| 采集字节MB（十进制） | 10.933 | 4.042 | 3.432 |
| 离线还原/评分/导出总秒 | 2.081 | 0.628 | 0.497 |
| 离线进程墙时秒 | 2.199 | 0.712 | 0.574 |
| 离线进程CPU秒 | 2.180 | 0.698 | 0.561 |
| 离线峰值RSS MiB | 357.39 | 162.21 | 158.12 |
| 已知来源答案等待p95秒 | 62.868 | 61.348 | N/A |

同轮selective/full成本比中位数：事件 0.1963，字节 0.3697，
离线进程墙时 0.3309，离线CPU 0.3249，离线峰值 0.4539。
在线CPU比 1.0836；p95延迟比 0.9296。这些比值不等于分组中位数的比值。

本轮主要收益落在采集与离线端：事件减少80.37%、字节减少63.03%、离线墙时减少
66.91%、离线CPU减少67.51%、离线峰值内存减少54.61%。在线CPU的同轮比值中位数
反而增加8.36%（五轮有四轮更高）；p95延迟比中位数下降7.04%，但有一轮上升，需
结合逐轮范围解释，不能宣称所有在线资源稳定改善。三业务JVM的RSS接近。

三策略每轮都采集3,720条公共HTTP/JSON相关事件，边界字段覆盖经独立复核一致。
内部证据从full的23,268条降至selective的1,578条，减少约93.22%；内部字节从
7,491,221降至607,972，减少约91.88%。selective剩余采集字节约85%来自公共边界。
这些结果支持减少内部观测降低日志与离线处理代价，尚不能解释此前对MirrorTaint
全部在线优势的来源。boundary虽没有内部事件，但900个来源答案均unknown。

事件格式、边界字段覆盖与还原器保持一致，因此full/selective差异反映这套系统中观测策略改变的净效果。
不能把CPU差异全归因于JSON写出，也不能据此定量分解先前与MirrorTaint的全部在线差距。
边界控制只提供unknown结果，公共驱动保留的批次写出时间不代表已知来源答案可用。

逐事件字节分解见 `artifacts/observation-ablation-formal-20261015/observation-components.json`；
主报告为同目录 `results.md`，独立复核为 `independent-validation.json`；
可提交摘要为 `observation-ablation-20261015.json`。原始计时、资源、实例答案、unknown和输入全部保留。
