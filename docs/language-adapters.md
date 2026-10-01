# 语言适配层与共用溯源核心

## 当前状态

已经抽出第一个 C 适配器，并接入受限 Go 适配器。**C 的既有真实采集结果已重放验证；Go 的真实编译与 BCC 采集尚待主机验证。**不能把两种参数约定的离线测试称为“Go 程序已跑通”。

本地没有 Go 编译器：完整测试运行 80 项，79 项通过，1 项实际 Go 编译测试明确跳过。新增的汇编夹具由 GCC/汇编器构建、Unicorn 独立执行，验证两种 ABI 边界可以使用同一个来源重建核心；它们不是 Go 编译器的输出。

## 分工

| 部分 | 文件 | 职责 |
| --- | --- | --- |
| 语言边界 | `scripts/language_adapters.py` | 参数/返回寄存器、字段布局、入口核查、执行身份与挂接线程策略 |
| 指令与依赖 | `scripts/interproc_model.py` | x86 指令语义、读写版本、参数/返回传播和依赖边 |
| 按执行顺序重放 | `scripts/loop_provenance.py` | 逐事件验证 CFG、生成执行版本并反向提取最终来源 |
| eBPF 采集 | `scripts/interproc_provenance.py` | 按适配器读取边界，保存同一事件格式 |
| 实验基础设施 | `scripts/hybrid_provenance.py` | 构建、进程管理、ELF 映射、挂接、评分与打包 |
| Go 编译入口 | `scripts/go_provenance.py` | 编译纯 Go 夹具、调用共同的计划/推断/采集核心 |

Go 入口没有另写覆盖或合并来源的规则，也不按业务函数名写传播答案。当前共同的数据语义是寄存器/内存定义和依赖图；还不是完整的跨语言高级语义 IR，也没有通用库函数传播摘要。

`NativeAdapter` 声明 ABI、入口三个参数的位置、返回寄存器及保留寄存器；`FieldLayout` 提供字段名字、偏移和大小；`ExecutionPolicy` 提供上下文验证、分组和挂接策略。适配器可报告不支持，不能通过“忽略运行时调用”让结果成功。

旧配置不含 `adapter` 时默认使用 `c-sysv-u32`，原有 C 命令继续有效。新增 `adapter.json` 保存实际选择的边界。当前两个适配器都只接受连续 uint32 字段，声明字符串或任意布局不会自动获得支持。布局由编译期大小/偏移断言核查，尚未实现自动 DWARF 类型恢复。

## C 重构回归

重新读取此前三个实际运行包，共 **964 条真实事件、52 次调用**：

| 实验 | 事件 | 调用 |
| --- | --- | --- |
| 单函数 | 88 | 16 |
| 跨函数 | 448 | 12 |
| 单函数循环 | 428 | 24 |

逐包校验 ELF 哈希，从 ELF 重新生成探针计划；生成的 BPF 源码、映射基址、完整推断 JSON 和评估 JSON 均与原包一致。审计记录见 [adapter-refactor-host-replay-20261001.json](adapter-refactor-host-replay-20261001.json)。旧 C 实验无需重跑。

编译期 C 布局断言也由适配器提供的布局生成。旧版单函数分析器保留为回归基线，已改用同一 C 边界配置；Go 首轮使用后续的逐事件重放核心。

## Go 首轮运行

```bash
git pull origin main
go version
sudo env "PATH=$PATH" /usr/bin/python3 scripts/go_provenance.py run
```

`PATH` 保留用于使 sudo 找到同一个 Go 编译器。成功或失败返回 `artifacts/go-provenance-*.zip`。如尚未安装 Go，脚本会生成缺少工具的失败包；不要为此重装 BCC 或 Docker。

运行器接受 Go 1.22–1.26 候选工具链，记录真实 `go version`；这不代表该范围逐版本通过了实测。Linux amd64、关闭 cgo、标准库夹具、不下载模块、使用本地工具链。关闭本实验包的函数内联以保留观测边界，保留默认优化及调试信息，构建 PIE。未加入 `//go:nosplit`，不会为了通过而跳过 `morestack`。

Go 的 `go tool nm -size` 以十进制输出符号大小，由单独的解析器处理。共同 ELF 映射器支持首个加载段虚拟地址非零的布局，同时核查所有观测点位于可执行映射；没有把 C PIE 的零链接地址假设带入 Go。

三个普通 Go 函数覆盖分支选源和 XOR、覆盖、两个来源合并。两个数值轮次、两个选择参数，共 12 次入口调用。输入字段故意同值。测试主程序独立计算输出及预期来源，推断不读取这些真值。

Go 默认优化可能消去无用的读取或写入，因此首轮只评分来源字段；内部仍生成执行读取实例，但不会把源码里被消除的读取算作应观测事件，也不把 C 夹具的读取序号硬套到 Go。

## Go 适配边界

- ABI 为 amd64 ABIInternal，入口签名固定为 `func(*output, *input, uint32)`：输出指针 RAX、输入指针 RBX、选择值 RCX。普通结构体布局由 `unsafe.Sizeof` / `unsafe.Offsetof` 编译期断言验证。
- 只分析无内部调用的函数，遇到 `runtime.morestack` 或任何其他直接/间接调用拒绝计划。旧跨函数规划器也明确拒绝这个 Go 适配器，不能据此声称 Go 跨函数传播已支持。
- 夹具在开始采集前调用 `runtime.LockOSThread()`。只接受一个 OS 线程与一个非零 R14（当前用户 G）身份的组合；切换线程或 G 会产生分析错误。这不是一般 goroutine 调度支持。
- 由于固定的用户 goroutine 不一定在进程主线程上，Go 挂接器只枚举已停止子进程的现有 task，并逐线程挂接。不会使用全局 PID=-1 探针。具体线程记录在 `attachment-threads.json`。
- 固定边界地址和有限栈窗口仍需通过逐事件验证。不支持在观测范围内发生栈迁移、分配或并发修改输入。
- 不支持字符串、切片、接口动态分派、堆对象历史、panic/defer 展开、一般 goroutine 切换或跨服务。

依据：[Go ABIInternal](https://go.dev/src/cmd/compile/abi-internal)、[Go runtime 执行与栈模型](https://go.dev/src/runtime/HACKING)。Go ABIInternal 随版本可变；本版是有边界的适配试验，不是通用多语言支持。

后续可以在同一接口下增加类型解析、库调用摘要和更完整的执行身份策略。应分别验证这些能力，不能仅增加语言名称就扩大覆盖声明。
