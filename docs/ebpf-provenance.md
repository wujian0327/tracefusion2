# eBPF 运行时数据记录与字段传播验证

本轮验证路线是：**eBPF 采集 → 保存通信数据 → 离线恢复消息 → 构建字段传播候选图**。
不添加字段传播埋点，不要求给业务字段写入来源编号。它不是 MirrorTaint 或 FlowDist 的复现，也尚不是完整的论文算法。

## 首轮实现与真实边界

- 采集机制：BCC 加载 `BPF.SOCKET_FILTER` 程序，挂到独立 Docker bridge 的 AF_PACKET 观察 socket。eBPF 按实验服务 IPv4 地址与 HTTP 端口筛选数据包；用户态把收到的原始帧立即追加到 PCAP。
- 这是真正的 eBPF 过滤采集，不是把 tcpdump 或现有 span 输出改名。不使用 kprobe/uprobe/LSM，也不采集变量赋值。过滤器丢弃的只是观察 socket 的副本，不改变业务流量。
- 使用原来的 11 个业务、存储和队列组件，独立项目名 `tracefusion2-ebpf`，端口 **28080/28081**。不加载本仓库此前新增的 Java agent、Node hook 或 Go 入口代理。上游镜像本身包含的库照常保留。
- 只采集明文 IPv4 TCP HTTP/1.x，服务端口 80/8079。数据库、RabbitMQ、TLS、HTTP/2、IPv6 暂不支持。当前购物车/订单场景的正常 HTTP 请求是验证对象。
- 捕获范围包含整个合成测试流程，因此 PCAP 含注册账号口令、会话 cookie、测试卡号等原始内容；只在本脚本的专用合成实验网络执行，不接入真实业务。

## 环境与运行

在 **原生 x86-64 Linux、rootful Docker Engine、Compose v2** 主机上执行。不要在 Docker Desktop、远程 Docker context 或 rootless Docker 环境运行首轮原型。

Ubuntu/Debian 上可安装 BCC 及匹配当前运行内核的头文件（包名随发行版可能不同）：

```bash
sudo apt-get update
sudo apt-get install -y python3-bpfcc bpfcc-tools libbpfcc-dev clang llvm linux-headers-$(uname -r)
```

使用系统 Python；不要 `pip install bcc`，那个名字可能指向其他项目。

```bash
git pull
sudo /usr/bin/python3 scripts/sockshop_ebpf.py check
sudo /usr/bin/python3 scripts/sockshop_ebpf.py run
```

`check` 检查 Python/BCC、root、Docker 命令及当前用户能否运行 `docker compose version`，**不代表 eBPF 已经加载成功**。`run` 才会实际编译、加载、挂接探针。缺少内核功能、头文件或权限时，会记录失败原因，不退回其他采集方式。

默认执行 **1 笔订单、并发 1**，先排查采集正确性。它不会停止原来的 `tracefusion2-sockshop` 项目，也不会清空数据库卷。服务保持运行，方便检查。

完成或失败均输出：

```text
RESULT BUNDLE: .../artifacts/sockshop-ebpf-日期-编号.zip
```

**把这个 ZIP 发回即可。**由 sudo 启动时，脚本会将结果目录和 ZIP 的所有权归还调用用户。ZIP 默认权限为 600。

第一轮通过之后再增加并发：

```bash
sudo /usr/bin/python3 scripts/sockshop_ebpf.py run --requests 4 --concurrency 2
```

每次重新发现容器 IP 和网桥，保存镜像 digest 与采集代码校验和。capture 默认最多 300 秒、64 MiB 原始帧；达到上限会报告不完整，不会当作成功。需要时可显式增加：

```bash
sudo /usr/bin/python3 scripts/sockshop_ebpf.py run --capture-seconds 600 --max-mib 128
sudo /usr/bin/python3 scripts/sockshop_ebpf.py down
```

`down` 仅停止该独立项目，不删除卷。自定义 `--project` 后，停止时也要传同一个项目名。

### Compose troubleshooting

如果报 `docker: unknown command: docker compose`，表示执行脚本的用户无法使用 Compose CLI 插件。先分别执行：

```bash
docker compose version
sudo docker compose version
```

如果仅第一条成功，插件可能只安装在普通用户的 `~/.docker/cli-plugins`，sudo 后不可见；应使用系统级安装。只有 `docker-compose`（带连字符）可用也不满足当前脚本要求，脚本没有切换到旧版 Compose v1。

Ubuntu/Debian **已经配置 Docker 官方 apt 软件源**时，安装方式为：

```bash
sudo apt-get update
sudo apt-get install -y docker-compose-plugin
sudo docker compose version
```

