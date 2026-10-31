# ZLT基础语义、来源取证与MT导出校准

**本轮补齐I2L和来源调用事实，TF两模式仍各15个unknown；最终固定原生MT＋B2.2适配器在同一15个正来源目标上15/15正确。** TF没有新增正确业务答案。两入口均为已暴露的开发回归，不是冻结后直接复用成功，也不能代替40 API验收。未扩大分页、代理、缓存、lambda、Gson、保存sink或动态Principal模型。

参照`c1a4e5c`及原两个任务、六组分页输入、来源边界、目标和SQL种子保持。原15个TF unknown、MT B0导出失败、原初始及修正审计均不改写。TF候选`ed77220`在业务运行前锁定源码、Agent与计划；两入口各原版/full/selective新部署，最终MT导出修订另行两次部署，TF及原版捕获直接复用。中间导出校准失败另列，不能替换为最终成功。

| API | 模式 | 实际目标 | 完整业务响应保持 | 目标绑定 | 目标的实际来源配对 | 独立实例真值充分 | 最终来源状态 |
| --- | --- | ---: | --- | ---: | ---: | ---: | --- |
| ZLT-MP-1 | full | 6 | 是 | 6 | 6 | 6 | {'unknown': 6} |
| ZLT-MP-1 | selective | 6 | 是 | 6 | 6 | 6 | {'unknown': 6} |
| ZLT-MP-1 | mirrortaint | 6 | 是 | 6 | 6 | 6 | {'known_correct': 6} |
| ZLT-MP-4 | full | 9 | 是 | 9 | 9 | 9 | {'unknown': 9} |
| ZLT-MP-4 | selective | 9 | 是 | 9 | 9 | 9 | {'unknown': 9} |
| ZLT-MP-4 | mirrortaint | 9 | 是 | 9 | 9 | 9 | {'known_correct': 9} |

每配置12个固定请求，目标数为6＋9；空页没有通配成员目标，仍保留其请求和来源调用完成。TF每模式12/12实际mapper调用闭合：Client使用已计划的实际Frame和collection-call ID（5份非空返回字段事实），User使用6个独立观察上下文和source-call ID（6份字段事实）。两者合计15个字段目标，不能将调用次数或静态候选数当目标数。

Client任务是`ClientController.list → ClientMapper.findList`的`clientId`；User任务是`SysUserController.findUsers → SysUserMapper.findList`的`username`。来源边界仍是原实际mapper返回，不移动到service/helper、SQL同值或响应快照。各JVM自身的调用开始/完成、caller/PC/Frame、字段owner/声明字段/版本与真实输出坐标构成真值；按原代码直接返回相应实体字段的规则核对。SQL及原版输入仅核验行/值，不代替物理坐标。真值不读取传播图或原生标签；预测单独评分。

最终四配置的所选字段和**整个解析后HTTP响应（含原始日期字符串）**逐请求相同，没有日期归一化。两张被读SQL表的实际TSV快照逐模式与原版核对；详见小型结果中的storage。MT的ObjectMapper实际来自业务`jackson-databind-2.13.4.jar`，类SHA256为`46a402c06d4e579014ad56ec64ff590461215a32e404c6acfda0a0b095d996b5`，与原业务依赖类核对；不能仅凭新jar打包成功声称业务环境相同。

I2L按JVM有符号32位整数精确扩展至long，保留数据依赖、选择证据及unknown，丢弃装箱/分配身份。规划器、应用解释器、单方法内核和已有标量求值路径一致支持；新计划在真实I2L指令记录输入及JVM结果，按方法、PC和Frame核验。控制包含−2147483648、−1、0、1、2147483647、同值不同字段来源、unknown及非法bool/浮点/越界值；两模式各10个已知转换目标匹配，另10个必要不透明结果仍unknown。缺事件、错输入、结果和PC分别拒绝。ZLT Client捕获每模式真实记录12次I2L，这不等于已解释了整个服务代理调用。

