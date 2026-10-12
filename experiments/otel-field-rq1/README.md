# RQ1：OTel 调用链上的字段来源——第一条真实路径

2026-10-12。**本目录是新路径的原生工作负载与通信边界预检，不是已完成的字段溯源准确性实验。**
主实验定位及表格见 [RQ1 新计划](../../docs/rq1-otel-field-plan.md)。

## 冻结对象与查询

- 上游 Online Boutique v0.10.4，提交 `474d0f2eb73d97525234995a40d7781b7923a07d`。
- 正常优化的 Go 1.25.4 / Linux amd64；原版 gRPC 1.71.0、protobuf 1.36.6、OTel 1.35.0 / otelgrpc 0.60.0。
- 原始 `productCatalog.GetProduct` 与目录加载器运行在商品服务进程；
  原始 `checkoutService.prepOrderItems` / `convertCurrency` 运行在另一个进程。
- 源码及依赖锁不修改；测试驱动加入只读记录、SDK 导出器和 gRPC stats/interceptor。
  这是两个原始处理函数的跨进程工作负载，**没有使用原始完整服务启动和商店部署**。

来源从成功 `GetProduct` 返回的原始 `Product.price_usd.units/nanos` 开始，
目标是 checkout **发出的** `CurrencyConversionRequest.from.units/nanos`。
目录文件解码、商品选择的控制依赖、换汇服务内部计算、支付端接收字段均不在该查询范围。
来源身份保留目录记录、RPC 返回实例、字段和不可变版本；目标保留工作负载调用、商品序号及字段。
目标不是 `OrderResult` 或最终支付金额。

`cases.json` 在运行前冻结 15 个工作负载实例，8 种不同商品 ID 序列；
不是 15 个独立系统或 15 种独立输入。包括原目录中价格完全相同的 Tank Top 与 Candle Holder、
同一商品的重复读取、不同商品混合、空路径、缺失商品和 8 个并发实例。
缺失商品的原始错误行为保留，后续循环没有被驱动强制继续。

`contract.py` 在原生运行前从固定目录输入与预先登记的源码规则生成 56 个查询请求：
50 个应有目标，6 个无目标检查（空路径两个、两次缺失商品各两个）。
这是独立于传播引擎输出的源码推导标注，第二位研究者复核仍待完成。
本轮没有传播引擎输出，不将边界检查算作 TP/FP/FN 或准确率。

## 本轮验证了什么

1. 在两个 OS 进程间实际执行原版 gRPC/protobuf 请求与响应。
2. 由 SDK client/server span 的父子关系绑定商品 RPC，再用本进程的消息和字段对象指针绑定边界。
3. 核对原始 handler 返回的对象就是预先登记的目录记录，consumer 的 `From` 就是实际收到的 `PriceUsd`。
4. 在身份绑定后检查内容与独立输入一致；不以内容相同或时间接近建立来源关系。
5. 原始目录运行前后的内容不变；检查实际并发 span 重叠。
6. 缺失 span、重复 payload、错误父 span、同值不同目标对象、同价不同目录记录、缺失目标均被拒绝。

gRPC stats 提供的是实际收发后的**类型化 payload**和长度。
`snapshot_hex` 是该对象的确定性重新序列化，**不是 socket 原始字节捕获**；
内容一致性和长度核验不等于逐字节污点传播或序列化实现的独立准确性。

## 发现的上下文断点

原版 `convertCurrency` 使用 `context.TODO()`，不会把工作负载上下文交给换汇 RPC。
本轮同时观察到：出站目标处的上下文无有效 span；实际换汇 client span 成为新 trace 的根。
**不修补上游、不以相同金额补连 trace，也不声称 OTel 自己提供了字段来源关系。**
今后的算法必须利用服务内调用实例和对象/字段证据连接这一段，或另行披露上下文接入变体。
只靠 Trace ID 的连接器无法承担当前完整字段查询。

为让原始消费方法正常返回，checkout 进程另开一个测试专用换汇回显服务。
它不是原版 Node.js currencyservice，计算与响应不进入本查询真值或传播评分。
不能把此驱动称为完整 Go→Node.js 或完整支付链实验。

## 复现与只读复核

```bash
python3 experiments/otel-field-rq1/run.py \
  --source /path/to/clean/online-boutique-v0.10.4 \
  --go /path/to/go1.25.4/bin/go \
  --output artifacts/otel-field-rq1-new

python3 experiments/otel-field-rq1/verify.py artifacts/otel-field-rq1-new
```

输出目录必须不存在。首次构建需要原版依赖；运行器不修改来源 checkout，
在输出目录复制原包、添加测试驱动，构建与执行两个新工作负载。
只读复核检查源码摘要、重新生成冻结契约，从原始 JSONL 重新进行身份与内容核验，不执行采集二进制。

结果与保存证据见 [PREFLIGHT-RESULTS.md](PREFLIGHT-RESULTS.md)。
本环境没有 BCC，因此没有采集 eBPF 或运行既有还原器；外部工具也未运行。
下一验收是该路径的自动观测计划、非真值驱动还原、RPC 字段映射及外部同语义比较。
只有这些步骤通过，才向 RQ1 主准确性表填数。
