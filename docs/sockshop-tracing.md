# Sock Shop 订单调用链采集

## 范围与真值

当前目标收窄为：给定一次敏感响应，记录/重建与其关联的服务调用链。
先采集可核验的 trace/span 参考答案；暂不做字段来源编号、字段传播埋点、记录级归因或完整字段血缘图。
调用链上的服务不自动被解释为敏感字段的来源。

采用 W3C `traceparent`。每个测试客户端 HTTP 请求创建独立 trace 和 CLIENT span。
服务端、下游 HTTP 调用和消息操作创建自己的 span，保留 parent span ID。
不按时间接近、字段值相同或既定拓扑推断真值边。

## 运行

```bash
git pull
python3 scripts/sockshop_trace.py run
```

默认启动 2 个并发测试流程，每个流程使用独立客户、会话和购物车，均执行注册、创建地址/卡片、预置购物车、卡片预览、创建订单。只对最终的创建订单 trace 做路径覆盖验收；其他请求与健康检查的 span 也保留在原始采集中。

```bash
# 一个流程便于定位启动/传播问题
python3 scripts/sockshop_trace.py run --requests 1 --concurrency 1

# 扩大请求关联检查规模（不是性能基准）
python3 scripts/sockshop_trace.py run --requests 10 --concurrency 4

# 停止包括辅助组件在内的当前 Compose 项目，保留数据库卷
python3 scripts/sockshop_trace.py down
```

沿用 baseline 的 Compose 项目名 `tracefusion2-sockshop` 和 18080/18081 端口，切换时会重建相关容器。新增本机 18082 采集端口，可用 `TF2_TRACE_PORT` 改变。使用不同项目名同时运行时，也必须配置不同的三个宿主端口。

脚本下载官方 OpenTelemetry Java agent **1.32.0**，检查 JAR manifest 版本，记录实际 SHA-256；不是从 registry latest 动态选择版本。也可预先下载官方该版本，通过 `--agent-jar /absolute/path/opentelemetry-javaagent.jar` 指定。下载可能受 GitHub 网络影响，失败会生成诊断包，不会自动改用其他版本。该历史 agent 版本只用于兼容实验，与应用一样不是生产部署推荐。

## 组件与测量边界

原来的 11 个业务/存储/队列组件保留，增加 **2 个入口代理和 1 个采集器，共 14 个容器**。
这是增加观测后的部署，不再称为 11 组件部署。

| 部分 | 实现 | 测量范围 |
| --- | --- | --- |
| front-end | 预加载 Node 4 兼容 HTTP hook，利用 domain 隔离旧版回调上下文 | 入站 SERVER 与出站 CLIENT span |
| orders、carts、shipping、queue-master | Java agent 1.32.0；100% 采样；W3C 传播；Zipkin v2 JSON 导出 | Java HTTP、执行器上下文和 RabbitMQ producer/consumer |
| user、payment | Python HTTP 入口代理；原镜像改为 user-backend/payment-backend | 服务边界转发 span，明确标记 `tf2.observer=leaf-http-proxy` |
| trace-collector | 标准库 Zipkin v2 JSON 接收器 | 追加原始 span、提供快照，不生成推断边 |

user/payment 的 span **不是 Go 进程内部执行 span**，也不记录 Go→MongoDB 操作。Java Mongo 插桩关闭，本阶段不把数据库查询纳入验收范围。RabbitMQ 是消息通道，不伪造 broker 内部 span；验收 shipping producer 到 queue-master consumer 的上下文关联。

旧版应用内置 Sleuth 的日志 trace ID 不作为本轮答案：Java 配置关闭旧 Sleuth，使用独立 W3C 链路，避免将 B3 日志与本次采集混用。

代理会增加延迟；本阶段不据此报告无插桩系统的性能。Node hook 限于当前场景使用的 HTTP API，不宣称完整实现 OpenTelemetry Node SDK 或覆盖所有 Node 网络库。

## 验收与结果

每个订单需要满足：

- 客户、购物项、金额及响应内容通过原有 smoke 检查。
- 根 span 正确，所有记录到的子 span 都有父节点，无环、无冲突 ID。
- front-end→user/orders，以及 orders→user/carts/payment/shipping 的实际边存在。
- user 的客户、地址和卡片读取，以及 carts 的购物项接口被记录。
- queue-master 的 CONSUMER span 与 shipping 的 PRODUCER span 通过父链相连。
- 不包含另一测试客户/地址/卡片 ID 的请求路径。
- 分别报告结构检查和执行结果：缺失父节点等导致结构 incomplete；HTTP/应用错误记录在 runtime_errors，并使 execution_status=failed。

