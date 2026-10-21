# Spring任务与Future的实例配对

冻结版本 `cb693c1959f075ec38436c89822d78a514b0aa51`。这是统一执行内核的**异步事实协议阶段**，尚未实现异步工作方法的跨线程依赖传播，也没有把保存调用概括为来源保持。`async_evidence: true` 将固定契约写入计划的 `async_protocol`；默认关闭，旧profile继续使用原路由。

## 记录实际任务，而不是仅传递trace上下文

原版Orders使用Spring 4.3.6。`AsyncExecutionInterceptor`创建Callable，`AsyncExecutionAspectSupport.doSubmit`交给执行器，返回外层FutureTask。工作线程调用原应用方法，取得内层AsyncResult，再调用它的get解包；调用者的Future.get读取外层结果。

已有W3C上下文包装保留。在同一提交位置额外创建一个带进程内唯一task-id的Callable包装，记录实际原Callable、包装对象、调用者Frame和call-id、目标方法、接收者及实参。doSubmit正常返回时记录实际外层Future；提交失败则记录异常。包装只调用原Callable一次，不额外调用get、toString或业务方法。

工作线程用ThreadLocal标识当前task；已计划应用Frame记录该task-id。开始、正常完成和异常完成分别有事件。对固定拦截器中的`MethodInvocation.proceed`和内层`Future.get`，仅旁路观察原调用结果，不重复执行调用。原应用Frame返回的内层Future、拦截器解包结果和包装Callable的完成结果必须按实际对象身份闭合。

已观测调用者的Future.get/cancel，在原正常或异常完成事件中附上Future与task的对应事实。执行器可先运行工作任务，再从doSubmit返回；协议允许这种次序，不要求提交返回一定早于任务开始。重复get仍对应同一task，两个同值任务不能按值合并。

## 固定前提及离线核验

契约绑定四个原Spring类的SHA256，以及宿主JDK与原Orders镜像JDK的FutureTask、ExecutionException、CancellationException字节码哈希和运行时版本，见[固定契约](async-task-contracts-20261021.json)。原类加载时核对未修改字节码。只在实际使用AsyncResult时要求其类加载证据；没有执行该类的全失败路径不能凭空要求它已加载。

离线端核验：

- 唯一提交及其正常/异常完成、调用者Frame/call-id、外层Future身份及原调用返回值。
- 工作任务的开始与唯一完成、线程、实际应用方法Frame、接收对象、实参和完成区间。引用参数按身份核验，基本类型参数按实际标量核验。
- 原应用返回的内层AsyncResult、实际解包结果、工作Callable完成值和成功get结果的对象对应。
- 工作异常与ExecutionException的实际cause身份；超时、取消、线程中断分别保留，不把它们当正常值返回。
- 必要get记录缺失、重复生命周期、错误任务/对象/参数/库哈希时拒绝验证。完整但超出协议的外层Future类型、Callable或未计划工作方法记为分析能力限制。

原Orders工作方法中的RPC，还按已核验任务的实际工作线程和起止区间输出消息收据。这些收据没有产生来源边，也没有代替原HTTP/JSON字段、版本或解码证据。

## 为什么配对成功还不等于答案已知

本阶段明确设置`observation_only: true`。`validate_async_protocol`返回核验收据，不向Value、State或统一图注册新来源，收据中的`known_origins_created`为0。原必要不透明调用及其可能影响的状态仍受保守屏障约束。

下一阶段才能依据工作Frame的已解释计算、实际RPC解码字段及任务结果建立依赖传递，并核验任务涉及的共享对象、逃逸与副作用。HATEOAS默认忽略的wire id不能按字段同名连接；Mongo保存及回调也不能仅因返回同一对象就宣称所有字段不变。

当前协议限于固定Spring拦截器、声明Future返回、外层FutureTask及内层AsyncResult、可计划的应用工作方法和独立工作线程。任意Executor、inline executor、嵌套自定义Future、CompletableFuture、任意共享对象并发修改或其他框架不因本阶段获得支持。取消控制覆盖“任务尚未执行”的情形，不声称已验证运行中取消和所有竞争次序。

实现：[采集钩子](AsyncTaskHooks.java)、[框架插桩](SpringTransportAgent.java)、[离线配对](infer_async_protocol.py)、[真实Spring混合控制](run_async_task_semantics.py)、[原版Orders驱动](run_async_orders_revision.py)。
