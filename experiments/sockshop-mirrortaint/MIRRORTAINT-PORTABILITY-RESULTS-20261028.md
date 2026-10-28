# MirrorTaint 外部基准迁移：首次实验进度与已取得结果

后续更新：[PiggyMetrics独立实例评分与业务变化诊断](PIGGYMETRICS-FIRST-CAPABILITY-20261028.md)。下文仍保留首次进度截点；最新40项状态见 portability-first-status-20261028.json。

**这是阶段性结果，尚未完成40个API的最终能力对照。** 已保留全部8应用、40条API，核验了实际候选JAR的方法签名，并完成冻结核心的首次静态规划。PiggyMetrics已取得原版、MirrorTaint及一批TF full/selective业务捕获；其他应用仍有环境准备、目标绑定和工具运行工作。**目前不能给出本批完整正确率，也不能宣称与MirrorTaint能力对齐或性能占优。**

本文件回应“当前结果是什么”，不把构建成功、规划接纳、HTTP成功或污染标签导出当作来源实例正确。原62/29查询及旧成本结果不填入这批新应用的结果表。

## 范围、版本与可复现性

- 只做任务书阶段1、2；第一轮算法固定 `ae7fe8d8b9e23d8ce197870ff0069c7f1bee84eb`，68项核心源码哈希已重新核对，未改算法、Agent、库语义或新增JDK模型。
- 原作者MirrorTaint固定提交 `54fcbfc5bb3a0d7cd30309098355d999553a861b`，原生传播未改；沿用既有隔离JSON导出适配器。
- 作者公开材料没有给全业务版本锁。除既有Sock Shop锁定镜像外，新应用使用**在规划前按确定规则选取的历史候选**，不能称为已确认的论文原版本。FEBS原仓库404，归档替代也不算原版复现。
- 原业务源码未编辑；候选JAR从固定原源码正常构建。Maven中央仓库镜像、依赖服务地址、独立数据库和正常OAuth测试身份属于环境准备，单独保存。
- Java8兼容候选选择既有内核支持的Ubuntu OpenJDK8u504，goodsKill/SuperMarket保留其原声明的JDK11。**内核认可一个运行时，不代表所有旧profile及新框架库契约都认可它**；read-forward首次运行仍报运行时限制，未补哈希绕过。
- 没有新性能实验，没有推送。

统计截点：`2026-10-28T08:56:38.277602+00:00`。下文仅使用 `artifacts/portability-first-20261028/checkpoint-audit-03/snapshot.json`，之后完成的运行不追加入这个截点的数字。

## 已完成的静态检查

实际业务JAR共20个角色，40/40方法签名已在JAR上核验。返回结构来自无Agent反射及原代码，不按TF支持情况筛选。

对237个**静态返回目标候选/未解析义务**，首次结果为：198个接纳、17个规划拒绝、22个目标不能绑定。这个分母不是实际目标实例数，更不是完整API能力分母。动态Map、泛型、运行时子类、null容器和非响应sink仍需逐项补齐。

特别是void API：仍保留保存/删除/消息参数义务；不能因为没有返回字段，就把这条API计作业务N/A或成功。当前静态调用扫描只列候选效果，并非完整持久化sink审计，不能用候选数为零证明没有副作用。

## 无Agent原版请求结果

