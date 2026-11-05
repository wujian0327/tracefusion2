# RuoYi字典：受限toList身份转移与集中能力回归

**冻结候选的字典full/selective各12/12正来源正确；原C1五查询各80/89正确、9 unknown、0证据无效、0错误确定答案。** 89个目标均已绑定。剩余9项为部门列表首请求的4项初始化限制，以及原SysConfig C1声明缺口的5项；没有加预热或修改原来源边界。C2继续单列。本轮没有性能实验、新应用或push。

这是已暴露入口的开发回归。旧12项无效、上一轮12 unknown、本轮先后试点及失败目录保留，不回填为修复后成绩。参照为`31df57b`报告及其在线`f8fd38f`、离线`629755b`实现。

## 实际分支与有限模型

Fastjson2 2.0.64的`JSONArray.toList(Class, Feature[])`先取得ObjectReader，再逐个处理成员。JSONObject/Map会进入`createInstance`；其他非空、非目标类型成员可能调用类型转换Function。**“成员已经是DTO”不能单独证明整个方法没有回调**：此前的reader查询缓存未命中，还可能进入模块和reader创建逻辑。

[运行证书](JsonListCopyHooks.java)只接受下列共同条件：

| 条件 | 实际检查 | 不满足时 |
| --- | --- | --- |
| 实现固定 | 原始加载字节码锁定JSONArray、JSONFactory、ObjectReaderProvider；JDK8u504的ArrayList、AbstractList、ConcurrentHashMap、ThreadLocal、Class、Object同时核验 | 不颁发语义资格，矛盾或监测失败保留无效标记 |
| 初始化已完成 | JSONFactory初始化结束点事实，定义加载器一致，且早于本次查询根 | 根内初始化继续unknown，不解释或放松初始化效果 |
| 只走缓存命中 | 原`getDefaultObjectReaderProvider`返回的精确provider；plain ThreadLocal；原`ConcurrentMap.get`的实际非空结果；精确ConcurrentHashMap、Class键、fieldBased=false | cache miss、其他provider或必要事实缺失不能获得此模型 |
| 不执行转换 | Feature数组为空；精确JSONArray；所有成员均为null或实际目标Class的实例，且不是Map | JSONObject、Map、类型转换及非空Feature继续不透明 |
| 复制身份而非数值 | 输出为原方法创建的新精确ArrayList；输入前后成员顺序、epoch与输出逐项引用身份一致 | 改动、错对象、错顺序或完成矛盾不能认证 |

缓存命中路径经过审阅的字节码直接返回reader；该reader在所支持的成员分支里不被调用。ArrayList创建和复制只写新列表。模型不将任意Fastjson方法、reader、模块或DTO构造器声明为只读，也不把复制后的对象重新登记为来源。没有额外执行getObjectReader、业务getter、toString、reader回调或转换方法。

[离线转移](infer_json_list_copy.py)保留已有成员的来源、选择证据与unknown，并登记新列表到原成员的可达关系；不生成DTO解码边、不授予对象私有性。每份捕获的索引保留全部初始化、类及cache候选；重复、错调用、错加载器及错误时序仍检查，不跨捕获缓存认证结论。此模型是有限公共契约及可执行保护，不宣称任意Fastjson转换完备。本轮仍不支持任意反射/native改写、类重定义与共享并发修改；provider的final cache构造布局及Factory的final ThreadLocal也在字节码审阅范围内。

试点越过toList后，实际下一道屏障是`StringUtils.isEmpty(Collection)`内部的`Collection.isEmpty()`。本轮把这一精确接口调用接入既有受支持列表读取语义，继续核验实际集合类型、内容阶段和JVM结果；没有开放任意Collection实现或其他方法。

## 试点与正式RuoYi结果

原字典首个非空输入`sys_user_sex`，两模式各三个目标。初次派生评分因后续isEmpty仍为3 unknown；补齐接口读取后，同一完整试点捕获各3/3正来源正确，首道依赖失效为零。该离线修订没有冒充第二次Agent部署，也未覆盖第一次评分。

