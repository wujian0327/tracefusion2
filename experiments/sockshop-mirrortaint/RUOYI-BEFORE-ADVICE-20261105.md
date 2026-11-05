# RuoYi：前置advice后的mapper来源与Redis集合取证

**部门列表full/selective各39/43正来源正确、4 unknown；字典各12项已取得有效来源事实，仍为unknown。** 没有修改removeIf解释，没有性能实验、新应用或push。原43项拒绝、上轮43 unknown、字典损坏捕获和本轮开发失败继续保留；这是已暴露查询的开发回归。

## 部门：实际匹配、前置效果与新读取

独立诊断Agent观察原输入101：动态匹配为true，实际链为ExposeInvocationInterceptor加动态MethodBeforeAdviceInterceptor，后者调用`DataScopeAspect.doBefore`。进入和返回均记录到同一个advice方法；不是因为拦截器没有匹配而绕过DataScope。原业务源码显示它清理查询参数中的dataScope并读取权限上下文，本轮没有将这些操作声明为只读。

[BeforeAdviceHooks](BeforeAdviceHooks.java)针对固定Spring5.3.39框架核验实际SingletonTargetSource、代理/目标、完整链和所有实际interceptor进入、原动态匹配结果、before完成及目标入口。只允许精确Expose单例和精确MethodBeforeAdviceInterceptor的静态/动态形式；额外around/after链、参数替换或证据不足继续不透明。匹配不重新调用，不额外执行advice。

[离线核验](infer_before_advice.py)要求匹配和before完成先于唯一实际目标Frame，核对目标实现/哈希、实参、返回或原异常。解释目标之前，对旧接收者、参数及可能全局状态保守失效，并将该段登记为opaque-before-effects；参数依赖也不凭同值保持。**随后目标内发生的mapper读取可重新建立字段来源**，不能复活更早的未知依赖，也不能获得“输入未修改”的worker导出资格。

| 条件 | 实现与实际证据 | 失败保护 |
| --- | --- | --- |
| 框架转发形态受限 | 既有直接分派哈希＋4个before相关实现；实际链、进入对象和原match结果 | 不支持链不发证书，完整观测后保守unknown |
| before确已完成 | 原`before()`返回点、调用ID、Frame、线程、索引和顺序 | 缺失、重复、错配或after-target时序不能认证 |
| 旧状态仍可能被改 | 目标前poison、未知实参依赖和opaque效果记录 | 旧来源同值覆盖控制仍unknown，不冒充只读 |
| 新来源确为本次读取 | 实际mapper开始/完成、调用者PC、对象/字段/版本 | 独立原始坐标评分，不用数值连接来源 |
| 目标后没有用户after处理 | 固定before-adapter尾部proceed返回及Expose finally；目标/调用者完成核对 | around改写、替换返回或其他未支持配置继续保守 |

这不是一般应用并发、反射/native、类重定义或任意代理的完备保证。它也没有依据“回调比对象分配早”推导SQL局部性：before效果仍保守处理，来源从完成后的实际mapper返回开始；后续必要未知效果仍失效。

## 必要基础值与试点顺序

越过代理后，首道屏障依次暴露为Long.intValue、继承的StringUtils.split及StringBuilder.append(Object)对Long的呈现。相应补充均为有限公共运算，不是业务字段公式：

- Long.intValue核验既有JDK的Long实现、精确signed64输入及signed32截断，保持原参数来源、选择和unknown。
- 固定Commons Lang3 3.12.0的单字符split和String-only contains：限定非空、至多10000成员的数组，核验实际tokens、成员和返回；任意equals回调、多字符分隔符、空/共享静态数组继续不透明。
- 继承静态调用从冻结类层级及方法缺席证明解析，原调用成功后传出其Class常量；观测不调用loadClass/getMethod，不初始化业务类型。
- StringBuilder仅对实际、精确Long对象补十进制呈现：核验Long及builder实现，signed64值和实际前后字符串；其他对象的未知toString仍不透明。

Commons两个依赖均须已在同一定义加载器中初始化，且初始化证据早于查询根。源代码未新增预热调用。晚初始化的合法执行继续采集，语义不满足条件时保守unknown。

第一次冻结`661adb1`的试点每模式8项均unknown，结果原样保存。补Long呈现后冻结为 **`f8fd38faf73f62bde40b17740b76c8b828dda7f5`**，使用原重复输入101（原case0、5）验证：每模式4项正来源正确、4 unknown，实际10个成员筛到4个。两个输入只是同一查询的初始化守卫检查，不算两个未见查询。原始结果的case0/1标签与原case0/5的对应仅在派生评分视图中声明，消息、输入及原始捕获不变。

两模式均有独立认证的mapper字段后才扩跑全部原六输入、43目标；首请求unknown仍保留，没有按答案筛样本。

## 同一候选的新部署结果

| 原C1任务，各模式分别统计 | 目标绑定 | 来源正确 | unknown | 证据无效／错误确定答案 |
| --- | ---: | ---: | ---: | ---: |
| 排除子部门列表 | 43/43 | **39正来源** | 4 | 0／0 |
| 字典类型列表 | 12/12 | 0 | 12 | 0／0 |
| 部门详情保持 | 5/5 | **5正来源** | 0 | 0／0 |

部门39项来源逐项对应本JVM实际`SysDeptMapper.selectDeptList`返回的字段、对象及写入版本，包含确实删除成员、保留多个结果的输入。其余4项均为首次101请求：ArrayUtils在查询内初始化，证书前提不成立，继续unknown。39/43是本固定任务的可回答且正确比例，已回答39/39匹配；不能称完整43项能力对齐。

