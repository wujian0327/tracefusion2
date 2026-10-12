# Sock Shop / MirrorTaint：真实 API 接入预检

2026-10-12。用户确认先做 Sock Shop，再做 PiggyMetrics。**当前没有本场景的字段准确率。**
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

公开 JAR 的 `TaintCollector.collect` 两个重载中，记录分组键来自
`SimpleDateFormat("hhmmss MM-dd")`，不是这里可见的 Sleuth Trace ID 获取。
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

## 主要来源

- [作者原版部署](https://github.com/MirrorTaint/MirrorTaint/blob/54fcbfc5bb3a0d7cd30309098355d999553a861b/Benchmarks/microservices-demo-mt.yml)
- [OrdersController](https://github.com/microservices-demo/orders/blob/e97ec6530811c92babbcb4227cf2d77896b5c26d/src/main/java/works/weave/socks/orders/controllers/OrdersController.java)
- [ItemResource.merge](https://github.com/microservices-demo/carts/blob/d0a55c9f483269034ab9f2473c1a738b2d7d422b/src/main/java/works/weave/socks/cart/item/ItemResource.java)
- [ItemsController.addToCart](https://github.com/microservices-demo/carts/blob/d0a55c9f483269034ab9f2473c1a738b2d7d422b/src/main/java/works/weave/socks/cart/controllers/ItemsController.java)
- [MirrorTaint 论文](https://lingming.cs.illinois.edu/publications/icse2023d.pdf)
