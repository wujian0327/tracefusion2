# 验证记录

日期：2026-09-30。

## 基础版：已由用户主机验证

输入结果包：`sockshop-20260930-172440-405c.zip`。

- `result.json` 为 passed；11 个容器采集时均 running。
- `POST /orders` 返回 201；客户、购物项和金额 9.99 与夹具匹配。
- `/card` 返回后四位，订单响应含完整合成卡号与 CCV。
- 日志显示支付授权成功，queue-master 收到该测试客户的发货任务。
- 运行镜像摘要已在输入结果包中保存。

因此可称“11 组件订单路径已完成一次运行验证”，不能称最小部署，也不能据此声称已有完整调用链真值或字段血缘真值。

## 追踪版：本地已执行

- `python3 scripts/sockshop.py check`：原 11 组件静态检查通过。
- `python3 scripts/sockshop_trace.py check`：14 组件追踪配置静态检查通过。
- `python3 -m unittest discover -s tests -v`：18 项测试通过（包含后续错误分类修复）。
- 其中 HTTP 集成测试使用真实本机 HTTP 服务与子进程：8 个并发 Node 请求，每个发起并行和嵌套下游调用，验证 32 个 span 及 Header 关联未混串；代理保持响应与重复 Set-Cookie，正确替换不同大小写的旧 traceparent；真实采集器接受 gzip Zipkin 批次并保存、导出记录。
- 图检查测试覆盖缺失父节点、环、冲突 ID、重复导出、错误 trace、错误客户 ID、缺少消息 producer 关联及空集合不能通过结构验收；HTTP/应用错误与空值 Zipkin error tag 保留为独立的执行失败。
- 原有 6 项响应判定测试保持通过。
- Python 编译和 Node 语法检查通过。
- `python3 scripts/sockshop_trace.py run --out artifacts/trace-no-docker-check`：在无 Docker 环境按预期返回失败，保留诊断 ZIP。

Node 集成测试运行时为 **v24.19.0**，hook 使用 Node 4 兼容语法/API；这不能替代实际 Node 4 镜像的运行验证。

## 追踪版：用户主机回传与复核

输入：`sockshop-trace-20260930-175156-cac0.zip`。
SHA-256：`58474a764db5f1d2885b47cc16eaef24ac1dd9391969ba4977ef00799a61d618`。

- 两笔订单成功，均与各自夹具匹配；客户端订单区间确实重叠，overlapping_order_interval_pairs=1。
- 两条 trace 分别含 31 和 34 个独立 span；预期服务边、用户/地址/卡片/购物项接口均覆盖。
- 已记录 span 无缺失父节点、无环、无冲突 span ID；未检测到其他夹具 ID 混入。
- shipping producer 与 queue-master consumer 的父子关系实际存在。旧 Node 前端、Java HTTP 和消息传播在这次样本中工作。
- 共 4 个 error span，全部位于 queue-master：Docker 镜像拉取请求、容器创建请求，以及一个消费处理异常。异常指出 `/var/run/docker.sock` 不存在。
- 源码核对证实 ShippingTaskHandler 调用 DockerSpawner，后者尝试启动 worker。因此先前认为队列消费者无需 Docker socket 即可完成任务的判断不准确；baseline 的“收到任务”仅证明接收，不证明 worker 成功。

旧验证器把所有 error span 都归入 incomplete，混淆了“已记录到失败操作”和“缺失追踪数据”。修复后对原包离线复核：结构 status=passed，execution_status=failed；原 ZIP 保持不变，全部失败 span 与边仍保留，总运行结果仍不能标为成功。

这包可用作已观测的故障调用链样本，不能用作完整配送无故障基线。当前提交只修复状态分类和离线复核，没有改动 queue-master 的 worker 分支或补上 Docker 运行依赖。更大规模并发、重试语义、未执行路径及严格无遗漏性仍待验证。

## 边界

源码标签与旧镜像的构建对应关系尚未全部验证。运行的 `images.json` / `compose.lock.json`、agent SHA-256、采集代码 SHA-256 用于记录实际组合。user/payment 记录的是入口代理边界，不是 Go 内部或数据库 span。当前不包含字段传播真值、不包含链路重建算法、不报告算法准确率。
