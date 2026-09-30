# 程序内部赋值的 eBPF 验证

当前问题是：**能否通过 eBPF 用户态指令探针，记录一次赋值读取哪个字段、经过哪个寄存器、最终写入哪个字段？**不再以 HTTP 抓包作为主线验证。

## 方法和边界

使用 Linux uprobe 作为动态插桩机制，在选定用户程序的机器指令执行前运行 eBPF。探针读取寄存器和用户内存，事件通过 perf buffer 交给用户态即时保存。这里的“不改业务源码”指不在业务操作中添加日志、污点标签或探针调用；运行时仍有动态探针与执行开销，不能称为完全无侵入。

eBPF 不自动理解 `a=b`，也不自动监听每次用户态内存写入。完整数据流需要额外的指令定位、操作语义、对象布局及依赖传播逻辑。本例明确提供一个两字段 C 结构体模型，通过实际反汇编决定源字段偏移和变换操作；不是根据同值猜来源，也不是仅靠函数名称推断来源。

本次严格限制为 Linux x86-64 原生 C、GCC `-O2`、单线程、32 位整数、无分支的 `load → [xor] → store → ret`。不支持任意指令、堆对象别名、并发、JIT、Go ABI 或跨服务消息关联。完整函数指令序列不符合预期就拒绝挂探针，不硬套偏移。

## 三个场景

业务操作放在 `scenarios/uprobe-assignment/operations.c`，是普通 C 函数：

```c
dst->value = src->secret;
dst->value = src->public_value;
dst->value = src->secret ^ 0x55u;
```

测试夹具故意让 `secret` 和 `public_value` 数值相同，验证能否区分来源；每个场景运行两次，共六次赋值。不同轮次复用栈地址，事件按线程和动态调用编号区分。源字段标记属于显式提供的结构体语义，不是系统自动发现“敏感”的能力。

夹具启动时使用 SIGSTOP 等待外部探针挂接，操作完成后输出验证结果；暂停与结果打印仅是测试协调。业务操作函数中没有新增日志、标记或 USDT。源码分为两个编译单元，不使用 LTO，让这些函数在本实验二进制中保留；这不证明任意优化后应用都能得到相同探针位置。

采集器在每条受支持指令前挂 uprobe。直接复制采三个位置：加载前、加载后/写入前、写入后；XOR 场景增加变换前后的寄存器证据。每次保存线程、调用编号、指令地址、源/目标地址、EAX、源字段快照、目标字段快照及内存读取错误码。

离线分析将机器指令语义与动态观测结合：验证源值确实进入 EAX、变换符合指令、目标内存确实变成写入寄存器的值，再报告 `input.secret/public_value → eax → output.value` 的局部依赖。该结论依赖已验证的直线指令序列和单线程场景，不推广成通用污点追踪。

## 运行

这次不需要 Docker、Compose 或 Sock Shop。沿用已经能加载 BCC 的 WSL2 环境，安装编译工具后运行：

```bash
sudo apt-get update
sudo apt-get install -y gcc binutils
git pull origin main
sudo /usr/bin/python3 scripts/uprobe_assignment.py run
```

BCC 依赖仍为系统 Python 的 `python3-bpfcc` 及可用的内核编译环境。上一轮 socket filter 成功不保证 uprobe 配置也可用，这正是本轮需要实测的内容。

成功或失败都回传 `artifacts/uprobe-assignment-*.zip`。正常运行预期有六次局部赋值记录、二十条指令事件，且记录的失败/丢失计数均为零；否则不能宣称验证通过。

仅编译、查看机器指令与探针位置，不需要 root/BCC：

```bash
python3 scripts/uprobe_assignment.py build
python3 -m unittest discover -s tests -q
```

## 结果文件与真值隔离

| 文件 | 内容 |
| --- | --- |
| `assignment-demo`、`build-identity.json` | 实际二进制、编译器信息及校验和 |
| `disassembly.txt`、`probe-plan.json` | 实际机器指令、每个探针偏移和受支持语义 |
| `collector.bpf.c`、`collector.log` | 生成的 BPF 程序及编译/挂接诊断 |
| `events.jsonl` | 实时保存的指令寄存器/内存事件 |
| `capture.json` | 事件计数、提交错误、丢事件、目标进程退出状态 |
| `attached-probes.json` | 各指令和入口诊断探针的实际挂接参数，全部限定目标子进程 |
| `target-process.json`、`target-maps.txt` | 目标 PID/命名空间、可执行文件和地址映射诊断 |
| `assignments.json` | 仅使用探针事件及指令模型恢复的局部依赖 |
| `program.stdout.jsonl` | 测试程序独立输出，仅供最终评估 |
| `evaluation.json`、`result.json` | 六个受控样例的验证状态及失败阶段 |

