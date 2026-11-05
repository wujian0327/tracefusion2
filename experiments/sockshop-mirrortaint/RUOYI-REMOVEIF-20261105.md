# RuoYi：removeIf 解释与字典集合诊断

**筛选控制通过，但部门列表尚无新增认证答案：full/selective 各43项由语义还原拒绝变为证据有效的unknown。** 首次来源失效发生在筛选之前的服务代理调用。字典拒绝集合的实际运行类已确认是`com.alibaba.fastjson2.JSONArray`，本轮没有放开该类型。没有性能实验、其他应用扩展或push。

这是已暴露入口的开发修订，参照为上一轮最终代码`e8311fd`及报告提交`8cc1bef`。原首次、上轮拒绝和本轮失败目录均保留。

## 有限筛选语义

[观测器](RemoveIfHooks.java)只接受精确`java.util.ArrayList`，并核验既有OpenJDK8u504的ArrayList、BitSet、Objects字节码；未登记新运行时。它记录原调用的接收者、谓词、成员顺序、内容阶段和modCount，不额外调用谓词，也不迭代未知集合子类。

[离线解释](infer_remove_if.py)将原调用内的实际lambda Frame与SAM、捕获参数、调用位置和call-id连接，按原成员顺序解释谓词。保留成员沿用各自字段来源，成员选择另外携带谓词依赖及unknown；布尔返回值也继承谓词依赖，不能被当作常量。未知回调或无法证明的影响仍保守失效，不为业务谓词添加字段规则。

经原JDK字节码审阅，Java8 ArrayList先执行全部谓词、记录删除位，再统一压缩。谓词中途抛异常时，尚未提交的删除不发生，已经执行的字段写入继续存在；回调结构修改导致ConcurrentModificationException，回调添加的成员仍保留。正常完成核验删除结果、顺序、modCount和内容阶段；异常完成核验原异常对象及实际修改。

独立JVM[控制](run_remove_if_controls.py)两模式各10个字段目标：7个正来源、1个已知空来源正确，2个必要不透明回调unknown。两个成员的文本相同，但分别来自两次Store.read；筛选后按实际读取身份评分。同值常量覆盖后，第一个成员是新版本空来源，不能继续连接旧读取。另覆盖全删、无删除、空结果、空谓词、原异常及回调追加。六类缺失/重复/错配证据扰动各模式均拒绝。

不支持的ArrayList子类单独验收：业务结果及迭代次数与无Agent相同，捕获保留problem及粘性无效标记。最终Agent可靠性控制两模式各27个业务场景、5项父状态检查保持；没有重新重复全部历史业务部署。

## 原C1输入的新部署

三查询各六个原输入，两模式分别独立部署，共六份新捕获。原版参考复用既有无Agent记录；响应按原规则比较初始化时钟，各部署自己的返回时间另与其DB核对。下表每模式分别统计，不合并旧岗位列表或C2成绩。

| 查询 | 业务保持 full / selective | 目标绑定，各模式 | 新状态，各模式 |
| --- | --- | ---: | --- |
| 部门详情，保持检查 | 6/6 / 6/6 | 5/5 | 5正来源正确 |
| 排除子部门列表 | 6/6 / 6/6 | 43/43 | 43 unknown，0无效，0错误确定答案 |
| 字典类型列表，类型诊断 | 6/6 / 6/6 | 12/12 | 12 evidence_invalid，0认证答案 |

部门列表每模式六次筛选，原列表均10项，实际保留4、7、9、9、10、4项。每次十个实际谓词Frame均进入本轮筛选解释；成员/完成证据闭合，但依赖仍unknown，不能把实际筛选结果当作已认证来源。

两模式共86个列表目标分别以本JVM的独立mapper来源坐标连接诊断，全部首次失效于`SysDeptController.excludeChild`的PC5（模型指令索引）：

```text
ISysDeptService.selectDeptList(SysDept) -> List
```

实际CGLIB链包含ExposeInvocationInterceptor及动态匹配拦截器，不满足已有有限转发规则。mapper已经读到来源，但外层未解释代理完成使这些字段失效；这发生在removeIf之前。不能靠筛选恢复旧依赖，也没有把DataScope链、StringUtils.split或ArrayUtils.contains等后续义务统一声明只读。**本轮没有缩小这43项与历史MT正确答案的差距。** MT未重新部署，原配置和结果保持。

## 字典：把集合类型与来源缺证分开

正式请求在`ValueOperations.get`及外层`RedisService.getCacheObject`的`binding-after`快照拒绝处记录到`com.alibaba.fastjson2.JSONArray`。每模式五次缓存非空返回、十条内外层诊断，带实际对象、Class对象、加载器、Frame、消息、call-id及根路径。诊断的`source_capture:false`明确表示这些记录来自调用后快照；它们不是已经完成的声明来源快照，更不能用mapper首次ArrayList代替缓存返回对象。

新增诊断只读对象运行类和监测身份，不调用未知getter、toString、集合get或iterator，不建立来源边。原problem、失败sidecar和footer保持，整批继续拒绝。JSONArray的实现、转换配置及安全观测模型留待后续核验，本轮不因得知类名就放行。

## 版本、复用与交付

- 在线源码冻结：`e03a376b3535982f3fc357cd8eb8290d47fdab8a`；Agent SHA256为`3114d08b7ffe051314018d6d71fedebacc680c390b0f616f221231265d7207d4`。
- 最终离线语义：`0bdee20f107ff443ccc8735a2340d1f1370c1b71`。采集后只补removeIf布尔返回依赖；122项清单中仅该Python文件变化，Agent和计划不变。补充前后离线转移在六份完整捕获上全图节点、边、来源、选择证据或拒绝结果相同；没有冒充额外新部署。
- 最终控制和业务Agent的896个class哈希相同；不把打包时间不同的JAR写成同一文件。原六份计划/捕获哈希保持，full/selective逐项状态及已知来源逻辑签名一致。
- 本轮三查询子集不能替代原五查询、C2、Mall、Account、ZLT及62＋29＋15的新版本全量验收；这些旧成绩仍归原版本。

主工件：`artifacts/ruoyi-removeif-20261105/`。`controls-04`为最终筛选控制，`final-C1`为新业务捕获，`audit-final-01`为独立评分及首道失效诊断。开发试点及早期控制保留。离线兼容驱动首次误用绝对路径读取Git对象，失败目录保留；修正驱动在`offline-compatibility-02`复核相同捕获，未修改算法或重采业务。

小型[结果快照](ruoyi-removeif-results-20261105.json)、[逐实例新旧表](ruoyi-removeif-paired-20261105.csv)及修改前协议随Git保存。完整工件与必要既有运行时/镜像的备份引用见[备份清单](ruoyi-removeif-backup-20261105.json)。这是本机备份，不是异地副本。

```bash
python3 experiments/sockshop-mirrortaint/audit_ruoyi_remove_if_revision.py \
  --home artifacts/ruoyi-removeif-20261105 \
  --out /tmp/tf2-ruoyi-removeif-recheck-new
```

输出必须使用新目录。代码及小型报告提交main，push由用户完成。