来源观测与解释能力分开：规划器明确列出未解释调用者中的已声明站点和类哈希；Agent在实际方法建立仅用于观察的独立上下文，记录真实接收者、实参、调用、正常/异常完成和字段事实。它不是伪造应用Frame，不伪造source_call_id，也不使调用者自动可解释。离线检查完成区间、caller/PC、父状态、结果对象、唯一性和完整性；`observation-only-call`事实继续返回unknown，不直接注入已认证依赖。

针对性嵌套控制每模式3次同线程请求，6次来源调用（5正常、1原异常），3个嵌套上下文；原异常对象保持，失败后的根及父状态正确，两个正常返回仍unknown。缺完成、重复、错caller/PC/父上下文、错误返回对象/类哈希及异常完成扰动均拒绝。监测可靠性27场景、原严格48目标的状态/来源、同对象泄露unknown、同值覆盖和粘性无效保护保持。没有机械重跑历史大批业务。

当前真实断点：

- Client：I2L不再静态阻断，mapper来源已完整落地。但根`IClientService.listClient`（PC4）的CGLIB接收者与实际target对象不同，没有适用的代理转发证明；首道依赖失效仍在该调用。Page构造器`<init>(JJ)`无已支持字节码/契约，后续分页效果也未完成，不宣称解决代理后就必然正确。
- User：`findUsers`仍因`Lambda SAM unsupported`不进入解释；Page构造及后续效果未解释。新观察器在实际mapper调用PC19记录6次完整配对，能够建立9个独立目标真值，仍不解释lambda或保证其后无修改。

MT只增加有限Class导出元数据（名称、primitive/array、component、loader identity），不遍历Class内部、不调用应用toString、不初始化业务类型；metadata_only不声明原生来源。单独控制验证延迟初始化类型保持未初始化。原生MT传播JAR未改，源调用另记录开始/完成、实际caller和变换后指令索引；后者明确不是原字节码PC。标签仍来自原生传播，不能由元数据或真值生成。两入口缺标签、缺完成、错对象、歧义来源与problem五类保护分别通过。

导出适配器的失败与修正分开保存：

| 适配器阶段 | 保留结果 | 修正及边界 |
| --- | --- | --- |
| 原B0 | Class形态导出失败 | 原记录不改 |
| B2 | 协议头过早访问Spring类，seq1丢失，两入口15目标无效 | 原始记录不补头、不重排；新版本启动头使用空上下文 |
| B2.1 | 15个所选标量来源匹配，但User完整响应9目标所属请求有日期`+0000`/`+00:00`差异 | 新构建遗漏既有私有Jackson打包；实际ObjectMapper来自capability.jar，完整业务保持未通过 |
| B2.2（正式） | 业务响应、依赖环境、来源配对及15目标评分均通过 | 复用既有baseline.internal.jackson隔离打包；没有新增Date传播/序列化模型 |

这些是构建/导出修订，不归于TF来源能力或MT原生传播变化。B2.1两API曾拟在同一Python进程执行，发现旧环境拦截器未复位后，在第二部署启动前中断并保留空记录；随后使用新进程和新目录。最终驱动每API单独进程，并显式恢复拦截器。首次B2派生审计还因空异常文本误入保护检查而失败；修正仅在独立评分驱动，新目录复算，同一捕获未覆盖。原始B2.1严格业务差异评分与后续字段/完整业务分层评分也分别保留。

迁移修改按层分开：I2L为基础语义；独立source observation为采集/完整性协议；原始事实索引为共享离线优化；Class表示、调用导出、启动和私有JSON打包为MT适配器；评分/驱动修正单独锁哈希。无新JDK登记、公共框架契约或业务字段传播规则。

工件：`artifacts/offline-zlt-revision-20261031/`。正式TF/original在`final-zlt-03`，最终MT在`final-zlt-MT-isolated-01`；最终评分为`zlt-audit-B22-01`。小型[逐实例CSV](zlt-foundation-paired-20261031.csv)和[结果快照](zlt-foundation-results-20261031.json)随Git，包含各阶段与二进制哈希。TF源码候选及702文件锁定记录保留；后续仅MT适配器/打包及独立评分有单列变更，不把它们混称新TF部署。没有性能实验或push。完整数据与依赖备份见本轮备份清单。
