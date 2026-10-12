# Sock Shop / MirrorTaint 预检结果

2026-10-12。**没有本场景的字段准确率，也没有跨服务还原或性能结果。**

本页保留最初环境的历史预检证据。后续用户报告主机两种模式业务均 15/15 通过，
来源追踪受异步线程状态和日志覆盖阻塞，见 [主机状态](HOST-STATUS-20261012.md)。

| 检查 | 实际结果 | 可支持的结论 |
| --- | --- | --- |
| 5 个原版应用 Git 提交与源码摘要 | 通过；tracked 源码未修改 | 源码版本与标注依据固定，不证明发布镜像对应源码 |
| orders 0.4.7 原生构建 | Maven 返回 0 | 原版源码可在本轮 JDK/Maven 构建，测试未运行 |
| carts 0.4.8 原生构建 | Maven 返回 0 | 同上 |
| shipping 0.4.8 原生构建 | Maven 返回 0 | 同上 |
| 固定 MirrorTaint JAR 加载 | 返回 0，premain invoked | agent 可加载，不证明字段传播正确 |
| 原版 Orders 原生启动，无 agent | 返回 1，HTTP 尚未就绪 | 环境缺失 `/proc/self/fd` 导致原有 Prometheus 启动失败 |
| 原版 Orders 原生启动，有 agent | 同一启动失败；生成控制器/RestTemplate 插桩记录 | 不是已测得的 MirrorTaint 传播失败；业务正例未执行 |
| 真实 Docker/API 负载 | `blocked`：Docker 不可用 | 0 次实际工作负载、0 个实际准确性评分查询 |
| 原有 Sock Shop 响应校验测试 | 6/6 通过（unittest） | 原有响应判定回归检查，不是来源引擎准确率 |
| 新部署/输入静态检查 | 通过 | 预运行配置与源码预期一致，不是运行结果 |

构建使用 Amazon Corretto 8.504.04.1 / JVM 1.8.0_504-b04、Maven 3.9.9。
原系统 Java 无法加载 libjli，因此使用独立 JDK。最初 Maven 直连 DNS 失败；
随后用仅转发公共 Maven Central 的 loopback mirror，未改依赖版本或业务源码。
首次逐次建连下载超时，复用 HTTPS 连接后三个构建成功。下载路径、内容摘要和最终日志保存。
这是构建 transport 适配，不是被测业务的外部服务 mock。

原生启动两种模式均未经过任何有效 HTTP 请求。没有通过删改 Prometheus 配置或替换业务
绕过环境故障，因此没有把裁剪后的启动冒充原版完整启动。
agent 的 error 日志为空也不能证明传播完整；这一运行在初始化阶段就终止了。

## 公开 agent 的实证与未决问题

JAR SHA-256：`e4c679206993b45c6727a4ace1d4dcff6df0ded2b80b56b27b8c86741be63fe7`。
首次 native audit 创建 6 个日志文件，实际目录为 `AgentLogs/ShadowTaint/tf2-preflight`。
原版 Orders 初始化过程中还生成 `FacadeRequestSourceTransformer`、
`FacadeResponseSinkTransformer`、`RestSourceSinkTransformer` 等插桩输出。
这些类文件只说明转化器触发，未证明目标方法的传播规则经过执行校准。

对固定 JAR 的 javap 审查显示：`TaintCollector.collect` 两个重载把格式化当前时间
`hhmmss MM-dd` 作为部分记录的分组/trace 参数，随后将该值用于 sink 文件路径和记录构造。
常量池检查未在 agent 自身 class 中发现 Sleuth/MDC/Tracer 引用。
这不等价于证明完整公开工具没有其他连接机制，也不等价于论文方法失效。
**当前跨服务请求实例连接尚未获得可复现校准证据**；不能按时间或值相等补上连接后仍称
“原版完整 MirrorTaint”。实际字段标签、来源边界、并发连接与异步线程传播是下一项资格验收。

## 已冻结但未执行的 API 工作负载

15 次订单请求预计包含 14 个有目标订单、1 个支付拒绝无目标订单；
98 个有目标字段查询（Java 服务边界 42、外部来源边界 56），另有 7 个无目标检查。
这 98 个预计目标中，空购物车 total 的显式来源集合为空；其余为单来源复制和多字段总额计算。
目标对象身份、Carts 项记录 ID、读取版本、实际 RPC 实例不得依赖内容相等确定。

源码查询契约在目标 API 请求前冻结，来源集合不从任一引擎生成。
当前还缺运行级 oracle、第二研究者人工审核、镜像与源码对应核验以及双方引擎输出。
PATCH/重复添加只覆盖当前读取版本，不声称覆盖数据库历史写入来源。
有真实 Go 服务参与业务不等于已证明跨语言前端可迁移性。

## 可复核材料

- [source-audit-20261012.json](source-audit-20261012.json)：原始源码提交与摘要。
- [preflight-validation-20261012.json](preflight-validation-20261012.json)：构建、agent 和两个原生启动结果。
- [native-evidence-20261012.zip](native-evidence-20261012.zip)：原始构建日志、下载摘要、javap、agent 日志及启动日志；不含 JAR/class。
- [evidence-20261012.json](evidence-20261012.json)：ZIP 摘要及文件数。

证据 ZIP 共 563,004 字节，SHA-256：
`5970feaa04cb6a330dce7ced54b814ce70d40ee41aff44651df49484087f4340`。
复核应从可信固定源码构建，不执行上传材料中的脚本或二进制。
完成主机实际运行与资格校准后，再进入来源准确性评分、选择性采集及同负载成本比较。
