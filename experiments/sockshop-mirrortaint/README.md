# Sock Shop / MirrorTaint：真实 API 接入预检

2026-10-12。用户确认先做 Sock Shop，再做 PiggyMetrics。**正式准确率资格尚未完成；2026-10-13 已完成五方法的选定字段校准与首轮开销测量，见文末。**
这一步冻结原版业务、查询契约和外部 agent，准备真实服务的 API 负载；不把预检当成来源还原。

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
