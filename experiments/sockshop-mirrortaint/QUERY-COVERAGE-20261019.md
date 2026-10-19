# 冻结后的新查询覆盖结果

后续[响应目标绑定修订与封存测试](RESPONSE-BINDING-REVISION-20261019.md)已完成。本文仍完整保留原冻结算法首次0/20结果；这20个查询在后续修订中已作为开发集，不再称为未见查询。

**首次覆盖结果：Sock Shop与Train Ticket各预先选定10个新查询，当前冻结规划接口均拒绝；默认接受率与加入固定显式集合profile后的接受率均为0/10。** 本轮没有修改规划器、Agent、还原器或库摘要，也没有把拒绝查询换成成功查询。结果说明现有自动规划入口的适用范围比此前已选支持路径更窄，应作为论文负结果保留。

算法冻结于`a84ce9de4c970c667e340da9de58e345574a7acf`；[协议](QUERY-COVERAGE-PROTOCOL-20261019.md)、[完整候选池及选择结果](query-coverage-pool-20261019.json)在首次规划前提交为`dfd929c`。算法实际从冻结源码副本执行。原始工件为`artifacts/query-coverage-first-20261019/`，包含源码归档、9个原版业务JAR、依赖/配置哈希、原始javap、全部尝试与回溯。以下均是首次覆盖结果，不混入修复回归。

## 候选与选中数量

候选来自人工审阅的19个公开业务响应端点契约，随后按原JAR的声明展开响应叶字段、列表查询族和已知Map键。目录不包括健康/欢迎接口、协议包装status/msg、鉴权管理写接口以及没有可声明字段的标量/void响应；它不是应用所有API的普查。Basic的`TravelResult.status`属于业务载荷，不是被排除的`Response.status`协议元数据。

| 应用 | 展开后目标 | 排除历史查询/显式诊断目标 | 最终候选 | 选中 | 未选候选 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Sock Shop | 49 | 12 | 37 | 10 | 27 |
| Train Ticket | 56 | 2 | 54 | 10 | 44 |

按服务名轮转，各服务内部按预先固定的SHA256顺序排序，每应用取10个；没有按规划结果筛选。候选不足的服务不制造重复目标：Shipping的两个字段已是历史查询，全部排除。列表下标只构成一个通配查询族，没有逐下标扩充查询数量。

| 服务 | 候选数 | 选中数 |
| --- | ---: | ---: |
| Sock Shop Carts | 10 | 5 |
| Sock Shop Orders | 27 | 5 |
| Sock Shop Shipping | 0 | 0 |
| Train Ticket Basic | 6 | 2 |
| Train Ticket Price | 10 | 2 |
| Train Ticket Route | 15 | 2 |
| Train Ticket Station | 6 | 2 |
| Train Ticket TicketInfo | 9 | 1 |
| Train Ticket Train | 8 | 1 |

“新查询”指相对所保留开发记录新声明/评价的入口＋目标字段路径，而非作者从未见过其类或字段。部分字段曾是旧实验的输入来源或被默认快照采集；不把这种测试称为第三方盲测。已明确诊断过的Carts `Item.id`被排除，候选草稿修订及当时规划调用数0的记录保留。旧查询换值不算新查询，已查询的total、Item返回字段、Shipment字段和价格Map键没有进入对应旧入口的新目标计数。

## 规划与运行分母

| 指标 | Sock Shop | Train Ticket |
| --- | ---: | ---: |
| 选中查询 | 10 | 10 |
| 默认流程接受 | 0 | 0 |
| 固定显式集合profile新增接受 | 0 | 0 |
| 最终规划拒绝 | 10 | 10 |
| 实验驱动异常 | 0 | 0 |
| 规划接受率 | 0/10 | 0/10 |
| 新查询业务请求执行 | 0 | 0 |
| 运行后已知目标实例 | 0 | 0 |
| 运行后unknown目标实例 | 0 | 0 |
| 运行后未产目标N/A | 0 | 0 |
| 运行后证据无效实例 | 0 | 0 |
| 实际生成目标的可回答率 | N/A：无运行样本 | N/A：无运行样本 |
| 已知答案来源实例完全匹配率 | N/A：无已知答案 | N/A：无已知答案 |
| 已知答案关系TP / FP / FN | 0 / 0 / 0，空样本 | 0 / 0 / 0，空样本 |

