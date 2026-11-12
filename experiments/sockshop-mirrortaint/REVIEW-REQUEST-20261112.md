# 本轮三项请求的核查与修复

起点 main `15c7f35`，用户审查基线 `16ddf1f`。工作遵循根 AGENTS.md，在 main 分项提交，不 push。

## 一：保留已有异常完成修复

问题已由 `2cff7b8`、`66933b8`、`9fbbc34` 修复；本轮未覆盖这些正确转移。`test_exception_completion.py` 的30项回归已覆盖载荷与条件、空完成证明、隐式空引用/数组、abort/catch清理及finally。原失败和独立预期继续保留。

本轮准确命令（工作目录 experiments/sockshop-mirrortaint）：

```sh
python3 -m unittest test_control_dependencies test_call_write_effects test_application_call_status test_jvm_semantic_rules test_http_instance_sources test_response_binding test_exception_completion
python3 audit_exception_completion.py --out /tmp/tf2-task1-audit-20261112
python3 run_constructor_scope_controls.py --case 8 --out /tmp/tf2-task1-case8-20261112
python3 run_exception_completion_controls.py --supported-sequence --out /tmp/tf2-task1-sequence-20261112
```

结果：93单测通过，失败0、跳过0、缺依赖0。旧证据审计72项通过。新JVM原case8 full/static/selective各2/2，与独立origins/selectors/版本/known预期匹配；域内连续序列各28/28。JDK 8u504、原Agent SHA256 `367cbb2300e507e5db4716c4e2fcbed1a39898c5e6c6f5f23583c4c1487e2764`，此项采集协议未变。命令和新原始事件保存在上述目录，历史证据未改。

原66项旧捕获仍60正确、6 unknown（scenario14/16各输入0/1/2）；0为未执行备选构造效果未闭合，1/2另有实际opaque构造失效。没有扩大只读许可。全候选池另有2项既定写地址限制、2项覆盖分派拒绝，历史结果按 EXCEPTION-COMPLETION-SEMANTICS-20261112.md 保留；不宣称完整Java语义已通过。

追加回归：新业务异常控制中的 returning-finally 暴露了编译器复制相同终止代码造成的多报条件。`ControlFlow.completion_join` 按原指令、操作数和异常保护范围识别等价终止后缀，在两份后缀入口结束异常范围；已携带到局部值、栈和堆的选择不清除。4项独立单测覆盖相同后缀、不同常量、不同异常保护及作用域清理。新JVM控制初版 case6 两输入均多报g，保留原12/14结果；同捕获按原独立预期复算14/14。新采最终结果在任务二目录单列。

历史审计默认冻结核心哈希，修改后直接执行会按预期拒绝。新增 `--current-core` 仅解除当前实现哈希锁，保存实际源码哈希；原始失败工件、金标准、许可JSON及旧Agent仍核验。`python3 audit_exception_completion.py --current-core --out artifacts/review-request-20261112/task1-current-core-audit`：72项扰动通过、18份旧公共捕获答案/根审计保持、旧构造池14正确/4 unknown/2拒绝、原66项60正确/6 unknown保持。此为旧捕获复算。

## 二：业务异常类型分派

`exception_dispatch.py` 校验新类型见证，并逐层比对原class_parents元数据；`infer_application_execution.handle` 按Class身份及原异常表选择首个处理器。`ExecutionKernelHooks.exceptionDispatch`、`CollectionServiceHooks.caught` 和 `Recorder.abort` 记录实际类/父链/加载器及原对象；协议见 OBSERVATION-PROTOCOL-20261112.md。没有新增构造/native效果许可。

新增12项dispatch单测（含追加的父链元数据校验），加上任务一4项finally单测及原93项，共109项通过、失败0、跳过0、缺依赖0。真实JVM `ExceptionDispatchFixture` 的7种形态×2输入：三模式各14/14义务正确，其中13 known字段答案和1 aborted无答案；正常/异常、业务多层继承、Base/Mid匹配、有序多个catch、finally、重抛、跨方法及未捕获均验证。完整origins/selectors/物理版本/状态按原始source调用独立预期评分。初版case6多报g的12/14结果原样保留在task2-custom-02；修复后新采task2-custom-final-02各14/14。原JDK控制新Agent各28/28。

同名不同loader：ExceptionLoaderProbe用两个真正定义加载器分别定义Leaf，Class身份不同，即使原字节码相同仍各返回exception-loader限制。30项新捕获扰动：24 evidence_invalid、6 analysis_limited，全部符合预期；含旧格式typed custom明确限制。证据及Agent类哈希见 artifacts/review-request-20261112/task2-receipt.json。Agent SHA256 `f08ca5e108b554a958f86919a62801a221d9da75bdcb86a12d42645e03c474fc`，exception_dispatch_version=1，目标运行JDK仍8u504，构建器沿用 build_distributed_plans.build，编译器8u512/Java8目标。

