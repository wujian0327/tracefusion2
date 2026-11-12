# 方法边界与状态退役

基线 main 4035a025c07f1a6a7f3cbc0b0fe5c72066b0798b。开始时无未提交文件。遵循根 AGENTS.md，在 main 分两项提交，不 push。原127项单测先行通过（失败/跳过/缺依赖均0）。所有新工件在 artifacts/method-lifecycle-20261112/；历史工件不改。

## 第一项：方法边界

声明类型编码统一复用 Recorder.fieldValue/primitiveValue：Frame enter/正常finish/异常abort；Collection beginAt/end/throw；ExecutionKernel constructorBegin/constructed/constructorFailed、lambda捕获；SourceObservation调用；由已核验Method取得声明的直接分派、before advice和async-submit参数；async Future cancel结果；日期调用、removeIf额外结果和根binding-return。PlannedServiceAgent.arguments及其它ASM参数数组仍可装箱，但编码发生在id之前。原始Object[]只是载体时不登记载体ID；声明为Object/数组/Integer/Long的业务值继续保留真实引用。Callable.call/Future.get的声明返回Object，绝不按运行时Number猜测基本类型。

start增加method_value_version=1；边界携带method_descriptor。基本类型保留primitive类型、值和F/D原始bits；void为object:null/value:null/void:true。method_value_protocol逐条核对原Frame签名、原调用指令/PC、构造、lambda bootstrap参数和已固定Method，验证数量、类别、范围、浮点bits、返回值及构造receiver。原field_value_version=1不变。旧捕获缺少method版本时按旧入口处理；有新描述符却删版本、描述符缺失或矛盾、基本类型与引用伪装均证据错误。没有扩大构造/native许可或虚调用支持。

首阶段140单测通过（原127+新增13），失败/跳过/缺依赖0。固定业务JDK8u504，构建javac8u512；新Agent SHA256 f6814df627aed5af8f495b471a7fe359a38aec26daa6b9b1408ff2de74693c51，build/源码/依赖收据见method-agent-01/build.json。真实JVM method-controls-final-02在full/static/selective均通过：八种基本类型、混合双槽、同值不同身份Integer/Long/Object、null/void、带基本参数构造、异常完成、primitive与真实引用lambda捕获及独立来源/selector/版本核验。42项新证据扰动全部拒绝。原异常序列method-existing-builtin各28/28；method-old-audit旧证据复算72扰动通过，18旧公共捕获保持、原6 unknown和既有拒绝保持。

固定对象图两阶段各200次probe，三模式一致：旧Agent IDS 56→9656→19256，新Agent 6→6→6；VERSIONS均0。配对工件method-stress-before/after，二者fixture哈希相同。没有把装箱分配减少推断成性能或内存收益。

```sh
PYTHONPATH=experiments/sockshop-mirrortaint python3 -m unittest test_control_dependencies test_call_write_effects test_application_call_status test_jvm_semantic_rules test_http_instance_sources test_response_binding test_exception_completion test_exception_dispatch test_field_value_protocol test_method_value_protocol
python3 -c "import sys;sys.path.insert(0,'experiments/sockshop-mirrortaint');from build_distributed_plans import build;from pathlib import Path;build(Path('/tmp/tf2-method-agent-new'),{})"
python3 experiments/sockshop-mirrortaint/run_method_observation_controls.py --agent /tmp/tf2-method-agent-new/distributed-observer.jar --out /tmp/tf2-method-controls-new
python3 experiments/sockshop-mirrortaint/run_method_observation_controls.py --stress-only --agent /tmp/tf2-method-agent-new/distributed-observer.jar --out /tmp/tf2-method-stress-new
python3 experiments/sockshop-mirrortaint/check_method_observation_controls.py --home artifacts/method-lifecycle-20261112/method-controls-final-02 --out /tmp/tf2-method-guards-new
```

所有--out目录必须新建。method-controls-01保留初版POP2使probe超出解释支持的unknown；修订fixture以原支持的LSTORE/DSTORE消费结果。method-controls-final保留直接Predicate.test超出既有回调分派而poison来源的unknown；最终lambda控制只验证捕获，不将未支持的直接调用包装成known。原失败与独立预期保留，未扩张许可。

## 第二项：首批状态退役