| 应用 | 已完成情况 | 当前限制 |
| --- | --- | --- |
| PiggyMetrics | 五API各6次，共30次；24次HTTP200，另4次400、1次401、1次500 | 包含预设非法输入、重复用户和缺认证；保存及副作用目标仍需实例真值，不仅看HTTP响应 |
| Apollo历史候选 | 五API各6次，共30次；计数接口6次200，其他24次500 | portal→admin服务发现未打通；保留两次环境尝试，不能把500都当作应用没有目标 |
| mall-swarm历史候选 | 五API各6次，共30次；当前混合200/400/500 | 登录依赖mall-auth尚待接入；验证码请求编码和非法更新输入另列。已保留SQL示例数据导入失败，第二次使用原DDL及认证种子数据 |
| ZLT-MP | 两角色原版启动预检已执行 | 公共默认配置指向外部MySQL/Redis地址，隔离网络下不可达；尚未完成配置/依赖准备，不是TF失败 |
| FEBS归档替代 | 三角色原版启动预检已执行 | Nacos外部配置/动态主数据源未就绪；原项目404问题继续保留 |
| goodsKill | Java11原版服务/网页角色启动预检已执行 | MySQL、Zookeeper/Dubbo依赖未就绪；尚未进入工具比较 |
| SuperMarket | Java11四角色原版启动预检已执行 | Mycat/Eureka等原架构环境未准备完整；启动日志不是目标方法执行证据 |
| Sock Shop | 已锁定原镜像及实际JAR、核验五方法 | 本批五API共同返回/持久化/消息任务尚未重新执行；旧字段实验不能代替整API新任务 |

30次请求是每应用一组原版输入；负例、访问失败与方法正常返回要分别核对，不能以“HTTP200比例”当溯源正确率。

## PiggyMetrics首次工具运行与离线复算

截点内有5个MirrorTaint逐API运行，以及full 23个、selective 23个逐目标运行。每个运行使用新容器/数据卷及6个固定输入。MT一次可导出多个字段，TF按字段分别部署，次数和范围不相同；这里不比较成本。

| TF指标，逐目标部署累计 | full | selective |
| --- | ---: | ---: |
| 已完成逐目标部署 | 23 | 23 |
| 实际发出的查询请求 | 138 | 138 |
| 按原版正常响应保留的候选目标实例 | 66 | 66 |
| known、尚未独立评分 | 0 | 0 |
| unknown | 16 | 16 |
| 冻结还原器拒绝/无效状态 | 16 | 16 |
| analysis_limited | 0 | 0 |
| 插桩后业务完成发生变化，影响目标 | 34 | 34 |
| 原版未生成对应候选路径的查询请求 | 41 | 41 |

这些是**当前已完成字段部署的累计状态**，既不是独立API总数，也不是全部40API的分母。正常/非法请求在各字段部署重复执行。未生成候选路径只针对该路径，不能等同于整API无sink。

关键首次失败已经实际出现：

1. Account的部分返回字段业务可以完成，但还原为unknown；例如当前已复算的`/name`、`/note`、`/saving/capitalization`。这说明规划接纳没有自动带来端到端来源答案。
2. `lastSeen`涉及当前未认可的Date序列化库，冻结还原器报`Unmodeled Date serializer library`；枚举currency的JSON投影也未唯一落地。这些应诊断为契约/投影限制，不宜笼统称为原始日志损坏。
3. Recipient输入含枚举键Map，TF采集报`Only String map keys admitted`，旧read-forward还报`Unmodeled JDK read-effect runtime`。原版正常请求在部分插桩配置下变成500。**这是需要单独处理的工具/业务行为保持问题，不能排除这些目标后再报告准确率，也不能记业务N/A。**
4. MT原生标签和返回快照已导出，但部分API也有导出器`problem`事件；Principal运行时对象、枚举键Map，以及void保存/消息sink的完整实例输出还没有完成校准。当前不能把“有标签”计作MT正确，更不能先判TF与MT谁更好。

**实例完全匹配率、关系TP/FP/FN、双方逐实例能力差距：当前均未完成，记待评分，不填0或100%。** 原始源码/请求/数据库事实已保存，但不完整的实例真值不能由TF图或MT标签补成。

## 逐API首次检查表

A/R/B分别为静态返回候选的接纳/拒绝/目标绑定不支持；0/0/0不表示API成功。

