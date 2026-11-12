# 共享异常完成与操作守卫修订

**原构造控制中多报b.value selector的问题已修复，新采三个配置各2/2完整正确。** 数据来源仍来自b.value，完成条件只保留g.value。域内连续控制各28/28正确；原6项构造unknown和2项不支持覆盖调用拒绝继续保留，native构造建模与正式计时暂停。完整新控制池还有2项既定写地址限制，不能把域内通过当作全池或完整Java语义通过。

实际起点main为 **`16ddf1f462a00481b35a9449b424bd95e3f1b116`**。规范提交`1b10783`，共享转移`2cff7b8`，JVM驱动`66933b8`，最终离线核心 **`9fbbc343658a476299340f20e361f0434a862e2b`**。最后补丁仅保护ATHROW参数可能为null时的类型分类；采集Agent、事件格式及计划未变，完整捕获以最终核心复算。原`2cff7b8`和最终冻结清单分别保存。

Agent未重新编译，SHA256仍为`367cbb2300e507e5db4716c4e2fcbed1a39898c5e6c6f5f23583c4c1487e2764`；Java钩子及30份公共契约／运行时JSON哈希保持。没有新增应用、native效果契约或性能数据，分阶段提交main，未push。

## 公共规则及代码

| 内容 | 实际处理 | 实现 |
| --- | --- | --- |
| 计算／写入数据 | 参数按原语参与origins／字段版本；不因调用失败自动变成selectors。consumed仍保存本指令实际操作数 | [control_dependencies.py](control_dependencies.py)，`ControlledStack`、`exception_guard` |
| 异常完成 | 已解释callee的活动条件及操作守卫，经abort导出；catch消费该完成状态和调用者守卫，不并入全部参数。空的已核验完成与没有完成证明分开 | `exceptional_completion/abort/caught`；[execution_dependency_state.py](execution_dependency_state.py)，`exception_control_ready` |
| 隐式守卫 | 字段空引用选receiver；数组空引用选array；越界选array/index；数组类型失败另需存储引用。写入载荷不决定字段NPE或数组越界 | `exception_guard`；[infer_application_execution.py](infer_application_execution.py)，原异常分派、数组事实核验 |
| 有限库操作 | 原Assert和List边界模型在现有事实核验后提交明确守卫；未解释非空调用没有完成证明时不能输出完整known选择 | 同上的既有异常分支及守卫接口；未新增框架许可 |
| 正常完成／finally | 按异常类别分别传递完成条件，依据原异常表及CFG汇合。类型依据真实静态定义和已有分派范围；null参数不能被静态声明成IAE后排除NPE | `normal_completions/normal_outcome/throw_types`；[exception_completion.py](exception_completion.py) |
| 控制上下文 | 区分仅由活动作用域临时附加的选择与已合流／存储的选择，避免重复当成新异常条件跨越finally。数据origins、已合流选择及unknown不被清除 | `guard_selection`、`apply/at`，每Frame临时映射及作用域token |

异常类型表来自原解释器的有限分派，移到共享模块，没有开放任意Throwable或native行为。Object[]存储的兼容性已由原数组事实核验：所有引用可放入Object[]，故正常／越界守卫不需要存储载荷；String[]等类型检查仍保留相应引用选择。

空接收者PUTFIELD现在接入既有NPE分派：原写失败时不制造写事件或新版本，载荷继续作为实际操作数核验。正常写仍走原版本／别名保护；同值覆盖不变。catch、abort、逐层传播共用异常完成规则，catch消费后清理；每指令重置操作守卫，每根请求使用新State。瞬时标记只保留本Frame活跃值，不跨捕获缓存认证。

当前内核和旧v1入口共用Control。旧v1仍没有新增catch执行路由；本轮的新异常JVM控制使用v8，旧v1真实成功入口的单测保持。除法守卫接口不等于新增除法opcode支持。范围限现有解释操作、有限异常分派及闭合调用，不宣称任意Java隐式流、最小selectors或新的根响应存在性分析。

## 原反例：保留数据，去掉无关选择

旧`ConstructorScopeFixture`程序、输入、Store来源、Out.value目标及独立预期不变。用原完整case8捕获逐项配对：input0原本正确；input1过去selectors为`{b.value,g.value}`，现在为`{g.value}`。两个输入的数据来源、owner／声明字段／版本和known均保持；选择变化符合原独立预期。[配对表](exception-completion-counterexample-20261112.csv)记录三个JVM各自的物理坐标。

候选稳定后用原case8再次新采full、固定许可／body-off、selective，各2/2完整正确。各JVM先用本次原始调用、字段、对象和版本独立评分，再比较规范化读取出现。没有跨JVM匹配对象号，没有按数值7配对来源，没有改动原错误答案或金标准。

## 组合控制与故障保护

