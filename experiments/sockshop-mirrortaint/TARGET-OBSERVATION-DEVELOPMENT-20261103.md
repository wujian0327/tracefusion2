# 开发集证据成本与机制消融

本表分解完整捕获，不截断或过滤记录。历史捕获只用于定位记录成本；开发短捕获只验证实际省略和答案，不用于速度结论。独立机制消融与最终正式成本另行追加。

| 参照捕获 | 完整字节 | 事件 | 最大记录类型（按字节） |
| --- | ---: | ---: | --- |
| artifacts/zlt-body-cost-20261031/round-01-mall-full/capture/events.jsonl | 39890429 | 60607 | collection-call-exit 13.68%；collection-call-enter 11.29%；binding-opaque-touch 9.21%；locality-end 5.81% |
| artifacts/zlt-body-cost-20261031/round-01-mall-selective/capture/events.jsonl | 37760146 | 52687 | collection-call-exit 14.45%；collection-call-enter 11.92%；binding-opaque-touch 9.73%；locality-end 6.14% |
| artifacts/zlt-completion-slice-20261031/final-candidate-01/zlt/runs/ZLT-MP-1/full/capture/events.jsonl | 810544 | 1915 | binding-opaque-touch 18.10%；binding-opaque-result 10.87%；write 8.50%；collection-call-exit 7.49% |
| artifacts/zlt-completion-slice-20261031/final-candidate-01/zlt/runs/ZLT-MP-4/full/capture/events.jsonl | 1316231 | 2732 | collection-call-exit 16.37%；binding-opaque-touch 14.72%；collection-call-enter 11.79%；binding-opaque-result 9.24% |

Mall 的调用完成／开始、opaque 快照和局部性协议占据主要部分。ZLT 还有较大的字段／容器快照成本。因此本轮将可证明无关的边界快照值纳入统一字段需求闭包；没有删除整个调用或移除证书。

| Mall 开发捕获 | 完整字节 | 事件 | 跳过标量取值 | 省去 Map 叶记录 |
| --- | ---: | ---: | ---: | ---: |
| artifacts/target-closure-revision-20261103/pilot-01/mall/tool-runs/mall-swarm-3/selective/query-002/capture/events.jsonl | 1112489 | 2000 | 225 | 30 |
| artifacts/target-closure-revision-20261103/pilot-01/mall/tool-runs/mall-swarm-3/full/query-002/capture/events.jsonl | 1212374 | 2220 | 0 | 0 |

标量计数是实际 Agent 在反射取值前跳过的次数；Map 计数是省去的叶记录，迭代和已有值读取仍保留；没有把离线过滤记录当作在线节省。完整 full/selective 差异还包括此前已有的观测选择，不能全部归因于新增值投影。当前不报告短窗口的 CPU 或延迟改善。

保留理由：数据事件为目标计算提供依赖；分支与异常确定实际路径；引用、版本、发布和效果协议保护别名及局部性；来源调用、目标／通信绑定和闭合协议认证实例；启动元数据、共享事件和诊断另列。尚未分类的记录继续保留。

共享索引、协议编码和诊断开关没有作为新增剪枝贡献。本轮主要省略发生在反射取值／装箱和字段事件构建之前，而非改变序列化编码。


## 最终候选和能力保持

算法冻结 `130858947f3eabc1dbee8693f11c926f37f289e9`。新增值投影和更强体内省略资格没有新增公共框架契约。原完整部署先在 candidate01 完成；最终 Python 修订核对 Agent class 和实际计划，仅四个转换查询的两模式重新采集，其余一致捕获在新目录正常复算，不称又一批新 Agent 部署。

| 集合，每模式 | 保持结果 | 边界 |
| --- | --- | --- |
| Mall | 98/103，MT 正确 88 项全部保持 | 5 项仍 unknown／真值不足 |
| ZLT | 15/15 正来源 | 两个已暴露入口的开发回归 |
| Account | 40/40 | 4 正来源、36 已知空来源 |
| 原 62 查询 | 428/431 | 原 3 unknown 保持 |
| 原 29 字段 | 232/244 | 原 12 真值不足 unknown 保持 |
| 原 15 写入口 | 96/96 | 原边界和来源签名保持 |

针对性 JVM 控制每模式 25 个目标，18 个独立来源／空来源匹配，其余必要不透明效果 unknown；36 项派生证据保护通过。正常／异常／finally、构造器同对象发布、Map／lambda 发布及守卫失败前采全均比较无 Agent 业务输出。旧同对象泄露及本轮发现的旧资格失败原捕获永久保留。

SQL 早回调留下工厂或 handler 的两种严格反例，每模式四个目标均保持 unknown。原局部性、应用调用、可靠性及源坐标保护的结果另存，不将预期 unknown 合并成准确率。

## 新机制独立消融

以下是新的短捕获：同一 Agent、同一计划和既有体内守卫，只关闭运行时值投影。它不是过滤旧日志，不据短窗口判断速度。

| 开发任务 | selective 完整字节 | 关闭新增值投影字节 | 实际省去标量值 | 实际省去 Map 叶记录 | 图节点：开／关 | 边列表：开／关 | 答案保持 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| mall | 4944522 | 5146284 | 1080 | 144 | 888／1128 | 120／120 | 24/24 |
| zlt-client | 2794992 | 3039074 | 1896 | 0 | 208／468 | 52／52 | 26/26 |
| zlt-user | 4548056 | 4925921 | 3036 | 0 | 252／612 | 72／72 | 36/36 |

Scalar 计数是实际取值前省略；Map 计数是未构建的叶记录，引用遍历与已有值读取继续执行。正常离线构建的节点及边列表数也保留在各新进程 summary；没有为计数重复还原一次图。完整 full/selective 收益仍混合既有机制，不能全部算作本轮新增投影。

本轮没有完成任意 Java 方法体最小切片。解释字段及有限转换仍保守扩张；不适用时采全。详见[算法与伪代码](TARGET-OBSERVATION-ALGORITHM-20261103.md)。
