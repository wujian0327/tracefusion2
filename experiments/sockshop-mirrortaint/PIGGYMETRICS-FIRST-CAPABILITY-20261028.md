# PiggyMetrics：冻结版首次能力评分与业务变化诊断

**已完成五API的目标/sink审阅、首次捕获的逐任务状态表，以及证据充分子集的双方独立实例评分。尚无完整五API的细粒度正确率。** 第一轮算法仍为 ae7fe8d8b9e23d8ce197870ff0069c7f1bee84eb，核心、Agent和语义契约未改；没有新增性能实验。

最明确的结果是：createNewAccount 的40个实际返回目标，MirrorTaint正确36个、unknown4个；TF full/selective各0个已知正确、16个unknown、16个拒绝/无效状态、8个未绑定。**这批任务存在真实能力差距，不能引用旧62查询结果抵消。** 其余API缺失的物理实例事实保留缺口，不用预测标签或同值匹配补真值。

## 数据与独立真值

复用原版30次请求、固定MirrorTaint五次API部署、TF full/selective各23次逐字段部署。评分前保存全部首次捕获的SHA256清单，评分后逐文件核对未变，没有覆盖首轮捕获或机械重跑。

原业务使用历史候选 6bb2cf9ddbca980b664d3edbb6ff775d75369278 的原源码构建JAR，不是已确认的论文业务提交。原生MT JAR和既有隔离JSON适配器不变。

独立规则在 portability_piggy_oracle.py，只读原代码、输入、实际DB事实及原始字段坐标，不导入TF还原或MT标签解码。工具预测由另外的冻结还原器/解码器提供。**详细规则在首次捕获后独立审阅并冻结，是回溯评分，不能冒充运行前已完整预注册。**

AccountServiceImpl.create 明确：name复制本次User.username；Saving为固定初始化值；incomes、expenses、note为新对象默认null；lastSeen为本地new Date。时钟生成事实单列，不在声明的入口/仓储/RPC读取边界中人为添加来源；不混入一般隐式控制依赖。

每个JVM分别核对响应和实际DB的用户名、固定Saving、默认null及保存时间。MT的预期来源取同一root的实际argument0.username；TF取实际根Frame的binding-input。源位置由原代码决定，值仅作核验；不跨JVM比较对象编号。

输入匹配也有限制：原版连续跑五API，工具按API/字段独立部署，整个初始数据库并非逐字节相同，BCrypt盐、令牌、时钟及未读取的tf2-current记录也不同。对这里40个目标，已按原代码username查询谓词核对各JVM的相关Account/Auth记录均不存在，且请求内容相同。**只能称相关读状态和任务输入校准，不能称全库完全相同。**

## 五API目标与sink清单

返回目标是原版实际序列化的scalar/null叶；空容器另作结构检查。保存参数是独立sink出现，不与返回字段合并。DB内容不能替代Java保存参数的对象/字段/版本坐标。

| API | 正常完成请求 | 返回目标 | 持久化参数义务 | 原逻辑与缺口 |
| --- | ---: | ---: | ---: | --- |
| saveCurrentAccount | 5 | 0，void | 40 | 读取已有Account后覆盖并保存；name来自实际仓储返回，不能指成同值输入name。statistics RPC走fallback，不算远端执行 |
| createNewAccount | 4 | 40 | 40本地＋8远端附加 | 本地保存和返回为不同目标出现；远端Auth保存及密码转换另列 |
| createUser | 5 | 0，void | 10 | username复制，password经BCrypt和新盐转换；controller退出的null哨兵不是保存来源答案 |
| getUser | 5 | 195 | 0 | 实际OAuth2Authentication/Principal含动态结构与计算getter，不能按同名JSON路径猜物理字段 |
| saveCurrentNotificationsSettings | 5 | 34 | 34 | accountName来自Principal；其余字段按实际输入/新Date规则；内存Map键是枚举 |

共269个实际返回目标、132个持久化参数义务（含8个跨服务附加范围），另有11项持久化空容器结构检查。**不是原论文F/M，不合成全任务准确率。** 原版另有4次400、1次401和1次重复用户500，均保留；void不计业务N/A。

