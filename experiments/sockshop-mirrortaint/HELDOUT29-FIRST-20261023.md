# 冻结后的29个新字段首次覆盖验证

核心保持 `76d2050`，先提交协议 `dfd9195`，随后规划和首次执行。原91个候选（Sock Shop37、Train Ticket54）中62个已用于开发，本轮纳入剩余全部29个（Sock Shop7、Train Ticket22），不按结果替换。它们来自8个已见入口，全部属于“旧入口新字段”，不作为新入口或第三方盲测证据。

## 端到端结果

| 配置 / 应用 | 查询族 | 请求（含N/A） | N/A请求 | 目标实例 | 已独立核验正确 | unknown | 已知错误 | 证据无效 | 真值不足 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| full/sockshop | 7 | 42 | 12 | 30 | 18 | 12 | 0 | 0 | 12 |
| full/trainticket | 22 | 148 | 29 | 214 | 214 | 0 | 0 | 0 | 0 |
| selective/sockshop | 7 | 42 | 12 | 30 | 18 | 12 | 0 | 0 | 12 |
| selective/trainticket | 22 | 148 | 29 | 214 | 214 | 0 | 0 | 0 | 0 |
| mirrortaint/sockshop | 7 | 42 | 12 | 30 | 18 | 0 | 0 | 0 | 12 |
| mirrortaint/trainticket | 22 | 148 | 29 | 214 | 192 | 5 | 17 | 0 | 0 |

计数单位为查询族－请求及实际元素实例；MirrorTaint按入口一次捕获可评多字段，因此表中基线请求为查询请求数，不能当作独立HTTP部署请求数。固定null若出现在响应中仍是目标，空列表无元素才记N/A。真值不足不等于unknown：已知但未核验的答案单列known_unchecked，不计为正确。

- full/all: 232/244目标得到独立正确答案；已知答案率232/244（含错误及未核验答案），已知且可核验答案匹配232/232；24/29查询族至少一个正确答案；关系TP/FP/FN=225/0/0（真值不足目标不计关系分母）。
- selective/all: 232/244目标得到独立正确答案；已知答案率232/244（含错误及未核验答案），已知且可核验答案匹配232/232；24/29查询族至少一个正确答案；关系TP/FP/FN=225/0/0（真值不足目标不计关系分母）。
- mirrortaint/all: 210/244目标得到独立正确答案；已知答案率239/244（含错误及未核验答案），已知且可核验答案匹配210/227；22/29查询族至少一个正确答案；关系TP/FP/FN=203/10/22（真值不足目标不计关系分母）。

## 逐查询结果

| 查询 | full：正确/目标 | selective：正确/目标 | MirrorTaint：正确/目标 |
| --- | ---: | ---: | ---: |
| `sockshop-orders-newOrder-id` | 0/6 {'unknown': 6} | 0/6 {'unknown': 6} | 0/6 {'known_unchecked': 6} |
| `sockshop-orders-newOrder-customerId` | 0/6 {'unknown': 6} | 0/6 {'unknown': 6} | 0/6 {'known_unchecked': 6} |
| `sockshop-orders-newOrder-customer-addresses-each-city` | 0/0 {} | 0/0 {} | 0/0 {} |
| `sockshop-orders-newOrder-customer-cards-each-id` | 0/0 {} | 0/0 {} | 0/0 {} |
| `sockshop-orders-newOrder-address-street` | 6/6 {'known_correct': 6} | 6/6 {'known_correct': 6} | 6/6 {'known_correct': 6} |
| `sockshop-orders-newOrder-address-city` | 6/6 {'known_correct': 6} | 6/6 {'known_correct': 6} | 6/6 {'known_correct': 6} |
| `sockshop-orders-newOrder-card-ccv` | 6/6 {'known_correct': 6} | 6/6 {'known_correct': 6} | 6/6 {'known_correct': 6} |
| `trainticket-basic-queryForTravel-data-percent` | 7/7 {'known_correct': 7} | 7/7 {'known_correct': 7} | 7/7 {'known_correct': 7} |
| `trainticket-basic-queryForTravel-data-trainType-confortClass` | 7/7 {'known_correct': 7} | 7/7 {'known_correct': 7} | 0/7 {'known_wrong': 7} |
| `trainticket-ticketinfo-queryForTravel-data-status` | 7/7 {'known_correct': 7} | 7/7 {'known_correct': 7} | 7/7 {'known_correct': 7} |
| `trainticket-ticketinfo-queryForTravel-data-percent` | 7/7 {'known_correct': 7} | 7/7 {'known_correct': 7} | 7/7 {'known_correct': 7} |
| `trainticket-ticketinfo-queryForTravel-data-trainType-economyClass` | 7/7 {'known_correct': 7} | 7/7 {'known_correct': 7} | 7/7 {'known_correct': 7} |
| `trainticket-ticketinfo-queryForTravel-data-trainType-confortClass` | 7/7 {'known_correct': 7} | 7/7 {'known_correct': 7} | 7/7 {'known_correct': 7} |
| `trainticket-ticketinfo-queryForTravel-data-prices-confortClass` | 7/7 {'known_correct': 7} | 7/7 {'known_correct': 7} | 7/7 {'known_correct': 7} |
| `trainticket-ticketinfo-queryForTravel-data-message` | 0/0 {} | 0/0 {} | 0/0 {} |
| `trainticket-train-query-data-each-id` | 10/10 {'known_correct': 10} | 10/10 {'known_correct': 10} | 10/10 {'known_correct': 10} |
| `trainticket-train-query-data-each-averageSpeed` | 10/10 {'known_correct': 10} | 10/10 {'known_correct': 10} | 10/10 {'known_correct': 10} |
| `trainticket-route-getRouteByStartAndTerminal-data-each-id` | 10/10 {'known_correct': 10} | 10/10 {'known_correct': 10} | 10/10 {'known_correct': 10} |
| `trainticket-route-getRouteByStartAndTerminal-data-each-distances-each` | 30/30 {'known_correct': 30} | 30/30 {'known_correct': 30} | 20/30 {'known_correct': 20, 'known_wrong': 10} |
| `trainticket-route-getRouteByStartAndTerminal-data-each-startStationId` | 10/10 {'known_correct': 10} | 10/10 {'known_correct': 10} | 10/10 {'known_correct': 10} |
| `trainticket-route-getAllRoutes-data-each-id` | 10/10 {'known_correct': 10} | 10/10 {'known_correct': 10} | 10/10 {'known_correct': 10} |
| `trainticket-route-getAllRoutes-data-each-stations-each` | 30/30 {'known_correct': 30} | 30/30 {'known_correct': 30} | 30/30 {'known_correct': 30} |
| `trainticket-route-getAllRoutes-data-each-terminalStationId` | 10/10 {'known_correct': 10} | 10/10 {'known_correct': 10} | 10/10 {'known_correct': 10} |
| `trainticket-price-findByRouteIdAndTrainType-data-id` | 5/5 {'known_correct': 5} | 5/5 {'known_correct': 5} | 0/5 {'unknown': 5} |
| `trainticket-price-findByRouteIdAndTrainType-data-routeId` | 5/5 {'known_correct': 5} | 5/5 {'known_correct': 5} | 5/5 {'known_correct': 5} |
| `trainticket-price-findByRouteIdAndTrainType-data-basicPriceRate` | 5/5 {'known_correct': 5} | 5/5 {'known_correct': 5} | 5/5 {'known_correct': 5} |
| `trainticket-price-findAllPriceConfig-data-each-routeId` | 10/10 {'known_correct': 10} | 10/10 {'known_correct': 10} | 10/10 {'known_correct': 10} |
| `trainticket-price-findAllPriceConfig-data-each-basicPriceRate` | 10/10 {'known_correct': 10} | 10/10 {'known_correct': 10} | 10/10 {'known_correct': 10} |
| `trainticket-price-findAllPriceConfig-data-each-firstClassPriceRate` | 10/10 {'known_correct': 10} | 10/10 {'known_correct': 10} | 10/10 {'known_correct': 10} |

