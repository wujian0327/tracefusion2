# TraceFusion 2

当前阶段：**面向微服务聚合 API 敏感数据暴露的动态数据溯源验证**。

当前验证主线：**静态候选依赖分析 + 自动选择 eBPF 观测位置 + 动态来源重建**。此前 HTTP 抓包、trace/span 和调用链基线保留为前期实验设施。

## 当前：Go 单函数循环待主机验证

新增零次、一次、两次和四次迭代，覆盖加工、重复覆盖与累积，共 24 次入口调用。复用已有 Go 适配器和动态循环重放核心，本地独立 ISA 测试通过；**普通 Go 编译和真实 eBPF 采集仍需运行新场景**。

```bash
git pull origin main
sudo env "PATH=$PATH" /usr/bin/python3 scripts/go_loop_provenance.py run
```

返回 `artifacts/go-loop-provenance-*.zip`。新增 7 项测试通过，1 项实际 Go 编译测试跳过；完整套件 91 项通过、3 项旧 HTTP 测试因环境禁止 socket 而阻止、3 项 Go 编译测试跳过。五个旧真实包共 1390 条事件、76 次调用的计划、BPF 和结果重放一致。详见 [Go 循环验证](docs/go-loop-provenance.md)。

## 已验证：Go 跨函数真实采集

新增普通 Go 的参数传递、返回值加工、重复调用覆盖和两个来源合并场景。复用已有跨函数依赖核心，额外观测 Go 栈保护值，拒绝实际进入扩栈/抢占慢路径的调用。**2026-10-03 用户主机 Go 1.25.4 / BCC 0.29.1 真实采集通过：72 个探针、364 条事件、12 次根调用、最大深度 3，动态字段来源 TP=16/FP=0/FN=0，原始事件重放一致。**报告丢失、提交、状态及内存读取错误均为 0。详见 [主机审计](docs/go-interproc-host-20261003.json)。

```bash
git pull origin main
sudo env "PATH=$PATH" /usr/bin/python3 scripts/go_interproc_provenance.py run
```

返回 `artifacts/go-interproc-provenance-*.zip`。完整测试 87 项通过、2 项真实 Go 编译测试跳过；旧 C/Go 四个真实包共 1026 条事件、64 次调用重放一致。详见 [Go 跨函数验证](docs/go-interproc-provenance.md)。

## 已验证：语言适配层与 Go 单函数

C 的调用约定、字段布局和执行身份策略已抽入语言适配器。此前三个真实 C 包共 964 条事件、52 次调用重新生成计划并重放，结果与重构前一致，不用重跑。

新增受限 Go 适配器，复用同一依赖重建核心。**2026-10-01 用户主机 Go 1.25.4 / BCC 0.29.1 真实采集通过：62 条事件、12 次调用、字段来源 TP=16/FP=0/FN=0，报告丢失、提交和状态错误均为 0。**重复挂接问题已修复；从原始事件重算的完整结果一致。详见 [Go 主机验证记录](docs/go-host-20261001.json)。该单函数版本当时本地测试 81 项通过、1 项因缺少 Go 编译器跳过；主机采集另行验证。

```bash
git pull origin main
go version
sudo env "PATH=$PATH" /usr/bin/python3 scripts/go_provenance.py run
```

无需 Docker；Go 编译器需在当前 PATH 中。脚本接受 Go 1.22–1.26 候选工具链，实际兼容性仍需验证。成功或失败请返回 `artifacts/go-provenance-*.zip`。首轮只测试固定字段、无内部调用的纯 Go 函数及一个固定在线程上的用户 goroutine，不声称支持一般 Go 运行时。详见 [语言适配层](docs/language-adapters.md)。

## 已验证：单函数循环与读取实例

验证循环加工、重复覆盖和多次累积，区分同一读取指令的不同执行实例。覆盖只保留最终来源，累积保留多个实际来源；覆盖零次、一次和多次循环。本地完整 72 项测试通过；**2026-10-01 用户主机真实采集通过：47 个探针、428 条事件、24 次入口调用，无报告丢事件或读取错误，字段来源与读取实例均匹配预期，离线重放一致。**

```bash
git pull origin main
sudo /usr/bin/python3 scripts/loop_provenance.py run
```

无需 Docker，沿用现有 BCC 环境。成功或失败请返回 `artifacts/loop-provenance-*.zip`。共 24 次入口调用，当前观测函数内全部指令，未证明低开销。详见 [循环验证](docs/loop-provenance.md)。

## 已验证：跨函数来源传播

