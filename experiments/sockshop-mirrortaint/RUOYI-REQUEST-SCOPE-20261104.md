# RuoYi请求归属与mapper正来源闭环

**部门详情已打通：full/selective各5/5正来源正确；岗位列表进一步达到各24/24。** 原五查询的C1配置每模式仍保留全部89个目标：29正确、43语义还原拒绝、12证据无效、5 unknown，0错误确定答案。SysConfig的C2校准另有各5/5正来源正确，不与C1合并成新的总体成绩。

本轮是已暴露入口的开发回归，不是未见查询。没有新增应用、性能实验或push。原首次、上轮0/89、开发失败及中间检查点全部保留。

## 版本与采集

参照为`d69f54a32193d8cadc4de86d199ab266082239ca`。最终在线Agent源码检查点为 **`9ebb239817acf7a90ef7b90f4715594447edafed`**，实际Agent SHA256：

`d8d01198720251bb6a08f51c126b32558ee0ec1a7b4e9159069f03e9738f518b`

最终代码为 **`e8311fd78453efa5cf66311682e93bd0d3e708fc`**。采集后只补了构造证明的静态预算异常透传：`AnalysisLimit`不再被当作普通“不支持形态”吞掉。Agent不变，六份计划逐字节相同，覆盖两模式的12份配置；兼容依据保存在`planner-budget-plan-equivalence.json`。该补丁没有额外业务部署，最终评分使用修订后的代码。原在线冻结与最终119项源码清单分别保留，不把两者写成同一个源码哈希。

最终目录`final-03/`有C1十份、C2两份独立新TF部署，未复用旧Agent业务捕获。`c16ed34`、`d02b780`的开发检查点及捕获保留；收尾补齐了框架上下文辅助类型核验，并将省略资格收紧到实际验证过的同步生命周期。MT原生传播及适配器未变；其C1基线和相同C2任务的捕获兼容复用，明确不称新MT部署。

## 修复的首道问题及后续阻断

旧部门详情的第一处problem来自独立认证准备请求`/user/info/admin`：当时没有查询入口Frame，却因计划允许Map包装，所有响应都进入目标集合检查。准备响应的集合不在该目标模型内，整批因此失效。修改发生在遍历之前，没有删除problem或放宽footer规则。

[请求范围观测](RequestScopeHooks.java)、[规划许可](plan_request_scope.py)及[离线核验](infer_request_scope.py)记录实际MVC分派方法、请求/响应对象、消息、加载器、入口覆盖和完成区间。只有独立、无父消息、无活动RPC、没有查询根的同步准备响应，才省去目标模式的body遍历。认证及日志handler本身仍执行，其业务写入没有被删除，也没有被声明为只读。

最终部门捕获每模式各有三份独立响应省略事实，分别对应`/user/info/admin`、`/logininfor`、`/user/recordlogin`；六次正式请求均保留查询根关联。缺失ID输入产生的业务失败/handler输出仍按原协议单列，没有因为TF失败而删除目标或记为成功。

| 条件 | 检查位置与实际证据 | 不满足或损坏时 |
| --- | --- | --- |
| 查询入口确已插桩 | `PlannedServiceAgent`登记原类哈希和入口覆盖；实际根Frame另记录消息关联 | 无覆盖不省略；缺失/重复证明拒绝认证 |
| 实际分派与载体一致 | 固定Spring 5.3.39的九个MVC类；读取已核验字段，匹配handler、request、response及ClassLoader | 未支持上下文采全；矛盾留下失败标记 |
| 可核验的同步生命周期 | 精确`StandardServletAsyncWebRequest`、`NEW`状态、空asyncContext和实际生命周期响应；完成时复核 | 普通/自定义WebRequest不省略；省略后状态矛盾拒绝 |
| 真正独立于查询 | 无父消息、无活动RPC、该消息从未进入查询根或选择查询handler | 查询及关联响应保留完整检查 |
| 捕获完整 | 分派与输出开始/完成配对、唯一身份、线程和顺序；原problem、sidecar、粘性footer继续有效 | 不能因后续状态恢复重新认证损坏批次 |

观测读取已核验的框架字段及HashMap内部表示，不额外调用未知业务getter、toString或包装集合重写方法。这里是有限通信观测资格，不是任意框架、异步或反射程序的完备证明。

排除准备响应后，部门详情仍经历了真实的语义阻断；不能把业务恢复或物理绑定等同于来源正确：

1. 服务接口调用经过CGLIB代理。实际链不是空链，而是单个`ExposeInvocationInterceptor`。新增Spring 5.3.39的有限转发配置，核验SingletonTargetSource、实际单例、实参、目标Frame、结果和异常；11个必要实现包含`NamedThreadLocal`及`AopContext`。额外advice继续不透明，未开放一般代理“只读”白名单。
2. 虚调用指令可以命名子类，但方法定义在父类。规划器现能枚举该继承实现，运行时仍按实际类层级和Frame核验，因而能解释`BaseController.success`。
3. [构造效果证明](plan_map_constructor.py)只允许新建、直接继承HashMap的受支持包装：先执行无参HashMap初始化；写入只能是`invokespecial HashMap.put(this,字面String键,value)`；辅助静态谓词不能访问堆或执行回调，且初始化证据必须早于查询根。既有JDK条件照常核验。它只保持参数对象已有字段依赖，不生成Map条目的来源。包装到引用参数的可达性仍登记，后续发布或不透明效果仍可使其失效。
4. 包装快照已包含根相对路径`/data/deptName`，原规划又加了一层`/data`。现在按实际Map根路径绑定，未改变查询目标、来源边界或采用同值连接。

