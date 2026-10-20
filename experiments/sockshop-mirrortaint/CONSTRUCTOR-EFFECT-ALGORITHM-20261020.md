# 构造器执行与顺序过滤依赖还原

冻结核心 `3f78922334dc867228599f4d1f4d0f6abde256a7` 将一类构造器主体纳入普通应用Frame，并把有限顺序filter的实际Predicate执行交给同一内核。目标是解释原版Cart真实来源链，不为FoundItem、Item或某个字段手写传播公式。结果与边界见[阶段报告](CONSTRUCTOR-EFFECT-REVISION-20261020.md)。

## 构造器复用普通Frame

构造器分析从原字节码决定执行策略。简单字段赋值仍有快速路径；同类构造器的有限委托可以展开成参数或常量表达式；无法归约的主体，在满足下面的初始化前提时进入普通Frame。

首版Frame要求原方法以 `ALOAD 0; Object.<init>()V` 开始。JVM成功完成这两条原指令后，Agent才把已经初始化的this传给监测器，并记录独立Frame、父Frame、调用位置、实参和实际对象。离线核验此前缀，程序计数器从主体开始；字段读取、写入、算术、分支、应用调用、公共契约及不透明屏障均复用普通方法逻辑。

```text
NEW对象 → 原JVM完成空Object初始化 → 构造器Frame
        → 按原字节码处理字段与子调用 → 正常退出或异常退出
        → 调用者的构造完成或构造异常证据
```

每次构造对应实际新对象、Frame和事件序号；指令位置不作为动态实例身份。调用者的构造完成对象、构造器Frame接收对象、实参、实际写入对象及版本必须一致。字段依赖按每次实际写入更新，写other不会自动删除text来源。

异常构造器保留自身abort，以及调用者同一Throwable的构造异常记录，再依据原异常表转入handler或继续抛出。异常钩子不访问构造失败的未初始化接收对象；未完成构造不生成成功对象证据。混合正常、异常和后续正常请求用于检查配对不会串请求。

这不是所有Java构造器的支持：带复杂super前缀、无法解释的this委托、递归构造和未建模库构造器仍受限制。成功完成空Object初始化是本Frame模型的前提。

## 委托快速路径由字节码生成

`plan_constructor_effects.py`用符号栈跟踪参数、常量、this和字段赋值；只展开有界、同类、无其他必要效果的构造器委托。比如单参构造器把参数和常量传给多参赋值构造器，可以生成字段表达式，而不需要逐类登记。

运行时仍核对实际对象、原参数以及每个应有字段的实际写入和版本。字段写入缺失、重复或与表达式不符即拒绝。返回值或字段数值相同不能替代写入证据。复杂主体走Frame，不能通过把调用当成无效果来套用这条快速路径。

## 有限日志工厂契约

Cart构造器调用 `LoggerFactory.getLogger(Class)` 初始化自己的LOG字段。该调用的接收信息是Class，不是客户、商品或订单实体。原版固定slf4j及默认logback环境使用一条独立公共契约：核对LoggerFactory、LoggerContext和Logger的实际类字节码哈希，以及返回logger的类型和名称关系。

版本清单见[公共库契约指纹](constructor-library-contracts-20261020.json)。它来自固定原业务JAR和无网络JDK探针，不包含业务字段或预期来源。版本不匹配不能继续给出确定依赖。本契约只覆盖声明的固定默认环境及这一个工厂API，不把保存、任意日志调用、自定义绑定器或其他外部调用统一声明为只读。

工厂契约不创建字段来源；它使已核验的库内初始化不再对业务对象施加未知全局效果。未满足契约的调用继续进入保守屏障。

## 顺序filter解释实际Predicate调用

支持形态限定为固定具体List创建的顺序stream、单个filter和findFirst，不支持一般pipeline、parallel stream、排序或任意集合实现。新ReferencePipeline过滤实现和String字节码指纹按Java运行版本固定。

filter阶段只登记stream实例、来源容器与阶段、实际Predicate实例；此时不执行Predicate，也不计算来源。原JDK执行findFirst时，Agent记录每次真正进入的应用方法Frame，并将其配到当前终结调用的call-id。离线按原列表顺序逐个核对：

1. Predicate必须来自已核验的lambda创建站点，实际实现与捕获参数一致。
2. 第i次回调的实参必须是来源列表实际第i个成员；同值另一个对象不能替代。
3. 回调方法体通过普通Frame执行，包括Item.equals中的实际分支和String.equals。
4. 首个true之后不允许额外回调；全false时必须覆盖全部成员；空列表没有成员回调。
5. 实际Optional状态和成员身份必须与该执行结果一致，原列表内容阶段必须保持一致。

如果必要Predicate体不透明，内核不能根据最终值推测选择；相关容器与捕获引用受到保守失效。任意未知调用仍按原接收者、实参、逃逸和全局别名规则处理。

所选成员携带自己的字段数据来源，Predicate使用的输入另存为选择证据。因此，两个商品quantity和unitPrice相同，也必须追到实际被选中的商品实例。额外真实输入专门请求列表第二个同值商品，避免仅凭数值或固定首项推断来源。

## 公共配置与实现入口

本轮所有查询继续统一使用 `execution_kernel: true` 与 `application_calls: true`。构造器策略、lambda实现和字段效果均由字节码及实际证据决定，没有为三个Cart目标单独选择传播规则。

- [构造器分类及委托表达式](plan_constructor_effects.py)、[应用调用计划](plan_application_calls.py)。
- [构造完成和异常、过滤公共证据](ExecutionKernelHooks.java)、[统一调用序列](CollectionServiceHooks.java)。
- [Frame与实际回调解释](infer_application_execution.py)、[构造器及过滤独立控制](run_constructor_effect_semantics.py)。
- [原版Cart独立实例真值验收](run_constructor_cart_acceptance.py)、[冻结工件审计](audit_constructor_effect_revision.py)。

本轮仍保守保留必要观测，没有切片收缩或性能结论。HttpEntity、一般框架包装、保存和异步协议没有由这组构造器或日志契约自动取得支持。