在单函数闭环的基础上，新增自动发现直接调用、参数/返回值传播、栈暂存与恢复，以及同一辅助函数多次调用的上下文区分。本地 66 项测试通过；**2026-10-01 用户主机真实采集通过：81 个探针、448 条事件、12 次入口调用，无报告丢事件或读取错误，离线重放一致。**

```bash
git pull origin main
sudo /usr/bin/python3 scripts/interproc_provenance.py run
```

无需 Docker，沿用现有 BCC 环境。成功或失败请返回 `artifacts/interproc-provenance-*.zip`。本轮共 12 次入口调用，说明见 [跨函数验证](docs/interproc-provenance.md)。

## 已验证：单函数静动态最小闭环

先分析编译后二进制的控制流与字段读写依赖，自动生成观测位置，再通过执行路径、寄存器和内存证据筛选来源。四类受控场景覆盖分支选择、覆盖、源码指针选择及计算，共 16 次调用。支持范围是明确的无环原生指令子集。

```bash
git pull origin main
sudo /usr/bin/python3 scripts/hybrid_provenance.py run
```

沿用已有 BCC 环境，无需 Docker。成功或失败请返回 `artifacts/hybrid-provenance-*.zip`。开发端 60 项测试通过；**2026-10-01 用户主机真实采集通过：26 个探针、88 条事件、16 次调用，无报告丢事件或读取错误。**独立重建探针计划并重放结果一致；准确率仅针对本轮受控来源关系。详情见 [静动态验证说明](docs/hybrid-provenance.md)。

## 已验证：程序内部赋值的 uprobe 可观测性

在原生 C 机器指令处挂 eBPF 探针，验证敏感字段复制、同值普通字段复制和 XOR 变换。普通业务赋值函数没有加入日志、标签或探针调用。只支持明确的 x86-64 直线指令子集，不是通用语言无关污点追踪。

```bash
sudo apt-get install -y gcc binutils
git pull origin main
sudo /usr/bin/python3 scripts/uprobe_assignment.py run
```

不需要 Docker。仍需系统 Python BCC；成功或失败请返回 `artifacts/uprobe-assignment-*.zip`。**用户主机已实测通过：20 条指令事件、6 次赋值、无报告丢事件或内存读取错误，同值不同来源和 XOR 变换均通过检查。**离线重放完全复现结果；结论限于该受控原生 C 指令子集。见 [程序级赋值验证说明](docs/uprobe-assignment.md)。

## 前期：eBPF 网络数据记录与溯源候选验证

需要原生 x86-64 Linux、rootful Docker、Compose v2 和系统 Python BCC。Ubuntu/Debian 的依赖安装与范围说明见 [eBPF 验证说明](docs/ebpf-provenance.md)。

```bash
git pull
sudo /usr/bin/python3 scripts/sockshop_ebpf.py check
sudo /usr/bin/python3 scripts/sockshop_ebpf.py run
```

默认用独立项目 `tracefusion2-ebpf`、端口 **28080/28081** 运行 1 笔订单。保存原始 PCAP、HTTP 正文、字段候选图和采集质量检查。完成或失败都请返回 `artifacts/sockshop-ebpf-*.zip`。

**用户主机已完成首轮真实 eBPF 采集：217 个包、21 组 HTTP 请求响应，4 个目标字段均生成候选子图。**该次运行的正文和选定路径检查通过，但因采集器遗漏读取 BPF 分片计数，整体仍为 `incomplete`；计数读取已修复，等待重新实测。`capture_verified` 只表示选定 HTTP 采集检查通过，字段血缘准确率尚未测量。

## 既有实验状态

11 组件基础版已经通过一次用户主机订单验证。新增追踪版保留业务镜像，增加 2 个入口代理与 1 个采集器，共 14 个容器；用户回传的两笔重叠订单已通过调用图结构与路径覆盖检查；同时发现 queue-master 的 Docker worker 启动失败，尚不能作为无故障的完整配送基线。

## 前期：同步 HTTP 还原与评测

已有 ZIP 可以直接用于导出观测、运行时间基线和评分，无需重新部署：

```bash
python3 scripts/http_dataset.py /path/to/运行结果.zip --out artifacts/http-v1
python3 scripts/http_baseline.py artifacts/http-v1/algorithm-input --out artifacts/http-v1/prediction.json
python3 scripts/http_score.py --reference artifacts/http-v1/oracle/reference.json --prediction artifacts/http-v1/prediction.json --out artifacts/http-v1/metrics.json
```

算法仅读取 `algorithm-input/`，真值保存在 `oracle/`。当前输入是去除关联标识的 HTTP 插桩观测，尚不是独立抓包。
队列/worker 分支不参与本阶段 HTTP 评分，其原始 span 和运行错误继续保留。
详见 [HTTP 评测范围、数据格式与指标](docs/http-evaluation.md)。