保存调用位置已核对原字节码：Account.saveChanges@39、Account.create@67、Auth.UserServiceImpl.create@20、Recipient.save@11。完整参数规则、补充RPC及源码哈希见 oracle-and-sink-protocol.json。原Auth DB的9组密码（含4组远端创建）通过无Agent的原BCrypt独立核验；内容匹配不等于来源实例坐标已齐备。

## 40个Account返回目标：逐实例配对

| 指标 | MirrorTaint＋固定适配器 | TF full | TF selective |
| --- | ---: | ---: | ---: |
| 实际目标 | 40 | 40 | 40 |
| 已知且实例完全匹配 | 36 | 0 | 0 |
| 错误确定答案 | 0 | 0 | 0 |
| unknown | 4 | 16 | 16 |
| 原还原器拒绝/无效 | 0 | 16 | 16 |
| 目标接口/清单未绑定 | 0 | 8 | 8 |
| 可回答且正确比例 | 90% | 0% | 0% |
| 已知答案条件匹配率 | 36/36 | N/A，无已知答案 | N/A，无已知答案 |
| 数据关系TP / FP / FN | 4 / 0 / 0 | 0 / 0 / 4 | 0 / 0 / 4 |

两种TF模式各有36个“MT正确、TF未回答”，另4个双方未回答。36个MT正确目标中，4个是实际User.username的正来源答案，32个是空数据来源；不是36条正来源关系。MT剩余4个currency枚举目标无法唯一导出。其预期来源为空，因此关系FN为0仍不代表回答了全部目标。

TF具体阻断：

- name、note、deposit、capitalization各4个unknown：必要应用/字段效果未解释。
- lastSeen共4个：冻结Date序列化库契约不认可当前库。
- amount、interest各4个：不支持NumberSerializer，冻结还原器拒绝相应捕获；业务仍正常返回。
- currency共4个：冻结JSON目标投影未唯一落地；原记无效，诊断属投影限制，不是字节损坏。
- null incomes/expenses共8个：原候选只有成员路径，遗漏实际null字段目标。本次补回分母，没有改规划器使其通过。

逐项CSV和JSON保存各JVM自己的message、源调用/Frame、对象、字段、版本及预测。七项评分保护通过：缺wire叶、重复目标、同值错误对象、歧义来源、错连password来源、缺标签、缺关闭事件均不能误算正确。这些是评分保护，不是新业务样本。

## 其余361项任务：事实与缺口分开

| 部分 | 数量 | 已有事实 | 细粒度缺口 |
| --- | ---: | --- | --- |
| Principal返回 | 195 | 客户端真实结构、原代码身份返回 | MT exporter遇到HashSet，未导出完整来源/目标；TF没有可表达目标；计算getter物理投影不足 |
| Recipient返回 | 34 | 原输入、原响应、DB和逐字段业务规则 | MT exporter遇到HashSet/枚举Map；TF被监测异常中断，不能记业务N/A |
| 保存参数 | 132 | 原保存站点、DB内容、密码核验；TF另恢复36项本地保存前原始实例事实 | MT未导出保存参数实例；TF这36项已有事实但无保存sink查询接口，另外96项仍有事实缺口；不用DB值或void哨兵伪造 |

全部条目在 remaining-task-instances.json，按API、输入、sink和字段保留；工具状态与oracle不足分开。不能填写完整关系FP/FN为零，也不能由导出器失败推断MT原生传播一定不会做。**完整五API对齐尚未完成；证据充分的40项已有明确差距。**

进一步复查原捕获，TF full/selective各有36项Account保存参数的原始事实：具体save call-id、实参对象、保存前字段/版本快照及根输入坐标已经存在（另4项currency投影缺失）。已用同一个查询的既有捕获恢复，未重新部署。它们仍没有冻结TF的保存sink查询答案，MT也缺相应sink实例导出；因此不能算新增正确答案。但这36项应归“已有事实、目标接口不足”，不能统一归为采集范围不足。第三次审计的原始缺口表不改写，细化结果见 piggy-save-fact-supplement-01。