每个 HTTP 调用有独立 span，重复调用不合并。`service_edges` 只是便于查看的服务聚合视图；精细的调用实例边保存在 `span_edges`。

默认并发启动不保证两个 `POST /orders` 一定在时间上重叠；`overlapping_order_interval_pairs` 根据同一测试客户端时钟统计实际重叠。为 0 时不能宣称已经覆盖订单并发，应该提高请求数后检查。

`oracle/callgraphs.json` 中 `status=passed` 仅表示已采集记录满足上述结构一致性与覆盖检查，**不是数学意义上的无遗漏证明，也不是算法准确率**。固定预期边只用于发现缺口；不会写入观测图。缺失消息链、导出丢失导致的路径缺口或丢失父节点时保留 `incomplete`，不按业务拓扑修补。被正确记录的失败操作属于真实调用链，保留节点和父子边，单独标记 execution_status=failed；最外层 result.json 仍为 failed，不把业务故障改成成功。

输出 `artifacts/sockshop-trace-*.zip`，包括：

| 路径 | 含义 |
| --- | --- |
| `result.json` | 业务与采集验收总结果 |
| `oracle/orders.json` | 本次订单与客户端 trace/span 对应关系 |
| `oracle/spans-final.json` | 最后采集的原始 span 快照及实际客户端 span |
| `oracle/callgraphs.json` | 各订单 span、实际父子边、聚合服务边和缺口 |
| `oracle/raw/spans.jsonl` | 采集器接收日志；容器继续运行时会追加 |
| `requests/request-*/` | 每个测试用户的响应、夹具和客户端记录 |
| `images.json`、`agent.json`、`instrumentation.json` | 镜像摘要、探针校验和、采集代码校验和 |
| `compose.log`、`commands.log` | 启动、代理与 Java 导出诊断 |

诊断 ZIP 不包含约几十 MB 的 agent JAR，但本地运行目录会保留它供容器挂载。不要在容器停止前删除或移动本次运行目录。

所有 trace/span、客户端关联表、含 ID 的原始日志都是**真值/诊断数据**。后续评测不依赖 trace 的重建算法时，须另行导出移除 Header、日志、文件名及元数据中关联标识的输入；本提交没有把这些原始文件宣称为可直接使用的算法输入。

## 依据与状态

- [W3C Trace Context](https://www.w3.org/TR/trace-context/)
- [agent 1.32.0 支持的库](https://github.com/open-telemetry/opentelemetry-java-instrumentation/blob/v1.32.0/docs/supported-libraries.md)：Java 8 执行器、HTTP、RabbitMQ Client 2.7+、Spring RabbitMQ 1.0+。
- [agent 1.32.0 导出依赖](https://github.com/open-telemetry/opentelemetry-java-instrumentation/blob/v1.32.0/javaagent-tooling/build.gradle.kts)：包含 Zipkin exporter。
- [前端固定版本 Dockerfile](https://github.com/microservices-demo/front-end/blob/0.3.12/Dockerfile)：Node 4，工作目录 `/usr/src/app`。

用户结果包 `sockshop-trace-20260930-175156-cac0.zip` 已观测到两笔订单的实际 HTTP 与 RabbitMQ 上下文传播。分别有 31/34 个 span，结构与预期覆盖检查通过；queue-master 后续 Docker worker 操作失败。详见 [验证记录](validation.md)。不能据此称所有路径已覆盖或完整配送无故障。

## 离线复核已有结果包

```bash
python3 scripts/trace_validation.py /path/to/sockshop-trace-20260930-175156-cac0.zip
```

直接读取原 ZIP，不修改原始结果、不重新运行 Docker。输出结构 status、execution_status、runtime_errors、真实服务边和 span 数。结构不完整或存在运行错误时仍返回退出码 1。

已知部署缺口：queue-master:0.3.1 的 ShippingTaskHandler 在收到消息后无条件调用 DockerSpawner.init()/spawn()，尝试拉取 worker 镜像并通过 Docker socket 创建容器。本部署没有挂载该 socket，因此收到消息不等于 worker 已成功运行。本次报告修复只区分追踪结构与应用执行状态，没有修复该运行依赖，也没有隐藏或删除相关 span。

源码依据：[ShippingTaskHandler](https://github.com/microservices-demo/queue-master/blob/ca72773d51ca4676306e6c5f25835990f3753748/src/main/java/works/weave/socks/queuemaster/ShippingTaskHandler.java)、[DockerSpawner](https://github.com/microservices-demo/queue-master/blob/ca72773d51ca4676306e6c5f25835990f3753748/src/main/java/works/weave/socks/queuemaster/DockerSpawner.java)。
