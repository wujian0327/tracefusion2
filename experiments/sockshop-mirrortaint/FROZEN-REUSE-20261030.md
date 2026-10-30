# 冻结版直接复用：ZLT 两个新入口

**未修改 `c1a4e5ceb60a276cc3651e4cdb413aa29d7f8d5d` 的核心、Agent或公共契约。两个新入口的15个实际正来源目标，TF full/selective 各15 unknown、0个认证答案；固定MT＋B0的15项目标因导出器problem未能评分。** 这次没有取得新的直接来源复用成功，也不能据此判断MT原生传播是否能回答。业务恢复正常、目标绑定和来源正确分开报告。

96项核心源码逐项与冻结提交及原源码清单一致，沿用Agent SHA256 `375cdbeb9b1c3b06df488011cf848e4f614ef4de6dbe29d5e8bdcfd18f66f0fa`。新增的只有实验驱动、任务配置、评分保护和报告，单独保存哈希。Mall98联合保持不在本轮重复开发，不追5项真值不足目标；没有新Gson、保存sink、动态Principal或通用切片实现。

## 证书与严格反例复核

| 证书条件 | 检查位置 | 实际证据 | 失败保护 |
| --- | --- | --- | --- |
| 无回调必须有观测入口及完整捕获 | `SourceLocalityInstrumentation.transform`、`infer_source_locality.validate`；正式入口另核验序列、metrics/problem/footer | Mall full q002：ownership1、call17、Frame f12、end seq711；两类 HandlerInstantiator 与 BeanDeserializer 均有匹配 class 定义事实 | 本轮分别移除三类入口定义事实，全部拒绝；旧 missing-reader/corridor/source-finish 等保护保持 |
| 分配、默认解码、实际返回属于同一调用 | `SourceLocalityHooks.birth/decoded/returned/complete`、`infer_source_locality.validate` | body o128 的分配、图和实际客户端返回均绑定同一 ownership/call；不把返回快照当来源 | 分配、调用ID、线程、返回对象、外部可变引用、重复完成扰动均拒绝 |
| 发布与后续效果进入共同可达性状态 | `infer_application_execution` 的 `write_field/escape/poison` 与 source_ownership | 控制包括直接、包装对象、数组、列表、lambda/回调、全局发布；必要不透明效果保留 unknown | 仅完整证书图暂时从非本地根移除；再次发布或成为不透明实参后恢复保守失效 |
| 同值不能证明没有写入 | 同上 `state.field_write`，实际写入版本；认证不采用值/版本未变推断未修改 | 控制 mode4：两次同值 setter 均有更新版本并成为已知空来源 | mode19 经真实上下文泄露并执行未观测同值写入；冻结版 full/selective 各两次均 unknown |
| 默认解码与回调配置是有限条件 | `plainBean/rootType/typeFactory/factory/mixins/decoder/graph` | 实现哈希、无注解/相关mixin、类型与工厂、真实 setter/属性表和局部图均有事实；cache 仅 null/精确 JDK EmptyList | 24类严格扰动每模式全部拒绝；无证明对象继续使用原屏障 |
| 监测不额外调用未知应用方法 | `SourceLocalityHooks` 的 exact/pin 检查与反射只读取值；`BusinessJackson.call` 实际目标为已核验库实现 | Bean类的注解信息用 ASM读字节码；属性方法仅比较 Method/字节码，不调用应用getter/setter；cache 不调用未知 isEmpty；图只遍历精确JDK容器 | 自定义mapper/decoder/property/type/handler/cache等不符合条件时不给证书；这不是任意反射、native、动态重配置或并发共享写入的保证 |

源码、96项冻结哈希与原Agent均保持；本轮严格反例复核使用原始捕获的派生副本，不称新Agent部署。已确认的旧不安全候选93c77c9、`controls-22-adversarial-confirmed`、对象身份断言、未观测同值写入及最终unknown保护一起锁定832个文件；不把旧失败覆盖为新成功。未发现需要改动冻结核心的新真实性问题。

## 候选池与运行前封存

选择规则先于规划及工具运行：从原40 API中保留ZLT的全部五项，固定选择此前无Agent环境预检已有非空列表的两个GET入口，按API编号执行；不以TF或MT成功替换入口。每入口封存六组分页输入、单个字段通配目标、实际mapper读取边界和独立规则。正来源是这次具体mapper返回中的字段，不把业务service/helper参数重新注册成来源。

| 原API | 本轮任务／准备状态 | 策略适用性和结果 |
| --- | --- | --- |
| ZLT-MP-1 ClientController.list | `/clients/list`；`/data/*/clientId`；六组分页输入 | 旧read-forward运行时拒绝；统一内核conditional；6目标unknown |
| ZLT-MP-2 saveOrUpdate | 写入与认证准备尚未封齐，本轮不执行 | 未判定适用性，不计TF拒绝或N/A |
| ZLT-MP-3 findByMobile | 既有原版预检仅验证缺失行；未纳入本轮非空列表规则 | 本轮不规划，不替换失败入口 |
| ZLT-MP-4 findUsers | `/users`；`/data/*/username`；六组分页输入 | 旧read-forward运行时拒绝；统一内核conditional；9目标unknown |
| ZLT-MP-5 getLoginAppUser | 正常认证上下文尚未准备 | 未判定适用性，不计业务无目标 |

