# TraceFusion 2

## 当前研究范围与下一步

主线固定为：**无需修改应用源码或离线重写可执行文件，通过二进制分析与选择性运行观测，重建跨服务输出字段的实际来源依赖。**先完成范围适中、证据完整的论文，再由结果决定投稿目标。部署便利、正确性和运行成本分别评价。

下一里程碑是 Online Boutique 原始订单函数的局部来源重建：优先适配默认优化产物，绑定输入对象、调用返回与输出条目，再进行独立真值和主机 BPF 验收。**目前已实现默认优化二进制的对象候选图及未知栈副作用的保守失效处理，尚未完成精确别名/调用摘要、对象类型绑定或真实函数 BPF 溯源。**详见 [研究范围与验收标准](docs/research-scope.md)、[对象图实现](docs/checkout-object-graph.md) 和 [副作用处理及 26 项本地测试](docs/checkout-stack-effects.md)。

继续提取了两个真实 gRPC 客户端的 [接收者访问摘要](docs/checkout-receiver-summary.md)：识别接收者字段读取及下游指针加载链，39 项本地测试通过。摘要仍带别名条件，没有据此取消保守主图中的未知标记，尚未新增 BPF 验收结果。

## 真实 Go 函数审计：Online Boutique 订单条目

固定 v0.10.4 的原始结算函数，完成默认/关闭内联构建与六组本地 gRPC 夹具检查。确认需要绑定动态对象与 RPC 返回实例，当前四字节叶函数模型不能直接覆盖；这不是现有强基线的失败证据。尚未对该函数执行 TraceFusion BPF 溯源，详见 [真实函数审计及研究边界](docs/checkout-origin-audit.md)。

## 当前对比：来源观测策略与独立方法基线

新增来源集合、路径敏感分析与当前自动策略的公平对比，复用双 Gin / OTel 场景与相同采集器。五个固定四字节场景的本地构建、机器码来源和 HTTP 检查已通过。两个关联分支场景于 2026-10-08 通过真实 BPF 主机验收，确认路径敏感基线与当前策略探针和来源结果一致、没有额外观测节省，见 [对比方法、负结果与核验记录](docs/gin-provenance-comparison.md)。

## 当前待主机验收：双 Gin 服务与 OpenTelemetry

使用 OpenTelemetry SDK、otelgin 与 otelhttp 生成真实调用 span，导出本地 JSONL；外部来源分析复用现有赋值/覆盖核心，核对两端收发与解码证据后拼接来源图。六个目标的探针计划和真实 HTTP/SDK 测试已通过，新版本 eBPF 采集尚待主机验证。运行方法与明确边界见 [双服务 OTel 实验](docs/gin-otel-provenance.md)。


当前阶段：**无需应用重写的跨服务动态字段来源重建验证**；敏感输出来源审计作为应用方向。

当前验证主线：**静态候选依赖分析 + 自动选择 eBPF 观测位置 + 动态来源重建**。此前 HTTP 抓包、trace/span 和调用链基线保留为前期实验设施。

## 已验证：Gin 默认调度下的自然并发

新增默认运行时调度场景：请求不固定线程，不设置 `GOMAXPROCS`，没有辅助迁移 goroutine、阶段汇合或人为延时。保留相同业务和真实 `c.JSON`，完整复用已验证的 G/请求采集状态。

**2026-10-03 默认调度场景真实 eBPF 采集通过：892 条事件、28 个请求、36 次计算、56 次读取，来源关系 TP=28/FP=0/FN=0。**观察到最多 4 个请求重叠，使用 7 个线程；31 对请求的重叠同时通过时间戳和全局事件顺序核对。默认调度条件满足，原始事件推断与评估完整重放一致，全部客户端正文匹配，报告丢失、提交、状态及读取错误均为 0。见 [汇总核验](docs/gin-default-host-20261003.json)。

**本轮没有观察到请求中途自然换线程。**它验证了当前业务在默认调度下的自然并发溯源；线程迁移由下面独立的受控实验验证，两者不混为一次覆盖。

