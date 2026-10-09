# 原始订单金额到支付参数：一次集成回归

状态（2026-10-09）：实现已加入；本地优化构建与 10 个 native 用例通过，7 个离线语义回归通过。**尚无这条整段路径的真实 eBPF 通过结果。**不把此前的 Sum 单函数结果当作本次业务集成结果。

这就是论文收尾协议中固定的那一条集成路径，不再单独发布 MultiplySlow 小实验。

## 运行

沿用之前跑通 Sum 的 Linux amd64、Go **1.25.4**、系统 Python/BCC 环境，无需 Docker。

```bash
cd ~/tracefusion2
git pull --ff-only origin main
sudo env "PATH=$PATH" GOPROXY=https://goproxy.cn,direct \
  /usr/bin/python3 experiments/checkout-payment-path/run.py run
```

若 Go 不在 sudo 的 PATH 中，加 `--go /usr/local/go/bin/go`；也可用 `--checkout` 指向干净的 Online Boutique v0.10.4 checkout。默认复用 `artifacts/online-boutique-v0.10.4`，版本和未跟踪 Go 文件均检查。

一次命令完成固定 10 个用例 × native/selected/all_branches/boundaries，最后打印整个结果 zip 的路径。只返回该 zip 即可；异常也会归档。采集器失败会提前停止并保留日志；来源不一致则保留用例结果，不静默删掉失败用例。

只构建/运行原程序而不加载 BPF：

```bash
python3 experiments/checkout-payment-path/run.py build
python3 experiments/checkout-payment-path/test_replay.py
```

`build` 成功只证明程序和夹具能运行、ELF/DWARF 可分析，不证明 BPF 加载或来源推断通过。

## 跟踪什么

调用原始 `checkoutService.PlaceOrder`。只加入测试入口和本机 gRPC 后端替身；`main.go`、`money.go` 不修改，不关闭优化，不复制业务金额算法。

- 起点：本次 `prepareOrderItemsAndShippingQuoteFromCart` 成功返回的运费、各商品 `Cost.Units/Nanos`。
- 中段：原始 PlaceOrder 的金额初始化、结构体拷贝、订单循环，以及实际的 MultiplySlow/Sum 嵌套调用。
- 终点：PlaceOrder 调用 `chargeCard` 时传入的 `amount.Units/Nanos`，尚未进入支付函数。

商品价格由本机 gRPC 替身返回，支付替身独立记录金额并验证算术值。独立来源真值使用预先固定的正价用例依赖表，不读取观察者的指令、计划或事件；推断先落盘，评估器随后才打开真值。推断不能使用用例名称、预期条目关系或预期输出。

不声称追到商品数据库、汇率计算内部、支付端接收字段，或已完成真实商店的跨服务溯源。已有双 Gin/OTel 的证据单独报告。

## 如何接通

`payment_adapter.py` 从 ELF 定位源边界、支付调用、原始函数的分支/间接访存/调用与返回位置。校验指令字节和 Money、OrderItem、CartItem、orderPrep 布局；手工 ABI 和运行时契约列在计划中。

`scripts/observed_copy_machine.py` 维护寄存器、每个动态调用的栈字节和内存字节的来源集合。MOV/MOVUPS 按实际读写复制来源；完整覆盖替换旧来源，32 位寄存器写入清除高位。间接访问通过该指令处的真实基址/索引快照绑定地址，**不通过数值相同猜来源**。未知字节不是常量空来源。

循环按已观测分支重放，每次调用创建独立帧。Sum 复用已有二进制路径模型，将局部 `l/r.Units/Nanos` 来源映射回调用者的实际来源集合。MultiplySlow 本身不使用“结果来自输入”的手写业务摘要，其拷贝和循环同样来自指令与事件。

事件按进程/G 绑定；栈状态按调用帧相对偏移保存，避免把线程 ID 或旧的物理栈地址当作数据身份。这是本实现的建模方式，**本轮 native 结果不构成自然线程迁移或栈增长的内核验证**；离线测试包含模拟的迁移事件。

输出的 `source_identity` 为进程、G、源返回事件；`origins` 中的字段路径相对该身份。`calls` 记录实际重放出的 Sum 输入/输出依赖及 MultiplySlow 的嵌套调用；`controls` 单列条件证据。不是完整程序的逐指令历史图。

## 对照与用例

`cases.json` 在首次主机采集前固定：0、1、8、32 项；数量 1/2/3；同价但不同条目；进位；准备失败；支付失败。支付失败时金额已交给支付调用，仍是有效来源查询；准备失败时未产生目标，单列为 `no_sink`。

| 策略 | 采集/推断范围 |
|---|---|
| native | 无 BPF，检查原始业务和独立夹具 |
| boundaries | 源快照、支付边界、PlaceOrder 完成；成功金额报告 unknown |
| all_branches | 调用方和 MultiplySlow 的分支、间接地址、调用边界；Sum 全部分支 |
| selected | 调用方与上一组相同；Sum 使用已有按来源区分选取的分支 |

**边界组尚未实现候选路径枚举或利用值约束的分析，因此其 unknown 不是“所有边界分析均不可能”的证据。**全部分支组也不是通用全程序污点系统。当前选择性收益仅来自 Sum 内，不声称已经自动精简整个 PlaceOrder 的最小观测集。

本地构建生成 106 个 selected / 114 个 all_branches 静态探针位置。动态事件数依赖循环和运行时路径，等待主机测量；静态位置数不能代替开销。每个事件结构为 208 字节，perf 允许对齐后的 212 字节样本，原始字节数单列。

`summary.json` 报告固定查询分母、集合完全一致率、确定覆盖率、错误确定归因、关系 TP/FP/FN、事件数与 perf 字节。边界组的未知回答不从查询分母排除，也不记为准确溯源。没有预测边时 precision 为 null；未知查询的真实边仍计 FN。保留每例推断、真值、原始事件与 BPF 源码。

缺失调用、错误 G、丢失计数、未知指令检查明确标为**离线故障注入**。不是额外真实内核运行。

## 仍有哪些边界

- 固定 Go/amd64 ABI；一个 PlaceOrder/进程，至多 32 项，源 Money 对象彼此不同，在金额区间内无未建模并发修改。源别名会拒绝确定归因。
- 未知指令/调用、证据不一致、内存读取或 perf 丢失使结果为 unknown/失败，不自动套用“全部参数参与”的摘要。无法检测所有违反假设的隐藏写入。
- runtime.newobject、gcWriteBarrierN、wbMove 使用显式运行时契约。gcWriteBarrier 的慢路径可破坏 SIMD，解释器会清除 X0–X14 状态；wbMove 本身执行指针屏障，真正的数据拷贝由后续已解释指令完成。
- Quantity 影响循环次数，作为控制信息记录；不会自动成为数值字段的显式数据来源。输出是字段依赖集合，不是每个数值的数学贡献比例。
- 这是正确性和采集量集成 runner。原生单请求时间仅作诊断；**论文协议中的配对预热、稳定负载 CPU/RSS/延迟实验尚未实现/运行**，不能用这些单次时间作性能结论。

本机只能完成 native 与离线语义检查，以及 C 语法/布局桩检查；没有 BCC 内核加载、附着与动态重放的本地实证。主机结果回来后先核验这条集成路径，不再默认扩语言、应用或函数场景。
