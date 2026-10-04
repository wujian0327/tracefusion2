# 双 Gin 服务：OpenTelemetry 调用链 + 动态来源图

## 状态与运行

正式双服务实验使用 OpenTelemetry SDK；[旧版最小上下文转发实验](gin-cross-provenance.md)保留作回归。

本地验证完成六个真实服务二进制的探针规划、采集器生成，以及三组共 24 次外部请求、24 次上游调用、99 个真实 SDK span 的父子关系检查。44 项相关测试通过，其中包含合成采集事件的来源推断、实际二进制规划、原有单服务/手工转发回归及真实 HTTP/SDK 集成。此前单服务主机归档的 1576 条事件重放结果不变。**当前环境不能加载 BCC，新双服务版本的 eBPF 采集尚待主机验收。**

```bash
cd ~/tracefusion2
git pull --ff-only
sudo env "PATH=$PATH" GOPROXY=https://goproxy.cn,direct \
  /usr/bin/python3 scripts/gin_otel_provenance.py run
```

仍用 Go 1.25.4、Gin 1.11.0、Linux amd64、系统 Python 与 BCC。无 Docker、Collector 或 Jaeger 依赖。新模块锁定 OTel Go 1.38.0、otelgin/otelhttp 0.63.0；版本仅为本实验复现基线，不声称是最新版本。首次构建需下载依赖。成功或失败均打印归档路径，请返回完整 `artifacts/gin-otel-provenance-*.zip`。

只构建、不采集：`python3 scripts/gin_otel_provenance.py build --output <新的输出目录>`。场景目录含三个角色入口，必须通过 runner 按角色选择源文件，不能直接在该目录 `go build .`。`TRACEFUSION_GO` 可显式指定 Go 可执行文件。

## SDK 负责什么

测试客户端用 SDK 创建一个根 span 与八个 CLIENT span；Gin 中间件创建 SERVER span；下游的 `otelhttp.NewTransport` 创建远程调用的 CLIENT span并注入标准 W3C `traceparent`。一组八个请求共用根 trace，各有独立的请求 span。

每个请求的父子顺序：客户端 CLIENT → 下游 Gin SERVER → 下游 HTTP CLIENT → 上游 Gin SERVER。加上公共根 span，每组 33 个 span。SDK 全采样，使用批量 stdouttrace exporter 写入独立 JSONL 文件；服务先结束 HTTP 请求，再 Shutdown tracer，避免丢失尾部 span。批量导出发生在后台 G，不在业务来源作用域内。

**本实验的 SDK 初始化、Gin 中间件注册和 HTTP Transport 接入涉及应用配置/源码变更。**这部分是现成 tracing 基础设施。数据来源分析仍由外部二进制分析与 eBPF 观测完成，不向业务数据添加来源标签；不能把整个 SDK 接入过程称为零修改。生产场景若已有 OTel，可复用其上下文；当前只验证指定版本和固定实验拓扑。

## 来源分析负责什么

继续复用冻结的四字节字段来源核心及三组操作：

| 下游操作 | 最终应保留的来源 |
| --- | --- |
| assign | 本次上游读取并选择的 A 或 C |
| partial | 上游选择的 A/C，加下游本地 B |
| overwrite | 仅下游本地 B |

所有源文件内容与最终 JSON 都相同，不能通过值相等区分来源。业务输出依然是 `{"result":[83,65,77,69]}`。SDK span 只证明调用关联，不能替代字段依赖证据。

推断分三步：

1. 分别通过两端的进程/G/请求代次、读取与业务指令、Marshal/Writer 证据构建请求内来源图。
2. 从 SDK 导出验证完整父子关系、service.name、span kind、instrumentation scope，以及唯一候选。对照两端实际收到的 header 与下游 SDK 注入的 header，确认属于这次调用。
3. 继续验证上游 Writer 正文、下游 ReadAll 正文、交给 Unmarshal 的同一缓冲区、解码对象和业务读取对象。按固定 `$.result[i]` 模型连接两端位置依赖，然后从最终输出反向切片；完全覆盖后不保留上游来源。

下游不再手工转发 header。新探针观察 `propagation.HeaderCarrier.Set` 的实际 SDK 注入参数；`readRemote` 的参数现为 `(context.Context, string)`，对应的 Go ABI 参数位置已从真实二进制检查。请求内 goroutine 的观测状态继续复用既有实现。

拼接推断不读取客户端的 ticket、source 选择或响应真值。客户端记录只用于最后评估。不同请求即使处在同一个 trace、输出相同，也必须匹配各自 SDK CLIENT span。

## 输出与失败边界

每组保存：

- 两端 `capture/events.json` 与 `inference.json`：eBPF 事件、各自来源图。
- 两端 `capture/spans.jsonl`：SDK span；下游另有 `client-spans.jsonl`、`client-responses.json` 与 `client-run.json`。
- `joined.json`：最终来源集合、图、实际远程调用 context、入口请求 context，以及用于核对的 SDK span 链。
- `evaluation.json`：来源真值与 HTTP 正文检查、SDK 链、并发覆盖、负向检查。
- 构建记录、模块版本清单、二进制/源码哈希、反汇编和采集器。

11 类离线负向检查涵盖原有五类传输证据错误，以及缺少 span、重复 span、错误 parent、错误服务、错误 kind、实际注入 context 不符。单位测试另检查导出乱序不影响匹配、额外候选产生歧义、缺少本地证据、采样不完整等。证据不足返回 unknown；不会用相同 trace ID 或正文补猜来源。

限定为两个同机 Go/Gin 服务、每请求一次同步 HTTP 调用、受信任且完整的 span 导出、已配置读取/解码边界、固定四字节数组字段、关闭内联。当前不支持重试/重定向/扇出/缓存、任意 JSON 结构、跨 G 业务数据转移或任意未配置传播。严格拓扑检查可能将这些额外行为判为 unknown，这是本轮验证范围的限制。SDK 接入也不自动解决所有调用链丢失或上下文错误。

主机验收要求数据来源正确、两端采集完整并且都观察到自然并发作用域重叠。自然线程迁移次数如实报告，不强制发生。本轮不测性能，也不把本地 HTTP 成功当成 eBPF 来源推断成功。

## 开发回归

给已构建的目录设置 `GIN_OTEL_BUILD` 后，可重跑实际二进制规划与无 BCC 的原生 HTTP/SDK 测试：

```bash
GIN_OTEL_BUILD=/absolute/path/to/build \
  python3 -m unittest discover -s tests -p test_gin_otel_provenance.py -v
```

不设置该变量时，仅执行合成证据测试，明确跳过两个真实二进制测试。

官方接口说明：[otelgin](https://pkg.go.dev/go.opentelemetry.io/contrib/instrumentation/github.com/gin-gonic/gin/otelgin@v0.63.0)、[otelhttp](https://pkg.go.dev/go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp@v0.63.0)、[stdouttrace](https://pkg.go.dev/go.opentelemetry.io/otel/exporters/stdout/stdouttrace@v1.38.0)。