分析函数 `infer(events, plans)` 不接收程序 stdout，也不依靠源值相等决定来源。最终 `evaluate` 才读取已知测试场景的预期源字段。缺事件、重复事件、读内存失败或寄存器/内存与指令矛盾时拒绝生成对应赋值记录。

开发环境已实际编译执行 C 测试程序，并测试指令定位、同值不同来源、XOR 和异常事件处理；开发环境没有 BCC，内核加载与真实事件采集通过下述用户主机回传验证，合成事件测试与实际采集结果分别记录。

2026-09-30 首轮用户回传 `uprobe-assignment-20260930-200345-5029.zip`：程序完成六次赋值，编译/挂接调用没有报错，但 `events.jsonl` 为空，`attempted_events=0`。这次结果尚未证明任何赋值被采到，不能用测试程序 stdout 代替探针证据。

检查发现旧采集器把 Python `subprocess.pid` 直接与 `bpf_get_current_pid_tgid()` 的内核 TGID 比较，在 PID 命名空间中存在误过滤风险。已移除该多余比较，采集范围仍由每次 `attach_uprobe(pid=目标子进程)` 强制限制，没有改为全系统探针。旧包缺少过滤前计数和命名空间记录，**尚不能断言 PID 不一致就是这次零事件的已证实原因**。

新版增加函数入口命中计数 `entry_hits` 和指令处理器最前面的 `raw_instruction_hits`，记录目标命名空间和收到事件的内核 TGID。CET `endbr64` 存在时独立探测函数入口；否则复用第一条指令的探针，避免重复挂接同一个位置。入口有命中而指令为零时继续检查偏移；入口与指令均为零时检查挂接与执行上下文。零事件不再显示 `capture_clean=true`。

### 用户主机复测通过

2026-09-30 回传 `uprobe-assignment-20260930-201759-a693.zip`，使用 BCC 0.29.1、GCC 13.3.0、WSL2 内核 `6.18.40.1-microsoft-standard-WSL2`：

- 13 个探针挂接完成，3 个函数入口各命中 2 次；20 次指令探针命中，尝试提交与收到事件均为 20。
- `lost_events`、`submit_errors`、`state_errors` 均为 0，20 条事件的用户内存读取返回码全部为 0。
- 六次局部赋值检查全部通过，`status=selected_assignment_checks_passed`。
- 从原始事件独立重放，`assignments.json` 和 `evaluation.json` 与包内结果完全一致；实际二进制校验和、源文件校验和及反汇编生成的探针计划一致。
- 结合目标进程的可执行映射计算加载基址，20 条事件的指令地址全部精确对应预定指令位置。

第一轮赋值的动态证据为：

| 操作 | 观测到的来源 | EAX 和写入结果 |
| --- | --- | --- |
| 敏感字段复制 | `input.secret` 的地址 | EAX 载入 424242，目标内存随后变为 424242 |
| 普通字段复制 | 相邻偏移 +4 的 `input.public_value` 地址 | 数值同为 424242，仍恢复为普通字段来源 |
| 敏感字段 XOR | `input.secret` 的地址 | EAX 从 424242 变为 424295，目标内存随后变为 424295 |

第二轮换成 424243，同样分别恢复直接复制和 XOR 后的 424294。这不是单靠数值相同建立的候选边：来源由已验证的加载指令及结构体偏移确定，寄存器和内存事件提供执行证据。字段名称与敏感属性仍由实验的显式结构体模型提供。

本次同时记录到用户态子进程 PID 为 66849，而事件内核 TGID 为 5524，证实该环境存在两种 PID 编号。旧比较条件会排除本次全部事件，与上一轮零事件现象吻合；上一轮未记录实际内核 TGID，无法直接回溯该数值。

通过的是六次受控赋值的可观测性及局部依赖检查，**不是通用污点跟踪、跨语言支持或真实微服务血缘准确率的验证**。当前不需要为了修复问题重复运行同一实验。

## 接下来如何扩展

先验证本轮确实采到 load/store 执行，再选择一种目标语言/运行时的实际序列化或字段复制路径。逐步解决优化指令、对象布局、别名和并发关联。稀疏函数边界快照通常只能提供局部候选，完整动态污点传播需要覆盖所声明范围内的传播操作，不能由“把快照存下来”自动获得。

技术依据：

- [Linux uprobe 文档](https://www.kernel.org/doc/html/latest/trace/uprobetracer.html)：用户态指令位置、寄存器和内存读取。
- [BCC reference guide](https://github.com/iovisor/bcc/blob/master/docs/reference_guide.md)：`attach_uprobe` 的 `sym_off`、PID 限定及用户内存读取。
