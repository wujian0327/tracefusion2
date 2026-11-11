# Galette兼容性、共同来源校准与非空选择依赖

**固定官方Galette与8u504的验证错误已定位；单列的修改版Galette在六个固定任务上39/39显式来源正确。TF非空选择控制同时发现真实缺口，正式计时门槛未通过，成本为N/A。** 本轮没有修改TF核心、Agent、计划生成或公共框架契约，没有性能测量、任务替换或push。

开始main为`f01418c7d229de46a7ecacdef659509c39f47765`。140项核心源码及其中30份契约／运行时JSON哈希保持；TF Agent仍为`367cbb2300e507e5db4716c4e2fcbed1a39898c5e6c6f5f23583c4c1487e2764`。`c8918bf`的成本、负面增长结果及`c866d67`的后续离线修复保留原归属。原协议、旧报告、启动失败、适配器失败和两份ZLT损坏捕获均未覆盖。

## 验证错误的证据与原因

官方固定提交仍为[`bc6002cc5ee4d6eaa30518b2d176a9831d77cb1a`](https://github.com/neu-se/galette/tree/bc6002cc5ee4d6eaa30518b2d176a9831d77cb1a)。核对了该版本README、Maven插件、instrument、bootclasspath、javaagent、实际类加载位置及文件哈希。原始8u504成功，官方插桩Java失败；官方Maven插件另外生成的JRE也复现同一VerifyError，其模板字节与原instrument产物相同，JVM二进制与基础8u504相同。因此不是旧产物／路径混用，而是该固定工具与该JDK资源模板的兼容性问题，不推广为Galette普遍不可用。

| 检查 | 原始证据 | 结论 |
| --- | --- | --- |
| 最小caller-sensitive对照 | `template-evidence-02/original`退出0，`galette`退出1；完整命令、verbose加载记录和堆栈保留 | 原版成功／固定官方工具失败 |
| 普通／hosted变换 | 同一原始模板分别生成ordinary、hosted、ordinary-then-hosted及javap | 失败由变换上下文造成 |
| Maven官方准备路径 | `maven-plugin-counterexample-02/result-final.json`，模板SHA相同，仍失败 | 排除独立instrument命令特有问题 |
| 本地修改后 | `modified-probes-01`的caller-sensitive及原标签API均退出0 | 只证明该修复及小控制 |

原始`MethodHandleImpl$BindCaller$T`不声明`finalize`。AOT的`GaletteInstrumentation.apply`按普通类调用`transform(bytes,false)`；`ShadowMethodCreator.findMissingObjectShadows/createObjectShadow`补出`finalize(TagFrame)V`，`NativeWrapperCreator.computeWrappedCallOpcode`生成指向命名模板的`INVOKESPECIAL finalize()V`。但该资源随后由`Unsafe.defineAnonymousClass`在另一host中定义，接收者验证不再满足这个命名类约束。运行时虽请求hosted变换，已有插桩标记使其返回null，未修正先前字节。hosted变换则生成`INVOKEVIRTUAL java/lang/Object.finalize()V`，最小反例成功。三份变换及原始／插桩后字节码完整保存，未通过关闭验证得出结论。

检查公开main、artifact及knarr-integration分支、公开issues/PR与releases：当次查询的main仍是原固定提交；未找到对应的hosted模板修复。knarr分支相关变换实现无对应差异；公开PR5为D2F/D2L常量修复，非此问题。保存的远端refs及API响应限定了检索范围，不能据此断言其他分支或未来版本没有修复。

## 修改版与官方测试

[实际构建补丁](galette-hosted-template-built-20261111.patch)只修改instrument组件的`GaletteInstrumentation.apply`：对**精确模板名及原始SHA256**使用工具已有hosted变换，其他类保持原逻辑；未知模板哈希直接拒绝。没有修改原生传播Agent，没有新增排除类，没有使用`-noverify`／`-Xverify:none`。原[补丁草稿](galette-hosted-template-local-20261111.patch)保留；官方Maven格式化器只调整了导入顺序和换行，实际构建补丁与构建源码的Git差异逐字相同。首次交付准备以草稿字节直接比较而失败，记录与该次归档保留，未改动已测二进制。

首次对整个JDK处理时，守卫拒绝了`ct.sym`中同名但不同字节的编译器签名stub，失败保留，未放松哈希。随后采用官方Maven插件相同的**JRE目录范围**完成插桩。相对官方插桩rt.jar的19896个class，只有该模板一个class不同；Java和libjvm仍是原8u504二进制。不能宣称各工具的Java类库字节相同。

运行时始终使用原官方传播Agent，SHA256为`cbb34a9e713b3ca506a3c0cb64add2a9b1ad3aba217e59ab99bd84c5f789d27e`。本地重编译Agent的全部class内容与其一致，但不同打包文件仍分别记录，未用不同JAR冒充同一文件。修改版rt.jar为`8f0db634bf0607f2c582f7502dcc71e81ad8f3440297810037876f6c74ca5e12`。构建沿用Maven3.8.6／Temurin17环境；测试和业务运行分别核对为基础8u504及其修改版插桩JRE。完整版本和补丁哈希见[收据](galette-compatibility-tool-receipt-20261111.json)。

| 官方测试范围，8u504 | 总数 | 通过 | 失败／错误 | 跳过 |
| --- | ---: | ---: | ---: | ---: |
| 原版MethodHandle／MethodReflection／ClassReflection | 260 | 260 | 0／0 | 0 |
| 原版完整integration-tests模块 | 1381 | 1228 | 0／0 | 153 |
| 修改版完整同模块、原传播Agent | 1381 | 1228 | 0／0 | 153 |

153项中150项因JRE版本不适用、3项标为Unimplemented。260项是完整套件的子集，不相加计数；套件未覆盖该最小caller-sensitive反例。新增复跑驱动另在独立目录重新得到260/260。此前skipTests构建仍不算测试通过，也未声称所有JDK／所有模块均验收。首份相关测试因临时目录缺失在执行测试前失败，单列保留。

## 共同业务来源校准

先通过最小反例，再按high→Mall→其余固定任务接入。业务源码和原JAR、输入、目标及来源边界不变。新增[适配器](GaletteBoundaryAgent.java)只插入声明调用开始／完成、实际应用Frame与成功写事实、来源标记和目标标签导出。[Hooks](GaletteBoundaryHooks.java)按本JVM实际调用ID、owner、声明字段、可见版本生成标签，调用原生`Tainter.setTag/getTag`；不含TF传播、业务依赖公式或预期来源集合。评分先保存原始物理事实真值，再比较原生标签；related-high的257个读取出现不按值去重。

| 固定任务 | 原版目标义务 | 修改版Galette正确 | 错误显式来源 | 来源调用配对 | 业务保持 |
| --- | ---: | ---: | ---: | ---: | --- |
| 8非目标字段 | 6 | 6 | 0 | 6 | 6/6 |
| 64非目标字段 | 6 | 6 | 0 | 6 | 6/6 |
| 256非目标字段 | 6 | 6 | 0 | 6 | 6/6 |
| related-high | 6 | 6，每目标257来源 | 0 | 6 | 6/6 |
| Mall expiresIn | 6 | 6 | 0 | 6 | 6/6；新增6条登录日志 |
| ZLT User原六输入 | 9 | 9 | 0 | 6 | 6/6 |

已评分39项均完成目标物理绑定和充分的实际来源事实配对，unknown／无效／未评分各0。主表仅比较显式数据来源，不要求Galette或MT提供隐式流。完整响应按原业务规则核对；Mall生成token及TTL按既定规则检查，不以跨部署字符串相同为要求。

五个任务使用适配器`boundary-build-06`；ZLT使用单列的`boundary-build-08`，**不写成同一个适配器二进制的全量成绩**。ZLT前两次业务均保持，但来源导出遇到`/0/entityClass`的`java.lang.Class`。v08仅增加有限Class引用元数据：保留对象身份、实际类型和`getName`，不遍历内部状态、不初始化业务类型、不调用未知toString。Class控制验证同一个Class对象在两个引用槽位上的标签不合并、常量覆盖清除标签、类名观测不初始化业务类型。它是新工具导出接入，不是TF框架契约或新传播语义。v07还修正了诊断detail被请求message字段覆盖的问题；旧捕获缺失的错误文字没有补写。

原官方Galette的启动阻断及其39项未评分义务保留；本表属于明确标记的**修改版Galette**。固定MT与三种TF的旧短校准各39/39作为兼容参考列入[共同校准CSV](galette-common-calibration-20261111.csv)，未伪称本轮重采。其逐任务适配器仍按旧协议锁定。旧耗时未与新Galette配对，不产生外部成本排名。原User空页业务500及旧分母处理也不改写。

当前适配器是这些同步任务的有限观测接入：版本反映观测到的应用成功PUTFIELD，未见写的字段以边界初始版本记录；不宣称覆盖任意反射／native写或共享并发。来源与目标的原始对象／字段事实、边界及这些限制均保留。独立原始调用审计另有7类缺失、重复、歧义、错caller、错结果对象及损坏保护，均拒绝；这不是Galette完整传播正确性的证明。

## 非空选择依赖：正例与真实反例分别保留

两种控制都使用两个实际Store.read返回的同值、不同owner成员，另一次Gate.read提供选择条件。无Agent业务与新采full、fixed-permission/body-off、selective均一致，各JVM先独立评分，再按逻辑读取出现规范化，不跨JVM比较对象号。

| 控制，每模式分别统计 | 数据／版本 | 非空selectors | 未解释谓词 | 缺选择来源字段 |
| --- | --- | --- | --- | --- |
| 首先封存的`b.id != choice.index` | 2/2正确 | **0/2，错误地返回known** | 两目标unknown，符合预期 | **仍known，保护失败** |
| 之后新增的直接返回`decisions.next().drop` | 2/2正确 | **2/2正确**，每目标含两个实际Flag读取 | 两目标unknown，符合预期 | unknown，符合预期 |

第一行的独立预期为两个实际id读取和一次index读取组成选择依赖。实际分支被核验但操作数依赖没有进入随后返回的布尔常量：`infer_application_execution.py:1287`的条件跳转分支丢弃操作数；`infer_remove_if`只能接收到空依赖的谓词结果。因此显式数据来源虽对，**完整选择答案不正确**，不是unknown。缺少条件字段仍known的派生反例同样保留。这需要后续核心选择依赖转移修订，本轮按要求不修改TF。

第二行在发现第一行失败后另封存协议，使用已有Iterator／字段读取／removeIf，谓词直接返回来源布尔字段。它验证已有成员筛选能转移非空selectors：输出数据仅属于选中成员，两个实际执行的谓词字段都进入选择依赖。它是补充正例，**没有替换第一行、修改原预期或抵消其失败**。两行各模式的缺谓词Frame、重复Frame和错谓词对象均拒绝。三种TF的规范化答案分别一致，只能说明同一行为；第一行一致地错误仍然失败。该控制不是新业务覆盖，也不验证body收缩。

static在本报告明确称**固定许可／body-off**：共同固定许可下关闭动态body收缩，仍计算资格并保留认证检查。它不是独立静态污点分析器，不称复现或优于SelectiveTaint；旧标签和捕获不改。

## 正式门槛与可写结论

Galette共同显式数据任务已通过，但新增TF选择正确性及缺证保护未通过。未以补充正例代替反例放行，也没有重新封存正式计量环境。**正式部署0次，high／Mall CPU、p95、离线成本均N/A，不是0开销。** 准备、短校准及官方测试可能存在并行，不用这些进程的偶然耗时生成速度表。没有重新运行原60份矩阵。

可以写：固定官方工具的一个JDK兼容问题可被最小反例、上下文变换和独立补丁定位；修改版原生传播在本批共同显式来源任务上得到39/39，不能归入官方原版成绩。TF已有直接布尔筛选能保留非空选择依赖，但条件分支形成布尔结果的路径仍有核心缺口，不能写成任意选择语义完整。TF／Galette的共同任务成本取舍仍缺正式配对数据，先前负面增长结论不变。

## 工件、提交与复核

主目录`artifacts/galette-compatibility-selection-20261111/`。协议为`protocol-before-revisions.json`；其封存晚于初步源码检查及首个官方测试启动，早于补丁和选择控制执行，不称完全预注册。模板证据为`template-evidence-02`，官方／修改版套件为`official-tests-related-02`、`official-tests-full`、`modified-tests-full`。正式使用的短捕获为`final-{low,medium}-01`、`final-high-02`、`final-related-high-01`、`final-mall-01`、`final-zlt-user-03`；所有此前失败目录保留。逐目标复核为`delivery-audit-03`，最终源码／补丁完整性复核为`final-integrity-02`。

分阶段代码提交：`416a5f1`原始取证及选择反例，`bc7a601`独立工具补丁，`839f0fb`Galette边界适配，`4178232`补充直接谓词控制，`78e86c3`有限Class导出及官方测试复跑。核心冻结未变。小型[逐目标物理来源表](galette-compatibility-targets-20261111.csv)、[控制表](galette-selection-controls-20261111.csv)、[结果JSON](galette-compatibility-results-20261111.json)、版本收据和本报告随Git；完整原始事实、标签、命令及字节码另备份。

```bash
python3 experiments/sockshop-mirrortaint/audit_galette_compatibility_selection.py --out /tmp/tf2-galette-compatibility-audit-new
python3 experiments/sockshop-mirrortaint/diagnose_galette_hosted_template.py --out /tmp/tf2-galette-template-new
python3 experiments/sockshop-mirrortaint/run_nonempty_selection_control.py --out /tmp/tf2-selection-branch-new
python3 experiments/sockshop-mirrortaint/run_nonempty_selection_control.py --direct-predicate --out /tmp/tf2-selection-direct-new
python3 experiments/sockshop-mirrortaint/run_galette_official_test_check.py --variant official --suite related --out /tmp/tf2-galette-related-new
python3 experiments/sockshop-mirrortaint/run_galette_official_test_check.py --variant modified --suite full --out /tmp/tf2-galette-modified-suite-new
```

第一条只审计已有证据；第二条新运行最小对照，第三／四条新采JVM控制，第五／六条在新源码及缓存副本上执行官方测试。分支控制驱动保存失败门槛，不通过删除失败让进程返回码充当验收结论，应检查`results.json`的`correctness_gate_passed`。

新采共同任务使用`run_galette_boundary_calibration.py --tier high|mall|low|medium|related-high|zlt-user --adapter <已封存JAR> --out <新目录>`；重编译适配器使用`--build <新目录>`。主表五任务对应06，ZLT对应08；默认08并不把未来运行自动记成现有成绩。修改版instrument的实际命令及原始日志在`modified-jre-instrument-02.log`：原8u504的Java运行修改版instrument JAR，输入原JDK的`jre`目录、输出独立JRE。补丁、构建日志、两份Maven缓存和实际工具均归档，不要求重新下载会变化的SNAPSHOT代替封存产物。

所有输出必须是新目录；复核不冒充正式计时。[备份收据](galette-compatibility-backup-20261111.json)列本轮完整归档和复用的原工具／镜像／JDK归档及校验结果，为本机副本。代码和小型报告提交main，不push。