如果找不到该软件包，不要卸载已有 Docker。按 [Docker 官方 Compose 插件安装说明](https://docs.docker.com/compose/install/linux/) 配置适合发行版的软件源，或使用其系统级手动安装步骤；系统级手动路径为 `/usr/local/lib/docker/cli-plugins`。不同发行版仓库的包名可能不同。

确认 `sudo docker compose version` 成功后，重新运行 `check` 和 `run`。前置检查只读取 Compose 版本，不安装软件、不修改 Docker 配置。

## 保存的信息

| 文件 | 含义 |
| --- | --- |
| `capture/packets.pcap` | eBPF 过滤后的原始帧，可用 Wireshark 查看 |
| `capture/capture.json` | eBPF 类型、过滤范围、收包数、socket 丢包、分片与采集上限状态 |
| `capture/recorder.log` | BCC 编译、内核加载和采集错误 |
| `services.json` | 容器服务与 IPv4 地址映射、Docker 网络和网桥身份 |
| `analysis/transactions.json` | TCP 重组后的 HTTP 请求响应、JSON 正文、字段证据所在的包编号 |
| `analysis/field-graph.json` | JSON 字符串字段的发送/接收观测节点和两类边 |
| `analysis/queries.json` | 从订单响应目标字段反向检索出的候选子图 |
| `analysis/summary.json` | 重组问题、消息数、边数、已观测查询终点 |
| `capture-validation.json` | 独立客户端响应与抓取正文的一致性及选定路径覆盖检查 |
| `workload/` | 合成测试夹具、客户端响应；不用于生成候选依赖边 |
| `queries-input.json` | 已知暴露响应的订单 ID，仅用于选择查询终点 |
| `result.json` | 最终阶段、错误与验证状态 |

原始载荷立即写入文件；HTTP 消息和字段图在停止采集后离线生成。事件/字段观测 ID 仅用于证据库索引，不会写回业务字段。

## 重组与关联规则

1. 保存 TCP SYN/FIN 和所有数据段，不只捕获带 HTTP 头的包。利用序列号重组、去重重传，支持乱序到达及序列号回绕。
2. 按 TCP 连接代次区分端口重用；缺少 SYN、存在字节缺口或重传内容冲突时拒绝恢复该连接。
3. 支持 Content-Length、chunked（含 trailer）和 gzip；保持连接内按 HTTP/1.x FIFO 配对，跳过 100 等临时响应。数量不一致时不猜配对。
4. HEAD、close-delimited 响应和其他未实现的编码会产生显式问题。不会从不完整正文补造字段。
5. 图包含长度至少 3 的 JSON 字符串叶字段；本轮没有实现数值来源、隐式流或格式转换识别。

节点是某条 HTTP 消息某个字段的发送/接收侧观测，边有两类：

- `wire_transfer`：同一条已捕获通信消息的两端，依据为包编号。表示观察到了线上传输，不证明接收程序实际使用了该字段。
- `candidate_exact_value`：服务收到与随后发送的字段内容一致，且存在兼容的入站请求时间区间。是**候选依赖**，并非真实赋值证据。索引用 SHA-256，建立候选时再检查原值相等。

第二类边用的是粗粒度请求区间约束，没有线程/协程归属证据。并发请求、同值重复读取可能保留多个候选；不选择一个武断的“唯一来源”。原始头信息保留在证据中，本轮匹配算法不使用 trace/header 标识。不能把区间包含作为执行级因果真值。

目标查询为 `card.longNum`、`card.ccv`、`address.street`、`customer.firstName`。结果只追到可观测接口；不会把 User 的 HTTP 响应延伸成未采集的 MongoDB 文档读取。

## 如何看结果

`capture_verified` 仅表示：订单业务完成，采集器正常停止且未报告 socket 丢包/分片，重组无已知问题，最终订单正文与独立客户端响应相符，选定的 Orders 下游 HTTP 分支与卡片读取被观察到。

它**不是字段血缘正确率，也不是无遗漏证明**；整条连接完全未被观察到，未必能从 TCP 序列号发现。并发时，下游覆盖检查的区间约束也不是请求归属真值。准确率保持 `null`，不能将候选边数量当成恢复正确数。

既有 queue-master 后续 Docker worker 缺少 socket 的问题保留在容器日志中；本实验没有修复它，也不宣称完整配送成功。RabbitMQ 分支不参与该 HTTP 验收。

## 离线重跑与验证状态

分析既有目录不需要 root、BCC 或 Docker：

```bash
python3 scripts/sockshop_ebpf.py analyze --out artifacts/sockshop-ebpf-日期-编号
python3 -m unittest discover -s tests -v
```

本次开发环境完成了 TCP/HTTP 合成数据包回放和图查询测试，包括乱序、重传、缺失、chunked、同值来源、并发候选和失败状态检查。**开发环境没有 Docker、BCC 和可用的 eBPF 编译条件，尚未验证内核程序实际加载、网桥可见性和真实 Sock Shop 流量。**用户主机运行是首轮实测，不是复现已经完成的结果。

## 方法参考

- BCC socket filter 示例：https://github.com/iovisor/bcc/tree/master/examples/networking/http_filter
- MirrorTaint：https://lingming.cs.illinois.edu/publications/icse2023d.pdf
- FlowDist：https://www.usenix.org/system/files/sec21-fu-xiaoqin.pdf

本轮借鉴服务边界记录及分阶段分析思路；没有实现论文的运行时污点传播或静态依赖细化。原始证据持久化后，可在下一轮引入更强的局部关联与转换证据。
