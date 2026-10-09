# 固定金额路径的配对性能协议

工具状态：已实现 Python 计量/归档入口及 Go 连续请求驱动；本地协议、重放与统计测试通过。当前开发环境无 Go/BCC，**新驱动的实际 Go 构建、主机 eBPF 采集与正式性能结果仍待核验**。旧正确性 runner 保持原样，不需单独重跑十个用例。

## 一次主机命令

在已有 Go 1.25.4、Linux amd64、系统 Python/BCC 的主机，进入本仓库后运行：

```bash
sudo env "PATH=$PATH" GOPROXY=https://goproxy.cn,direct \
  /usr/bin/python3 experiments/checkout-payment-path/performance.py run
```

可用 `--go /usr/local/go/bin/go`、`--checkout /path/to/clean/upstream`、`--output /path/to/new/result`。输出目录必须不存在。构建、布局或采集失败都会保存 `failure.txt` 和已有诊断并打印 ZIP 路径；不继续运行剩余块，也不从失败中挑选成功测量作正式汇总。请返回最后打印的完整 ZIP。

默认冻结协议：固定八个商品、每项数量二、同价不同对象、正常正价；同一个优化二进制、原始 PlaceOrder/money 代码及本机 gRPC 后端替身。四种策略为 native、boundaries、all_branches、selected；每块打乱四组顺序，保存随机种子及实际顺序。十个配对块，每组同一进程内预热二十次、测量一百次串行请求。总计四十个目标进程、4,800 次调用（其中测量 4,000 次），三十次 BPF 编译/挂载。native 不启用 BPF，但使用完全相同的业务、真值检查和阶段门控。

每组另启一个全新的采集进程，避免前一组 BCC/离线重放的 Python 堆影响本组 RSS；不在每个请求重新编译/挂载。现有外部探针与 G 作用域复用，入口—完成事件逐次分组；每次重放建立新堆/调用状态，来源身份包含源返回事件。只支持**同时至多一个、完整返回的串行 PlaceOrder**，不新增并发性能或一般运行时覆盖主张。

原有 checkout 并未新增 OTel SDK；四组使用同一原始配置。所谓公共 trace 条件一致，不应写成已经部署了完整商店 OTel。

## 计量口径

| 指标 | 实际测量范围 |
|---|---|
| 延迟 | Go 单调时钟包围每次原始 PlaceOrder 调用；同进程与连接完成预热。p50/p95 使用每块一百个样本的 nearest-rank；不报 p99/饱和吞吐 |
| 目标 CPU | Go `getrusage(RUSAGE_SELF)` 在测量循环前后取差；包括业务、同进程 mock 后端、公共夹具检查和上下文管理；不能称为纯业务或真实远端后端 CPU |
| 采集进程 CPU | Python 自身 user/system CPU 差；从释放测量门到收到完成标记，包含 perf 轮询、原始样本写入和 RSS 采样；结束后 drain 单列。排除编译/挂载、离线推断与 JSON 导出 |
| RSS | 测量窗口 `/proc/PID/status` 的 VmRSS 时间戳样本及观测峰值；轮询至多十毫秒等待，但事件唤醒可使间隔缩短。这是采样峰值，不是精确峰值，也不是包含初始化的 VmHWM |
| 事件/字节 | 全局提交/读取/丢失计数检查后，按完整调用切分。只汇总一百次测量请求；原始 perf 回调 size 求和，包含对齐、不含外层 perf header 或新增归档帧头 |
| 离线成本 | 原始样本解码、串行分组分别计时；逐调用推断计时，测量请求与预热分开。排除独立真值评估、JSON 文件写入；不相加冒充应用延迟 |
| 部署成本 | target launch、每组 BPF 编译及 attach 各自 wall time；统一 target 构建/布局/计划时间另存。部署阶段的编译子进程 CPU 不混入在线采集 CPU |

RSS 不可获取时为 null，并保留原因；任何块缺测的指标不以其余块替代完整十块中位数。没有内核全局 BPF 内存/CPU 计量，也没有把 perf 样本字节称为全部系统内存。

所有延迟原始值保留，汇总同时提供各块 p50/p95、各块内相对 native 的比值、配对比值中位数，以及 selected/all_branches 的块内对比。块中位数之比与配对比值中位数分别解释；负开销保留。十块不足以直接宣布统计显著或一般生产环境优势。

## 正确性与证据

所有预热和测量调用都接受独立支付金额检查。BPF 三组还逐调用重放；推断保存后才读独立来源真值。selected/all_branches 要求来源集合完全一致；boundaries 仍允许本模型的 unknown，但必须保留正确输出、完整事件和全部查询分母，不能将其记为成功溯源。

丢失/提交/读取错误、时间顺序冲突、跨 G 配对、缺失开始或完成、必要内部证据缺失、错误来源均阻止性能汇总。失败查询的推断和评估保留；不把 unknown 从分母排除。不为长跑出现的新障碍默认扩大指令集或业务范围。

ZIP 包含：

- `protocol.json`、`schedule.json`、`source/`：实际工具源码、版本/工作区状态、二进制/业务源哈希、协议和硬件信息；二进制及三种计划也保留。
- `trials.jsonl`、`summary.json`：逐组资源/延迟/正确性，以及完整块的配对汇总。
- 每组 `samples.bin`：小端 CPU/size 帧头及原始 perf 样本；`capture.json` 保存计数、实际 size、RSS 样本和部署/采集成本。
- 每组 `inference.jsonl`、`evaluation.json`：按完整源返回—完成事件分组的逐请求结果，包含预热和测量；两阶段指标分开。
- `measurements.json`、`truth.json`、目标 stdout/stderr、采集进程 stdout/stderr、采集器 C 和命令日志。

本机无 BCC 但有固定 Go/依赖时，可先检查构建、native 连续驱动及门控：

```bash
python3 experiments/checkout-payment-path/performance.py build --warmups 2 --requests 3
python3 -m unittest discover -s experiments/checkout-payment-path -p 'test_*.py' -v
```

`build` 不执行 BPF，也不生成四组性能结论。更改 blocks/warmups/requests/seed 的 run 保留数据，但 `frozen_protocol=false`；不能混作默认正式结果。原始正确性归档继续独立报告，本次工具实现不产生新的性能收益数字。
