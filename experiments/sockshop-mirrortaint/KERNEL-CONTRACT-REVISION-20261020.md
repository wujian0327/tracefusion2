# 公共契约接入与对象数组阶段结果

**统一内核已恢复原版Cart读取能力，并通过有限Supplier和对象数组语义测试；原36个基线领先实例仍全部被规划拒绝。** 冻结核心为 `ade72a8d5c594cbd60be1c43041d01c1675c148e`。本阶段没有新增修复基线差距，开发台账继续为原169个中已修复60个、剩余109个；不能把Cart能力恢复或小程序成功计入新增真实业务覆盖。

本轮不跑性能实验，不扩展Orders保存、异步或Date。29个未测候选继续封存，原62查询的431目标结果与成本表不改写。算法机制见[公共契约与对象数组说明](KERNEL-CONTRACT-ALGORITHM-20261020.md)，预先支持范围与选择规则见[阶段协议](kernel-contract-protocol-20261020.json)，逐实例结果见[36实例CSV](kernel-contract-gap-instances-20261020.csv)。

## 冻结与验收顺序

协议先提交为 `7b4d9fd`，随后才修改内核。最终核心冻结为 `ade72a8`，`algorithm-freeze.json` 保存41个核心或协议文件哈希、九个原业务JAR哈希及29候选封存协议哈希。冻结后核心哈希未变。

开发失败和开发成功均保留。冻结后重新在新目录编译Agent，用原版JAR部署Cart与Station/Route；每个套件先运行full，再运行selective。共13次冻结后服务容器部署：Cart准备1次、读取2次、创建保护2次、循环回归8次。套件使用独立端口与数据卷，可并行执行正确性检查，不据此推断性能。

新内核查询统一开启 `execution_kernel` 和 `application_calls`，没有为单个字段挑选成功策略。旧profile继续保留，本轮并未宣称自动路由已可替代全部旧配置。

## Cart读取能力恢复

任务为原 `ItemsController.getItems → /*/itemId` 六组已使用输入。本轮仅恢复旧read-forward已经正确的能力。

| 配置 | 请求 | 实际目标 | 已知且实例来源完全匹配 | TP / FP / FN | unknown / 无效 |
| --- | ---: | ---: | ---: | --- | --- |
| full | 6 | 6 | 6/6 | 6 / 0 / 0 | 0 / 0 |
| selective | 6 | 6 | 6/6 | 6 / 0 / 0 | 0 / 0 |

每种配置实际进入5类方法、30个应用Frame：ItemsController、CartsController、CartResource、实际DAO实现和FirstResultOrDefault。顺序流与非空Optional使用同一公共契约入口；回退lambda创建后没有执行。最终来源来自本次实际仓储读取返回的Cart.items元素字段，不来自输出快照。

独立真值按原业务逻辑定位本次唯一非空仓储返回，再依据实际容器路径 `/0/items` 加客户端元素路径选择原始字段，核对客户端值、源调用、对象、字段、版本和消息坐标。评分不调用TF传播或图连接来决定预期来源。

## 空Optional与保存回退保护

full和selective各使用全新数据卷，针对同一个customerId连续GET两次。两次返回的customerId数值相同，来源调用不同。

| 请求 | 原业务执行 | 每种配置结果 | 独立预期来源 |
| --- | --- | --- | --- |
| 首次GET | 空读取、执行回退、创建与保存、再次读取 | 1个unknown | 本请求第二次仓储读取返回的customerId |
| 后续GET | 读取已有Cart | 1个已知且完全匹配 | 本请求第一次仓储读取返回的customerId |

必要保存效果及回退中的递归链仍未解释，首次请求没有被强行改成known。原声明边界是仓储读取返回，不能把入口参数重新作为首次GET的最终来源。这组是已暴露查询的保护输入，不是新增未见查询或新增差距修复。

## 36个差距实例的逐查询复测

重用原能力对照中的实际输入、响应、原始消息与独立真值，先对全部六个查询生成统一策略计划。六个查询均在部署前拒绝，因此没有机械重启业务，也不把36个拒绝目标写成运行unknown或N/A。full/selective共用相同计划与支持条件。

| 查询 | 原实际目标 | 本轮规划 | 第一阻断 |
| --- | ---: | --- | --- |
| Cart.get → quantity | 5 | 拒绝 | FoundItem构造器第4条指令调用Object.getClass，超出现有窄参数赋值构造器模型 |
| Cart.get → itemId | 5 | 拒绝 | 同上 |
| Cart.get → unitPrice | 5 | 拒绝 | 同上 |
| TicketInfo.queryForTravel → trainType.id | 7 | 拒绝 | HttpEntity构造器尚未建模 |
| 同入口 → prices.economyClass | 7 | 拒绝 | 同上 |
| 同入口 → trainType.averageSpeed | 7 | 拒绝 | 同上 |
| 合计 | **36** | **36个对应目标仍不可回答** | **新增真实正确答案0** |