所有查询均在规划阶段拒绝，按预先协议及用户要求没有强行部署、设计输入或将已有捕获冒充新计划运行。运行计数0表示没有该阶段样本，不表示运行成功、未产目标或来源正确。20个未执行拒绝查询单列，不能将其计为20个unknown、N/A或20个运行错误。本次不能提供新目标的运行后来源实例正确性证据；条件准确率不写100%。

## 全部逐查询结果

每查询固定尝试：默认`plan_service→copy_plan`，以及独立的显式`plan_collection`。三函数各实际执行20次，共60个拒绝记录，全部保留；下表为原因缩写，原始错误文本、query规范、模型与traceback在各查询目录和[结果快照](query-coverage-first-20261019.json)。

原因：S1＝没有支持的目标写入或身份返回；S2＝默认CFG/路径界限；S3＝该标量profile未接纳目标类型；C1＝没有自动字段复制绑定；C2＝路径界限；C3＝不支持回边；L1＝没有直接目标setter；L2＝不支持invokedynamic（opcode186）；L3＝不支持ANEWARRAY（opcode189）；L4＝目标切片没有Map结果修改；L5＝不支持循环/回边。

| 应用/服务与入口 | 目标响应路径 | plan_service | copy_plan | plan_collection |
| --- | --- | --- | --- | --- |
| Sock Shop Carts ItemsController.get | /quantity | S1 | C1 | L2 |
| Sock Shop Orders.newOrder | /address/number | S1 | C1 | L1 |
| Sock Shop Carts.getItems | /*/quantity | S1 | C1 | L1 |
| Sock Shop Orders.newOrder | /customer/addresses/*/country | S1 | C1 | L1 |
| Sock Shop Carts.getItems | /*/unitPrice | S1 | C1 | L1 |
| Sock Shop Orders.newOrder | /address/country | S1 | C1 | L1 |
| Sock Shop Carts.addToCart | /unitPrice | S1 | C1 | L2 |
| Sock Shop Orders.newOrder | /customer/firstName | S1 | C1 | L1 |
| Sock Shop Carts CartsController.get | /customerId | S1 | C1 | L1 |
| Sock Shop Orders.newOrder | /customer/lastName | S1 | C1 | L1 |
| Train Ticket Basic.queryForTravel | /data/status | S2 | C2 | L4 |
| Train Ticket Price.findByRouteIdAndTrainType | /data/firstClassPriceRate | S1 | C1 | L1 |
| Train Ticket Route.getRouteByStartAndTerminal | /data/*/stations/* | S3 | C3 | L5 |
| Train Ticket Station.query | /data/*/name | S1 | C1 | L1 |
| Train Ticket TicketInfo.queryForTravel | /data/trainType/id | S1 | C1 | L3 |
| Train Ticket Train.query | /data/*/confortClass | S1 | C1 | L1 |
| Train Ticket Basic.queryForTravel | /data/trainType/economyClass | S2 | C2 | L1 |
| Train Ticket Price.findAllPriceConfig | /data/*/trainType | S1 | C1 | L1 |
| Train Ticket Route.getAllRoutes | /data/*/distances/* | S3 | C1 | L1 |
| Train Ticket Station.query | /data/*/id | S1 | C1 | L1 |

不能把三列原因相加当作60个查询。按函数统计：plan_service为S1×16、S2×2、S3×2；copy_plan为C1×17、C2×2、C3×1；plan_collection为L1×15、L2×2、L3×1、L4×1、L5×1。

## 拒绝说明了哪些具体限制

