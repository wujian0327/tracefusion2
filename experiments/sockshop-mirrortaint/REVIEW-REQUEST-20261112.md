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

`exception_dispatch.py` 校验新类型见证；`infer_application_execution.handle` 按Class身份及原异常表选择首个处理器。`ExecutionKernelHooks.exceptionDispatch`、`CollectionServiceHooks.caught` 和 `Recorder.abort` 记录实际类/父链/加载器及原对象；协议见 OBSERVATION-PROTOCOL-20261112.md。没有新增构造/native效果许可。

新增10项dispatch单测，加上任务一4项finally单测及原93项，共107项通过、失败0、跳过0、缺依赖0。真实JVM `ExceptionDispatchFixture` 的7种形态×2输入：三模式各14/14义务正确，其中13 known字段答案和1 aborted无答案；正常/异常、业务多层继承、Base/Mid匹配、有序多个catch、finally、重抛、跨方法及未捕获均验证。完整origins/selectors/物理版本/状态按原始source调用独立预期评分。初版case6多报g的12/14结果原样保留在task2-custom-02；修复后新采task2-custom-final-02各14/14。原JDK控制新Agent各28/28。

同名不同loader：ExceptionLoaderProbe用两个真正定义加载器分别定义Leaf，Class身份不同，即使原字节码相同仍各返回exception-loader限制。30项新捕获扰动：24 evidence_invalid、6 analysis_limited，全部符合预期；含旧格式typed custom明确限制。证据及Agent类哈希见 artifacts/review-request-20261112/task2-receipt.json。Agent SHA256 `f08ca5e108b554a958f86919a62801a221d9da75bdcb86a12d42645e03c474fc`，exception_dispatch_version=1，目标运行JDK仍8u504，构建器沿用 build_distributed_plans.build，编译器8u512/Java8目标。

```sh
python3 -c "from build_distributed_plans import build;from pathlib import Path;build(Path('../../artifacts/review-request-20261112/task2-agent-new'),{})"
python3 run_exception_dispatch_controls.py --agent ../../artifacts/review-request-20261112/task2-agent/distributed-observer.jar --out ../../artifacts/review-request-20261112/task2-custom-new
python3 run_exception_completion_controls.py --supported-sequence --agent ../../artifacts/review-request-20261112/task2-agent/distributed-observer.jar --out ../../artifacts/review-request-20261112/task2-builtin-new
python3 check_exception_dispatch_controls.py --home ../../artifacts/review-request-20261112/task2-custom-final-02 --out /tmp/tf2-dispatch-guards-new
```

输出必须用新目录。记录的完整实际命令、配置、stdout、model、plan、truth-before-prediction、原始events和新评分均保留。上述旧捕获复算和新Agent控制分列；没有无关历史业务部署或性能计时。
