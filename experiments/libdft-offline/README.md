# libdft64 离线传播核心：RQ1 接入与校准

2026-10-12。**原版传播回调已成功离线编译并运行；受控 C 的同轨迹原版 Pin 主机校准已通过并独立复核。**
本实验落实“我们提供运行证据、适配已有传播核心”的 RQ1 路线，不更改 RQ2 的外部系统成本口径。
当前名称为 **libdft64 callback-core offline adapter**，不是完整 libdft64、HardTaint 或新的通用污点算法。

## 实际复用了什么

固定 AngoraFuzzer/libdft64 提交 `20804d5bae5d8aed31a71761b1a1149e35a0da95`。

- 从 `ins_xfer_op.cpp`、`ins_binary_op.cpp`、`ins_clear_op.cpp` 提取 27 个回调，
  包含 16/32/64 位寄存器/内存复制、按字节标签合并、清除与 LEA 回调。
  每个函数体逐字保留，记录原文件、行号和函数 SHA-256。
- BDD 标签集合、`tag_trait.cpp`、`tagmap.cpp` 及其头文件直接编译原版源码，未替换成我们自己的集合算法。
- `pin.H` 仅补离线编译所需类型和日志宏；单个影子线程上下文使用原版结构。
- 新代码负责读取记录、将受支持的 amd64 指令映射到回调并输出标签。
  **原版 Pin 指令分派器没有被复用，这一映射需要逐步校准。**
- 不修复上游传播规则。例如 32 位清除回调只清低四字节标签，离线版本保留这一行为，
  不能偷偷按我们的来源语义修正后还称原版。

生成目录保留完整上游源码、许可证、回调提取清单、编译命令及哈希。
未知指令/操作数、越界寄存器/地址、缺少完成记录等拒绝；当前不支持一般 SIMD、
系统调用、任意异常、线程迁移和跨线程共享内存。已有 Java/Go 前端缺口没有因此自动解决。

## 已完成的主机校准

上传 `libdft-offline-host-20261012-032317-563858.zip` 已由本地可信源码重新编译核心、
从上传 ELF 重建指令证据，并重放全部原始记录。详见 [HOST-RESULTS.md](HOST-RESULTS.md)
及 [host-validation-20261012.json](host-validation-20261012.json)。

- 24/24 查询最终逐字节标签、来源集合与独立真值一致；6 项正确为空来源。
- 916 条主机指令记录，逐步比较 16 个 GPR 与目标四字节，共 120,912 次字节标签比较全部一致。
- 来源关系 TP=22、FP=0、FN=0；27 个提取回调中，本工作负载实际触发 8 种。
- 校准采集仍使用 Pin；未验证 Go/Java/Rust/C++，未进行性能测量，不涵盖所有内存标签。

## 此前的本地验证（保留原始证据口径）

见 [local-validation-20261012.json](local-validation-20261012.json)。

| 项目 | 结果 |
| --- | --- |
| 原版回调提取并编译 | 27 个函数体不变；原版 BDD/tagmap 编译通过 |
| 新离线接入检查 | 6 项复制/合并/覆盖/清除/上位字节保留/别名检查，4 项非法输入拒绝通过 |
| 原始 C 业务源码 | 沿用 `scenarios/loop-calls-provenance`，未修改 |
| 新本地 ELF 的模拟采集 | Unicorn 执行五个原函数的 916 条机器指令 |
| 离线来源结果 | 24/24 查询匹配独立真值，22 条来源关系，无额外或遗漏 |
| 原生业务输出 | 单独执行同一本地 ELF，24 个值符合独立驱动真值 |
| 原版 Pin 诊断工具 | 固定 SDK 编译成功；本环境启动器 `Exec format error` |
| 原版 Pin 与离线核心同轨迹校准 | 当时未完成；现由上述独立主机记录补齐 |

916 条是模拟器执行记录，不是 BPF/Pin/内核采集。原生驱动只验证业务值和真值，
没有提供本轮原生动态轨迹。它与历史 940 条主机指令属于不同构建，不能互相替代。
新构建显式使用 `-fcf-protection=none`，避免把不受原版分派器支持的 ENDBR 当作已覆盖；
不声称与旧主机 ELF 相同。所有新增适配器输入不包含夹具答案，真值只在验证阶段读取。
旧 C 主机汇总中的 24/24 一致，不能替代新的逐指令／逐标签校准。

