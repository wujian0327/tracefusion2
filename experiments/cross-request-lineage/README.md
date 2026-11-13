# 跨请求共享状态字段溯源：第一轮

本目录只增加实验业务、薄适配、独立预期、评分和原始证据核验。调用现有 `build_distributed_plans`、`SpringTransportAgent`、对象身份／字段版本记录器及 `Reconstruction`／`infer_execution`，不复制或修改既有分析核心。首次结果、运行时拒绝和后续诊断分别保留。结果见 [本轮报告](RESULTS-20261113.md)，后续基线条件见 [BASELINES.md](BASELINES.md)。

在仓库根目录一键运行：

```bash
python3 experiments/cross-request-lineage/round_one.py
```

默认每组重复两次，每次组内两个 JVM 持续运行，连续处理独立 trace ID 的请求；不同组独立启动。输出自动选择新的 `artifacts/cross-request-round1-时间-随机值/`，已有目录会拒绝。包含先运行的全部 plain、再运行 TF、最后 MT；随后是单列的只读入口／直接 B 诊断和证据核验。只运行主实验可加 `--primary-only`，可用 `--out 新目录`、`--repeats 2` 和 `--java /绝对路径/bin/java`。

需要 Python 3 标准库、JDK 8 编译器和可绑定回环 HTTP 端口的 Linux 环境。没有 Docker、数据库、Redis、并发、异步任务或消息队列。HTTP 服务固定单个工作线程，以避免把原生 thread-local 污点状态的跨线程问题混入本轮。主实验 A 转发 JSON 给 B，B 持有普通单条进程内缓存。请求／响应 DTO 和缓存对象没有实验污点字段。

依赖沿用仓库锁文件：

```bash
python3 baselines/manage.py deps
python3 baselines/manage.py fetch --tool mirrortaint
python3 baselines/manage.py doctor --tool mirrortaint
```

当前默认运行时是已有、未经 Galette 插桩的 `artifacts/galette-static-baselines-20261111/runtime-base/java-8-openjdk-amd64/bin/java`，版本为 Ubuntu OpenJDK 8u504。当前 TF 核心按版本和 JCL 类哈希接受固定运行时；主机 8u512 会如实拒绝。迁移机器需提供同一 8u504 安装或已有核心契约接受的安装，不能通过改运行时契约放行。当前安装来自仓库原有 `artifacts/backups/ruoyi-request-scope-20261104/jdk8-runtime.tar.gz` 备份；实验不会下载或修改 JDK。二进制哈希和依赖锁见结果收据。旧 Jackson 2.8.6 只用于本机实验，请求数据均为生成的固定样本。

`workload.json` 只给驱动；`expected.json` 只给评分器。运行前复制并哈希封存两者和源码；分析器不导入它们，主分析进程另用 Python 审计钩子禁止打开这两个文件。预期按业务语义独立指定来源请求、JSON 字段和符号对象／字段版本，不使用 JVM 对象号。范围是显式数据来源，op/key 是控制选择；不宣称隐式流完备。

| 案例 | 最终数据来源 | 共享字段义务 |
|---|---|---|
| cache-hit | R1 `/value` | 同一 c1.text@1 被 R2 读取 |
| same-object-overwrite | R2 `/value` | c1.text@2 杀死 @1，即使同值 |
| new-object-replacement | R2 `/value` | 新 c2.text@1 替换旧 c1.text@1 |
| public-constant | 无外部数据源 | c1.text@2 为公开常量，即使与旧值相同 |
| miss-fallback | R2 `/fallback` | 缓存保持，输出选择当前外部备用字段 |
| missing-write | 真实执行来自 R2 `/value`；缺证后应 unknown／拒绝 | 原始运行保留，派生副本删除第二次 Cell.text 写事件并重新编号，禁止补答案 |

每个请求的 `/value` 和 `/fallback` 都相同，以防用值选择来源；常量组的输入和公开常量也相同。A→B 连接来自实际发送／接收的 `traceparent`，用 request span 区分具体消息；`TraceBoundary` 调用现有 W3C 标识及 JSON snapshot API。独立核验先按实际 HTTP 头配对，再比较原始 JSON 字节哈希和字段。跨 JVM 不比较对象号，不按测试名或预期配对。MT 适配层不传输标签，不调用 TF 图来补 MT 的答案。

补充诊断不是主实验成绩的替换：`read-only-network` 将普通写方法放在 HTTP 调度层，核心入口只做读取；`direct-B` 的请求直接由驱动通过 HTTP 发给 B，source 就是 B 的真实外部输入，不经过 A。后者用于区分单 JVM 缓存能力与 A→B 通信能力，不能冒充跨服务成功。当前 Agent 对查询帧外的写只递增版本、不输出写值，诊断如实保留这个观测范围限制。

每次运行保存：`freeze.json`、`experiment-source/`、构建及计划、`captures/*/*/*/{A,B}/http.jsonl`、客户端原始 JSON／HTTP 状态、进程命令／退出码、TF 原始 `events.jsonl`、MT 原生 source/sink ID 与默认日志、`predictions/`、`score.json`、`REPORT.md` 和完整文件哈希索引。缺证副本位于 `drop-second-field-write/`，不改原始事件。异常与 unknown 保留，不通过修改核心完成评分。

独立复核已有主捕获，输出仍用新目录：

```bash
python3 experiments/cross-request-lineage/verify.py \
  --run artifacts/cross-request-lineage-supported-20261113-04 \
  --out artifacts/cross-request-lineage-review-new
python3 experiments/cross-request-lineage/check_diagnostics.py \
  --run artifacts/cross-request-lineage-diagnostics-20261113-05 \
  --out artifacts/cross-request-lineage-diagnostic-review-new
```

`analyze.py`／`score.py` 是独立进程入口，常规复现由 `round_one.py` 安排；不要在历史目录原地重新评分。已有所有首轮目录均保留。本轮逐项目标和构件摘要为 [results-20261113.json](results-20261113.json)，完整原始归档路径／哈希也在其中。本轮不测性能，不改核心，不 push。
