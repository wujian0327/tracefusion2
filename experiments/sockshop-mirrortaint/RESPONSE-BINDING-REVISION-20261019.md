# 响应目标绑定修订与冻结后覆盖验证

**本轮实现了统一响应目标绑定和显式 profile 选择，但没有解决全部自动来源查询。** 冻结版在 Train Ticket 的新入口测试中接纳 10/12 个查询，运行产生的 71 个目标实例全部已知且与独立真值一致；Sock Shop 的旧入口新字段测试虽接纳 8/10 个计划，24 个实际目标仍全部为 unknown。不能把规划接纳率当作来源查询成功率。

本轮没有新增性能实验，也不把旧版成本数字移用于修订版。业务继续使用原版 JAR。算法原理、公共库契约和实现入口见 [算法说明](RESPONSE-BINDING-ALGORITHM-20261019.md)，执行顺序见 [协议](RESPONSE-BINDING-REVISION-PROTOCOL-20261019.md)。

## 版本、开发集与封存集

| 阶段 | 版本或提交 | 用途 |
| --- | --- | --- |
| 原冻结算法 | `a84ce9d` | [首次覆盖 0/20](QUERY-COVERAGE-20261019.md)，永久保留 |
| 后续查询封存 | `402b8d4` | 在任何本轮算法改动前提交查询和选择规则 |
| 初始修订检查点 | `90a4a65` | 开发回归；保留暴露的多次写入、异常路径失败 |
| 最终算法冻结 | **`803b92f15653dd570bd6b2b21acb14b69da594ce`** | 开发回归后冻结，随后首次运行封存测试 |

原 20 个查询已被用于定位限制，是开发集。原候选池仍为 Sock Shop 37、Train Ticket 54，共 91 个，没有按规划结果增删候选。剩余 71 个候选中，封存 Sock Shop 10 个、Train Ticket 12 个，另有 49 个没有纳入本次测试。

Sock Shop 没有完全未用入口可留出，因此按预先 SHA256 排序选剩余 10 个字段，来自 3 个旧入口，只称“旧入口新字段”。Train Ticket 将 5 个完全未用入口的全部 12 个剩余目标纳入，称“新入口”。[封存文件](response-binding-heldout-20261019.json)的 SHA256 为 `f502e69c7a2f2635379a23376a1d8cdad776d022a324eaaaad89429ac694f21e`。拒绝查询没有替换，冻结后核心源码哈希全部保持一致。

这不是第三方盲测；应用、候选结构和输入模板由本项目审阅设计。封存避免了围绕这些目标修订算法，但不能消除作者对应用的已有认识。

## 首次封存测试结果

| 指标 | Sock Shop：旧入口新字段 | Train Ticket：新入口 |
| --- | ---: | ---: |
| 选中查询族 | 10 | 12 |
| 规划接纳 / 拒绝 | 8 / 2 | 10 / 2 |
| 接纳查询的真实请求 | 48 | 60 |
| 实际生成目标字段实例 | 24 | 71 |
| 已知 / unknown / 证据无效 | **0 / 24 / 0** | **71 / 0 / 0** |
| 未产目标的请求 N/A | 24 | 9 |
| 实际目标的可回答率 | **0/24（0%）** | **71/71（100%）** |
| 已知答案的实例完全匹配率 | N/A：没有已知答案 | **71/71** |
| 已知答案关系 TP / FP / FN | N/A：空样本 | **71 / 0 / 0** |
| 至少给出一个已知答案的查询族 | 0/10 | 10/12 |

列表目标按通配查询族选择，按实际元素实例评分，不能混用这两个分母。N/A 的单位为请求：例如空列表没有元素目标；一个请求可能产生多个字段实例。固定字段实际为 null 且出现在 JSON 中，仍是目标，不按 N/A 排除。证据无效与业务未生成目标分开，拒绝规划的查询不计作运行 unknown/N/A。

Sock Shop 的 4 个已运行查询族在本组输入中始终得到空的 customer.addresses/cards 列表；其余 4 个查询族产生 24 个字段实例，均为 unknown。必要 HATEOAS 读取证据或调用效果未建模，独立实例真值也不能从已有原始源消息字段唯一落地，因此另列 oracle unavailable=24。没有据此宣称 FP/FN 为零或空来源正确，也不声称这些列表对任意输入均不可达。

