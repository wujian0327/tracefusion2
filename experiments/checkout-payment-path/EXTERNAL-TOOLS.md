# 外部工具接入与兼容性诊断

当前阶段：libdft64 最小接入已实现，原始传播库与适配器已用真实 Pin 3.20 SDK 编译通过。
首次主机诊断确认工具构建和 Pin 空工具执行 `/bin/true` 通过；
在 Go 目标构建前遇到旧 checkout 的 Git `dubious ownership` 检查，尚未执行 Go/Pin 来源查询。
现已将默认业务 checkout 移到外部实验独立目录，由当前普通用户克隆，不调整 Git 信任设置。
后续同一 `one` 用例已完成 native、nullpin 和 libdft64 三次业务执行；业务输出一致，但来源核验未通过。
原始候选标签只包含运费字段，漏掉商品价格字段；金额区间另观察到 `runtime.asyncPreempt.abi0` 的 `POPFQ`
未被上游指令分派器覆盖。包装器按约定返回 unknown。这两项事实尚不能证明同一个根因，不能通过忽略指令告警宣告成功。
新增逐字节标签跟踪已在主机执行，源字段打标正确，但运行时转换附近出现寄存器标签丢失，详见下方诊断。
当前受限开发环境不能执行 Pin 的 32 位启动器（`Exec format error`）；上述执行证据来自上传的主机结果。
新边界配置已对实际 Go 1.25.4 支付 ELF 完成指令字节/DWARF 核验，单个 `one` 原生夹具运行通过。
编译成功、模拟日志检查、已有 BPF 正确性结果均不等于外部工具复现成功。

## 固定版本与比较语义

