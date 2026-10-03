# Gin 默认调度场景

## 目标与状态

这一步只改变服务端调度方式，保留已验证的 Go/Gin 版本、28 个请求、7 种业务模式、真实文件读取、普通结构体和 `c.JSON`。

新入口 `scripts/gin_default_provenance.py` 不固定请求线程，不设置 `GOMAXPROCS`，不创建占用线程的辅助 goroutine，也没有请求内阶段汇合、主动让出执行权或人为延时。采集器完整复用已验证的 process/G/request 身份逻辑。

**2026-10-03 本场景的真实 BCC/eBPF 主机采集已通过。**892 条事件、28 个请求、36 次计算、56 次读取；本组固定夹具的来源关系 TP=28/FP=0/FN=0，全部客户端正文正确，报告丢事件、提交、状态及读取错误均为 0。

已从上传二进制重新反汇编、重建业务与框架探针计划，核对运行地址和挂接列表；从原始事件重新推断、评估，结果与包内记录完全一致。见 [主机汇总核验](gin-default-host-20261003.json)。公开记录仅含汇总指标与核对结论。

实际观察到最多 4 个请求范围重叠、共 7 个线程，以及 31 对有重叠的请求。重叠对数和峰值分别用全局观测顺序、时间戳再次核对，结果一致。启动与结束时均无调度环境覆盖，运行时配置允许多个 P；不据此推断实际同时占用多个 CPU。

**28 个请求各自始终保持一个 TID，自然迁移次数为 0。**这不影响本轮默认调度并发的通过，但不能把本包描述成自然迁移验证。之前受控迁移实验的证据独立保留。

## 运行

本轮已通过，无需重跑。以下命令保留用于复现。

```bash
git pull --ff-only origin main
sudo env "PATH=$PATH" GOPROXY=https://goproxy.cn,direct \
  /usr/bin/python3 scripts/gin_default_provenance.py run
```

返回整个 `artifacts/gin-default-provenance-*.zip`，失败时也返回。旧入口不用重跑。

仍使用 Go 1.25.4、Gin 1.11.0、系统 Python 与 BCC，无需 Docker。不要为这一轮主动设置 `GOMAXPROCS` 或调度相关 `GODEBUG` 参数；程序只查询有效 `GOMAXPROCS` 与 CPU 数，不修改设置。环境确实存在覆盖时，评估会明确标记默认调度条件不满足。

## 自然并发如何验证

客户端保留每批 4 个请求、共 7 批的有界并发发送。它不控制服务器的读取、计算或序列化先后顺序。服务器各请求独立完成，不等待其他请求到达同一阶段。

推断继续只读取采集事件、探针计划、字段配置和文件身份快照。客户端 ticket、响应正文、评估对象对应表，以及启动/结束时的运行时调度信息仅参与评估。

`evaluation.json` 分开报告：

- `provenance_checks_passed`：28 个响应、36 次计算、56 次读取的来源与正文正确，采集完整且无报告错误。保留同值异源、合并和覆盖检查。
- `default_scheduler_verified`：启动与结束记录均有效，未设置 `GOMAXPROCS` 环境变量，也未设置 `updatemaxprocs`、`containermaxprocs` 或 `asyncpreemptoff` 覆盖项。该记录与受审计的场景源码共同限定本轮条件，不是对任意程序默认行为的外部证明。
- `natural_concurrency_coverage_passed`：从原始事件看到至少两个请求范围重叠。不再要求每批四个请求在三个阶段同时汇合。

三者同时满足才通过。请求全部正确但没有任何范围重叠，会报告覆盖不足，不冒充并发验证通过。

`natural_scheduling` 另行记录请求重叠峰值、重叠请求对数、观察到的线程数量和迁移请求数。**自然迁移次数可以是 0，不因此判定来源重建失败，也不将其解释为已验证迁移。**实际发生迁移时，继续核查同一 G/请求实例的连续性。

不同请求在不同线程上的观测及范围重叠，不等于证明它们在两个 CPU 上同时执行；`multi_p_configured` 也只是运行时配置记录。本轮不做性能或真正 CPU 并行性的结论。默认调度可能按主机资源选择一个 P，程序不会为了制造多核证据强行修改它。

## 本地验证与复现

见 [本地检查汇总](gin-default-local-validation.json)。包括：

- 真正启动无调度夹具的 Gin，检查 28 个客户端响应和调度元数据。
- 执行真实 Go 指令后构造只重叠两个请求、打破旧阶段顺序且没有迁移的历史，要求正确通过。
- 检查自然发生迁移的历史仍正确接续；串行历史、环境覆盖、来源偏移错误、身份损坏及采集错误不能错误通过。
- 重放旧固定线程并发和强制迁移两个真实包，共 1784 条事件；完整推断与评估结果保持一致。

```bash
python3 scripts/gin_default_provenance.py build --out "$PWD/artifacts/gin-default-test-build"
GIN_DEFAULT_BUILD="$PWD/artifacts/gin-default-test-build" \
  python3 -m unittest discover -s tests -p test_gin_default_provenance.py -v
```

本地测试需要 Unicorn 及 loopback socket 权限。编译仍关闭内联，业务函数、字段布局和 JSON 摘要仍显式指定；没有扩展任意 Gin API、字符串/嵌套 JSON、数据库、子 goroutine 数据传播、共享可变对象或计算中的栈重定位。