Train Ticket 覆盖 Route 的单次仓储返回、列表元素及字段，Station 的 getter→包装字段与入口参数回退，Train 的第二次仓储读取返回。每个目标都有独立实例真值。两个 Station 批量查询在 opcode132（IINC）处首先拒绝，原方法也含循环；没有修复这些指令后再覆盖首次结果。Sock Shop 两个查询在 opcode186（invokedynamic）处拒绝。

## 开发回归结果：单独报告

| 指标 | Sock Shop | Train Ticket |
| --- | ---: | ---: |
| 原开发查询族 | 10 | 10 |
| 接纳 / 拒绝 | 8 / 2 | 8 / 2 |
| 真实请求 | 48 | 52 |
| 实际目标实例 | 42 | 89 |
| 已知 / unknown / 证据无效 | 0 / 42 / 0 | 82 / 7 / 0 |
| N/A 请求 | 8 | 8 |
| 可回答率 | 0/42 | 82/89（92.13%） |
| 已知答案完全匹配 | N/A | 82/82 |
| 仅已知答案关系 TP / FP / FN | N/A | 75 / 0 / 0 |

Train Ticket 的 7 个已知答案是原业务写入的布尔常量（包含实际分支下的 true/false），数据来源为空；选择证据不计入数值/字段数据来源。另 7 个 unknown 是必要 helper/转换效果尚不能解释的 trainType.economyClass。若把 unknown 阳性也记为漏检，对全部 89 个独立真值目标的关系结果为 **TP75 / FP0 / FN7**；不能只引用条件准确率 100%。

Sock Shop 开发 unknown 的独立实例真值未能在当前采集边界下全部落地（oracle unavailable=42），不对这些实例给出关系准确率。开发与封存结果不合并为总体准确率。

## 本轮修改了什么

1. 新增响应目标绑定层：实际返回对象/包装结构/字段或元素与 JSON 路径必须核验一致。根方法没有 setter 不再单独构成拒绝理由；返回快照永远不充当来源。
2. 根据目标写入形态显式选择 profile；局部布尔/标量不再需要 Map.put。旧配置及复制、归约、集合 profile 保持兼容，新 `response_path` 配置使用统一入口。
3. 记录来源边界读取和不透明调用效果，按真实对象、字段、版本、根调用及消息区分实例；不能只据同值或同 trace 连接。
4. 修复 DTO 提前加载可能跳过写入插桩的问题；多次标量写入按版本分别建图；把原异常保护区内可能改变实际路径的调用纳入证据闭包。
5. 区分字段不存在/歧义与目标类型不支持。一般循环、任意共享修改、反射/native、任意序列化配置继续不在保证内。

每个查询仍声明入口、字段/JSON 路径和来源边界，共三类配置；没有为单个目标手写业务公式、传播代码或来源答案。Spring Data 读取返回、包装 getter、只读 List 和 Collections 等属于新增的人工公共库契约，不把它们包装成“完全无需人工模型”。Basic 沿用已有、固定版本的 JsonUtils 默认 Jackson 摘要。没有为了接纳查询增加逐业务 helper 白名单、删除 entry 或扩大到旧宽计划。

返回对象转发只能证明绑定关系；必要输入证据、局部计算或调用效果缺失时仍给 unknown。这正是本次 Sock Shop 结果揭示的剩余限制。

## 真实执行与真值方法

每个接受查询固定 6 组输入，包含多记录、同值字段、单记录、空库/空列表、更多记录及重复值；开发 Basic 另用 8 种正常/回退/上游失败模板。值在计划生成后生成，结构与选择规则预先固定，不依据答案调整。

真值依据原版 javap、实际数据库事实、客户端 JSON 及原始源调用/对象/字段/版本坐标；不运行 TF 的依赖传播或图连接来决定预期来源。仓储直接返回的列表按原业务顺序投影，并核对字段与实际数据库。Train.retrieve 的原逻辑两次 findById，预期明确选择第二次调用，不能选择第一个同值实体；Station.queryById 正常取 Station.name，缺失时按原代码取入口参数零。真值代码位于实验驱动，未进入冻结核心。

封存集真值规则在算法冻结后、首次业务运行前审阅并保存于 `heldout-first/runtime-protocol.json`。原有入口参数边界包含标量参数，运行评分配置显式纳入 argument 节点；没有把边界移到输出。实验驱动与核心分开留哈希。

本轮确实重新部署了开发查询和历史业务回归；后续修订仅影响特定离线节点/异常规划时，对 **15 个未变透传计划**复用捕获，要求计划字节和全部编译后 Agent 类哈希一致。历史六个计划亦要求完全相同；票价计划仍选择原 37 个调用，并验证新要求的异常调用已包含，只有算法/异常清单元数据变化。复算保留实际原 Agent、原计划哈希和 reuse.json，不把复算冒充新部署或新增独立重复。