- 外部工具：[AngoraFuzzer/libdft64](https://github.com/AngoraFuzzer/libdft64)，提交 `20804d5bae5d8aed31a71761b1a1149e35a0da95`。
- Pin：官方 `pin-3.20-98437-gf02b61307-gcc-linux`，下载包和两个可执行文件以 SHA256 固定。
- 目标：既有原始 Online Boutique v0.10.4 支付夹具，Go 1.25.4/Linux amd64、GOAMD64=v1。
- 来源：准备结果中 shipping、每个 item.Cost 的 Units/Nanos；目标：chargeCard 金额的 Units/Nanos。
- 每个来源字段独立标签，分别覆盖 8/4 字节；在源返回后打标、支付调用前读标签集合，不用数值相等判断来源。
- 沿用直接数据依赖语义；数量和分支的控制影响不混进数值来源。

应称为“基于该 libdft64 移植版本的动态污点基线”，不能称为原始 libdft 论文工具的完整复现。
`external_boundaries.py` 只提取调用位置、验证 ELF 字节和 DWARF 字段布局；不调用生产选择器或来源推断器。
源边界、Go 寄存器 ABI、不可变且不同的源对象仍是显式配置与契约。初始版本只接受 ET_EXEC。

`libdft_payment.cpp` 只设置来源、读取目标及记录诊断；链接固定提交的原始传播库，不修改传播规则。
没有启用示例 `hook_file_syscall()`，因此不会额外把网络/文件输入当作本次来源。
原始来源日志解析完成后，Python 才读取夹具真值比较。

## 当前为什么不能做性能表

1. 上游 `bdd_tag.h/.cpp` 明确标有多线程支持 TODO，使用全局可变 BDD；Go 运行时的线程安全尚未核验。
2. 上游指令分派器默认跳过未覆盖 opcode。适配器记录目标 G 在金额区间执行的未列出 opcode，并拒绝把该次结果当作匹配。
   列出了 opcode 也不代表所有操作数形式都正确；部分指令被明确忽略，EFLAGS 不追踪。仍需实际传播审计。
3. 适配器拒绝观测到的目标 G 线程迁移、调用方栈地址变化；这不是通用协程/栈迁移支持。
4. 默认给所有指令插入诊断回调，成本很高。该配置仅用于兼容性调查。

适配器自身日志锁不保护上游所有传播操作，不能据此宣称解决了并发问题。
即使来源集合恰好与真值一致，报告仍保持 `external_baseline_qualified=false`、`performance_eligible=false`。
不关闭 Go 抢占、GC 或强制单线程来悄悄改变比较条件；原有相关环境变量记录在结果中。

## 先运行一个既有用例

以下命令保留用于复现。当前首例兼容性调查已经得到明确阻塞证据，无需重复运行相同配置或扩展十用例。

在已有 Linux 主机、Go 1.25.4、git、make、g++ 和 Python 3.12 环境中：

```bash
cd ~/tracefusion2
git pull --ff-only origin perf/payment-steady-state
GOPROXY=https://goproxy.cn,direct \
  python3 experiments/checkout-payment-path/external_compare.py run
```

无需 sudo/BPF。默认自动下载固定 Pin 和检出固定 libdft64 到 `artifacts/external-tools/`，不安装系统软件。
若已有工具，可传 `--pin-root /absolute/pin-kit --libdft /absolute/libdft64`；版本/源码改动检查仍保留。
Go 不在 PATH 时加 `--go /usr/local/go/bin/go`。默认业务 checkout 为 `artifacts/external-tools/online-boutique-v0.10.4`，
与旧 sudo/BPF 实验的 checkout 分开；可用 `--checkout` 指向当前用户拥有的干净 checkout。
需要 Intel 下载域和 GitHub 可访问；工具下载、编译、启动或执行失败都会保存阶段与日志并生成 zip。

默认仅运行既有 `one` 用例，顺序是：工具构建 → Pin 空工具启动 `/bin/true` → 构建原始夹具 → native → nullpin → 来源适配器。
任一步失败立即停止，返回最后打印的 zip。这个顺序用于诊断，绝不是随机化稳态性能比较。
每次日志包含源字段标签、目标集合、边界次数和结束记录；崩溃、缺日志、未知指令、来源不符不会被删去当成功。

仅在首例接入问题解决后，用 `--all-cases` 验证外部工具对既有十用例的语义；不新增场景，不重跑旧 BPF 正确性实验。
最终性能比较还需要解决上述限制、去除诊断回调，并分别核算 native、Pin 运行时、传播、来源/目标适配和报告成本。
应同时保留我们的 selected 和 boundary_replay，不能只挑弱控制组。

## 定位首例的来源标签丢失

```bash
GOPROXY=https://goproxy.cn,direct \
  python3 experiments/checkout-payment-path/external_compare.py run --trace-flow
```

仍然只运行既有 `one`，不关闭异步抢占、不改变 libdft64 传播规则，也不放宽 unknown 检查。
附加 `flow.jsonl` 记录源字段打标后的逐字节回读，以及指定原始函数执行前的寄存器/内存标签。
函数范围为 PlaceOrder、MultiplySlow、Sum、IsValid、asyncPreempt；指令集合从 ELF 全量提取，不读取生产选择器。
内存记录是当前指令执行前的状态，不能当作写后状态；每个内存操作数最多记录 32 字节，原始宽度同时保留。
标签以库内部节点号逐字节保存，完成时输出对应来源区间字典；上限 12000 条指令，超限明确拒绝。
这些额外记录只用于定位，不能生成性能结论。它们可能改变调度，因此下一次结果不保证复现同一次抢占位置。
新增诊断代码已用真实 Pin SDK 编译通过，诊断 PC 已对原始 Go ELF 校验；跟踪现已完成实际 Pin 运行。

## 标签跟踪结果与停止条件

2026-10-10 的 `one` 诊断中，native、nullpin、libdft64 均正常结束，业务金额一致。
上传包的五份适配器源码与提交 `96d27b7` 一致；离线核对 ELF 摘要、990 个诊断位置的指令字节，
并检查 1014 条执行前指令记录的连续性与日志结束标志。以下是来源正确性诊断，不是性能结果。

- 运费 Units/Nanos、商品 0 Units/Nanos 的每个字节均成功回读到各自独立标签。
  商品标签随后确实进入 `MultiplySlow` 的 R10/R11 参数寄存器，排除了“源字段没有打标”这一解释。
- 第 379→380 条记录从 `Sum` 的 RET 到 `runtime.asyncPreempt.abi0` 入口。
  R10/R11 数值保持不变，运费标签却已为空；这个丢失发生在 `POPFQ` 执行之前。
- 第 528→529 条记录位于 `MultiplySlow` 栈检查的 JBE 与其跳转目标之间。
  R10/R11 数值保持不变，商品标签变为空。JBE 本身不写这两个寄存器，上游分派器也不为 JBE 插入标签更新。
- 本次支付边界原始 Units/Nanos 标签集合均为空；包装器返回 unknown，仍记录一个未覆盖 opcode 种类。
  上次无流诊断的候选结果仅保留运费，说明不能把某次丢失位置或候选集合当作稳定结果。

这些记录证明当前接入存在标签状态连续性缺口，不能证明 JBE、RET 或 POPFQ 是丢失的唯一原因。
跟踪只覆盖指定函数，没有信号进入/返回记录；两个相邻记录之间仍可能发生未记录的信号或运行时活动。
数值不变仅用于描述丢失位置，绝不用于推断或恢复来源标签。

固定上游实现把影子寄存器保存在按 OS 线程索引的 `threads_ctx[tid].vcpu.gpr` 中，
初始化代码未注册 `PIN_AddContextChangeFunction`，也未实现信号上下文寄存器标签保存/恢复。
因此，信号/上下文恢复造成真实寄存器与影子标签不同步是符合证据的解释，但尚未被当前日志唯一证实。
仅把 POPFQ 加入允许列表无法修复已发生的标签丢失。

当前结论限定为：**固定 libdft64 原始传播库加本边界适配器，尚不能在原始 Go 支付首例中提供可信来源结果。**
停止扩大用例和性能比较，不把兼容性失败计为本方法的正确率或性能胜出。
继续接入需要单独开展信号上下文、Go 调度/栈行为及并发标签状态的适配与验证；届时应明确称为修改后的移植基线。

可在不执行上传二进制的情况下复查已有流诊断包：

```bash
python3 experiments/checkout-payment-path/inspect_external_flow.py /path/to/checkout-external.zip
```

该脚本检查 ELF 指令字节、源标签逐字节回读、步骤连续性和完成标志，报告 R10/R11 在分支/返回附近的标签丢失。
它不是完整传播验证器，不观测日志以外的上下文活动，也不会将外部基线标记为可做性能比较。

## 本地可复查的检查

```bash
python3 experiments/checkout-payment-path/external_compare.py build-tools \
  --pin-root /absolute/pin-kit --libdft /absolute/libdft64
python3 -m unittest discover -s experiments/checkout-payment-path -p test_external_compare.py
```

第二条只检查合成日志的完整性、来源身份和错误结果拒绝，明确不算 Pin、内核或来源传播正确性证据。
构建输出保存原始工具源码、适配器源码、命令日志、依赖提交、二进制摘要以及主机只读信息。

## HardTaint 与其他候选

[HardTaint 最终发表版](https://seg.nju.edu.cn/uploadPublication/copyright/125-753442135.pdf) §4.2 使用 Intel PT/PTWRITE，
§7.3 明确有单机双进程版本。因此不能把双机/RDMA一概写成不可避免的最低要求。
[官方实验包](https://zenodo.org/records/13117983) 已定位，尚未下载解包、编译或运行；单机入口是否可用仍待确认。
本脚本记录 CPU flags、intel_pt 设备、perf 权限的可读信息，但不执行 PT 测试，不把这些信息当作 HardTaint 兼容性结论。
下一步需确认主机 PT/PTWRITE 暴露、作者单机入口、Go ELF 重写、同一字段多来源查询语义。

[SelectiveTaint 的 64 位问题报告](https://github.com/OSUSecLab/SelectiveTaint/issues/2) 尚未解决，暂排后面；
该报告不构成“所有 amd64 程序均不支持”的证据。
