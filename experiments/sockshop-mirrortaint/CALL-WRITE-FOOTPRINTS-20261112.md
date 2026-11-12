# 公共调用写入范围：实际对象与嵌套路径

**嵌套写入漏选择依赖已修复；新JVM控制三配置各22/22完整正确。** 无法闭合的引用路径明确保守处理，没有因字段值相等而发证。原66项仍为60项完整可答、6项异常构造unknown，完整语义验收仍未通过，正式计时继续暂停。修改版Galette39/39及原性能负结果保持原归属。

起点为main `ff30c5d0da0fc5ea149fd1df0bb0bdf8f2a657ba`。反例／规范提交`f51560b`，公共路径转移`857f474`，JVM控制及驱动`568217e`，最终离线核心 **`060a5ff`**。Agent未重新编译，仍为`367cbb2300e507e5db4716c4e2fcbed1a39898c5e6c6f5f23583c4c1487e2764`；30份公共契约／运行时JSON、Java钩子及事件格式不变。代码在main分阶段提交，未push。

## 反例与实际修订

修改前先保存核心清单、协议及独立预期，真实静态栈分析复现：未执行`update(holder)`时，旧规则将`Child.value`登记在`holder`，实际`child.value`返回空selectors、known。原始输出保留在`before-module/`，没有把它说成旧业务答案已改变。

| 步骤 | 当前公共规则 | 实际代码 |
| --- | --- | --- |
| 静态写地址 | 从PUTFIELD接收者的真实定义追溯形式参数／this、局部别名和字段访问路径；不再把字段名与所有引用实参做笛卡尔积 | [call_write_effects.py](call_write_effects.py)，`Path`、`WriteEffects.summary` |
| 调用组合 | 按描述符实参次序、宽参数槽位、实例接收者映射；逐层替换形参，保留计划中的所有具体接口候选。缺候选定义不能静默忽略 | 同上，`bindings`、`candidates` |
| 实际对象 | 沿分支前已验证的写入／读取解析每条引用边，核对实际对象、版本、顺序、选择状态及不透明影响；不查后续快照补较早许可 | [control_dependencies.py](control_dependencies.py)，`_receivers/_reference`；[infer_application_execution.py](infer_application_execution.py)，`reference_lookup` |
| 闭合与提交 | 先解析所有候选，再登记物理字段。可能改写路径引用时（含不同形参实际同对象），不授予该受限证明；失败不留下部分字段集合 | `Control._field_effects` |
| 共享执行 | v8及旧v1仍共用Control；引用见证只保存当前根内已执行的事实，不跨请求缓存认证、来源或known | [execution_dependency_state.py](execution_dependency_state.py)、[infer_execution_kernel.py](infer_execution_kernel.py) |

对闭合的未执行写，实际子对象字段获得条件selectors及必要unknown。真正执行的写继续走原版本／值核验；同值覆盖照样推进版本。汇合后无条件替换引用或写入新值不被历史分支永久污染。没有给新列表、包装或其成员授予私有性。

本规则只为受支持应用字节码建立字段写地址范围。不在解释方法表内的调用仍由原有限库契约负责，不将空字段摘要当作一般无副作用证明；计划标记的opaque仍保守屏障。静态全局／数组写、动态引导和无方法体效果不被当成闭合空效果。未闭合返回别名、递归写范围、未知／null引用边，以及可能重写路径引用的调用保留`control-write-address`能力限制。本轮没有新增框架、异常构造只读摘要或一般并发／反射证明。

## 新JVM验收与证据保护

控制使用原Agent和恢复的OpenJDK8u504；无Agent原版与三配置逐请求业务输出一致。元数据提取进程仍使用宿主8u512，与业务运行JDK分开记录。程序及预期先封存在协议中，数据真值由各JVM自己的Store调用、对象、字段和版本建立，预测不生成真值；三个配置只在独立评分后比较逻辑读取出现。

