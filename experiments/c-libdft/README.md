# 原始 C 循环/调用场景的 libdft64 兼容性验证

这轮复用 `scenarios/loop-calls-provenance` 的原始 C 业务、驱动、编译选项和独立真值，不增加业务函数，不修改上游传播规则。已有本方法真实 BPF 结果不重跑。本轮是外部工具接入门槛，**不是新的四组性能比较，也不是 HardTaint 复现或真实大型应用评估**。

## 查询口径

- 三个根函数：覆盖、累积、嵌套变换；两轮数值 × 三个函数 × 0/1/2/4 次循环，共 24 个输出字段查询。
- 来源是根调用入口 `input.secret`、`input.public_value`、`input.noise` 的三个 uint32 字段；四字节分别打同一字段标签。前两个字段数值相同。
- 目标是根返回前 `output.value` 的四字节标签并集，按显式数据来源集合评分。仅在 Python 评分阶段读取驱动真值。
- 控制条件、`count` 参数、指针身份及读取实例不作为本轮来源标签；原有本方法结果中的 `argument_sources` 等不能混进该比较。
- 来源只读、对象不重叠、单 OS 线程。上下文变化、越出五个声明函数、未出现在上游 dispatcher 的 opcode、缺失边界或事件均报告 unknown。出现 opcode case 不代表其全部操作数形式已获支持；最终仍须和独立真值对照。

每个待查调用使用**一个全新进程**，原始驱动仍执行全部 24 次调用，但只在指定序号的根调用注入标签，防止不同调用之间的标签残留。没有修改业务源码、关闭信号或改写 libdft64 的指令传播。三个来源包括未使用的 noise，便于发现过度传播；空来源也作为完整查询评分。

Pin 从主可执行文件符号定位入口和范围，在原始根 RET 前读出 sink。适配器不读取本方法探针计划、推断结果或真值。包内的本方法计划仅由原构建入口生成以保留构建一致性。原始逐指令 PC、标签、stdout、ELF、工具及依赖源码身份均保留。

## 主机运行

在现有仓库目录中，以普通用户执行，不需要 sudo/BCC：

```bash
git pull --ff-only origin perf/payment-steady-state
python3 experiments/c-libdft/compare.py run
```

复用 checkout 外部工具实验的 `artifacts/external-tools` 缓存；不存在时自动取得固定版本。需要 GCC、make、binutils、Git 和 Python 3.12（自动安全解压依赖时）。固定 AngoraFuzzer/libdft64 `20804d5bae5d8aed31a71761b1a1149e35a0da95` 与 Pin `3.20-98437-gf02b61307-gcc-linux`，校验源码版本和 Pin 哈希。也可显式指定 `--pin-root /path/to/pin-kit --libdft /path/to/libdft64`。

程序先运行 native 和 nullpin，再分别查询全部 24 次调用；每次 libdft 运行的业务输出必须与 native 完全一致。成功、失败均打印并保存 `artifacts/c-libdft-*.zip`，请返回该包。失败不丢弃后续查询；unknown 和错误来源集合分别报告。

只诊断某一查询可加 `--sequence 4`，不能将单查询结果当作全套通过。`native` 模式只构建和检查原生真值；`build-tools` 模式另编译真实 Pin 工具，不执行 Pin。两者均不产生外部工具正确性结论。

## 结果解释与后续

2026-10-10 本地已完成：原生 24 次调用全部符合原驱动真值；真实固定 Pin SDK 的 `nullpin`/`libdft_c` 编译通过；6 项新增日志/评分测试（含 17 种故障变体）和原有 15 项外部工具测试通过。原始 C 业务文件没有修改。当前环境执行官方 Pin 启动器报 `Exec format error`，**尚无这轮 libdft 的实际传播结果**，等待主机包。机器可读记录见 `local-validation-20261010.json`。

`full_fixture_agreement` 只在 24/24 查询均通过时成立。即使通过，`external_baseline_qualified` 和 `performance_eligible` 仍为 false：全指令诊断、逐查询新进程与原微型负载不适合性能排名。工具也没有证明任意 C/C++、异常、线程并发、标准库或 SIMD 的完整支持。

已有本方法的真实 C 结果为 24 次根调用、940 条事件、字段关系 TP=22/FP=0/FN=0，见 `docs/loop-calls-provenance.md`。这是此前受控场景的证据，不与新运行耗时或事件量拼表。

完成外部工具主机验证后，再预先选定公开真实 C/C++ 程序和查询，评估共同支持范围、unknown 比例及完整成本；不因为某工具失败就把它当作准确率或性能胜出。