| API | 原表方法 | A/R/B | 无Agent原版 | 工具进度（本截点） |
| --- | --- | ---: | --- | --- |
| `apollo-1` | `findNamespace` | 29/0/4 | 500×6 | 未运行 |
| `apollo-2` | `findActiveReleases` | 0/0/1 | 500×6 | 未运行 |
| `apollo-3` | `getInstancesCountByNamespace` | 0/0/1 | 200×6 | 未运行 |
| `apollo-4` | `findBranch` | 29/0/4 | 500×6 | 未运行 |
| `apollo-5` | `getByRelease` | 3/1/0 | 500×6 | 未运行 |
| `piggymetrics-1` | `saveCurrentAccount` | 0/0/0 | 200×5；400×1 | MT 1；F/S 0/0；无返回字段，副作用任务未完成 |
| `piggymetrics-2` | `createNewAccount` | 18/0/0 | 200×4；400×2 | MT 1；F/S 18/18 |
| `piggymetrics-3` | `createUser` | 0/0/0 | 200×5；500×1 | MT 1；F/S 0/0；无返回字段，副作用任务未完成 |
| `piggymetrics-4` | `getUser` | 0/0/1 | 200×5；401×1 | MT 1；F/S 0/0 |
| `piggymetrics-5` | `saveCurrentNotificationsSettings` | 5/0/0 | 200×5；400×1 | MT 1；F/S 5/5 |
| `ZLT-MP-1` | `list` | 3/0/0 | 启动预检受阻，未验证入口 | 未运行 |
| `ZLT-MP-2` | `saveOrUpdate` | 3/0/0 | 启动预检受阻，未验证入口 | 未运行 |
| `ZLT-MP-3` | `findByMobile` | 24/0/1 | 启动预检受阻，未验证入口 | 未运行 |
| `ZLT-MP-4` | `findUsers` | 3/0/0 | 启动预检受阻，未验证入口 | 未运行 |
| `ZLT-MP-5` | `getLoginAppUser` | 3/0/0 | 启动预检受阻，未验证入口 | 未运行 |
| `SockShop-1` | `newOrder` | 34/0/0 | 本批待执行 | 未运行 |
| `SockShop-2` | `get` | 0/0/1 | 本批待执行 | 未运行 |
| `SockShop-3` | `delete` | 0/0/0 | 本批待执行 | 未运行；无返回字段，副作用任务未完成 |
| `SockShop-4` | `mergeCarts` | 0/0/0 | 本批待执行 | 未运行；无返回字段，副作用任务未完成 |
| `SockShop-5` | `postShipping` | 2/0/0 | 本批待执行 | 未运行 |
| `FEBS-Cloud-1` | `addOauthCliendetails` | 0/0/0 | 启动预检受阻，未验证入口 | 未运行；无返回字段，副作用任务未完成 |
| `FEBS-Cloud-2` | `jobList` | 0/0/3 | 启动预检受阻，未验证入口 | 未运行 |
| `FEBS-Cloud-3` | `userList` | 0/0/3 | 启动预检受阻，未验证入口 | 未运行 |
| `FEBS-Cloud-4` | `index` | 0/0/3 | 启动预检受阻，未验证入口 | 未运行 |
| `FEBS-Cloud-5` | `addUser` | 0/0/0 | 启动预检受阻，未验证入口 | 未运行；无返回字段，副作用任务未完成 |
| `goodsKill-1` | `executeSeckill` | 0/12/0 | 启动预检受阻，未验证入口 | 未运行 |
| `goodsKill-2` | `doWithSychronized` | 4/0/0 | 启动预检受阻，未验证入口 | 未运行 |
| `goodsKill-3` | `getDirectoryPermissionList` | 4/0/0 | 启动预检受阻，未验证入口 | 未运行 |
| `goodsKill-4` | `execute` | 4/0/0 | 启动预检受阻，未验证入口 | 未运行 |
| `goodsKill-5` | `roleLess` | 0/4/0 | 启动预检受阻，未验证入口 | 未运行 |
| `mall-swarm-1` | `login` | 3/0/0 | 500×6 | 未运行 |
| `mall-swarm-2` | `register` | 3/0/0 | 200×1；400×5 | 未运行 |
| `mall-swarm-3` | `login` | 3/0/0 | 200×1；500×5 | 未运行 |
| `mall-swarm-4` | `updatePassword` | 3/0/0 | 200×6 | 未运行 |
| `mall-swarm-5` | `update` | 3/0/0 | 200×5；500×1 | 未运行 |
| `SuperMarket-1` | `updateCart` | 3/0/0 | 启动预检受阻，未验证入口 | 未运行 |
| `SuperMarket-2` | `addCart` | 3/0/0 | 启动预检受阻，未验证入口 | 未运行 |
| `SuperMarket-3` | `addOrder` | 3/0/0 | 启动预检受阻，未验证入口 | 未运行 |
| `SuperMarket-4` | `pageManage` | 3/0/0 | 启动预检受阻，未验证入口 | 未运行 |
| `SuperMarket-5` | `registUser` | 3/0/0 | 启动预检受阻，未验证入口 | 未运行 |