## 实验有效性与边界

所有29个计划均由冻结规则选择；没有新增业务传播公式、库摘要或核心语义。单查询仍需入口、目标和来源边界三类声明，运行策略由公共静态规则选择。

full/selective在已完成的对齐目标上，状态或关系数量差异为0；这不能以跨部署同值代替物理实例检查，正确答案均先在各自捕获中独立核验。
实际业务ObjectMapper定义有8份原生类哈希审计。MirrorTaint原作者传播JAR与v09适配器二进制未变，仅隔离导出器私有Jackson；本组为新固定配置结果，历史368个正确实例集合仍单列。

Orders生成ID与self-link的独立物理坐标在预注册协议中明确未获保证，若不足继续报告oracle_unavailable，不能把未知来源当空。嵌套字段沿实际解码对象与版本核验。Basic percent按原代码的默认值/常量赋值评空输入数据来源；TicketInfo字段沿实际Basic响应投影。来源规则不调用TF传播或基线标签。

Orders基线首次启动因驱动移除业务JAR挂载而退出，未执行测试请求；失败目录永久保留。修正仅恢复同一原版JAR挂载，在native-orders-packaging-correction单独捕获，未改算法、输入规则或真值，不覆盖首轮。

未根据这批查询结果修改核心。旧62查询428/431及旧成本结果原样保留；本组不是最终优化版能力复验，也不建立当前版本外部成本排名。

原始工件见 `artifacts/heldout29-first-20261023/`；首次捕获、失败、计划、独立真值、预测、机器/镜像及类加载证据保留。Git只保存小型摘要，完整数据需单独备份。

Route过滤id首次评分因真值函数将数据库_id写成id而报KeyError。原始捕获和首次known_unchecked评分保留，independent-id-projection-correction仅按预注册仓储字段投影修正评分键，不调用TF传播、不重新部署、不改核心，不记作算法提升。
原始selective首次评分状态（修正前）：{'known_correct': 222, 'known_unchecked': 10, 'unknown': 12}；full相同。评分修正影响每模式10个目标，其余评分未替换。
全部analysis_limited、known_unchecked等状态详见JSON/CSV，不合并成N/A或正确。

## 逐实例能力差异

按相同查询、输入case及实际目标路径对齐：{'known_unchecked -> unknown': 12, 'known_correct -> known_correct': 210, 'known_wrong -> known_correct': 17, 'unknown -> known_correct': 5}。本组基线正确的210个目标全部被TF正确回答；另17个基线错误和5个基线unknown目标由TF正确回答。12个真值不足目标仍无法作能力优劣判断。该结论仅限本轮固定任务及适配配置。

两个可复核的差异：Route同值距离列表中，基线将/data/0/distances/1连到了源/0/distances/0（实际应为/0/distances/1）；Basic.confortClass的7个实例给出空来源而实际应来自Train响应字段。这里记录观测到的错位/漏关系，不据此断言其全部内部成因。基线的5个unknown属于PriceConfig.id，不能按空来源算成功。
