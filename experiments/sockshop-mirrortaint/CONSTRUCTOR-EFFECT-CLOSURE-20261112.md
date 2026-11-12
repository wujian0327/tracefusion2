# 构造效果闭合：6项unknown诊断与停止结论

**本轮没有消除原6项unknown，也没有启用新的生产构造许可。** 原66项新采full、固定许可／body-off、selective仍各60项完整正确、6 unknown，门槛false。固定JDK链包含可覆盖虚调用与native；当前证据尚未闭合内部写版本、实际分派、初始化及native效果范围，按任务停止条件保留核心和旧屏障。没有以补充正例、预分配异常或改预期取得66/66。

实际起点main为 **`d3307ee5859b5d75313488cabb423d64aecf6481`**，离线核心参照 **`060a5ffd1efc12be0b0901520a9340f89f18b984`**。原核心源码、30份公共契约／运行时JSON和Java钩子哈希均未改，Agent仍为`367cbb2300e507e5db4716c4e2fcbed1a39898c5e6c6f5f23583c4c1487e2764`。分阶段提交`5bd2e1b`规范与审阅、`b415d71`控制和故障结果；这些是实验／审阅代码，**不是修复6项的算法候选**。无性能实验、无新增应用、未push。

## 6项分别发生了什么

下表为原full完整捕获的指令索引PC和事件seq，另两模式的独立物理坐标全部保存在[18行诊断表](constructor-scope-diagnosis-20261112.csv)。实际构造与潜在合流分开记录。

| scenario／输入 | 原构造实际执行 | 第一处不确定性 | 实际opaque失效 | 数据候选／selectors候选与独立预期 |
| --- | --- | --- | --- | --- |
| 14／0 | 否 | PC258，seq1841，未执行备选效果合流 | 无 | 均匹配，但效果范围未证明，known=false |
| 14／1 | 是 | PC258，seq1888，同上 | 构造完成seq1890 | 数据来源丢失；selectors候选匹配，known=false |
| 14／2 | 是 | PC258，seq1938，同上 | 构造完成seq1940 | 同上 |
| 16／0 | 否 | PC300，seq2140，未执行备选效果合流 | 无 | 均匹配，但效果范围未证明，known=false |
| 16／1 | 是 | PC300，seq2189，同上 | 构造完成seq2191 | 数据来源丢失；selectors候选匹配，known=false |
| 16／2 | 是 | PC300，seq2241，同上 | 构造完成seq2243 | 同上 |

第一步由公共`Control._field_effects`把未闭合调用登记到`control_barriers`；`field_selection`使屏障前已建立的旧字段状态不确定。这是**可能效果的合流**，不是声称未执行调用实际改写了对象。各根的潜在来源字段清单是本次三个Datum对象的`value/nullable`，版本均1，具体owner在JSON保留。

四次实际执行又由`infer_application_execution.poison`保守处理新this、参数及当前非局部／可达对象；被影响的旧来源字段包括上述三个Datum对象，共六个字段坐标，连同根接收者／Store及新异常的对象清单完整保留。捕获没有显示它们真的被JDK改写；这是当前未解释调用的失效政策。随后catch读取的旧字段无法恢复数据来源。

必要条件的实际读取及分支能配对，预测selectors集合仍等于原预期，但当前Value只有总体unknown，没有可分离的“选择部分已认证”状态。**集合相等不等于效果闭合或完整选择认证**，本轮没有拆字段包装known。输入0连数据候选也匹配，仍不能用同值或候选匹配证明旧对象未被影响。汇合后独立常量的旧控制继续known，屏障不是永久污染全Frame。

## 固定JDK审阅与缺少的证明

业务运行使用恢复的OpenJDK8u504；原rt.jar提取的Object、Throwable、Exception、RuntimeException、IllegalArgumentException五个class逐个保存哈希及javap。模型提取进程为宿主8u512，与业务运行分开记录。rt.jar、libjava.so、libjvm.so、Java二进制及独立VM flags收据见[JDK审阅结果](constructor-scope-jdk-review-20261112.json)。独立flags进程不是旧请求中的运行事实。

