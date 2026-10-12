# 第一条跨服务字段路径：原生边界预检结果

2026-10-12。**工作负载、OTel 商品 RPC 关联与字段对象边界检查通过。
字段来源推断器和外部工具均未在此路径运行，没有 RQ1 准确率或性能结果。**

对象为 Online Boutique v0.10.4，固定提交
`474d0f2eb73d97525234995a40d7781b7923a07d`；Go 1.25.4，Linux amd64，默认优化。
原始商品处理函数和原始 checkout 消费方法分别编译为两个测试驱动进程，真实 TCP gRPC 收发；
上游业务源码及 go.mod/go.sum 未修改。原始服务 startup 不在本驱动内。

| 本轮检查 | 数量/状态 |
| --- | --- |
| 工作负载执行实例 / 不同商品 ID 序列 | 15 / 8 |
| 并发工作负载 / 实际最大重叠根 span | 8 / 8 |
| 商品 RPC 尝试 | 27 |
| 成功 / 原始 NotFound 错误 | 25 / 2 |
| 预先登记的字段查询请求 | 56 |
| 已确认存在并检查边界的字段目标 | 50 |
| 无目标检查 | 6 |
| 商品 client/server SDK parentage | 27 次均绑定到各自请求实例 |
| 源记录对象、解码对象与出站 From 对象核对 | 25 条成功路径通过 |
| 换汇出站目标上下文缺失 | 25 / 25 |
| 实际换汇 RPC 开始独立 trace | 25 / 25 |
| 损坏/缺失证据拒绝检查 | 6 / 6 |

两次 NotFound 后原函数退出；缺失商品没有出站换汇字段。
空工作负载的两个查询模板也无目标，这六项不计为字段答案或 TP。
同价的 Tank Top 与 Candle Holder 来自原始目录，没有改数据制造同值。
重复读取同一目录对象通过不同 RPC span 区分返回实例；跨进程地址不相互比较。

来源边界在原始 GetProduct 成功返回之后、protobuf 编码之前；
目标是 checkout 发出的 Convert 请求字段，而非真实 currencyservice 的接收字段或最终支付金额。
为完成驱动，换汇使用测试专用回显服务，范围外；没有运行原版 Node.js 换汇逻辑。

## 重要发现

原始 `convertCurrency` 的 `context.TODO()` 导致目标处无有效当前 span，
换汇 RPC 的 OTel client span 有新的 Trace ID 且没有 parent。
验证器使用测试专用的调用归属及实际对象别名检查这一步，不按相同价格补连 trace。
这些只读验证证据不能拿来当作已实现的自动 Go/eBPF 归属和来源还原。

数据快照来自实际 gRPC stats 的类型化 payload；snapshot_hex 是重新序列化。
身份先由 SDK parentage 与本进程对象绑定，随后检查 snapshot 一致，
**没有通过序列化内容相同来建立消息身份，也没有记录原始 socket 字节标签。**

只读拒绝检查分别破坏 server span、重复请求 payload、remote parent、
同值目标对象、同价源目录对象和目标记录；全部被拒绝。
它们是对保存记录的离线破坏，不增加原生工作负载或独立业务用例数。

## 可复核证据

- 汇总：[native-preflight-20261012.json](native-preflight-20261012.json)。
- 无可执行二进制证据包：[native-evidence-20261012.zip](native-evidence-20261012.zip)。
- 证据包 SHA-256：`26d554811addc149d8bde8c1e8cdf63a61abdb5b84f14abacba53f9c0415cc27`，112,030 字节。

包内保留原始双进程 JSONL、运行前冻结的查询契约、上游源码摘要、实际编译的源码与驱动、
原生 stdout 和构建/运行命令。只读复核只解析 JSON 与源码摘要，不执行包内代码。

```bash
python3 -m zipfile -e experiments/otel-field-rq1/native-evidence-20261012.zip artifacts/rq1-evidence
python3 experiments/otel-field-rq1/verify.py artifacts/rq1-evidence
```

预计状态 `verified_native_boundary_preflight`。它不是 `provenance_verified`。
本环境没有 BCC；自动观测计划、eBPF 实际采集、非真值驱动还原、外部比较及选择性采集待完成。
源码推导的关系契约尚需第二位研究者审核。