首次MT配置还发现一项实验接入缺口：五个配置的手动 source_calls 均为空，初始扫描在应用服务接口处停止，没有导出具体仓储读取出现。此缺口与MT原生传播能力分开，不据此判它不会处理DB来源；原配置不改写。40个Account正常返回样本中，被查询Account/Auth记录均不存在，DB返回null，正数据来源只来自根User.username，因此这里的配对仍有实际根来源坐标；该论证不扩展到其他API的DB来源任务。见 configuration-source-call-audit.json。

## 原版正常、插桩后500：直接根因

Recipient五种字段计划、两种模式共十次首次部署，48次查询请求比较出现“原版200、插桩500”，每模式24次；各模式影响34个已请求原版目标。

1. 四种read-forward计划：ReadEffectHooks.enter 的运行时核验抛出 Unmodeled JDK read-effect runtime。
2. lastNotified计划：根参数快照遍历枚举键Map，抛出 Only String map keys admitted。
3. 异常经 ResponseBindingHooks.enter 到 Recorder.enter，后者记录problem后再次抛出监测异常，Spring最终返回500。异常发生在用户业务方法体之前。
4. source-read/json-read的同类Map错误会记录problem并返回，会破坏证据，但不是全部500的直接抛出点。

48次失败请求前后，Recipient集合的原始DB内容均未改变；与异常栈一致，没有执行这次保存。NumberSerializer问题不改变业务完成，另列证据/契约失败。

另用相同冻结Agent/计划，在新目录限制Tomcat为单工作线程做混合请求诊断，不计入首次40项目标或性能重复。原版合法非空/空Map均200；TF非空Map为500，空Map可200，非法输入仍400。

原Frame序列揭示第二个缺陷：进入失败后ThreadLocal栈未回滚，f2.parent=f1，f3.parent=f2；后来成功的空Map根f4仍挂在失败f3之下。**不能只吞异常，还必须清理监测状态；不能继续信任残留栈给确定答案。** 原版、full和selective均已完成，同线程状态泄漏在两种TF模式下复现；逐请求状态与Frame父关系已保存至diagnostic-audit.json。

## 其他应用：仅恢复无Agent环境

- Apollo历史候选第四次环境准备：等真实admin注册与portal地址缓存就绪，加入合法发布/实例数据；五API各6请求，28次200，另有缺失应用404和400。旧尝试仍保存；findBranch正常为空不算元素来源正确。
- Mall第四次环境准备：接入原版mall-auth及合法注册/验证码，五API均有业务code200正常用例。HTTP为29次200和1次预设非法更新500；HTTP200内的重复注册/错误密码/非法参数仍是业务失败，不算成功。
- ZLT、FEBS归档、goodsKill、SuperMarket原环境阻断保留；Sock Shop本批新任务待执行。所有40条API保留，不用成功项目替换受阻项目。

本轮没有启动这两个恢复应用的新工具对照。它们的详细输入/真值须在首次工具运行前另行封存，不能把静态候选当完整任务协议。

## 工件与下一版本边界

主目录：artifacts/portability-first-20261028/piggy-independent-first-03/。

- first-captures-manifest.json：首次原始文件哈希，复算后逐项相等。
- oracle-and-sink-protocol.json：回溯独立规则、sink位置与源码哈希。
- account-return-paired-instances.json、paired-account-return.csv：40目标逐实例配对。
- remaining-task-instances.json：其余361项任务及oracle/导出缺口。
- business-preservation-root-causes.json：首次十次Recipient部署的异常链、48次失败请求。
- password-database-checks.json、scoring-guards/checks.json：密码事实核验与评分保护。
- summary.json：小型结果与配对缺口统计。

复核脚本为 audit_piggy_first_capabilities.py，输出必须指定新目录，不能覆盖首次结果。第一次独立审计遇到Python日期字符串格式问题，派生失败目录仍保留；修复只在评分驱动。第二、三次记录分别保存；第三次补充相关数据库读状态核对。

下一版本应先隔离监测异常与应用执行，并回滚进入失败的ThreadLocal状态；核验失败仍留下不可用答案，不能变成空来源。之后再处理枚举Map、动态返回、保存sink和解码语义。**本报告核心仍为ae7fe8d，没有混入候选修复。**

完整工件和Docker镜像另行备份；Git保存代码及小型摘要，push由用户完成。旧报告截点不改写。