| 层次 | 确认的行为 | 仍不能授予许可的原因 |
| --- | --- | --- |
| IAE(String)→RuntimeException(String)→Exception(String)→Throwable(String) | 本次安装字节码逐层转发同一this／String | 旧计划把整个调用标为opaque，没有这些JDK方法的解释Frame或字段版本证据 |
| Throwable(String) | 写cause=this、stackTrace、suppressedExceptions、detailMessage；虚调用fillInStackTrace | 这些是实际新对象写入，不能用末态猜版本；虚调用可被子类覆盖 |
| fillInStackTrace() | synchronized Java实现，调用private native的int重载，涉及栈状态 | 旧runtime记录没有该链实现哈希／实际分派、初始化资格及对应效果见证 |
| native int重载 | JNI→JVM_FillInStackTrace→VM辅助函数，清理／安装接收者backtrace和stackTrace，分配回溯结构并读取VM配置 | 仅审阅直接写不足以认证完整native辅助调用、分配及异常路径；当前Ubuntu运行二进制的效果契约和运行条件未建立 |
| Throwable类初始化 | 原字节码含静态哨兵、集合与数组建立 | 缺少查询前初始化资格。源码中已有的预分配对照也不能补造旧捕获内的初始化证明 |

固定上游`jdk8u504-ga`的[Throwable.java](https://github.com/openjdk/jdk8u/blob/jdk8u504-ga/jdk/src/share/classes/java/lang/Throwable.java)、[JNI入口](https://github.com/openjdk/jdk8u/blob/jdk8u504-ga/jdk/src/share/native/java/lang/Throwable.c)、[JVM入口](https://github.com/openjdk/jdk8u/blob/jdk8u504-ga/hotspot/src/share/vm/prims/jvm.cpp)及[VM辅助实现](https://github.com/openjdk/jdk8u/blob/jdk8u504-ga/hotspot/src/share/vm/classfile/javaClasses.cpp)下载原文、URL及SHA在工件保存。它们用于审阅，**不等于已证明当前libjvm所有效果或建立了native契约**；没有只凭哈希启用规则。

独立JVM反例还验证：普通IAE构造不触碰测试旧对象；子类覆盖fillInStackTrace后，在父构造期间真实执行回调，把旧字段7改为9。该原版JVM安全控制不是来源评分，也没有把任意子类纳入局部构造模型。

停止点是缺少**一套可核验且经控制验证的新JDK/native效果契约与采集协议**：实际类／分派／配置及初始化条件、正常与异常完成、内部写地址／版本和引用边需要对应见证。现有边界只有构造开始／完成、args及结果身份，不能覆盖这些条件。若未来增加采集，须单独版本化Agent并新采；本轮未实施该改动，更未从旧日志补造。

## 公共摘要：已交付审阅器，生产接入仍未完成

[规范](CONSTRUCTOR-EFFECT-SCOPE-SPEC-20261112.md)定义写地址、引用存储／发布、回调、初始化及完成义务。[审阅器](constructor_effect_scope_audit.py)复用call_write_effects的形式参数路径与静态栈分析，分类fresh-this、参数可达、全局写及未知调用，保留外部引用登记义务。父子构造以同一this组合；未知虚调用、native、缺字节码和未解释初始化不能成为闭合空效果。

它输出`static_local_candidate`与尚缺证明，**始终不发runtime_license，也未被规划器／Agent／还原器消费为许可**。这是可执行审阅与接口规范，不能写成生产公共构造效果规则已实现。没有新增JDK/native公共契约，没有改变实际调用失效，也没有删去未执行备选合流。该摘要10项独立单测通过；原公共控制及调用写范围44项也重跑通过。24项原始写版本核对确认：实际同值旧参数写由版本1推进到2，未执行写保持原版本，详见[版本表](constructor-scope-write-versions-20261112.csv)。

## 新采原任务、补充控制及未通过项

原PublicControlFixture源码、原66项字面预期、输入、目标及来源声明保持。新采三个配置完整66项，每模式仍60正确／6 unknown；来源、版本、selectors和状态规范化一致。原程序内的异常构造没有换成预分配对象。[逐项原任务表](constructor-scope-original66-20261112.csv)保留198行。

补充10种构造形态×0/1输入，原本先完整采集20项目标；三配置都在不支持的覆盖回调处整体拒绝，**整批原失败保留**。随后同一预定10形态逐个新JVM采集，仅定位各形态，不替换原整批成绩、没有删除失败入口。参数旧对象、父子构造、静态发布、已解释回调、未执行分支、写后异常及后续正常请求均保留分母。

| 补充分批结果，每模式 | 数量 | 解释 |
| --- | ---: | --- |
| 完整正确 | 13 | 简单／父子初始化、修改旧参数的实际转移、受控旧参数写、局部构造不污染旧字段、已解释回调等 |
| necessary unknown | 4 | this／参数发布到全局的构造尚未解释，继续保守 |
| 拒绝 | 2 | 实际不支持的覆盖方法被当作计划基类Frame期待，报Planned application frame evidence absent；没有认证来源 |
| 错误确定的选择集合 | 1 | 构造写后抛原异常，数据和版本正确，却额外带入b.value selector；不能称完整正确 |

最后一项以原预期保留，没有删掉多报selector或改金标准。诊断确认`Control.caught`把本次构造调用已消费的全部实参加入选择，包括本不影响抛出条件的b.value；异常完成传入的选择原本只有g.value。补充控制仍未全部通过。预分配原异常只用于这组对照，绝不抵消原6项unknown。

[补充逐项表](constructor-scope-supplement-20261112.csv)分别保留60个目标义务。54项分配／构造ID／父Frame／默认字段／写入／引用／完成证据扰动全部被拒绝；它们验证既有构造协议，不构成新的native效果认证。[保护表](constructor-scope-guards-20261112.csv)单列。

## 旧结果、复核与备份

核心未变，仍以最终旧完整捕获重算原调用写范围验收：44项原单测、新JVM22/22的既有捕获、18份旧控制与14份受影响完整捕获的答案和根审计均保持。该复算不是新业务部署；修改版Galette39/39的18份捕获／评分文件哈希保持。没有重新部署无关历史应用，没有性能数据。

主目录`artifacts/constructor-effect-closure-20261112/`保存冻结协议、18项模式内诊断、固定JDK原class与源码审阅、新原66项、整批补充拒绝、全部逐形态捕获、错selector trace、扰动和早期驱动失败。网络／诊断驱动失败原目录保留，补充的分批诊断明确单列。

```bash
python3 experiments/sockshop-mirrortaint/audit_constructor_effect_scope.py \
  --out /tmp/tf2-constructor-scope-audit-new
python3 experiments/sockshop-mirrortaint/diagnose_constructor_effect_unknowns.py \
  --out /tmp/tf2-constructor-six-diagnosis-new
python3 experiments/sockshop-mirrortaint/review_fixed_constructor_jdk.py \
  --out /tmp/tf2-constructor-jdk-review-new
python3 experiments/sockshop-mirrortaint/run_public_control_semantics.py \
  --out /tmp/tf2-constructor-original66-new
```

输出必须使用新目录。前两条复核旧捕获／派生表，第三条重新提取固定JDK元数据，第四条新采原JVM控制；均不是性能实验。审计完成只表示忠实生成结果，**`original_full_acceptance_passed`和`supplement_full_acceptance_passed`均false，生产实现工作未完成**。结果见[快照](constructor-scope-results-20261112.json)，完整工件按[备份收据](constructor-scope-backup-20261112.json)保留，是本机副本。代码及小型报告提交main，未push。