```bash
git pull --ff-only origin main
sudo env "PATH=$PATH" GOPROXY=https://goproxy.cn,direct \
  /usr/bin/python3 scripts/gin_default_provenance.py run
```

本轮已通过，无需重跑；以上命令用于复现，输出 `artifacts/gin-default-provenance-*.zip`。详见 [默认调度场景与验收范围](docs/gin-default-provenance.md)。固定字段、显式 JSON 摘要和关闭内联的限制仍保留。

## 已验证：Gin 请求内线程迁移

新增不固定请求线程的 Gin 场景，采集状态通过实际 G 地址与请求实例接续；同一线程可先后承载多个请求，原始线程号始终保留。测试主动诱发读取之间、计算到 JSON 之间的迁移，要求 28 个请求都提供实际换线程证据，不能只凭响应正确判定通过。

**2026-10-03 固定版本场景的真实 eBPF 迁移采集通过：892 条事件、28 个请求、36 次计算、56 次读取，输出来源关系 TP=28/FP=0/FN=0。**28 个请求均观察到读取之间、计算到 JSON 之间的线程变化；原始事件重建与评估完整重放一致，全部客户端正文匹配，报告丢失、提交、状态及读取错误均为 0。见 [主机核验](docs/gin-migration-host-20261003.json)。

调度夹具使用 `GOMAXPROCS(1)` 和占用旧线程的辅助 goroutine；请求自身不调用 `LockOSThread`。本包没有出现单次计算函数执行中途迁移，不据此声称覆盖该时机、一般调度、子 goroutine 传播或性能。此前 6 个旧主机包共 4270 条事件完整重放一致。

```bash
git pull --ff-only origin main
sudo env "PATH=$PATH" GOPROXY=https://goproxy.cn,direct \
  /usr/bin/python3 scripts/gin_migration_provenance.py run
```

本轮已通过，无需重跑；以上命令用于复现，输出 `artifacts/gin-migration-provenance-*.zip`。详见 [迁移身份、覆盖门槛与边界](docs/gin-migration-provenance.md)。

## 已验证：Gin 并发请求状态隔离

新增每批 4 个、共 28 个并发请求，输入对象和采集状态按请求隔离。通过阶段同步确保请求交错，并使用独立评估对应表匹配客户端请求；不依赖发送/完成顺序或 JSON 值配对。仍保留请求内 `LockOSThread`，线程迁移和子 goroutine 传播暂缓。

**2026-10-03 真实 Go 1.25.4 / Gin 1.11.0 / BCC 0.29.1 并发采集通过：892 条事件、28 个请求、36 次计算、56 次读取，输出来源关系 TP=28/FP=0/FN=0。**7 批均确认 4 个请求范围实际重叠，原始事件重建及评估完整重放一致，全部客户端正文匹配；报告丢失、提交、状态和读取错误均为 0。相同数值的不同读取位置正确区分，线程复用后状态正确重置。该结果限于本轮固定线程的受控场景，见 [主机核验](docs/gin-concurrent-host-20261003.json)。

```bash
git pull --ff-only origin main
sudo env "PATH=$PATH" GOPROXY=https://goproxy.cn,direct \
  /usr/bin/python3 scripts/gin_concurrent_provenance.py run
```

本轮已通过，无需重跑；以上命令用于复现，输出 `artifacts/gin-concurrent-provenance-*.zip`。详见 [并发场景、身份匹配和验证范围](docs/gin-concurrent-provenance.md)。

## 已验证：真实 Gin Web API 串行场景

新增普通 Go 结构体 + `c.JSON` 的 `GET /account/summary`。自动发送 14 个串行请求，连接文件读取、业务计算、标准库 JSON 序列化和 Gin 响应写入。覆盖双来源加工、常量覆盖、同值换源、0/UINT32_MAX，以及连接复用和新建连接。

