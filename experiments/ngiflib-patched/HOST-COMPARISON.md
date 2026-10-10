# ngiflib 原生来源对照入口

状态：**主机运行入口已实现，本地已编译；实际 Pin 执行仍需主机回传验证。当前没有新增真实主机对照结果。** 本地启动固定 Pin 仍报 `Exec format error`。既有 24 个受控 C 查询的 libdft64 主机结果不属于本实验。

## 比较什么

| 运行组 | 数据来源推断 | 采集与范围 |
| --- | --- | --- |
| 原生基线 | 无 | 原始 `gif2tga` 转换，逐像素检查 |
| nullpin | 无 | 同一原始程序，检查 Pin 是否改变业务输出 |
| `boundary_replay` | 我们新接入的有界 C 位来源执行器 | Pin 仅观测边界；不初始化 libdft 传播 |
| `libdft64` | 固定上游的原版字节污点传播 | 独立新进程；适配器只设置源标签、读取返回标签和记录诊断 |

**这里比较的是新接入的来源重放后端与 libdft64。不是原来的 selected/eBPF 采集方案的完整对比，也不是性能实验。** 两种工具运行都有诊断逐指令回调，不能把时间、日志条数或这个 Pin 采集器当作论文的 eBPF 开销结果。没有修改上游传播规则，也没有对源业务函数做日志插入或计算替换。

双方都把 `GetGifWord` 内部成功的 `GetByteStr` 缓冲区填充视为来源，查询每次返回的 `AX`。来源标签对应输入文件的字节偏移；每次填充单独记录版本。声明范围之外的码宽、掩码、对象地址、字典及控制来源不混入这个显式数据查询。

文件身份和偏移依赖明确的顺序读取契约：从第一轮 `LoadGif` 开始记录所有 `GetByte/GetByteStr` 的入口/返回，检查相同父对象和 `FILE *`、累计读取位置和输入内容、完整文件读取、两轮 `LoadGif` 的返回，以及无读取期间 seek、线程变化或信号上下文变化。偏移由操作顺序累加，不用相同字节值反向猜测位置。这个契约仅适用于当前固定原始程序及正常单图输入，不等于通用 libc/数据库来源追踪。

## 提前披露的上游语义限制

固定 AngoraFuzzer/libdft64 `20804d5bae5d8aed31a71761b1a1149e35a0da95` 的 `src/libdft_core.cpp` 将标量 `SHL/SHR/SAR` 分派到直接 `break` 的分支，不更新标签。代码审计会核验这一事实，主机诊断会记录实际执行次数。不能把“opcode 出现在 dispatcher”当作传播语义已实现。

当前独立参考来自 GIF 位流，表示固定元数据下某个码值所用输入字节。因此评分分别给出码值一致数、精确格式来源集合数、覆盖的必要字节、缺失的必要字节及额外来源字节；这些字段不是与普通字节污点完全相同的指令语义真值。若出现差异，应报告具体移位/掩码路径与上游版本限制，不概括为所有 libdft 工具错误，也不宣称本方案对任意程序更准确。

来源元数据已带标签、未覆盖指令、丢记录、返回/读取失败、线程/上下文变化、对象或 ABI 不符等情况保留原始记录并报告 unknown，不用空标签掩盖失败。libdft 产生空但可读取的返回标签则作为原版行为保留，由格式参考评分区别“缺失来源”和“采集失败”。

## 在此前运行成功 libdft64 的主机执行

在 `perf/payment-steady-state` 工作目录中：

```bash
git pull --ff-only origin perf/payment-steady-state
python3 -m venv artifacts/ngiflib-venv
artifacts/ngiflib-venv/bin/python -m pip install -r experiments/ngiflib-patched/requirements-host.txt
artifacts/ngiflib-venv/bin/python experiments/ngiflib-patched/compare_host.py run
```

不需要 sudo，不需要 Daybreak，不运行漏洞版本或异常图片。需要 Linux amd64、GCC/G++、make、Git、binutils 和 Python；Pin/上游 libdft64 会优先复用 `artifacts/external-tools` 下此前的固定依赖，否则下载固定版本并核对摘要。首次下载 Pin 需要支持 `tarfile.data_filter` 的 Python（例如 Python 3.12）。

若依赖存放在其他目录：

```bash
artifacts/ngiflib-venv/bin/python experiments/ngiflib-patched/compare_host.py run \
  --pin-root /path/to/pin-3.20-98437-gf02b61307-gcc-linux \
  --libdft /path/to/pristine-libdft64 \
  --source /path/to/ngiflib
```

默认从固定已修复 Git 对象构建原始程序，生成既有 4 张正常图片，各运行真彩色和索引色两种模式。每个用例包括原生、nullpin、只观测、libdft 共四次运行；这是新主机对照的业务一致性检查，不重跑此前独立受控 C/Go 正确性实验。若该主机已有 `validate_normal.py` 的完整输出，可用 `--validation /path/to/output` 复用 ELF 与图片。

结束时打印 `Return this result archive: .../ngiflib-comparison-....zip`。成功或失败都会打包，**请回传整个 zip**。包内包括 ELF、固定源文件摘要、输入、工具构建与依赖身份、原始记录、双方推断、独立参考、逐查询评分及失败原因；不要只回传汇总表。若某组 unknown，脚本仍尝试后续组并最终以非零状态退出。

`build-tools` 子命令仅准备目标和编译适配器，不执行 Pin。`--timeout` 控制每次命令的运行上限，默认 180 秒。没有正式性能计时。

## 已完成的本地检查

- 双模式适配器在固定 Pin/libdft64 上编译、链接通过，33 个上游传播源文件摘要与固定 checkout 一致。
- 22 项记录协议检查：2 个正向合成协议样例和 20 个故障拒绝，包括偏移/内容、ELF 重定位、源标签、版本、线程、缺失事件、返回值等。合成外部标签只是测试替身，不是 libdft64 实测。
- 接入沿用已通过的 C 位来源执行器；未新增应用、图片或 PoC。
- 本地 Pin 启动失败，尚无这条路径的 native/BPF/libdft 运行准确率。机器记录见 `host-adapter-local-validation-20261010.json`。

真实结果必须回传后从上传 ELF 重建计划、检查工具源码与原始记录、重新推断并评分；目前不预先写结论或胜出数字。
