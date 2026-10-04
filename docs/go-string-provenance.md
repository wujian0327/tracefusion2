# Go 字符串多来源溯源：第一阶段

目标是从一次 JSON 输出反向找到参与加工的读取实例。场景执行三次文件读取：A 为 phone，B 为 prefix，C 为不参与输出的 other；随后计算 `prefix + phone`，输出 `{"result":"..."}`。本阶段只有一个进程、一个请求，不涉及跨服务。

## 运行

在已具备 BCC 和内核 BPF 支持的 Linux amd64 主机上运行。当前 ABI 适配器只接受 Go 1.25.4 或 1.25.5；使用能导入 BCC 的系统 Python。不需要 Docker。

```bash
cd ~/tracefusion2
git pull --ff-only
sudo env "PATH=$PATH" /usr/bin/python3 scripts/go_string_provenance.py run
```

如果 sudo 环境看不到指定的 Go，可以显式传入其绝对路径：

```bash
sudo env "PATH=$PATH" TRACEFUSION_GO=/usr/local/go/bin/go /usr/bin/python3 scripts/go_string_provenance.py run
```

脚本编译目标、生成探针计划、采集三个用例、离线推断并评估。无论采集成功还是失败，都会打印 `Return this archive: ...zip`，请返回该 ZIP。产物默认位于 `artifacts/go-string-provenance-<时间>/`；请使用自动生成的新目录，或通过 `--output` 指定尚不存在的目录。

仅编译与检查观测位置，不需要 root：

```bash
python3 scripts/go_string_provenance.py build
```

## 观测和推断

这次新增的是字符串 API 摘要路径，没有把原有 uint32 指令解释器扩展成通用字符串解释器。

| 层 | 文件 | 职责 |
| --- | --- | --- |
| Go 适配 | `scripts/go_string_adapter.py` | 解析二进制直接调用，验证 ELF 偏移，根据指定 Go ABI 解码字符串指针和长度 |
| 采集 | `scripts/string_capture.py` | 在调用及其续接位置挂 uprobe，采集参数/返回值、进程与 goroutine 身份、时间及丢失计数 |
| 值依赖 | `scripts/value_lineage.py` | 将读取返回值定义为来源实例，利用拼接与 JSON 摘要建立实际观测依赖 |
| 共用图 | `scripts/lineage_graph.py` | 从输出反向遍历依赖边；旧 C/Go 循环溯源也复用这部分 |
| 运行与评估 | `scripts/go_string_provenance.py` | 编译、夹具、采集、离线推断、独立真值评分和打包 |

配置的操作模型为：

| 操作 | 观测输入/输出 | 依赖语义 |
| --- | --- | --- |
| `main.readValue` | 文件路径、返回的完整字符串 | 每次实际读取调用是一个新来源实例 |
| `runtime.concatstring2` | 左右字符串、返回字符串 | 返回值依赖两个输入，保留 left/right 角色 |
| `main.marshalResult` | 输入字符串、返回 JSON 字节 | 固定 `result` 字段的值依赖输入字符串 |

数据身份使用观测到的“地址 + 长度”，字节内容用于一致性校验，不按字符串相等直接认定来源。`source:1/2/3` 是读取调用的观测顺序编号，不是预先写进数据中的标签。报告附有每次读取的路径、长度、摘要和事件序号。

推断器只接收事件及探针计划；推断结果保存后，评估器才读取 `oracle.json`。真值来自受控夹具的已知程序语义，没有作为目标程序中的溯源标签传播。

目标程序没有追踪回调、来源编号或强制线程绑定。构建会对自身包禁用内联，以保留当前观测位置；依赖符号信息、指定编译器和显式函数摘要。因此本实验并不证明任意现成生产二进制都能直接支持。

## 检查什么

三个用例分别为普通不同值、三路输入完全同值、包含中文及 JSON 转义字符。预期来源为 A+B，排除虽被读取但未参与结果的 C。

依赖图应有四条语义边：B → 拼接的 left，A → 拼接的 right，拼接 → JSON 值输入，JSON → 输出字段。评分分别报告来源关系的 TP/FP/FN、precision/recall，以及这些已建模操作边的 TP/FP/FN。它们不是完整指令级或字节级血缘准确率。

另有五个证据破坏检查：采集报错、缺少一次读取、缺少拼接返回、未知输入身份、JSON 内容不一致，均应返回 `unknown`。这只验证已声明观测契约的缺失和矛盾，不保证发现所有未观测到的内部写入。

当前二进制规划为 12 个逻辑事件位置、11 个物理探针：拼接返回位置与 JSON 调用位置重合，必须由同一探针按顺序发出两个事件。正常每个用例应收到 12 个事件；收到事件仍不代表依赖图必然正确，需同时查看评估。

关键产物：

- `plan.json`、`disassembly.txt`、`symbols.txt`、`build.json`：二进制与观测位置。
- `<用例>/events.json`、`collector.c`、`target.stdout`、`target.stderr`：原始观测、采集代码及程序输出。
- `<用例>/inference.json`：反向切片、贡献来源及被排除的读取。
- `evaluation.json`：独立真值比较及负向检查；采集失败时查看对应 `.log` 与 `runner-error.txt`。

## 当前边界与验证状态

只支持本夹具固定的三次读取、一次拼接、一次 JSON 操作序列；读取来源指一次 `readValue` 调用及其返回完整字符串，不是数据库内部表、行、历史版本或文件系统调用级血缘。JSON key `result` 为固定模型的一部分，未重建动态 key 的来源。

来源字符串限 2–128 字节，单个快照最多 512 字节。当前要求存储身份独立且在观测区间内有效；发现重复身份或已定义值内容变化时拒绝归因。尚未覆盖一般别名、可变缓冲区、内存回收复用、任意库函数、跨请求并发或跨服务传输。程序不固定线程，事件要求来自同一进程和 goroutine；这次测试没有证明发生过真实线程迁移。

提交前已完成：Go 1.25.4 真实编译、三个用例直接运行、七项单元测试，以及旧 C/Go 共 884 条事件、48 次调用的回放，旧推断结果与保存结果完全一致。测试还修改同值输入的观测身份，确认推断会随证据改变，并被原始真值评分判错。

当前环境没有 BCC，尚未完成本实验的内核编译、探针挂载和真实采集。主机执行成功并审查 ZIP 后，才能确认动态采集端到端通过。