修改前的完整持有关系表见 [STATE-RETIREMENT-SCOPE-20261112.md](STATE-RETIREMENT-SCOPE-20261112.md)，涵盖请求/调用/异步ThreadLocal及旁路缓存。实现位于WeakIdentityMap.java、OwnerVersions.java、Recorder.id/drainRetired/lifecycle及相关Hooks。

WeakIdentityMap按System.identityHashCode分桶、按引用==匹配，不调用业务equals/hashCode；不是WeakHashMap。弱引用负责查找，独立PhantomReference/ReferenceQueue确认最终可退役，确认后clear phantom。ID使用捕获内单调long序号，累计分配不受当前表size编号影响。弱引用已清除而终止证明尚缺时，无法认证的同identity-hash查询明确拒绝（含复活边界），不会给可能相同对象重新编号。活对象跨请求/线程保持原ID。ACTIVE非空域还会延迟该ID及关联元数据的退役。

IDS、字段版本、ARRAY_VERSIONS/ARRAY_SLOTS、READ_ONLY、CONTENTS/EPOCHS、Date WIRE以及Future关联纳入范围。VERSIONS由owner-ID索引归属，最终队列确认后按预算删除owner字段条目，禁止清空/删除活跃版本。CONTENTS只存安全观测数据，入表前safeEvent校验；自引用容器表示为ID，不反向强持有容器。FUTURES由Future→Task改为弱身份Future→独立Long任务ID，不持有Task/delegate；同一存活Future多次get、cancel、异常完成继续关联原任务，不在首次get后删除。实际执行中的Task由执行栈和ACTIVE保持，finally恢复外层任务/移除当前任务。

清理复用原Recorder锁，不重构事件顺序或全局锁，不发事件改写历史。普通操作每表处理有限队列项；每64次id查询推进所有可退役表，显式诊断预算限制为0..1024，字段条目另分预算清理。每表当前登记（含待确认/活动域延迟）上限100,000；字段条目上限1,000,000，原事件上限不变。未提高原身份表上限，超限明确失败，不静默丢弃证据。累计分配序号可超过100,000。

start增加identity_lifecycle_version=1，metrics包含累计ID分配/当前登记/累计退役、弱清除/终止延迟、字段/数组条目及退役/待清理数，以及保留状态和当前线程诊断。离线校验累计分配=登记+退役、非负计数和必要footer；未知版本、缺计数或删除新版本字段都拒绝。旧捕获无此版本/计数时按旧格式解析。此协议只是运行时计数，不改变历史ID和版本语义；登记数包含待处理项，不等于实测存活对象或堆内存。

继续保留：未消费stream及其真实source/predicate（存在值回边风险）；Class/ClassLoader/Field缓存及初始化/覆盖证明；原活动网络读取、调用、来源域及嵌套ThreadLocal。诊断逐项暴露其数量。未证明安全的对象复活明确拒绝；类型卸载、未闭合I/O、未消费stream图不在退役许可。由这些保留状态实际可达的对象也可能继续登记，不宣称整个Agent已无生命周期泄漏。

## 准确结果

最终147项Python单测通过：原127、方法协议新增13、退役协议新增7；失败0、跳过0、缺依赖0。GC/并发/Future另为真实JVM组件控制，不冒充Python单测或来源端到端评分。

| 控制 | 修复前 | 最终修复后 |
| --- | --- | --- |
| 固定引用图，三模式各两阶段×200次probe | IDS 56→9656→19256 | IDS 6→6→6，VERSIONS均0 |
| 64普通对象+64自引用数组释放，有界GC重试 | IDS128、字段64、数组版本64、slots64不降，终止队列见证0 | 终止见证128，IDS/字段/两数组表均0 |
| 8线程共享活对象，4,000次写入 | 本轮无旧并发重跑成绩 | 同一ID，原版本5连续至4005；其余请求结束不清共享对象 |
| 可变equals/hashCode、业务hash相同、真实identity-hash碰撞 | 保留旧实现作为比较，不回填成绩 | 均保持不同对象身份；另用会抛异常的equals/hashCode验证完全未调用 |
| 4线程登记与并发GC | 未执行旧实现对照 | 4,000终止队列见证通过，无重复ID或丢版本 |
| 40批×(1,500普通对象+1,500数组) | 旧强表不能完成首批释放，未声称完成累计控制 | 累计120,000；每批后字段/数组状态归零，累计序号不停增；与事件数量上限分开 |
| 活动读取域已无物理owner引用 | 未执行旧实现对照 | 终止证明到达仍保留版本，Scope.close后才清理 |
| 自引用容器及Date WIRE | 静态审查旧强持有，不伪造旧GC成绩 | 队列确认后READ_ONLY/CONTENTS/EPOCHS/WIRE退役；没有值回指阻止回收 |
| 存活Future正常/异常/取消重复get，及拒绝 | 旧Future→Task→delegate持有关系见清单 | Future保留原任务ID，delegate终止队列证明通过；运行中cancel仍保持执行状态，finally后清理 |
| 对象复活 | 不宣称旧实现可退役 | 拒绝重新编号，版本保留至最终终止证明；明确能力边界 |

