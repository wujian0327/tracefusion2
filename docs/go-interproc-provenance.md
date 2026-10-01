# Go 跨函数动态来源验证

## 状态与运行

新增普通 Go 场景及受限调用适配器。**本地通过独立汇编/Unicorn 验证；本地没有 Go 编译器或 BCC，新的 Go 编译、探针挂接和真实采集仍待用户主机验证。**此前通过的 Go 单函数结果不能替代此项。

```bash
cd ~/tracefusion2
git pull origin main
sudo env "PATH=$PATH" /usr/bin/python3 scripts/go_interproc_provenance.py run
```

成功或失败均返回 `artifacts/go-interproc-provenance-*.zip`。无需 Docker。只构建检查可把 `run` 换成 `build`，构建通过不代表内核采集通过。使用本地 Go 工具链，关闭 cgo 和实验包内联，保留普通优化和 Go 自带栈检查；不添加 `nosplit`，不在目标函数内写来源标签。

## 场景

输入 `secret` 和 `public_value` 故意同值，两个数值轮次、两个选择参数、三个入口，共 12 次根调用。主程序独立计算数值及预期来源，只在评分阶段读取真值。

| 入口 | 函数关系 | 预期来源 |
| --- | --- | --- |
| `goCallSelect` | 根函数 → `transformSelected` → `readSelected`，返回后 XOR，再写输出 | 随分支选公共或敏感字段；两种选择输出值相同，来源不同 |
| `goCallOverwrite` | 两次调用同一个 `readSelected`，依次写入输出 | 只保留后一次公共字段来源 |
| `goCallMerge` | 经 `transformSelected` 读取敏感字段并加工，再读公共字段，相加 | 保留两个来源 |

验证指针/标量参数、单个 uint32 返回值、栈中保存的参数和中间值、三层调用，以及重复 helper 的调用点上下文。不扩展到数据库或微服务部署。

## 实现与栈检查

`language_adapters.py` 新增 `go-amd64-u32-calls`，沿用 Go 参数寄存器与固定 goroutine 身份规则，声明根入口返回地址以上 32 字节的参数保存区，以及 R14+16 的栈保护值位置。此布局有版本限制。

`go_interproc_provenance.py` 识别栈检查并根据直接调用目标发现应用 helper。业务函数名仅用于入口配置及符号定位，不承载来源答案。`interproc_model.py` 复用已有 C 跨函数 CFG、候选路径枚举、符号依赖和机器状态核对；参数边、返回边、覆盖消除与反向切片使用同一算法。

Go 为寄存器参数保留栈上的保存空间，本轮允许有界正向栈偏移。只有实际写入过的槽位可参与符号读取，仍拒绝部分重叠、未建模读取和根返回地址写入。采集器仅为新适配器扩大栈快照并记录 guard；旧 C 和 Go 单函数事件格式与 BPF 保持不变。

只识别 `CMP RSP,[R14+16]; JBE slow` 和先以 `LEA R12,[RSP-N]` 计算比较地址的变体，并用符号表核实慢路径包含 `runtime.morestack_noctxt.abi0`。其他形式明确拒绝。比较处有探针，保存实际 guard；模型重算标志位并核对分支。慢路径入口也挂拒绝探针：**进入扩栈/抢占慢路径的调用不产生成功来源结果**。不把 runtime 调用当 NOP，不声称恢复迁移后的栈。

慢路径入口之后的代码不进入受支持的候选路径，计划保留 `unsupported_runtime` 标记；完整反汇编另行保存。采集器保留错误证据，整包评估不能忽略失败调用。

## 验证与限制

本地完整测试 89 项：87 项通过，2 项真实 Go 编译测试因无编译器跳过。新增 ISA 测试由 GCC 汇编器生成 ELF，再用 Unicorn 独立执行；不是 Go 编译器输出，也不是内核 eBPF 验证。

覆盖参数及返回传播、重复调用覆盖、合并、两种栈检查、参数保存区，以及错误 guard、读取失败、缺失 guard、损坏栈/返回地址、漏事件和 G 身份变化。独立模拟真正走入慢路径时必须失败。

另重放 C 单函数、C 跨函数、C 循环和 Go 单函数四个真实包，共 1026 条事件、64 次根调用；重新生成的计划、BPF、完整推断和评分保持一致。见 [旧场景回归](go-calls-regression-20261001.json)。旧实验无需重跑。

范围限 Linux amd64、声明的 uint32 字段、固定用户 goroutine、无环直接调用、256 字节向下栈窗口和有界调用深度。只识别 `main.*` 应用 helper；拒绝递归、循环、间接调用、其他 runtime/外部调用、栈迁移、堆历史和并发修改输入。字符串、切片、多返回值高级类型语义与跨服务溯源不在本轮范围。

评分是调用的来源字段集合与输出值；图用于解释，不声称有完整图边或数据库读取实例真值。Go 1.22–1.26 只是候选工具链范围，不代表逐版本验证。

设计依据：[Go ABIInternal](https://go.dev/src/cmd/compile/abi-internal)、[Go 栈检查](https://go.dev/src/runtime/stack.go)。