## 前期：采集订单调用链

```bash
git pull
python3 scripts/sockshop_trace.py run
```

默认运行 2 个并发测试流程，按 `--scope synchronous-http` 检查订单 HTTP 分支，并自动导出 `http-evaluation/`。完整消息链和 worker 错误另存 `oracle/full-callgraphs.json`；`--scope full` 可恢复全链验收。
成功或失败都请返回 `artifacts/sockshop-trace-*.zip`。
第一次下载官方 Java agent 1.32.0，需要能访问 GitHub。

详细范围、命令、14 组件组成、结果解释及真值隔离见 [调用链采集说明](docs/sockshop-tracing.md)。

```bash
python3 scripts/sockshop_trace.py down
python3 scripts/sockshop_trace.py check
```

## 基础版：仅验证订单场景

需要 Docker Engine、Docker Compose v2 和 Python 3.9+。当前镜像固定为历史版本，并使用 `linux/amd64`；建议先在 x86-64 Linux 上运行。ARM 机器需要 Docker 支持 amd64 模拟。

```bash
git clone https://github.com/wujian0327/tracefusion2.git
cd tracefusion2
python3 scripts/sockshop.py run
```

脚本依次检查 Docker、拉取镜像、记录 registry digest、生成 digest 固定的 Compose 文件、启动 11 个组件、等待应用与配送消费者就绪，然后创建一个全新测试用户、地址、卡片与购物项，并调用原有前端的 `POST /orders`。

完成或失败都会输出 `RESULT BUNDLE: ...zip`。**把该 ZIP 发回即可**，其中包括本次订单响应、测试夹具、镜像信息和诊断结果。镜像拉取失败也会保留错误原因，不会自动换镜像或伪造成功结果。

默认端口只绑定本机：

| 端口 | 用途 |
| --- | --- |
| `127.0.0.1:18080` | 原有 Front-end HTTP 接口 |
| `127.0.0.1:18081` | Carts 数据初始化接口 |

端口冲突时先设置 `TF2_FRONT_PORT` / `TF2_CART_PORT` 环境变量。前端的商品浏览页面不属于裁剪场景，不应以首页能否完整展示判断部署成功。

```bash
# 停止本项目容器，保留测试数据库卷
python3 scripts/sockshop.py down

# 不需要 Docker 的静态检查与响应判定测试
python3 scripts/sockshop.py check
python3 -m unittest discover -s tests -v
```

运行会新增合成数据，不清空已有数据库；每次生成唯一用户。请使用本包创建的独立 Compose 项目，不接入真实用户数据。上游日志会记录合成卡号和本次随机测试账户信息，结果包只应用于本实验。

## 结果含义

`result.json` 中 `status: passed` 表示本次订单成功，并且客户、购物项、金额与夹具匹配。**它不表示漏洞已修复、不表示所有服务调用已采集，也不表示血缘重建正确。**

每个目标字段单独报告：

- `full_value_returned`：与合成源值完全相同。
- `last_four_only_or_masked`：仅后四位或前缀由掩码字符构成。
- `absent_or_empty`：字段不存在或为空。
- `different_value_needs_review`：返回其他值，需检查，不直接当作脱敏成功。

脚本额外检查原有 `GET /card` 的后四位预览，与 `POST /orders` 的卡片字段进行比较；不修改上游业务代码。地址与姓名的返回仅记录可见性，不自动认定为越权暴露。

## 文档与验证状态

- [当前跨函数来源传播验证](docs/interproc-provenance.md)
- [已通过主机验证的单函数闭环](docs/hybrid-provenance.md)
- [MirrorTaint、FlowDist 算法与 eBPF 边界](docs/mirrortaint-flowdist-ebpf-review.md)
- [已完成的程序内部赋值验证](docs/uprobe-assignment.md)
- [前期 eBPF 网络数据验证](docs/ebpf-provenance.md)
- [前期调用链采集范围](docs/sockshop-tracing.md)
- [原始场景与候选字段路径（字段级设计暂缓）](docs/sockshop-scenario.md)
- [部署配置](scenarios/sockshop/compose.json)（JSON 是 Compose 支持的 YAML 子集）
- [源码版本与镜像依据](scenarios/sockshop/sources.json)
- [本地验证记录](docs/validation.md)

Sock Shop 业务路径保持原样。单函数闭环已通过主机验证；当前用独立 C 夹具扩展到受控直接调用，尚未接入真实微服务字段传播。