随后冻结 **`9536c316514696069988e9438ab8982f37f2d29b`**，锁定138项核心源码与正式计划，再用同一新Agent重新部署原C1全部五查询。原版参照沿用既有原请求和独立DB事实，MT原生传播及适配器不变，未声称重新部署MT。各配置独立容器和数据卷，保留全部六个原输入。

| 原C1，各模式分别统计 | 实际目标 | 正来源正确 | unknown | 无效／错误确定答案 |
| --- | ---: | ---: | ---: | ---: |
| 部门详情 | 5 | 5 | 0 | 0／0 |
| 排除子部门列表 | 43 | 39 | 4 | 0／0 |
| 字典类型列表 | 12 | 12 | 0 | 0／0 |
| 参数详情，原C1声明 | 5 | 0 | 5 | 0／0 |
| 岗位列表 | 24 | 24 | 0 | 0／0 |
| 合计 | 89 | 80 | 9 | 0／0 |

80/89是本配置的可回答且正确比例，已回答80/80实例匹配；不当作完整HTTP API准确率，不包含动态`/code`、handler或保存sink义务。C1保持历史MT正确84项中的80项，未保持的4项仍为原首次部门请求；MT另5项原事实不足，不据此填完整关系Recall。

字典每模式五次非空Redis返回均有独立来源事实及实际reader缓存命中。输出列表是新对象，成员仍为本次Redis读取返回中的原DTO；物理对象、字段和版本与目标对应。没有靠字典文本相等，也没有把来源改到DictUtils/helper返回。缺失字典类型输入仍不产生成员目标，未从输入清单删除。

SysConfig既定C2校准用同一候选重新部署，full/selective各5/5正来源正确，六个原输入的业务行为均保持。它不替换C1的5项unknown，不拼成新版94项准确率。最终离线版本的集中保持已通过，分集合结果如下。

## 标量与null反例：离线修订单列

冻结9536c31之后的补充控制发现真实缺口：复制字符串或直接null成员时，没有查询既有`@list:i`来源槽位，导致两模式各3项错误地判为已知空来源。第一次直接String Class字面量控制被旧规划范围拒绝；随后使用发生在新读取之前的opaque Class helper构造可接纳程序，实际捕获暴露了该问题。没有为了测试扩大Class字面量策略。

该失败保存在`scalar-reproduction-02/`，不改成unknown或并入业务89项。离线修订候选将标量/null成员交给现有来源查询：核对容器对象、槽位、epoch、调用发生及完成，唯一且充分的原来源事实才能建立依赖；缺失和歧义继续unknown。没有用值相等、String缓存身份或Class名字生成来源。

隔离修订已在原反例同一完整捕获上得到两模式各3/3正来源正确，并通过缺失槽位、歧义、错版本及错调用保护。DTO引用分支不变，RuoYi C1全部十份图的节点、边、来源、选择证据相同。原冻结采集使用其锁定源码，闭合后才将已封存修订合入main。最终离线代码为 **`5f0c64746e28705d7be5d5d39850ad49272d97d8`**；与在线9536c31的138项清单相比仅两项Python文件变化，Agent及全部计划不变。新JVM标量控制再次各3/3正来源匹配；不把原业务捕获复算冒充新Agent部署。

## 同一采集批次的最终能力保持

所有业务集合均以本轮新Agent、新容器与独立数据卷采集；TF全量部署在9536c31冻结下完成。两文件离线修复随后使用同一完整捕获复算，292份捕获的全图节点、边、来源和选择证据逐项相同。因此保留这批实际新部署的采集出处，另记录最终5f0c647还原版本，不称再次部署。

| 集合，每种模式分别统计 | 已知且独立实例正确 | 保留的unknown |
| --- | ---: | ---: |
| Mall固定任务 | 98/103 | 5，独立真值不足 |
| ZLT两个入口 | 15/15 | 0 |
| PiggyMetrics Account | 40/40 | 0 |
| 原62查询 | 428/431 | 3 |
| 已启封29字段 | 232/244 | 12，独立真值不足 |
| 15个Route/Price写入口 | 96/96 | 0 |