| 项目，每模式分别统计 | 结果 | 边界 |
| --- | --- | --- |
| 11种形态×0/1输入 | **22/22完整正确** | 直接写、嵌套写、局部别名、实参换位、同对象实参、二级转发、两种接口实现，以及无关参数／汇合后引用替换／独立新值 |
| 原main复算同一份新捕获 | 各7项目标漏selectors且known | 为嵌套路径的未执行分支；新核心全部修复，数据来源未按相同值合并 |
| 引用边可能被调用改写 | 各2项目标义务，整份捕获analysis_limited | 两次业务均保持；没有输出认证答案。不称为两项独立完成的来源评分 |
| 条件来源缺失／歧义／版本缺口 | 三配置合计9项unknown | 不能从具体taken恢复known |
| 错call／caller／PC、分支缺失重复矛盾、错Frame／父调用、引用对象／版本／写证据损坏及sticky | 三配置合计39项evidence_invalid | 原始捕获不改，派生副本受扰动 |
| 公共规则单测 | **44项通过** | 新路径28项＋原控制16项，包含用户未复跑的旧v1真实入口测试；未来引用证据、同版本矛盾、路径改写别名、缺候选、原子失败、递归边界等 |

完整目标表比较实际owner／声明字段／版本、origins、selectors和known；full、固定许可／body-off、selective逐项规范化一致。没有新增观测省略或速度结论。

## 旧执行保持及剩余停止线

最终核心复算18份上一轮完整控制捕获：原比较谓词、直接布尔返回、66项组合、预分配异常、隐式正常完成和接口调用。全部答案及根审计与上一轮封存结果相同；原66项每模式仍60 known／6 unknown，没有修改独立预期。

另外对14份完整旧选择／removeIf／RuoYi捕获，以ff30c5d与最终核心分别独立进程复算：数据来源、版本、selectors、状态和根审计均保持。部门详情各5、部门列表各39/43及字典各12个旧known保持；部门列表的完整选择真值仍尚未充分独立评分。它们是旧在线执行的新离线复算，不是新业务部署或新版全量能力成绩。

原6项异常构造unknown体现的保守边界不变。该范围修复验收通过，只说明本批闭合写路径不再漏依赖；`revision_full_acceptance_passed:false`继续保留。没有机械重跑Mall、Account、ZLT或其他历史部署，没有正式计时。

## 工件与复核

主目录`artifacts/call-write-footprints-20261112/`。`final-jvm-01/`为新JVM控制，`final-unclosed-jvm-01/`为未闭合范围控制，`old-captures-final-02/`及`delivery-audit-02/`为最终核心复算。引用边保护的最后补丁仅改离线规则，Agent、计划及原捕获不变；`candidate-857f474.json`和最终`candidate-060a5ff.json`分别保留，不写成同一源码哈希。

初版错误地把原库契约拥有的调用全部登记为新opaque，导致旧部门任务回退；该开发结果保留在`old-captures-development-01/`。修订恢复原合同归属，没有为业务添加只读特例。故障驱动首次假设write事件有message，按原格式改为Frame和区间匹配，失败目录及说明保留。

[逐目标表](call-write-targets-20261112.csv)、[保护表](call-write-guards-20261112.csv)、[旧控制表](call-write-old-controls-20261112.csv)、[结果快照](call-write-results-20261112.json)、[运行时收据](call-write-runtime-20261112.json)随Git。18份修改版Galette原捕获／评分文件哈希逐项保持。完整工件和冻结源码按[备份收据](call-write-backup-20261112.json)保存，是本机副本。

```bash
python3 experiments/sockshop-mirrortaint/audit_call_write_footprints.py \
  --out /tmp/tf2-call-write-audit-new
python3 -m unittest discover -s experiments/sockshop-mirrortaint \
  -p test_call_write_effects.py -v
python3 experiments/sockshop-mirrortaint/run_call_write_footprints.py \
  --out /tmp/tf2-call-write-jvm-new
python3 experiments/sockshop-mirrortaint/run_call_write_footprints.py \
  --limited --out /tmp/tf2-call-write-unclosed-new
```

输出使用新目录。第一条为已有完整捕获审计，第二条为隔离单测，第三／四条新采JVM控制；均不冒充业务能力或性能测量。计划、Agent、来源边界及旧失败均保持，未push。