```sh
python3 -c "from build_distributed_plans import build;from pathlib import Path;build(Path('../../artifacts/review-request-20261112/task2-agent-new'),{})"
python3 run_exception_dispatch_controls.py --agent ../../artifacts/review-request-20261112/task2-agent/distributed-observer.jar --out ../../artifacts/review-request-20261112/task2-custom-new
python3 run_exception_completion_controls.py --supported-sequence --agent ../../artifacts/review-request-20261112/task2-agent/distributed-observer.jar --out ../../artifacts/review-request-20261112/task2-builtin-new
python3 check_exception_dispatch_controls.py --home ../../artifacts/review-request-20261112/task2-custom-final-02 --out /tmp/tf2-dispatch-guards-new
```

输出必须用新目录。记录的完整实际命令、配置、stdout、model、plan、truth-before-prediction、原始events和新评分均保留。上述旧捕获复算和新Agent控制分列；没有无关历史业务部署或性能计时。

## 三：描述符感知的基本类型字段观测

`PlannedServiceAgent.field`插桩按Z/B/C/S/I/J/F/D调用对应入口；Recorder的primitiveValue/fieldValue在id之前分流。ResponseBindingHooks、SpringTransportAgent、CollectionServiceHooks、ExecutionKernelHooks及FoundationValueHooks的反射字段路径采用同一编码。`field_value_protocol.py`在离线服务、来源绑定和执行内核入口校验新格式，保留旧捕获。真实包装对象沿用引用身份，新增源字段和已写引用字段的身份一致性核验。协议细节见 OBSERVATION-PROTOCOL-20261112.md。

最终Agent SHA256为 `c2dff00ee079b89df6dfa122fd1ddd82abccfb862ec0c2562856ecc805850545`；exception_dispatch_version=1、field_value_version=1。固定业务JDK8u504，构建javac8u512；各Agent类哈希、JDK二进制/rt.jar/libjvm哈希、源码哈希、编译目标和运行命令见 [收据](review-request-results-20261112.json) 及 artifacts/review-request-20261112/final-audit-delivery/receipt.json。实际构建为 `build_distributed_plans.build(Path('artifacts/review-request-20261112/task3-agent'), {})`，未修改公共构造/native契约。

最终127项单测通过（用户要求6文件及exception_completion/exception_dispatch/field_value_protocol）；失败0、跳过0、缺依赖0。字段协议新增18项，覆盖长整型、boolean类型、char范围、溢出、double bits/NaN/负零、primitive/真实包装引用/null及旧格式。30项字段扰动中27 evidence_invalid、3必要unknown；30项最终Agent异常分派扰动仍全部按预期处理。不是通过忽略缺来源使答案known。

最终新Agent真实JVM，full/static/selective分别与独立预期比较：

| 控制 | 每模式结果 | 工件 |
| --- | --- | --- |
| 原构造case8 | 2/2完整正确，输入1只有g selector，b保留数据角色 | final-original-case8 |
| 异常连续域内控制 | 28/28完整正确 | task3-builtin |
| 自定义异常 | 13 known字段答案 + 1正确aborted完成，共14/14义务 | task3-custom-verified |
| 基本类型/包装引用/null复制 | 各3/3（big/boxed/absent），总9/9 | task3-final |
| 原66项 | 60正确、6 unknown，原整体门槛仍false | final-original66 |

原6 unknown逐项核查：scenario14/16各输入0仍有完整候选origins/selectors和正确物理版本，但未执行备选构造效果未闭合；各输入1/2仍丢失数据来源、selectors候选和版本匹配，实际opaque构造使依赖unknown。六项均没有改成known。逐项来源、selectors、版本、known及完成状态见 [339行表](review-request-cases-20261112.csv)，表中保留原6项独立完整预期不满足的事实，不将候选selector集合相等视为认证。

同一份最终fixture源码/固定JDK/相同扫描命令，8种基本类型加真实Integer/Long/普通引用/null共12字段，预热一次后每阶段1,000次扫描、两阶段合计24,000次重复字段读取：