部门full的首例，目标为`o201 / SysDept.deptName / version1`；独立原始事实指向`SysDeptMapper.selectDeptById`的本次调用，调用者Frame `f106`、PC3（模型指令索引）、call-id27、来源事件681。预测与该实例坐标完全匹配。selective在自己的JVM中独立评分，不跨JVM比较对象编号。

## 最终五查询结果

每模式有30次正式请求、89个实际字段目标。业务响应按原协议核对，SQL初始化时钟不作跨JVM同值假设，各部署自己的返回时间另与实际DB逐项核验。

| 原C1查询 | 目标/模式 | 业务保持 | 物理绑定 | full与selective各自的最终状态 |
| --- | ---: | --- | ---: | --- |
| 部门详情 | 5 | 6/6请求 | 5/5 | **5正来源正确** |
| 排除子部门列表 | 43 | 6/6请求 | 43/43 | 43语义还原拒绝 |
| 字典类型列表 | 12 | 6/6请求 | 12/12 | 12 evidence_invalid |
| 参数详情，原C1声明 | 5 | 6/6请求 | 5/5 | 5 unknown，声明接入缺口保留 |
| 岗位列表 | 24 | 6/6请求 | 24/24 | **24正来源正确** |

29个已认证答案全部为正来源，没有已知空来源答案。29/89是本配置的可回答且正确比例，29/29是已回答条件匹配；二者不能混为完整API准确率。逐项保持历史MT正确84项中的29项，尚有55项未保持。MT另5项原本没有充分目标/来源真值；不填完整关系Recall，也不以未回答取得性能胜利。

43个部门列表目标的捕获序列闭合、无Collector problem，实际拒绝是`Execution list method unsupported: java/util/List.removeIf(Ljava/util/function/Predicate;)Z`，不是通信身份损坏。后续需要实际谓词、成员变化、写入及异常语义，不能直接删调用或声明只读。

字典问题发生在正式请求的来源快照，`RedisService.getCacheObject`路径上的`binding-after: Unmodeled binding List type`仍使整批无效。它已与独立准备响应的问题分开。现有失败事实不足以确认被拒的具体List运行类，不能仅凭某次mapper返回ArrayList推断；缓存、转换及后续调用义务也仍保留，没有为打分把来源移到helper返回。

### SysConfig C2单列

原C1声明`selectConfigById`，实际执行`SysConfigMapper.selectConfig(SysConfig)`。C1保持原样；C2沿用此前已单列、双方一致的实际mapper声明，输入、目标和mapper返回来源层级不变。

| C2 | full | selective | 固定MT参考 |
| --- | ---: | ---: | ---: |
| 正来源实例正确 | 5/5 | 5/5 | 5/5 |
| 业务匹配请求 | 6/6 | 6/6 | 既有同任务捕获 |

C2不替换C1旧结果，也不拼入29/89。动态`/code`、handler义务、原40 API清单及其他未完成任务继续保留；本轮不是完整RuoYi或外部基准验收。

## 保护、保持与复核

- 最终MVC控制两模式均覆盖独立准备→正式请求→业务原异常→后续正常，以及正式集合错误、带父消息、普通/自定义上下文。输出、集合迭代次数及原异常对象与无Agent一致；不具资格的合法查询确实采全。真实监测失败仍整批拒绝，在派生副本删problem后footer仍拒绝。
- 构造控制每模式2个正来源正确、2个必要unknown；同值改写和经包装发布新DTO不能错误保持。辅助类在根内才初始化时，首根unknown、后续满足条件的根known，捕获仍完整。
- 最终完整部门捕获的36项故障检查中，32项拒绝、4项按既有规则保留unknown，均不产生认证答案；不把unknown统称为采集损坏。代理控制每模式2已知、4 unknown、2同对象异常及12类扰动保持。
- 新Agent可靠性每模式27个场景及5项父状态检查通过；应用调用每模式26已知/8 unknown、另2异常根及预算保护保持；原包装的未知方法拒绝继续有效。控制Agent与业务Agent全部895个class逐项核对，不以不同打包时间的JAR冒充同一文件。
- 原十份RuoYi损坏捕获，在派生副本移除problem后仍由粘性footer拒绝；原始文件未修改。另1774份旧首次文件及1746份旧Mall文件哈希保持。

构造证书消费复用现有、每份捕获内的类初始化索引，保留所有候选和歧义。12份完整捕获的新旧查找实现，其全图节点、边、来源、选择证据及拒绝状态相同；没有计时，不作为新性能结果。full/selective状态及已知答案的逻辑来源签名逐项一致。

本轮没有机械重复Mall、Account、ZLT及原62＋29＋15全部历史业务部署；旧`d69f54a`表仍属于旧版本。本轮针对性保持检查不替代新候选的全量历史部署验收。范围修订和索引为两模式共享改进，不归为selective剪枝收益，也不新增性能优势结论。

主工件为`artifacts/ruoyi-request-scope-20261104/`，最终新部署、评分及完整性核验在`final-03/`。失败、三个开发检查点、两个冻结记录、原始事件、独立坐标、全部计划及命令保留；完整工件、原业务输入和所需运行时另行备份。小型[结果快照](ruoyi-request-scope-results-20261104.json)、[C1逐实例新旧表](ruoyi-request-scope-paired-20261104.csv)、[C2表](ruoyi-request-scope-C2-20261104.csv)随Git。

```bash
python3 experiments/sockshop-mirrortaint/audit_ruoyi_request_scope_revision.py \
  --home artifacts/ruoyi-request-scope-20261104/final-03 \
  --out /tmp/tf2-ruoyi-request-scope-recheck-new
```

复核输出使用新目录。备份详情见[备份清单](ruoyi-request-scope-backup-20261104.json)，属于本机备份，不是异地副本。代码和小型报告提交main；push由用户完成。