1. **端到端入口绑定范围有限。** 多个目标由仓储返回、已有对象或嵌套响应转发形成，根方法没有当前规则要求的局部目标字段写入/直接setter，默认与复制规划均无法生成绑定，集合profile也没有补齐这类目标。不能把“目标不在支持的局部写入形态中”解释为不存在该业务字段。
2. **集合profile不是通用回退。** Basic原方法的价格Map是已有支持路径，但同方法中的业务布尔字段status仍被“需要Map结果修改”的限制拒绝。旧路径正确不能推出新目标自动被支持。
3. **指令与控制流限制真实存在。** 新选择的Cart入口含invokedynamic，TicketInfo入口含对象数组创建，Route查询含回边；当前显式集合profile分别拒绝这些形态。默认路径枚举仍会在Basic方法上达到界限，不能把集合profile的定义合并能力推广到所有profile。
4. **目标类型与表示需要区分。** Route的List字段确实存在；默认标量规划器的“Target field is absent or ambiguous”在此表示类型/匹配资格受限，不是JAR缺字段。TicketInfo的响应形状来自Basic RPC，泛型反序列化可能产生Map，目录中的DTO字段是形状声明，不是运行时对象类型已得到证明。本轮没有运行样本，不能声称已建立这些嵌套JSON目标到运行时字段的绑定。

这些是冻结查询到计划接口的覆盖结果，不是对所有可能观测策略的不可回答性证明。显式`transport-boundary`在现有构建器中用于没有局部entry的配置；本轮固定的带entry默认流程不会自动把新目标分类为纯边界转发。现有较宽计划生成的日志是否还能回答某些新查询，是另一个问题，不能偷偷换成旧宽计划并将其计为本轮规划成功。

## 配置与独立核验

人工先审阅19个端点的入口与返回形状，候选叶字段展开和选择由脚本完成。每查询保留三组声明：入口、目标字段/JSON路径、来源边界；业务JAR按服务共用。两个profile尝试顺序是所有查询共享的固定配置，没有逐查询试后调参。为模型提取所需的公共Response/JsonUtils类使用既有依赖与摘要，所增加核心实现、库摘要、业务JAR修改均为0。该计数是配置项目数，不是人工工时；完整记录可检查实际配置量。

来源边界预先限定为入口参数、仓储返回后具体实体字段/元素读取、实际下游RPC响应读取，排除数据库历史，选择依赖另存。因无接受计划，本轮未建立运行用例或独立来源oracle，不声称完成新查询实例正确性；若后续版本接受这些查询，应在新版本冻结并保存可执行边界与独立真值，不能回填本轮。

为排除驱动或模型提取失效，在相同冻结源码、相同模型构建方式下检查四个历史查询，**4/4接受**：Orders.total、Shipment.name、Station.queryForId的数据字段、Basic价格Map。这里只重做必要的规划正控制；旧业务正确性原始工件直接复用，没有机械重部署，也不计入新目标接受率。

独立审计不导入TF算法，核验候选去重、选择顺序、Git预注册池哈希、20项结果完整性、60次尝试与异常证据、20个原字段声明、9个JAR及冻结源码/依赖哈希。删掉一条查询的内存负控制被拒绝。该审计是人口与工件完整性核验，不替代未发生的运行正确性审计。[审计回执](../../artifacts/query-coverage-first-20261019/independent-audit.json)。

## 复现与结论调整

在具备原始工件的本机，可只读复核：

```bash
python3 experiments/sockshop-mirrortaint/audit_query_coverage.py --out artifacts/query-coverage-first-20261019
```

原实验目录不可覆盖重跑。若需再次规划，复制冻结归档、JAR、inventory、pool和对应封印至全新目录，保留原规划结果；使用同版本驱动的`plan --out 新目录`，并重新准备源码副本的artifacts路径。修复版必须另冻结、另报告。完整归档见[恢复说明](../../artifacts/query-coverage-backup-20261019/START-HERE.txt)；该归档仍是同盘材料，需单独复制，Git不包含大工件。

论文应保留此前两应用选定路径的正确性与成本结论，同时将自动规划表述限定为当前支持的查询形态。**本轮不支持“开发后任选新字段即可自动处理”或广泛新查询覆盖的结论。** 91个候选中仅20个被按协议选中并测试，不能据此断言其余71个也拒绝；样本按服务轮转，不能当作所有字段的均匀随机样本。

本轮没有扩展支持、修复原算法或进行新的成本扫描。最高优先级的首次覆盖测量与负结果已保存；在安排新运行及查询专门化成本实验前，应先决定论文保留此窄范围，还是单独预注册规划入口修复与回归。首轮0/20不得被任何后续修复结果覆盖。