两个被测入口的策略候选共4项：旧策略2项运行时不适用，执行内核2项conditional，没有运行前即可宣称可回答的入口。其条件明确包含实际源调用点未覆盖；没有新增运行时登记或切换到运行后成功的策略。

输入固定为page=1、2、3各配limit=1、2。Client六组输入中五组非空、共6目标，另一次空页没有元素目标；User六组全部非空、共9目标。空页仍保留为实际请求，不用空页获得来源正确。其余原40清单及首次实验不改写；本次两个返回字段查询不能替代整API、保存／消息sink或完整40 API验收。

这些源码、静态模型和环境此前已暴露。所用历史候选JAR仍不是已确认的论文业务版本，也不称第三方盲测。

## 原版、两种TF与固定MT的新部署

每入口各四个独立配置，共8次隔离部署；每部署六个选定查询请求，共48次，均HTTP200。两种TF与MT各自的实际响应逐请求与无Agent原版一致。旁路环境健康检查及未选入口的只读预检另有记录，不混入这48次查询。没有修改原业务JAR、认证、事务或传播实现。

| 入口，每配置分别统计 | 原版实际目标 | TF full | TF selective | MT＋B0 |
| --- | ---: | --- | --- | --- |
| Client.list clientId | 6 | 6 unknown | 6 unknown | 6 evidence_invalid，导出失败 |
| SysUser.findUsers username | 9 | 9 unknown | 9 unknown | 9 evidence_invalid，导出失败 |
| 合计 | 15 | 0认证、15unknown | 0认证、15unknown | 0认证、15未评分 |

TF两模式均有15项实际wire叶到对象／字段／版本的目标映射，**目标已绑定不等于来源正确**。没有确定来源答案，因此不填写已知答案条件匹配率为100%。MT的失败属于固定导出接入，不据此宣称原生传播15项错误。

独立逻辑规则来自未修改源码和mapper XML：列表元素的clientId/username来自对应实际mapper返回；原始SQL、实际DB主键／内容与原响应逐项核对。实例真值还必须有每个工具自己的实际源调用及字段坐标，不能由DB同值、TF图或MT标签填补。

TF确实记录了mapper字段快照，但 `source_scope=unscoped-fact-only`，`source_call_id`、`source_caller_method`、`source_pc`为空。声明及快照不能代替真实调用配对。因此15项均保留实例真值缺口，不给完整TP/FP/FN、关系Recall或双方能力优劣排名。

第一份派生审计仅依据快照坐标，把TF oracle标为充分；进一步加入实际调用配对保护后，在独立 `audit-reviewed/` 将充分数修正为0，工具的15 unknown状态不变。原审计、原捕获及380个首次文件哈希保持。没有用这项修正制造成功结果。

环境复用驱动沿用了旧无Agent检查器的 `agent:false` 和默认预检槽标签，这些字段在工具配置下不准确。原文件不覆盖；`actual-runtime-receipts.json`按实际compose命令、Agent／计划哈希及六份实际请求记录澄清模式。上表依据独立的 `selected-requests.json`，不采用旧默认槽的路径或agent布尔值。

## 首道阻断与后续迁移需求

两条实际来源调用者均因 **I2L（opcode133）** 未支持而列入opaque_methods：ClientServiceImpl.listClient和SysUserServiceImpl.findUsers。来源调用点分别在其PC28、PC19，未进入可解释Frame；全局源观测只能留下未配对事实。运行前的conditional限制与实际捕获一致。本轮没有只让规划器放行，也没有为成功把来源改成service返回。补I2L也不能保证后续分页、代理、lambda和字段效果全部恢复。

MT两个入口均出现 `unmodeled snapshot type java.lang.Class`；problem及关闭记录保留，严格导出器拒绝整批。不根据剩余标签猜答案，也没有改B0或原生MT。后续应单独设计有限的参数／字段导出和调用校准。

| 迁移需求 | 本轮处理 |
| --- | --- |
| 通用I2L及后续实际指令／效果支持 | 仅记录，不改冻结核心 |
| 实际mapper调用者Frame与开始／完成配对 | 未满足；unscoped事实永久单列 |
| 固定MT导出器的Class形态及完整实例输出 | 未修改，能力列未评分 |
| 分页、代理、角色赋值等后续语义 | 保留待核验，不预先宣称支持 |

原有基础模型在计划和运行时出现、目标绑定成功，均不能计作帮助产生认证来源答案。新增公共模型0，核心／Agent修改0，认证来源复用成功入口0/2；这不是整个应用的准确率。

## 工件与复核

主目录 `artifacts/frozen-zlt-reuse-20261030/`：候选池、输入及逻辑规则在运行前封存；全部原版及工具日志、独立数据库事实、逐请求输出、初始与严格审计、逐实例配对和模式澄清均保留。证书复核位于 `artifacts/frozen-locality-cost-20261030/certificate-review/`，24类严格扰动另存 `certificate-strict-recheck/`。小型[结果](frozen-zlt-reuse-results-20261030.json)、[配对CSV](frozen-zlt-reuse-paired-20261030.csv)随Git保存。

完整工件的归档与哈希另见本批备份清单；不把Git中的小型摘要当作完整工件。算法保持c1a4e5c，实验源码、配置和评分哈希分别留存，push由用户完成。同版本正式成本见独立报告，不由这批未认证目标推导成本优势。