记录模型由受信任采集器输出完整指令顺序与具体 GPR 值，原始 ELF 给出指令字节。
当前检查序号/范围/完成状态，不声称识别任意伪造或重新编号后的丢失记录；
host 校准另外通过原版中间标签和目标标签检查这一有限适配器。
没有性能测量，不使用模拟器/诊断日志耗时比较效率。

## 主机校准复现入口（本轮已通过，无需重复运行）

使用此前可以运行 libdft64 的 Linux x86-64 主机，普通用户，无需 sudo/BCC。
需要 GCC/G++、make、git、binutils 和 Python 3.12+。已有 Pin/libdft 缓存会复用；
没有缓存时按既有协议下载并校验固定版本。

```bash
git switch perf/payment-steady-state
git pull --ff-only origin perf/payment-steady-state
python3 -m venv .venv-libdft-offline
.venv-libdft-offline/bin/python -m pip install -r experiments/libdft-offline/requirements.txt
.venv-libdft-offline/bin/python experiments/libdft-offline/calibrate_host.py
```

最后打印 `artifacts/libdft-offline-host-*.zip`，成功或失败都保存，请返回这个包。
这是**新适配器的必要校准**，不是重新宣称旧 C 实验增加了覆盖。

流程：

1. 编译原 C 程序、原版 libdft64、只增加只读状态记录的 Pin 适配器，以及离线核心。
2. 原生与 nullpin 输出核对；24 个查询各用新进程，避免历史标签污染。
3. 在原版传播前记录具体寄存器、16 个 GPR 的逐字节标签、目标字段四字节标签。
4. 从记录中**去掉所有原版标签**，只将程序字节、具体寄存器、源绑定等提供给离线适配器。
5. 独立执行原版回调，逐步比较全部 16 个 GPR 和目标字段标签，最终比较每字节标签、
   来源集合及业务值。每条指令比较 132 个字节标签；并非观察所有堆或栈标签。
6. 所有 24 个查询通过才标记 `native_pin_equivalence=true`，且仅适用于此指令/操作数范围。

同轨迹校准使用 Pin 作为实验运输层；传播部分离线执行，且不读取原版传播结果作为输入。
以后可以替换为我们其他采集后端，但必须提供同等指令、地址与上下文证据；
本轮不声称已替代 Go 的实际采集或支持 JVM 字节码。

仅编译可加 `--build-only`，不会启动 Pin；这不算校准通过。
可用 `--pin-root`、`--libdft` 指向已存在的固定版本，不修改上游代码。

## 本地可复现入口

离线核心本身不需要 Python 额外包或 Pin SDK：

```bash
python3 experiments/libdft-offline/build_core.py --libdft artifacts/external-tools/libdft64 --output artifacts/offline-core-new
```

完整本地模拟检查需安装 requirements.txt：

```bash
.venv-libdft-offline/bin/python experiments/libdft-offline/check_local.py --libdft artifacts/external-tools/libdft64 --output artifacts/offline-local-new
```

输出目录必须不存在，不覆盖旧证据。成功后报告仍保持 `native_pin_equivalence=false`。

## 独立复核上传结果

`verify_host.py` 读取解压目录，使用可信上游检出与本地适配器重新编译、重放；
不会执行上传包中的程序、动态库或 Python 脚本。输出目录必须是新目录。

```bash
.venv-libdft-offline/bin/python experiments/libdft-offline/verify_host.py \
  artifacts/libdft-offline-host-20261012-032317-563858 \
  --libdft artifacts/external-tools/libdft64 \
  --output artifacts/libdft-offline-reverified-new
```

## 后续资格

同轨迹校准已完成。用户随后确认先增加真实开源对象，当前先接入
[cJSON](../cjson-provenance/PARSER-CALIBRATION.md)，已完成原生功能检查；独立扩展的 46 回调版本
已对字符串解码区间做本地模拟并编译主机工具，真实校准待运行；
已有 Go 路径接入保留为后续项，不预设成功。
C++/Rust 使用相同 amd64 核心的可能性需要真实执行证据；Java 需要不同的操作语义适配。
不能把当前单线程受控 C 的 24 个查询填入四种语言的准确率表，也不把此核心的成本当成
原版 libdft64 系统成本。Galette/HardTaint 接入仍为未开始状态。
