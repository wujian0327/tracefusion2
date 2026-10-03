# Go 真实文件读取来源适配

## 当前状态与运行

新增 Go 文件读取入口，复用 C 已验证的 `read_boundaries.py`：读取返回字节的版本、字段来源绑定、覆盖和反向依赖图没有另写 Go 规则。场景与 C 一致：**18 次计算、34 次读取尝试，九类行为各运行两个偏移轮次。**

**2026-10-03 修正版在 Go 1.25.4 / BCC 0.29.1 主机真实采集通过：400 条事件、18 次计算、34 次读取尝试，完整原始事件重放一致。**字段来源和精确读取来源均 TP=18/FP=0/FN=0，报告丢失、提交、状态和内存读取错误均为 0。开发环境没有 Go 编译器；对上传的真实 Go ELF 另做了独立指令执行，作为额外核查。

```bash
cd ~/tracefusion2
git pull origin main
sudo env "PATH=$PATH" /usr/bin/python3 scripts/go_read_provenance.py run
```

无需 Docker，沿用当前 Go、binutils 和系统 Python BCC。成功或失败都返回 `artifacts/go-read-provenance-*.zip`。已经通过的 C 文件读取和旧 C/Go 场景不用重跑。

## 首次主机运行与修复（2026-10-03）

上传包 `go-read-provenance-20261003-150416-50d4.zip` 在采集阶段失败，收到 0 条事件。Go 编译成功，但 BCC 0.29.1 报 `use of undeclared identifier 'args'`。[BCC 官方宏](https://github.com/iovisor/bcc/blob/v0.29.1/src/cc/export/helpers.h) 中普通 `TRACEPOINT_PROBE` 的参数名为 `args`，`RAW_TRACEPOINT_PROBE` 的参数名为 `ctx`；生成的 raw 回调误用了前者。

修复只修改两个 raw 回调中的上下文引用，保持原有参数解码和来源推断。原本本地 C++ 测试壳也将 raw 宏错误声明成了 `args`，掩盖了缺陷。现在测试宏与 BCC 官方定义一致：修正测试后旧生成代码编译失败，修正生成器后通过。定向 C/Go 读取测试共 18 项，17 项通过，1 项因本地无 Go 编译器跳过。这个测试仍不代替 BPF verifier 和实际加载。

对上传的真实 Go ELF 复核了二进制/源码哈希、仓库场景一致性、指令与范围计划；用该 ELF 的计算函数配合独立 Python 真实文件读取和 Unicorn 执行，与原生 C 真值比较，18 次计算、34 次读取来源正确。此处 400 条事件是测试构造的，**不是失败主机包采到的事件**。诊断与验证记录见 [首次主机报告](go-read-provenance-host-20261003-attempt1.json)。

## 修正版主机核验通过（2026-10-03）

包 `go-read-provenance-20261003-150644-1291.zip` 对应实现 `2217d929c7de48963a565ee823ecfd414f4fc961`，状态为 `ebpf_checks_passed`，目标进程正常退出。

- 50 个计算指令探针、2 个范围指令探针；400 条事件包含 330 条计算事件、34 对读取进入/返回事件、2 条范围事件。
- 34 次读取中，28 次返回 4 字节、4 次返回 EBADF、2 次返回 EOF；18 次计算全部符合独立真值。
- 同值的两个文件可以区分；合并保留两个来源；覆盖保留最后一次读取；同文件不同偏移及同偏移重复读取可以区分；失败和 EOF 不创建新字节版本；常量回退没有外部来源。
- scope、syscall 和计算事件中的实际 R14 均为同一个非零 G，kernel pid_tid 也一致。运行器 PID 与内核 TGID 不同，按范围入口学习内核身份的策略正常工作。
- 核对二进制/源码哈希、场景源码、从实际 ELF 重建的指令及范围计划、生成 BPF、运行时地址、探针挂接记录和文件快照。由完整原始事件重新推断/评分，与包内完整 JSON 一致。
- 另以实际 Go ELF 的计算函数、Python 真实 pread 和 Unicorn 独立执行得到相符结果；主机程序真值与原生 C 独立真值一致。这部分模拟事件与主机真实采集分别记录。

详见 [Go 读取主机核验记录](go-read-provenance-host-20261003.json)。字段与读取来源的准确率仅适用于本轮固定字段场景；没有据此测得完整图边准确率、通用 Go 程序覆盖率或开销。文件已由场景正常清理，文件身份核对基于捕获的 `/proc` 快照，未重新 stat 已删除文件。

## Go 读取接口及数据范围

本轮选择 `syscall.Pread`。已核实 Go 1.25.4 官方代码：

- [`syscall.Pread`](https://github.com/golang/go/blob/go1.25.4/src/syscall/syscall_unix.go) 调用平台实现 `pread`。
- [Linux amd64 实现](https://github.com/golang/go/blob/go1.25.4/src/syscall/zsyscall_linux_amd64.go) 使用 `Syscall6(SYS_PREAD64, ...)`。
- [系统调用汇编](https://github.com/golang/go/blob/go1.25.4/src/internal/runtime/syscall/asm_linux_amd64.s) 转换到 Linux syscall ABI：fd 在 DI、缓冲区在 SI、长度在 DX、文件偏移在 R10；不能套用 Go 函数入口的参数寄存器位置。

文件内容为相同的两个 uint32 记录，采用 little-endian。通过 `unsafe.Slice` 为固定全局输入结构体中的字段提供 4 字节视图，直接传给 `syscall.Pread`；没有来源标签或业务探针调用。**这个字节视图是明确的实验适配条件，不代表已支持任意 Go 切片、字节解码、对象移动或字符串传播。**固定全局缓冲区避免把可迁移的 goroutine 栈地址用作跨读取的持久来源键。

沿用同值异源、两来源合并、缓冲区覆盖、同文件换偏移、EBADF、EOF、常量回退及重复读同值的九类场景。Go 标准接口在失败时返回 `n=-1` 和 errno，内核事件保存原始负 errno；EOF 返回 0 且不产生新来源。实际读操作次数仍需真实事件验证，不能只凭接口名称认定。

## 采集适配与共同核心

计算目标继续使用 `go-amd64-u32-calls`、已有 Go 栈保护解码，以及共用机器指令/调用栈引擎。文件身份快照、读取进入/退出配对、字节版本及外部来源评分均复用 C 实现。

Go 采集端额外处理两点：

1. **工作负载范围**：在 `main.runWorkload` 栈检查的正常分支入口处挂 uprobe，结束处在实际 RET 指令上挂 uprobe。不使用 uretprobe，不改写 Go 返回地址。未知栈检查形式会在构建阶段拒绝。计算根函数中真正进入扩栈/抢占慢路径仍拒绝；不把工作负载边界选择当成一般 Go 运行时支持。
2. **执行身份**：保留 `runtime.LockOSThread`，并在 SIGSTOP 恢复后先 `runtime.Gosched`。读取使用 `raw_syscalls` 对应的 raw tracepoint `sys_enter` / `sys_exit`，从实际保存的用户寄存器读取 R14。读取进入、返回、范围边界和计算指令都核查同一个非零 G，不能只验证 OS 线程，也不能把入口 G 复制到之后的读取事件冒充实际观测。

只采集 PID 限定的工作负载入口所学习到的内核 TID，并筛选 pread64 与已有的 fd 失效操作 close/dup2/dup3。原始 syscall 回调解码参数后调用共用读取载荷处理逻辑；perf 提交仍传入真实 tracepoint context。寄存器读取失败进入状态错误，不能静默变成干净采集。

新增 `read-scope-plan.json` 保存范围入口/RET 偏移；`read-boundary-attachments.json` 记录实际范围挂接和 raw tracepoint 策略。推断和评分文件格式沿用 C；额外身份校验通过语言适配器对完整事件流执行，C 默认行为保持不变。

## 验证证据

新增 8 项测试：**7 项通过，1 项实际 Go 编译测试因无编译器跳过**。

- 独立 Go ABI 汇编夹具经 GCC 汇编、Unicorn 执行，配合 Python 实际 `pread` 文件操作构造事件流。18 次计算、34 次读取的结果与原生 C 独立真值一致，读取来源 TP=18/FP=0/FN=0。
- 修改 syscall、scope 或计算事件的 G，丢失读取事件、部分覆盖、未知 fd、计算证据缺失或栈保护读取错误，均无法通过。
- 范围挂接测试确认使用正常分支入口和 RET 指令，未调用 `attach_uretprobe`；未知栈保护形态拒绝。
- 将实际生成的 raw 回调 C 代码放入本机测试壳，验证 DI/SI/DX/R10 参数、带符号 fd/返回值、真实 context 传递、每次重新读取 R14、读取失败及 syscall 类型不符处理。测试壳模拟 BPF helpers/maps，**不是内核 verifier 或真实挂接测试**。

完整套件 132 项：124 项通过，5 项真实 Go 编译测试跳过，3 项既有 HTTP 测试被当前环境的 socket 权限阻止。九个旧真实包共 **4378 条事件、166 次计算调用**，重新生成计划并重放完整推断/评分，均与原包一致；C 读取 BPF 源码也保持一致。见 [旧包回归](go-read-regression-20261003.json)。

修正版 raw tracepoint 已在本次主机运行中加载成功，syscall 边界取得的 G 身份与计算事件一致。此结论限于本轮固定线程/goroutine 条件；其他程序仍需验证。失败会保留完整诊断包，不自动降级为只按线程关联。

## 边界

仍要求文件预先只读打开且内容不可变、缓冲区仅由被观测的 pread 写入、读取发生在计算根函数之前。没有接入 `os.File.ReadAt` 的额外封装语义、数据库、网络输出、并发 goroutine 或一般堆/栈迁移。来源图展示显式数据依赖，本轮不声称完整图边准确率或低开销。