## 语义与拒绝保护、历史回归

- 最终 9 组独立 JVM/真实 Jackson 小程序，54 次查询：48 次预期已知且来源匹配，6 次未建模必要 helper 保持 unknown；后者不是正确空来源。包含同值不同对象、重复调用、List/Map 坐标、分支、常量覆盖、多次 setter、未使用结果调用抛异常。
- 嵌套返回的 6 项拒绝检查（含同值自定义 serializer、缺失/歧义返回、缺失输入、错误对象与歧义消息）通过；另 5 项失败调用/handler/写入版本证据扰动通过。
- 原集合 full/selective 各10/10，小程序的 indexOf 篡改、接收集合修改和虚调用保护通过；27 项相关单元检查通过。
- 四个历史规划正控制继续 4/4；原版业务来源回归 Sock Shop **198/198、TP258**，Station 链路 **31/31、TP30**；真实票价 full/selective 各 **38/38、TP92**，FP/FN/unknown 均为0，另各2个目标 N/A。两版离线审计及原始捕获均保留。

开发中曾出现标量重复节点和未选择调用抛异常导致的证据无效，原失败记录保留于 `scalar-overwrite-first/`、`unused-exception-first/` 和 `development-01/`；修复后才冻结 `803b92f`。开发评分驱动也曾漏计 HTTP201 目标，原评价副本保留，最终从实际客户端响应重新枚举；该修正发生在封存业务测试前。没有覆盖旧冻结版的0/20，也没有根据封存结果改核心。

## 工件与复核

原始目录：`artifacts/response-binding-revision-20261019/`。关键入口为 `algorithm-freeze.json`、`audit.json`、`development-final/`、`heldout-first/`、`semantics-final/`、`additional-refusal-audit.json`、`legacy-offline-final/`、`price-offline-final/` 和 `logs/00…09`。`candidate-code-frozen.tar.gz` 与 `prototype-code-90a4a65.tar.gz` 保存源码，原始失败尝试不删除。

```bash
python3 experiments/sockshop-mirrortaint/audit_response_binding_revision.py \
  --root artifacts/response-binding-revision-20261019 \
  --development artifacts/response-binding-revision-20261019/development-final \
  --heldout artifacts/response-binding-revision-20261019/heldout-first
python3 experiments/sockshop-mirrortaint/audit_binding_refusals.py \
  --root artifacts/response-binding-revision-20261019
```

小型审计快照随 Git 保存，完整原始目录需另行备份。本轮本机备份入口为 `artifacts/response-binding-backup-20261019/START-HERE.txt`；它是同盘副本，不是异机冗余，也不包含 Docker 镜像层。迁移必须在新目录重新构建，不能盲用旧绝对路径。推送交给用户。

## 对论文主张的影响

当前证据支持：**在声明的默认框架/库契约下，能够自动为一部分 DTO/包装/元素返回和局部标量生成计划，并在部分新入口上给出经独立核验的实例来源。** 它不支持“任意响应字段都能自动回答”，也不支持修订版已经取得旧成本表中的优势。

下一步最有针对性的是为 Sock Shop 的实际 HATEOAS 读取和必要只读/保存/异步效果建立可核验的有限模型，再单独冻结、回归并保留新的未见查询。不能通过把源边界挪到输出或把所有 helper 当只读来消除 unknown。新增性能实验继续暂缓。

## 逐查询审计表

下面由最终 `audit.json` 生成。T/K/U/I 分别为实际目标、已知、unknown、证据无效；N/A 是请求数。拒绝项未运行。

### 开发集