Cart构造器随后还包含LoggerFactory调用。其GET路径另含绑定Predicate、Stream.filter和异常Supplier；本轮只记录Predicate创建，没有解释过滤执行。Object.getClass在普通已解释方法内已有窄JVM契约，但构造器仍受更严格的结构检查，不能据此宣布构造器全部效果安全。

TicketInfo的根方法还包含Class字面量、零长度Object数组、RestTemplate.exchange和ResponseEntity.getBody。数组本身已在小程序验证，但这次首先在HttpEntity处拒绝。后续Class投影、框架包装、实际Map/DTO返回类型及RPC来源绑定仍须核验；没有绕过第一阻断后宣称21个恢复。

以上均是第一阻断，不把它们解释成“补一个构造器就必定解决全部36个”。完整原36实例及拒绝原因保存在 `gaps-frozen/results.json` 和逐实例CSV中。

## 语义控制与拒绝保护

新增控制程序使用真实JVM、原始字节码、实际Jackson序列化和独立入口参数真值。23种行为各重复两次，每配置46次调用，其中44个生成目标、2个异常退出。

| 检查 | full | selective |
| --- | ---: | ---: |
| 已知来源且完整实例坐标匹配 | 38/38 | 38/38 |
| 必要不透明效果预期unknown | 6 | 6 |
| 根异常退出未产目标 | 2 | 2 |
| 必要证据扰动被拒绝 | 16/16 | 16/16 |
| 完整证据降低执行预算 | analysis_limited | analysis_limited |

控制包含数组默认null、同值不同位置、后写覆盖、同值常量覆盖、参数和返回转发、空引用/越界/负长度/类型不兼容、后续正常请求；lambda包含多捕获参数、两个实例、绑定方法引用、私有实例方法、未执行回退、空Optional实际回退及异常完成。另验证不透明调用可以经lambda捕获影响本地对象，不能错误保留此前字段依赖。

16项扰动覆盖父Frame、call-id、实参和异常身份、必要构造写入、lambda捕获与handle、数组对象/位置/整体版本/元素版本/缺失写入、缺失公共契约、stream来源和Optional状态。首次真实“selective缺少构造写入”的旧失败捕获也继续拒绝。预期unknown单独统计，不与38个已知匹配合并成准确率。

## 真实循环与旧能力回归

| 回归 | full | selective |
| --- | --- | --- |
| 原版Station两批量查询与Route两字段 | 60/60，TP60/FP0/FN0/unknown0 | 同左 |
| 上阶段应用调用控制 | 26已知匹配，8预期unknown，2异常根 | 同左 |
| 旧集合控制 | 10/10 | 10/10 |
| 旧调用生命周期 | 7已知匹配，4预期unknown，2异常根 | 同左 |
| 原循环小程序 | 15已知匹配，1预期unknown，1异常根 | 同左 |

响应绑定九组控制另有48个已知匹配、6个预期unknown，保留自定义serializer及消息歧义等拒绝检查。完整性与分析预算的状态区分检查继续通过。

原能力对照中TF实际运行的301个目标，在旧Agent、旧计划、旧原始捕获上用新离线代码复算，保持213正确、88unknown。这是兼容性复算，不能写成新版Agent重新部署通过213个，也不与新运行60个拼成新版总正确率。

## 工件与后续验收

原始根目录为 `artifacts/kernel-contract-revision-20261020/`。`algorithm-freeze.json`、源码包、`semantics-frozen/`、`cart-frozen/`、`create-frozen/`、`business-frozen/`、`gaps-frozen/`、`legacy-offline-frozen/` 和 `audit-frozen-first/` 保存冻结、原事件、独立预期、预测及审计。`logs/00…04` 记录协议、开发、冻结和最终节点。所有开发失败目录保留，包括数组插桩Verifier失败、离线游标声明失败、getClass契约缺失与扰动驱动误选序列化Frame；它们在冻结前修复，没有覆盖原始记录。

```bash
python3 experiments/sockshop-mirrortaint/audit_kernel_contract_revision.py \
  --root artifacts/kernel-contract-revision-20261020 \
  --out artifacts/kernel-contract-revision-20261020/audit-recheck-new-directory
```

审计输出写入新目录，核对冻结源码、九个原JAR、实际Agent class、重新生成计划、原始来源真值与封存协议；不覆盖原捕获。小型[结果快照](kernel-contract-results-20261020.json)随Git保存，完整工件另行备份。备份入口为 `artifacts/kernel-contract-backup-20261020/START-HERE.txt`；同盘备份不包含Docker镜像层，迁移后仍须重新构建。推送由用户完成。

下一阶段应先处理有限构造器效果与框架包装：Cart需要核验构造、日志以及实际Predicate过滤，TicketInfo需要HttpEntity、Class常量及实际返回结构和RPC来源。不能仅放宽接纳检查。保存与异步继续单独建模，性能继续暂缓。

整体基线保持验收仍须在同一个后续冻结版本上重新执行全部62查询full/selective，同时覆盖MirrorTaint正确368个和旧TF正确213个、不新增错误，才能确认至少382/431。本轮没有完成这一验收，29个候选保持未启封。