GC主控制全程仅32条事件，最终累计分配124,160、确认退役124,159、当前登记1；字段、array versions/slots、容器表、Future关联、WIRE及当前线程活动表均0。保留1个登记项如实计入，不将其隐藏成全表清空。状态表数量不换算内存。GC每项最多80次重试，并检查独立PhantomReference队列；一次System.gc不算成功，超时给出收到/预期见证数及完整状态计数。单独Map组件还验证活跃条目上限拒绝、GC后容量恢复、putAll字段归属及禁止全局版本清空。

最终Agent `1ec8bdb276e0a770925934268ceeaf2b2a69a0ba9adc07142402daa027964033`（lifecycle-agent-06），业务JDK固定8u504、常规Agent构建javac8u512。辅助真实Spring控制固定8u504编译/运行，独立Agent SHA `471c8f2fde88a3471b85e844e6312a0d32442050bef8dfabcdda250da33c6ff7`。二者不混称同一二进制；类哈希、协议、配置、源码/依赖哈希及实际命令见 [收据](method-lifecycle-results-20261112.json)。

最终full/static/selective重新采集并逐项与独立预期比较，之后才比较规范化来源角色，未跨捕获匹配原始ID字符串：

| 控制 | 每模式结果 | 新目录release下 |
| --- | --- | --- |
| 原构造case8 | 2/2正确 | case8 |
| 原异常连续控制 | 28/28正确 | builtin |
| 业务自定义异常 | 13 known字段答案+1正确aborted完成，14/14义务 | custom |
| 基本类型字段 | 3/3（big、真实boxed、null），合计9/9 | fields |
| 新方法边界 | 参数/返回/构造/异常/lambda捕获全部核验，来源/selector/版本正确；另验证F/D非标准NaN载荷和负零 | methods-bits |
| 原66公共控制 | 60正确、6 unknown，整体门槛false | original66 |

原6 unknown仍为scenario14/16各输入0/1/2。输入0的候选数据/选择/版本相符但备选构造效果未闭合；1/2实际opaque构造后数据来源仍不确定，候选选择及版本保持。没有改变独立完整预期，也没有把unknown改称known。构造/native效果、跨应用加载器、条件写地址和覆盖分派等限制均保留。逐项物理坐标、origins、selectors、版本、known和完成状态见 [342行案例表](method-lifecycle-cases-20261112.csv)。

114项最终新扰动（方法42、字段30、异常分派30、退役计数12）全部符合预期，其中必要来源删除保持unknown，其余矛盾证据拒绝。辅助真实Spring full/selective各15个任务、各14项扰动通过；新参数/字段/退役格式也在这些真实Method和Future捕获上逐条校验。监控故障控制full/selective各27个业务结果与原JVM一致，每模式5项父域保持检查；正常、异常及监控失败后状态清理，原异常身份/finally保持，故意损坏捕获有problem/sidecar/invalid footer，不算有效来源通过。相关框架RPC、异步、来源读取失败清理也保持。

旧捕获复算单列final-old-audit/final-old-business：18公共捕获、14业务捕获origins/selectors/known/版本/根审计保持，原调用写控制22/22及72旧扰动保持。旧审计的current-core模式保留实际源码哈希、历史失败/金标准/原Agent和许可JSON校验；最终审计再次校验这些哈希及所有新模块/Java源码，未删除验证以通过。

## 复现与保留

在仓库根执行，所有--out均使用不存在的新目录。运行JDK路径、Java/rt.jar/libjvm及所有Agent类哈希随收据保存，实际每次调用的配置和命令也在工件中。