| 查询 ID | 规划 | T/K/U/I | N/A请求 | 已知完全匹配 |
| --- | --- | --- | ---: | ---: |
| `sockshop-orders-newOrder-customer-firstName` | response-forward | 6/0/6/0 | 0 | N/A |
| `sockshop-orders-newOrder-customer-lastName` | response-forward | 6/0/6/0 | 0 | N/A |
| `sockshop-orders-newOrder-customer-addresses-each-country` | response-forward | 0/0/0/0 | 6 | N/A |
| `sockshop-orders-newOrder-address-number` | response-forward | 6/0/6/0 | 0 | N/A |
| `sockshop-orders-newOrder-address-country` | response-forward | 6/0/6/0 | 0 | N/A |
| `sockshop-carts-get-customerId` | response-forward | 6/0/6/0 | 0 | N/A |
| `sockshop-carts-get-quantity` | 拒绝：opcode 186 | — | — | N/A |
| `sockshop-carts-getItems-each-quantity` | response-forward | 6/0/6/0 | 1 | N/A |
| `sockshop-carts-getItems-each-unitPrice` | response-forward | 6/0/6/0 | 1 | N/A |
| `sockshop-carts-addToCart-unitPrice` | 拒绝：opcode 186 | — | — | N/A |
| `trainticket-station-query-data-each-id` | response-forward | 10/10/0/0 | 1 | 10/10 |
| `trainticket-station-query-data-each-name` | response-forward | 10/10/0/0 | 1 | 10/10 |
| `trainticket-basic-queryForTravel-data-status` | bounded-scalar | 7/7/0/0 | 1 | 7/7 |
| `trainticket-basic-queryForTravel-data-trainType-economyClass` | response-forward | 7/0/7/0 | 1 | N/A |
| `trainticket-ticketinfo-queryForTravel-data-trainType-id` | 拒绝：opcode 189 | — | — | N/A |
| `trainticket-train-query-data-each-confortClass` | response-forward | 10/10/0/0 | 1 | 10/10 |
| `trainticket-route-getRouteByStartAndTerminal-data-each-stations-each` | 拒绝：循环/回边 | — | — | N/A |
| `trainticket-route-getAllRoutes-data-each-distances-each` | response-forward | 30/30/0/0 | 1 | 30/30 |
| `trainticket-price-findByRouteIdAndTrainType-data-firstClassPriceRate` | response-forward | 5/5/0/0 | 1 | 5/5 |
| `trainticket-price-findAllPriceConfig-data-each-trainType` | response-forward | 10/10/0/0 | 1 | 10/10 |

### 首次封存集

| 查询 ID | 规划 | T/K/U/I | N/A请求 | 已知完全匹配 |
| --- | --- | --- | ---: | ---: |
| `sockshop-orders-newOrder-card-id` | response-forward | 6/0/6/0 | 0 | N/A |
| `sockshop-orders-newOrder-customer-addresses-each-postcode` | response-forward | 0/0/0/0 | 6 | N/A |
| `sockshop-carts-addToCart-quantity` | 拒绝：opcode 186 | — | — | N/A |
| `sockshop-orders-newOrder-customer-cards-each-ccv` | response-forward | 0/0/0/0 | 6 | N/A |
| `sockshop-orders-newOrder-customer-id` | response-forward | 6/0/6/0 | 0 | N/A |
| `sockshop-orders-newOrder-address-id` | response-forward | 6/0/6/0 | 0 | N/A |
| `sockshop-orders-newOrder-customer-addresses-each-street` | response-forward | 0/0/0/0 | 6 | N/A |
| `sockshop-orders-newOrder-customer-addresses-each-id` | response-forward | 0/0/0/0 | 6 | N/A |
| `sockshop-orders-newOrder-customer-username` | response-forward | 6/0/6/0 | 0 | N/A |
| `sockshop-carts-get-itemId` | 拒绝：opcode 186 | — | — | N/A |
| `trainticket-route-getRouteById-data-distances-each` | response-forward | 15/15/0/0 | 1 | 15/15 |
| `trainticket-route-getRouteById-data-id` | response-forward | 5/5/0/0 | 1 | 5/5 |
| `trainticket-route-getRouteById-data-startStationId` | response-forward | 5/5/0/0 | 1 | 5/5 |
| `trainticket-route-getRouteById-data-stations-each` | response-forward | 15/15/0/0 | 1 | 15/15 |
| `trainticket-route-getRouteById-data-terminalStationId` | response-forward | 5/5/0/0 | 1 | 5/5 |
| `trainticket-station-queryById-data` | field-copy | 6/6/0/0 | 0 | 6/6 |
| `trainticket-station-queryByIdBatch-data-each` | 拒绝：opcode 132 | — | — | N/A |
| `trainticket-station-queryForIdBatch-data-each` | 拒绝：opcode 132 | — | — | N/A |
| `trainticket-train-retrieve-data-averageSpeed` | response-forward | 5/5/0/0 | 1 | 5/5 |
| `trainticket-train-retrieve-data-confortClass` | response-forward | 5/5/0/0 | 1 | 5/5 |
| `trainticket-train-retrieve-data-economyClass` | response-forward | 5/5/0/0 | 1 | 5/5 |
| `trainticket-train-retrieve-data-id` | response-forward | 5/5/0/0 | 1 | 5/5 |