| 状态表 | 修复前预热/阶段1/阶段2 | 修复后预热/阶段1/阶段2 |
| --- | --- | --- |
| IDS | 13 / 6013 / 12013 | 5 / 5 / 5 |
| VERSIONS | 11 / 11 / 11 | 11 / 11 / 11 |
| ACTIVE | 0 / 0 / 0 | 0 / 0 / 0 |
| CHECKED_CLASSES | 4 / 4 / 4 | 4 / 4 / 4 |
| LIBRARY_HASHES / ARRAY_VERSIONS / ARRAY_SLOTS / INITIALIZED | 各0 / 0 / 0 | 各0 / 0 / 0 |

每1,000次观测的临时包装身份增量从6,000降为0；真实Integer/Long/普通引用各始终同一ID。修复前task3-before-final和修复后task3-final的源码哈希相同，命令、原始事件和计数保留。修复后full原66项结束IDS=383、VERSIONS=478；28项异常序列结束IDS=189、VERSIONS=117、ARRAY_VERSIONS/ARRAY_SLOTS各7。说明本项只消除了字段临时包装身份浪费，真正新业务对象和版本表仍保留；不宣称生命周期泄漏已修复或作堆内存估算。

最终旧捕获复算：18份公共控制答案/根审计保持，14份业务捕获相对16ddf1f的origins/selectors/known/版本/根审计均未变，原调用写控制22/22保持；72项旧扰动保持。旧捕获复算位于final-old-audit及final-old-business-02，与新采控制分列。

准确复现命令（以下在仓库根执行；所有--out使用新目录）：

```sh
PYTHONPATH=experiments/sockshop-mirrortaint python3 -m unittest test_control_dependencies test_call_write_effects test_application_call_status test_jvm_semantic_rules test_http_instance_sources test_response_binding test_exception_completion test_exception_dispatch test_field_value_protocol
python3 -c "import sys;sys.path.insert(0,'experiments/sockshop-mirrortaint');from build_distributed_plans import build;from pathlib import Path;build(Path('/tmp/tf2-agent-new'),{})"
python3 experiments/sockshop-mirrortaint/run_primitive_observation_controls.py --agent /tmp/tf2-agent-new/distributed-observer.jar --out /tmp/tf2-primitive-new
python3 experiments/sockshop-mirrortaint/run_exception_completion_controls.py --supported-sequence --agent /tmp/tf2-agent-new/distributed-observer.jar --out /tmp/tf2-builtin-new
python3 experiments/sockshop-mirrortaint/run_exception_dispatch_controls.py --agent /tmp/tf2-agent-new/distributed-observer.jar --out /tmp/tf2-custom-new
python3 experiments/sockshop-mirrortaint/run_constructor_scope_controls.py --case 8 --agent /tmp/tf2-agent-new/distributed-observer.jar --out /tmp/tf2-original-case8-new
python3 experiments/sockshop-mirrortaint/run_public_control_semantics.py --agent /tmp/tf2-agent-new/distributed-observer.jar --out /tmp/tf2-original66-new
python3 experiments/sockshop-mirrortaint/check_primitive_observation_controls.py --home artifacts/review-request-20261112/task3-final --out /tmp/tf2-primitive-guards-new
python3 experiments/sockshop-mirrortaint/audit_review_request.py --home artifacts/review-request-20261112 --out /tmp/tf2-review-audit-new
python3 experiments/sockshop-mirrortaint/audit_exception_completion.py --current-core --out /tmp/tf2-old-audit-new
python3 experiments/sockshop-mirrortaint/check_exception_completion_old_captures.py --out /tmp/tf2-old-business-new
```

依赖已就绪，本轮没有缺JDK/artifacts而跳过上述控制。未执行：无关历史业务容器重新部署、native构造闭合及性能基准。历史完整候选池的2项写地址限制和2项覆盖方法拒绝继续保留，未替换成正例。

开发失败也保留：task2-custom初版驱动KeyError；task2-custom-02包含returning-finally的12/14失败；task3-after为计划tuple/list未序列化驱动失败；task3-after-02把已有输入对象同时声明为调用来源导致正确的歧义unknown。后续字段复制控制改用独立的新鲜read-return源；没有放松来源唯一性，原失败目录未覆盖。字段扰动初版误选未解释来源调用体内部写入，最终改为预期核验的Out写入；初版结果保留在task3-guards。

剩余工作：构造/native效果闭合仍缺实际写范围与内部版本证明；跨应用加载器采用明确限制；条件写地址别名足迹和覆盖方法Frame分派仍待支持。下一轮建议以本次计数为基线，单独设计IDS/VERSIONS及数组/类缓存的生命周期与退役证据，保留跨请求真实引用和版本连续性；方法实参/返回值的描述符记录也可单独审阅。本项未把全局IDS替换为不受约束的弱映射。

三项工作在main分别提交；由用户手动push。