```sh
PYTHONPATH=experiments/sockshop-mirrortaint python3 -m unittest test_control_dependencies test_call_write_effects test_application_call_status test_jvm_semantic_rules test_http_instance_sources test_response_binding test_exception_completion test_exception_dispatch test_field_value_protocol test_method_value_protocol test_identity_lifecycle_protocol
python3 -c "import sys;sys.path.insert(0,'experiments/sockshop-mirrortaint');from build_distributed_plans import build;from pathlib import Path;build(Path('/tmp/tf2-lifecycle-agent-new'),{})"
python3 experiments/sockshop-mirrortaint/run_lifecycle_state_controls.py --agent /tmp/tf2-lifecycle-agent-new/distributed-observer.jar --out /tmp/tf2-lifecycle-state-new
python3 experiments/sockshop-mirrortaint/run_method_observation_controls.py --agent /tmp/tf2-lifecycle-agent-new/distributed-observer.jar --out /tmp/tf2-method-new
python3 experiments/sockshop-mirrortaint/run_method_observation_controls.py --stress-only --agent /tmp/tf2-lifecycle-agent-new/distributed-observer.jar --out /tmp/tf2-method-fixed-graph-new
python3 experiments/sockshop-mirrortaint/run_constructor_scope_controls.py --case 8 --agent /tmp/tf2-lifecycle-agent-new/distributed-observer.jar --out /tmp/tf2-case8-new
python3 experiments/sockshop-mirrortaint/run_exception_completion_controls.py --supported-sequence --agent /tmp/tf2-lifecycle-agent-new/distributed-observer.jar --out /tmp/tf2-builtin-new
python3 experiments/sockshop-mirrortaint/run_exception_dispatch_controls.py --agent /tmp/tf2-lifecycle-agent-new/distributed-observer.jar --out /tmp/tf2-custom-new
python3 experiments/sockshop-mirrortaint/run_primitive_observation_controls.py --agent /tmp/tf2-lifecycle-agent-new/distributed-observer.jar --out /tmp/tf2-fields-new
python3 experiments/sockshop-mirrortaint/run_public_control_semantics.py --agent /tmp/tf2-lifecycle-agent-new/distributed-observer.jar --out /tmp/tf2-original66-new
python3 experiments/sockshop-mirrortaint/audit_method_lifecycle.py --home artifacts/method-lifecycle-20261112 --out /tmp/tf2-method-lifecycle-audit-new
python3 experiments/sockshop-mirrortaint/audit_exception_completion.py --current-core --out /tmp/tf2-lifetime-old-audit-new
python3 experiments/sockshop-mirrortaint/check_exception_completion_old_captures.py --out /tmp/tf2-lifetime-old-business-new
```

辅助框架控制使用固定JDK的PATH（必须加引号），而非宿主java；其独立Agent的编译版本也单列：

```sh
env PATH="/home/wujian/tracefusion2/artifacts/galette-static-baselines-20261111/runtime-base/java-8-openjdk-amd64/bin:$PATH" python3 experiments/sockshop-mirrortaint/run_monitor_reliability_fixture.py --build artifacts/method-lifecycle-20261112/lifecycle-agent-06 --out /tmp/tf2-monitor-new
env PATH="/home/wujian/tracefusion2/artifacts/galette-static-baselines-20261111/runtime-base/java-8-openjdk-amd64/bin:$PATH" python3 experiments/sockshop-mirrortaint/run_async_task_semantics.py --libs artifacts/async-protocol-revision-20261021/inspection/libs --out /tmp/tf2-spring-async-new
```

主工件目录保留所有初版失败：方法POP2/未支持直接Predicate调用、生命周期驱动timeout参数错误、最小诊断plan缺json_schema、最初PATH未引用导致命令未启动；修订后的新目录不覆盖它们。GC组件使用无伪造业务Frame的独立诊断plan，只调用Collector状态API，不生成来源评分；六组业务控制则是原始字节码实际插桩的新JVM来源验证，两者分列。

本轮缺依赖0；未执行无关历史容器重部署、类卸载、堆内存测量或性能基准。没有论文创新或性能收益结论。两项在main分别提交，由用户手动push。

最终发布前另将引用节点构造放在owner ID登记之后，避免id登记推进队列时出现尚未入索引的引用；lifecycle-agent-06及release/整套新捕获重新通过。旧01..05 Agent和中间捕获全部保留。最终状态/单独Map组件工件在release/state；原强持有对照在lifecycle-before-portable-02，方法修复前后固定图配对在method-stress-before/after。