新控制固定15种形态、每种0/1输入，共30个目标义务。实际覆盖普通方法／构造、数据参数与抛出条件、隐式String／字段空引用、数组读写越界、null数组、存储类型失败、嵌套调用／递归、finally后的常量和后续同线程请求。source-null与常量null、同值来源和新版本继续分开。

| 组别，每模式分别统计 | 结果 | 解释 |
| --- | --- | --- |
| 原构造case8新采 | **2/2完整正确** | 数据b，选择g，原异常身份及业务输出保持 |
| 新完整候选池 | **28正确／30，2 analysis_limited** | 原预期保留，不能称30/30 |
| 域内连续新采 | **28/28完整正确** | 同JVM／线程交替正常和异常请求，数据／版本／selectors／known一致 |
| 原66项旧捕获复算 | 60正确、6 unknown | 原预期及必要构造屏障保持 |
| 原构造补充分批旧捕获复算 | 14正确、4必要unknown、2拒绝 | 原多报选择的一项转正确；不回填原整批失败或称新业务成绩 |
| 独立单测 | **84项通过** | 新异常30项＋原54项，含原44项控制／调用写范围和旧v1入口 |

新池的2项位于同一case6捕获：汇合后的条件引用又作为写地址，仍触发既定`Cross-join selected write address`限制，整份两目标捕获不发答案。没有放松别名证明或把预期改成拒绝。该资格来自上一轮已记录的支持边界；原开发整批失败和逐形态结果全部保留。

域内连续序列是在已披露该边界后封存的额外采集，不能替换完整30项。它包含原28项中的域内形态及单列新增的类型守卫控制，验证finally合流和后续请求清理；不称预注册或未见测试。[逐目标表](exception-completion-targets-20261112.csv)保留完整30项分母，范围外项不静默删除。

[72项扰动](exception-completion-guards-20261112.csv)中：18项必要条件／null守卫／索引或数据来源缺失、歧义及版本缺口保持unknown；48项错误调用／PC／Frame／父调用、分支／abort／catch缺失重复矛盾、错异常对象、数组结果矛盾或sticky损坏拒绝；6项删去真正无关的来源后仍正确known。后者分别是未被callee使用的payload，以及数组越界时未参与判定的存储载荷，不能因删除字段就自动变空来源。

未知guard即使数值、taken或异常类型可见也不恢复known。必要b.value数据来源缺失仍unknown；修复只去掉它错误的selector角色，没有删除数据依赖或关闭必要核验。

## 旧结果与开发失败

最终候选以原完整捕获复算18份公共控制和14份选择／removeIf／RuoYi捕获。后者与`16ddf1f`在独立进程比较：data、版本、selectors、状态和根审计逐项保持。RuoYi部门列表的完整选择真值仍未充分独立评分；不凭旧显式来源正确扩大结论。调用写范围的既有22/22控制捕获也保持。

原6个native构造unknown、原2项不支持覆盖调用拒绝均核验保持，修改版Galette39/39的18份捕获／评分文件哈希不变。没有机械部署Mall、Account、ZLT或其他历史集；旧捕获复算与本轮新JVM控制分开记录。

初版控制暴露PUTFIELD空引用没有接入分派，修订后保留原失败；新case11曾把完成条件穿过finally，已在同捕获中修复。开发中一次把全部根完成不确定性附加到响应，导致结构引用路径退化，结果保存在`old-business-development-01/`。最终按既有查询边界传递值和调用完成条件，不改根目标定义，也不通过增加unknown换取正确性。

## 工件与复核

主目录`artifacts/exception-completion-semantics-20261112/`。`final-original-counterexample-01/`和`final-supported-sequence-01/`为新采；`development-by-case-01/`保留全30项；`old-business-final-02/`与`delivery-audit-final-02/`为最终离线复核。原失败158份文件及原程序哈希参与完整性检查。运行JDK为恢复的8u504，元数据提取器用宿主8u512，二者不混称；详见[运行时收据](exception-completion-runtime-20261112.json)。

```bash
python3 experiments/sockshop-mirrortaint/audit_exception_completion.py \
  --out /tmp/tf2-exception-completion-audit-new
python3 -m unittest discover -s experiments/sockshop-mirrortaint \
  -p test_exception_completion.py -v
python3 experiments/sockshop-mirrortaint/run_constructor_scope_controls.py \
  --case 8 --out /tmp/tf2-exception-original-case8-new
python3 experiments/sockshop-mirrortaint/run_exception_completion_controls.py \
  --supported-sequence --out /tmp/tf2-exception-sequence-new
```

输出使用新目录。第一条复算已有证据，第三／四条新采JVM控制，不是新Agent业务部署或性能实验。整体语义门槛继续false；本轮通过的是这项错误选择修复及已声明域内异常转移，不把仍有限制的全池标为通过。

[结果快照](exception-completion-results-20261112.json)和[旧控制表](exception-completion-old-controls-20261112.csv)随Git；完整数据、源码冻结与旧工件引用按[备份收据](exception-completion-backup-20261112.json)保存，是本机副本。代码和小型报告提交main，未push。
