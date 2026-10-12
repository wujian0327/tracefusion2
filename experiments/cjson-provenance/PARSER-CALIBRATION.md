# cJSON 原始字符串解码：双核心接入与主机校准

2026-10-12。**本地模拟、真实主机执行与独立复核均已完成。**
原 cJSON 源码、输入用例、驱动与编译选项沿用前阶段，未改写业务逻辑。
主机结果见 [PARSER-HOST-RESULTS.md](PARSER-HOST-RESULTS.md)：18 个查询、1,545 条指令，209,609 次中间字节标签比较一致。

## 当前接入的边界

执行完整原生驱动，由 cJSON 自己解析 JSON、构造节点并返回字段。先用索引运行记录
`parse_string` 返回的节点与输出缓冲，再按 `(用例, 节点地址, 输出缓冲地址)` 关联目标字段。
不同进程重新绑定实际对象，不通过相同值猜测来源。输入 token 偏移来自独立的语法扫描配置，
与原始解析缓冲的实际偏移核对；它不是传入还原器的答案。

本阶段的来源边界在 **`parse_string` 的输出分配成功返回后、字符解码开始前**。
源是此时完整输入 JSON 缓冲中的各字节，标签为输入偏移加一；目标是此调用生成的字符串内容。
入口的寄存器、调用方栈、解析状态和对象元数据属于明确声明的边界状态，不追溯它们此前的来源。
输出内存分配在边界外，分配结果由真实调用记录，不假装已完整分析 malloc。
解码中的 `parse_hex4` / `utf16_literal_to_utf8` 调用按原始指令执行；未知指令、越界执行或缺失记录拒绝。

22 个请求保持原分母：

- 18 个字符串目标进入解析阶段，包含空内容、转义及 Unicode。
- 2 个缺失字段/解析失败请求检查原生 `no_sink`，不混入字符串准确率。
- 2 个覆盖写入后的新字符串目标明确为 `not_in_parser_scope`，保留在报告中。

本轮不分析替换函数的传播或序列化输出；索引运行确认解析结果与字段目标的对象关系，
不等于完成字段选择条件的全路径依赖分析。此前定义的整个 cJSON 工作负载仍未全部接入。

## 双方实现及校准

**libdft64 离线核心：**`parser_core.py` 在固定原版源码中原样提取 46 个回调（此前 27 个加 19 个），
保留原版 BDD/tagmap；追加低字节读写、合并/清除和符号/零扩展入口。
原版将 MOVZX 与 MOVSX 分派至相同传播回调，移位/BT 不更新标签，本适配器保留这些规则。
没有把我们的位路由语义偷偷替换进原版。实际工作负载只校准触发过的指令/操作数，不覆盖所有提取回调。

**我们的还原：**`parser_ours.py` 复用既有 `scripts/c_bit_machine.py`，增加本区间需要的符号扩展、
RIP/FS 地址、BT、间接跳转及嵌套调用适配。从入口快照和原始 ELF 指令重建位依赖，
用采集到的每步寄存器和控制路径校验具体执行，控制/地址来源单独输出。
它不导入 libdft 回调、不接收原版标签，也不接收预期字段来源。
这是有完整诊断轨迹的受限还原，不宣称已实现 cJSON 的最优选点、稀疏采集或成本优势。

**原版主机参考：**`parser_capture.cpp` 使用不修改传播代码的原版 Pin/libdft64，
每个目标解析调用使用新进程，边界前检查影子状态为空；每步记录 16 个 GPR 和已分配输出区域的字节标签。
这些参考标签仅供核验，在转成离线输入时全部去掉。
主机脚本比较每一步参考标签和离线核心标签，并核验我们的具体执行与输出值。
范围含单 OS 线程、不可变源、输入不超过 256 字节、单次字符串分配不超过 32 字节、8192 条解码指令预算；
私有 ABI 同时用原始源码探针和目标 ELF DWARF 核对。

## 本地证据

见 [parser-local-validation-20261012.json](parser-local-validation-20261012.json)。

| 项目 | 结果 |
| --- | --- |
| 原始 ELF 解码模拟 | 18 个查询，1,545 条执行指令记录 |
| 两个离线核心 | 重放完成；输出与原生值一致，字段存在性诊断符合预期 |
| 损坏证据检查 | 10 项通过：缺少完成标记、步序缺口、越界 PC、缺少返回，以及我们对错误寄存器和缺失栈快照的拒绝 |
| 原版 Pin 采集工具 | 固定 SDK 编译成功；本环境无法原生启动 Pin，未执行主机实验 |
| 真实性等级 | **Unicorn 模拟证据，不是 Pin/BPF/内核证据** |

例如 `\n\t` 的输出由常量生成，两个核心的显式内容来源均为空；这不能据格式语义判定为漏报。
本地同时输出逐字节标签，但独立字段存在性诊断只检查来源未跨入其他字段，以及应有数据来源时非空；
**它不证明每个输入字节集合都最小且精确，不能包装成逐字节准确率 100%。**
主机原始证据复核现已完成；完整 RQ1 精度表仍需要固定、可比的依赖语义及独立逐字节真值。诊断日志不可用于性能比较。

## 主机复现命令（已完成，无需重跑）

使用之前成功运行 libdft64 的主机。复用现有虚拟环境与 Pin/libdft 缓存；缺少 cJSON 时自动获取并核对固定提交。

```bash
git switch perf/payment-steady-state
git pull --ff-only origin perf/payment-steady-state
.venv-libdft-offline/bin/python -m pip install -r experiments/cjson-provenance/requirements.txt
.venv-libdft-offline/bin/python experiments/cjson-provenance/parser_host.py
```

如需在其他环境复现，成功或失败都返回最后打印的 `artifacts/cjson-parser-host-*.zip`。无需重跑此前受控 C 校准。
`--build-only` 只编译，不算采集通过；`--source`、`--pin-root`、`--libdft` 可指定已有固定版本目录。
脚本保留普通运行、索引运行及逐查询原始记录、来源快照、双方推断、失败原因、ELF、源码与依赖摘要。

本地模拟复现入口（已执行，无需用户补跑）：

```bash
.venv-libdft-offline/bin/python experiments/cjson-provenance/parser_local.py \
  --source artifacts/external-tools/cjson-v1.7.19 \
  --libdft artifacts/external-tools/libdft64 \
  --output artifacts/cjson-parser-local-new
```