**2026-10-03 真实 Go 1.25.4 / Gin 1.11.0 / BCC 0.29.1 采集通过：446 条事件、14 个请求、18 次计算、28 次读取，输出来源关系 TP=14/FP=0/FN=0。**原始事件重建及评估完整重放一致，14 个客户端正文均一致；报告丢失、提交、状态和内存读取错误均为 0。见 [主机核验](docs/gin-api-host-20261003.json)。当前只支持固定 `balance` uint32 字段和显式 JSON 摘要，不声称完整跟踪框架或支持一般并发。

```bash
git pull --ff-only origin main
sudo env "PATH=$PATH" /usr/bin/python3 scripts/gin_api_provenance.py run
```

本轮已通过，无需重跑；以上命令用于复现。固定 Go 1.25.4，首次构建需要下载依赖，无需 Docker。输出整个 `artifacts/gin-api-provenance-*.zip`。详见 [Gin 场景、运行方法与边界](docs/gin-api-provenance.md)。

## 已验证：JSON 标准输出来源验证

新增 C 场景，连接真实文件读取、计算加工、显式 JSON 序列化规则与成功的 stdout `write`。业务输出为 `{"value":…}`，测试真值在范围外单独写入 stderr。覆盖常量覆盖、同字节 JSON 缓冲区换源、写入失败以及 0/UINT32_MAX。**2026-10-03 修正版真实 BCC/eBPF 采集通过：500 条事件，22 条实际 JSON 输出，输出来源关系 TP=21/FP=0/FN=0。**原始事件完整重放一致，361 字节 stdout 与成功写入记录及独立预期完全相同；报告丢失、提交、状态与内存读取错误均为 0。见 [主机核验](docs/json-output-host-20261003.json)。

```bash
sudo /usr/bin/python3 scripts/json_output_provenance.py run
```

返回 `artifacts/json-output-provenance-*.zip`。场景包含 25 次计算、42 次读取、24 次格式化、23 次写入尝试和 22 条成功 JSON 输出。序列化使用明确的 uint32 规则，尚未逐指令分析 libc 或支持任意 JSON。旧 C/Go 读取场景不用重跑。详见 [JSON 输出模型、真值与范围](docs/json-output-provenance.md)。

## Go 真实文件读取来源适配

使用 `syscall.Pread`，复用 C 的读取实例、字节版本和来源绑定核心，保持 18 次计算、34 次读取尝试的同一组场景。新增 syscall 边界的实际 goroutine 身份采集，以及 Go 工作负载入口/RET 指令挂接。**2026-10-03 真实 Go 1.25.4 / BCC 0.29.1 采集通过：400 条事件、18 次计算、34 次读取，字段与精确读取来源均 TP=18/FP=0/FN=0；原始事件完整重放一致。**报告丢失、提交、状态和内存读取错误均为 0，见 [Go 读取主机核验](docs/go-read-provenance-host-20261003.json)。

```bash
git pull origin main
sudo env "PATH=$PATH" /usr/bin/python3 scripts/go_read_provenance.py run
```

返回 `artifacts/go-read-provenance-*.zip`。完整套件 124 项通过、5 项因缺少 Go 编译器跳过、3 项旧 HTTP 测试受环境 socket 权限阻止；九个旧真实包共 4378 条事件、166 次调用重放一致。旧实验不用重跑。详见 [Go 读取接口、适配条件与验证](docs/go-read-provenance.md)。

## 已验证：C 真实文件读取来源


将预先放好的输入字段推进到真实 `pread64` 返回：区分文件、偏移和读取实例，再接入已有加工/调用依赖图。覆盖同值异源、合并、缓冲区覆盖、失败和 EOF，共 18 次计算入口、34 次读取尝试。**2026-10-03 真实 BCC/eBPF 采集通过：316 条事件、18 次计算入口、34 次读取尝试，字段来源与读取操作来源均 TP=18/FP=0/FN=0，完整原始事件重放一致。报告丢失、提交、状态和读取错误均为 0。**详见 [主机核验记录](docs/read-provenance-host-20261003.json)。

```bash
git pull origin main
sudo /usr/bin/python3 scripts/read_provenance.py run
```

