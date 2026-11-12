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
