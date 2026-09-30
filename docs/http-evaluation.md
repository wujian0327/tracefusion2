# 第一阶段：同步 HTTP 调用链还原与评测

## 固定问题

给定 front-end 的某次 `POST /orders` 响应对应的入口调用，恢复它关联的跨服务 HTTP 调用树。
包括 front-end→user 的前置查询，以及 orders→user/carts/payment/shipping 的聚合分支。
RabbitMQ、queue-master、worker、数据库和字段血缘均不参与这一阶段评分。

入口请求本身是查询条件；算法不知道该请求包含哪些后续调用。重复调用保留独立事件。
若某个 HTTP 调用是消息消费后产生的，其原始观测可以出现在输入中，但不属于同步订单树的真值。

## 数据来源与隔离

当前输入来自**现有探针 HTTP span 测量的白名单投影**，与真值共用插桩采集。
不是独立抓包、不是黑盒无侵入采集；也不证明以后可以在缺少插桩时采到完全相同的信息。
本阶段只检验在“有单次 HTTP 操作记录、没有跨请求关联标识”的条件下，能否正确组合调用链。

每个数据集包含：

| 路径 | 使用者 | 内容 |
| --- | --- | --- |
| `algorithm-input/observations.json` | 算法 | 所有范围内 HTTP 操作的独立观测 |
| `algorithm-input/queries.json` | 算法 | 可观察到的 front-end POST /orders 入口事件 |
| `oracle/reference.json` | 评分器 | 真值边、请求归属及私有 event↔span 映射 |
| `manifest.json` | 实验管理 | 范围、数据量、采集限制 |

只把 **algorithm-input/** 交给待测算法。源 ZIP、oracle、客户端记录、日志和 manifest 不属于算法输入。
这是文件和程序职责上的隔离，不是操作系统级访问沙箱。

观测字段固定为：

```json
{
  "event_id": "随机、独立的本地观测编号",
  "service": "orders",
  "kind": "CLIENT",
  "method": "GET",
  "path": "/cards/某个业务记录ID",
  "peer_service": "user",
  "start_us": 1790761976500000,
  "duration_us": 2500,
  "status_code": 200
}
```

`event_id` 不是原 span ID，也不由原 ID 哈希生成。CLIENT 与 SERVER 是两条独立观测，**没有共享匹配编号**。
服务名、路径、客户端目标主机和时刻来自本地操作元数据，不从真值边补出。
SERVER 的 peer_service 为 null，避免把真实调用方直接告诉算法。

不输出 traceId、spanId、parentId、线程 ID、导出批次、Header、请求/响应体、URL 查询串、测试夹具或订单归属。
导出器还扫描原始追踪 ID，遇到其泄漏到输入即失败。
保留全部范围内 HTTP 流量，包括健康检查、初始化、其他请求；**不先按真值筛出订单流量**。
JSON 行按随机观测 ID 排序，去除 exporter 的批次/trace 分组顺序。
查询入口只按可观察的服务、方向、方法和路径选择，再独立检查真值能否覆盖这些查询。

路径中的业务记录 ID 保留，它们属于当前可观察信息。这会让不同客户的请求较易区分；后续需要同一客户、多订单等场景检验歧义，不能从两笔不同客户订单推断普遍效果。

## 真值边的定义

从实际 parent span 关系得到 HTTP 操作之间的边，跳过中间 Java INTERNAL span，不用时间或字段匹配生成答案：

- `local`：同一服务的入站 SERVER 操作 → 它发起的出站 CLIENT 操作。
- `transport`：出站 CLIENT 操作 → 对应服务的入站 SERVER 操作。

例如一次 front-end→orders 调用包含两个节点和一条 transport 边；orders 内部向 user 发起请求，再产生 local 边。
这和只画“服务A→服务B”的聚合图不同：本评测区分重复调用的实例。
订单 HTTP 真值须通过父节点、无环、端点一致性和预期路径覆盖检查。不完整时拒绝导出评分答案。

## 不重新部署，处理已有 ZIP

在仓库根目录执行；输出目录和输出文件须尚不存在，以免覆盖先前结果。

```bash
python3 scripts/http_dataset.py /path/to/sockshop-trace-20260930-175156-cac0.zip --out artifacts/http-v1
python3 scripts/http_baseline.py artifacts/http-v1/algorithm-input --out artifacts/http-v1/prediction.json
python3 scripts/http_score.py --reference artifacts/http-v1/oracle/reference.json --prediction artifacts/http-v1/prediction.json --out artifacts/http-v1/metrics.json
```

也可以把第一条命令的 ZIP 路径换成解压后的运行目录。原结果不改写。
已有数据足以验证导出和评分；无需为了跑这三个命令再启动容器。

## 新采集

```bash
python3 scripts/sockshop_trace.py run --requests 10 --concurrency 4
```

追踪版默认 `--scope synchronous-http`；自动输出本轮 `http-evaluation/` 数据集并打入 ZIP。
`result.json` 的 status 只代表明确写出的 evaluation_scope；`full_trace_execution_status` 继续报告完整 trace 中的执行错误。
`oracle/callgraphs.json` 保存当前评测范围，`oracle/full-callgraphs.json` 保留包含消息和 worker 错误的完整视图。
原始 span、失败分支不删除。需要恢复全链验收时使用 `--scope full`。

现存 queue-master Docker worker 失败尚未修复；该故障被排除在 HTTP 评分范围之外，并不表示完整配送恢复正常。
后台故障可能影响运行负载，本轮不据此报告性能结论。

## 当前基线与指标

`http_baseline.py` 是用于打通流程的简单基线，不作为论文主算法：

1. 用服务目标、HTTP 方法、具体路径和时间区间为 CLIENT/SERVER 做一对一匹配。
2. 用同服务内时间包含关系，把出站请求分给最近开始的入站请求。
3. 分数相同则保留歧义、不靠随机 event ID 打破平局。

默认时钟容差 5000 微秒，可用 `--slack-us` 修改。固定容差用于处理本机不同插桩时钟精度，未针对当前两条 trace 调参。算法不读取 oracle。

评分按每个查询分别计算，避免把“边存在于另一笔订单”误判为正确：

- **调用边 Precision / Recall / F1**：同时评测 local 和 transport 边。
- **请求归属 Precision / Recall / F1**：某个观测是否被分配给正确的入口请求，排除已给定的根节点。
- **完整调用树匹配率**：预测边集合与真值完全相同的查询比例。

缺失预测查询按空结果计分；未知查询/事件 ID 被拒绝。无预测边时 precision 为 null、非空真值的 recall/F1 为 0。
随机观测编号仅用于比较节点身份；每个输出边都必须引用输入已有的事件编号。

## 对已有样本的实测结果

输入 `sockshop-trace-20260930-175156-cac0.zip`：85 条 HTTP 观测，2 个订单查询，每条参考树 21 个 HTTP 节点、20 条边。
同一 trace 的结构检查还保留了客户端根和必要 INTERNAL 祖先，因此结构报告的 23 个 span 与投影后的 21 个 HTTP 节点不是同一口径。

| 指标 | 简单时间基线 |
| --- | --- |
| 调用边 TP / FP / FN | 18 / 22 / 22 |
| 调用边 Precision / Recall / F1 | 45% / 45% / 45% |
| 请求归属 Precision / Recall / F1 | 50% / 50% / 50% |
| 完整调用树匹配率 | 0 / 2 |

这只是两笔重叠订单上的流程校验，不是统计充分的论文实验，不代表最终算法性能。它说明真值隔离后，简单时间关联确实会在并发请求之间分错调用；后续算法改进有可评分的对象。