本轮已验证完成，以上命令保留用于复现，输出 `artifacts/read-provenance-*.zip`。读取发生在计算根函数之前，文件不可变且输入只由 pread 写入；Go 读取已由上方新入口验证，尚未接入数据库或网络输出。完整套件 117 项通过、4 项 Go 编译测试跳过、3 项旧 HTTP 测试受环境 socket 权限阻止；八个旧真实包共 4062 条事件、148 次调用重放一致。详见 [读取边界与验证范围](docs/read-provenance.md)。旧实验不用重跑。

## 已验证：C / Go 循环中的函数调用


新增 C、Go 两套普通源码夹具，共用动态调用栈和循环重放逻辑。每种语言验证零/单/多次迭代、覆盖、累积及三层嵌套调用，共 24 次根调用。**2026-10-03 修复后真实采集通过：C 940 条、Go 1276 条事件，各 24 次根调用，字段来源各 TP=22/FP=0/FN=0。报告丢失、提交、状态和内存读取错误均为 0，原始事件完整重放一致。**已核查重复调用实例、覆盖消除、累积贡献及三层父子关系；见 [重跑审计](docs/loop-calls-host-retry-20261003.json)。

```bash
git pull origin main
sudo /usr/bin/python3 scripts/loop_calls_provenance.py run
sudo env "PATH=$PATH" /usr/bin/python3 scripts/go_loop_calls_provenance.py run
```

返回 `artifacts/loop-calls-provenance-*.zip` 和 `artifacts/go-loop-calls-provenance-*.zip`。修复后完整套件 113 项：106 项通过，4 项 Go 编译测试跳过，3 项旧 HTTP 测试受环境 socket 权限阻止。本次两个真实二进制也分别通过独立模拟。本轮已经验证完成，无需再次运行；以上命令保留用于复现。详见 [循环与调用共用核心](docs/loop-calls-provenance.md)。

## 已验证：Go 单函数循环真实采集

新增零次、一次、两次和四次迭代，覆盖加工、重复覆盖与累积，共 24 次入口调用。复用已有 Go 适配器和动态循环重放核心。**2026-10-03 用户主机 Go 1.25.4 / BCC 0.29.1 真实采集通过：41 个探针、456 条事件、24 次调用，字段来源 TP=22/FP=0/FN=0，原始事件重放一致。**报告丢失、提交、状态及读取错误均为 0。详见 [主机审计](docs/go-loop-host-20261003.json)。该旧入口仅覆盖单函数；循环调用由上方新入口验证。

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

- [当前 Gin 并发请求状态隔离验证](docs/gin-concurrent-provenance.md)
- [已通过主机验证的 Gin 串行 Web API 来源](docs/gin-api-provenance.md)
- [已通过主机验证的 JSON 标准输出来源验证](docs/json-output-provenance.md)
- [已通过主机验证的 Go 真实文件读取来源](docs/go-read-provenance.md)
- [已通过主机验证的 C 文件读取来源](docs/read-provenance.md)
- [已通过主机验证的 C / Go 循环与函数调用](docs/loop-calls-provenance.md)
- [已通过主机验证的跨函数来源传播](docs/interproc-provenance.md)
- [已通过主机验证的单函数闭环](docs/hybrid-provenance.md)
- [MirrorTaint、FlowDist 算法与 eBPF 边界](docs/mirrortaint-flowdist-ebpf-review.md)
- [已完成的程序内部赋值验证](docs/uprobe-assignment.md)
- [前期 eBPF 网络数据验证](docs/ebpf-provenance.md)
- [前期调用链采集范围](docs/sockshop-tracing.md)
- [原始场景与候选字段路径（字段级设计暂缓）](docs/sockshop-scenario.md)
- [部署配置](scenarios/sockshop/compose.json)（JSON 是 Compose 支持的 YAML 子集）
- [源码版本与镜像依据](scenarios/sockshop/sources.json)
- [本地验证记录](docs/validation.md)

Sock Shop 业务路径保持原样。C / Go 单函数循环与无环跨函数场景已通过主机验证；循环中的直接调用也已通过真实采集，尚未接入真实微服务字段传播。