Mall逐项保持历史MT正确88项及此前TF正确98项；Account保留4正来源、36已知空来源和MT原正确36项。原62查询保持历史MT正确368项及旧TF正确213项，关系TP397、FP0、FN3，FN包括3个unknown阳性目标。29字段的12项真值不足不能用于完整关系Recall。不同集合不合成总体准确率，也不视为原40 API全部完成。

62、29、写入口及Account中，最终修复分支未产生不同图；原逐项独立真值及评分保留。62及ZLT另以最终代码重做正常离线还原，Mall/C1/C2的状态与来源签名复核通过。没有减少检查或将原unknown改为空来源。

## 控制与保护

独立程序两模式各8个目标：预初始化下2个正来源、3个已知空来源正确，3个必要unknown。覆盖重复文本的不同对象、null、空列表、同值覆盖，以及JSONObject转换、非空Feature和reader缓存未命中。原版与Agent业务结果一致；Box自定义equals/hashCode/toString的调用计数保持，观测没有额外调用它们。同值覆盖不再连接旧字段来源。

补充实际根内初始化控制：先在根内执行reader准备、再发生声明读取，随后toList实际cache hit；因初始化晚于根，第一项仍unknown，后续满足条件的根可回答。该控制在候选冻结后补入，不称预注册样本。没有用这个控制的预初始化方式改变RuoYi业务输入。

每模式7类证书扰动拒绝；完整正式字典捕获每模式12类扰动中，7类拒绝、5类保留unknown，均不输出认证答案。缺失/歧义来源、错误版本或资格不足的unknown与证据矛盾拒绝分别记录。已有成员的origin、selector、unknown及引用身份另做状态单元检查，复制不授予私有对象资格。监测可靠性两模式各27个业务场景、5项父状态检查及RPC/异步清理保持。

原ThreadLocal控制草案误尝试写static final字段，原版即失败，目录保留并撤回该场景；没有借助Unsafe修改它。完整捕获故障驱动的两次初稿误用消息/调用者Frame寻找copy事件，失败保留；最终按实际source容器对象与唯一后续copy call-id连接。修正只涉及测试驱动，没有改原捕获或算法。

## 工件与复核

主目录`artifacts/ruoyi-tolist-20261105/`。修改前协议、固定JAR/JDK的字节码审阅、工作树开发构建、试点评分01/02、正式C1/C2、控制、损坏副本及集中回归分开保存。在线Agent SHA256为`b3aed9effffda968512a7ba4fc28aed40789af19a2340d4b668e5849575322ab`，正式与最终控制的903个class逐项相同；JAR打包时间差异不当作同一文件。在线/离线冻结、原始失败和新结果分目录保留。

主审计为`audit-delivery-01/`；最终C1/C2分别为`audit-offline-C1/`、`audit-offline-C2/`，各历史集合为`audit-offline-historical/`、`audit-offline-mall/`及`audit-offline-zlt/`。初始业务评分、9536c31全量新部署及其验收在原目录保留，没有覆盖。

小型[结果快照](ruoyi-tolist-results-20261105.json)、[C1逐实例表](ruoyi-tolist-paired-20261105.csv)、[C2逐实例表](ruoyi-tolist-C2-20261105.csv)及[备份清单](ruoyi-tolist-backup-20261105.json)随Git保存。完整工件另作本机备份，既有镜像/JDK备份重新核对哈希与gzip CRC；这不是异地副本。代码和小型报告提交main，push由用户完成。

```bash
python3 experiments/sockshop-mirrortaint/audit_ruoyi_tolist_revision.py \
  --home artifacts/ruoyi-tolist-20261105 \
  --out /tmp/tf2-ruoyi-tolist-recheck-new
```

输出使用新目录。最终核心哈希、旧引用、原捕获、292份图等价及标量修复结果均参与核验。本轮没有新增性能数据或优势结论。