例如full第二个输入的`/data/1/deptName`，独立真值与预测均指向mapper调用者Frame `f96`、来源事件1211、读取路径`/1/deptName`、实际对象`o452`、`SysDept.deptName`版本1。其他JVM使用自己的坐标独立评分，不跨部署比较对象编号。六份部署的业务响应均为6/6保持；full/selective状态和已知答案的逻辑来源签名逐项相同。

本轮仅重跑三个C1任务。岗位列表、原C1参数详情、C2校准、Mall、Account、ZLT及62＋29＋15旧成绩仍归其原版本，不拼接成新版89项或总体正确率。MT原配置与结果未修改，也未冒充本轮新部署。

## 字典：结构观测已闭合，toList效果仍未闭合

固定Fastjson2 2.0.64的JSONArray/JSONObject按实际加载字节码核验，并核对既有JDK内部布局。[观测器](JsonTreeObservationHooks.java)只读ArrayList.elementData/size/modCount或HashMap表及精确LinkedHashMap.Entry，不调用Fastjson重写的get、keySet、iterator或toString。未知子类、节点形态、循环、大小超限或修改矛盾继续拒绝必要快照。

[证书](infer_json_tree_observation.py)将容器、成员、字段/键、epoch、加载器和快照引用连接到本次声明读取；SourceCapture必须为真，调用ID、Frame、线程、消息和完成事实必须对应。普通调用也可以安全记录这些对象的物理内容，但**获得观测资格不等于该方法获得语义或只读许可**。

新捕获中，实际`ValueOperations.get`返回的JSONArray及成员字段已经完整配对；12个目标均有独立物理实例真值。当前首次失效在`DictUtils.getDictCache` PC15的`JSONArray.toList(Class,JSONReader.Feature[])`。没有把来源边界移到getDictCache，也没有以转换前后同值或同对象替代效果证明。

原JAR的RedisConfig及FastJson2JsonRedisSerializer审阅保留：Object.class、WriteClassName和AutoTypeFilter。新增证书直接核验**实际读取返回对象**，不认证原始Redis字节的反序列化语义，也不宣称toList的完整转换/回调效果已解释。

## 控制、工件与复核

before控制每模式4已知正来源、4必要unknown，另2个同对象原异常；15类来源/调用/链/时序扰动保持保护。Commons控制每模式预初始化5已知/3 unknown，晚初始化4已知/4 unknown；继承别名未被监测初始化，原equals调用次数保持。Long截断及Long呈现各每模式9正来源、1必要unknown，极值、重复值及错证据保护通过。JSON控制覆盖重复值不同对象、null、空集合、读取配对和5类扰动；不支持子类业务保持、捕获仍无效。

没有机械重复全量历史部署。监测可靠性控制及最终原业务验收分别保留；本报告不把它们合并成一种成功指标。

最终在线源码为`f8fd38faf73f62bde40b17740b76c8b828dda7f5`，Agent SHA256为`dcc5fb470cd24d44c2a23d94cc0e5f50dfff92e2ad2eeb75f5d043b1f553c331`。最终离线源码为 **`629755be2f95def1272049ceead19aa9383feaab`**：134项冻结清单中只有`infer_application_execution.py`相对在线版本变化，Agent和部署计划未变。最终基础值、JSON和代理控制Agent的901个class哈希与业务Agent逐项相同；不同打包时间的JAR不写成同一文件。

离线修订处理before中已计划辅助方法的完整Frame前缀：先按原父子、开始/完成及作用域规则核验闭合的前缀，再保守登记before效果并连接实际目标；不把这些辅助方法的效果当作已解释。否则部门详情会报`Opaque callback contains unrelated parent evidence`。原`audit-final-01`失败保留，同一完整捕获经修订后恢复5/5；部门列表和字典的新旧完整图节点、边、来源及选择证据一致。其后发现错误helper父Frame可能在根族遍历时被遗漏，另加全局父Frame存在及先后检查；原反例和修订后拒绝结果均保存，没有删除原事件。

最终完整列表捕获每模式8项扰动：缺失/歧义字段各保留unknown，其余错call-id、错PC、缺失/重复before步骤、冒充空链和粘性损坏均拒绝。前缀控制另对提前目标Frame、缺helper完成、错helper父Frame各模式全部拒绝。60份本地完整开发捕获通过父Frame兼容检查；这只是归属检查，不是60份业务能力验收。监测可靠性两模式各27个场景及5项父状态检查的结果保留，没有为unknown放宽整批失败规则。

主工件`artifacts/ruoyi-before-advice-20261105/`，最终候选和新部署在`revision-02/`。原协议在首个核心修改前保存；后续设计、未冻结开发构建及两次冻结记录单列，部分开发协议的Git HEAD标签仅代表检出基点，不能当作所编译修改的冻结哈希。首次控制选到field-copy未能核验内核调用配对，后改用明确包含数组操作的小程序；原失败保留，不改动业务输入。

最终审计为`revision-02/audit-final-03/`，完整捕获兼容为`offline-compatibility-final/`，故障保护为`protection-final-02/`和`prefix-guards-02/`。小型[结果快照](ruoyi-before-advice-results-20261105.json)、[逐实例新旧表](ruoyi-before-advice-paired-20261105.csv)及[备份清单](ruoyi-before-advice-backup-20261105.json)随Git保存。备份是本机副本，不是异地副本；完整工件和必要既有镜像、JDK均保留引用。代码与小型报告提交main，push由用户完成。

```bash
python3 experiments/sockshop-mirrortaint/audit_ruoyi_before_advice_revision.py \
  --home artifacts/ruoyi-before-advice-20261105/revision-02 \
  --out /tmp/tf2-before-advice-recheck-new
```

输出必须使用新目录；冻结清单、旧引用及原捕获哈希均参与复核。没有新增成本数据或性能优势结论。