## 冻结与工件哈希

| 工件 | SHA256 |
| --- | --- |
| 原任务书 | `24e6897d0198b60226b9e9d00f659c8badb0333cca2b9ca4e1ade927cb1949b9` |
| 首次任务封存 | `f4e5c80690d7806d13e032b7a95193b0d308f4b858769fb71995f9250877e48c` |
| 版本选择协议 | `29262496f1bac4c5362bbd3a962b9befb799ff1ca6b080f40e7ba633889fe91f` |
| 本截点复算结果 | `360aec68c81c3af98c3e6db869003196f19ba10cddded6353694372c13f72c9c` |
| 原作者MirrorTaint JAR | `e4c679206993b45c6727a4ace1d4dcff6df0ded2b80b56b27b8c86741be63fe7` |
| 沿用的TF Agent | `b610c49df8acd25036ca5962d2d1cfb38a49a0b6b3e4a6de9db49eddf95cd83b` |

主目录：`artifacts/portability-first-20261028/`。`business-jars/index.json`和各`metadata/*/receipt.json`包含JAR、类、依赖清单；`runtime-selection-before-tools.json`记录运行时选择；`original/`保存原版请求/环境失败；`tool-runs/`保存工具原日志；`planning-first/`保存全部首次静态结果；`logs/`保存节点记录。完整工件不随Git自动同步。

构建镜像及业务依赖镜像的实际digest需连同最终环境清单汇总，当前不得把未锁定的`latest`当作历史版本。已拉取的Apollo `latest`实际为3.0.0/JDK17，已隔离留证，**未冒充论文原版或当前历史2.2.0候选**。

## 尚未完成，以及后续支持清单

当前40项封存文件记录的是静态候选和选择规则，尚未封齐全部API的具体输入及独立实例真值。因此全40项静态检查只算准备性结果，不能充作已满足严格预注册条件的完整能力实验。阶段1尚需完成各API实际全部sink及动态返回类型的人工审阅与细粒度真值封存；阶段2尚需补完其他应用环境与首次工具执行、独立实例评分和双方配对表。因此这轮**尚不能验收为完整首次结果**。

环境工作可先继续：Apollo admin发现、Mall auth/正常输入、ZLT/FEBS配置与数据库、goodsKill注册中心及存储、SuperMarket Mycat/Eureka。它们与算法修改分开。

首次结果保留后，再讨论新增语义/采集支持：枚举及非String键Map、JDK契约按profile的覆盖、不同Jackson/Date投影、动态Principal/Map返回、原始持久化/消息sink绑定，以及当前拒绝的指令/调用效果。**这些现在是待支持/待诊断清单，尚未修改实现使其通过。**

审计器第一次复算曾传错boundary参数，原派生审计保留在`checkpoint-audit-01/`；本表采用修正驱动后的`checkpoint-audit-03/`。修正还把原版正常、插桩后失败的目标保留在分母中。未改核心、未覆盖原始捕获。

方法及原实验条目参考：[MirrorTaint原论文](https://zhangyuqun.github.io/publications/icse2023c.pdf)、[固定作者工件](https://github.com/MirrorTaint/MirrorTaint/tree/54fcbfc5bb3a0d7cd30309098355d999553a861b)。原表F/M为关系数，不能直接用于本批字段实例分母。
