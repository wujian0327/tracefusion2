# 第三轮：A→B 通信与历史来源闭环，预先定义

起始 main `dbb813ad81b789149b90b403a52b6700e2f0588d`，干净工作区。原 workload、两轮预期、历史结果及 direct-B 正确结果保持。新增预期在实现前封存到 `artifacts/cross-request-lineage-round-three-spec-20261113-01`。只推进顺序 A→B，不启动 CVE。

Cache 普通业务沿用原件。新增独立 HTTP 入口，以每 RPC 一个真实 Socket／HTTP/1.1 close 连接暴露实际收发及两端地址；B 仍使用 JDK HttpServer。此通信适配范围不冒充原 HttpURLConnection 或任意框架支持。每组两个 JVM 持续处理多个请求，不重启或清空分析状态。普通工作负载仍用不同 trace；另加两个同 trace、不同真实消息、同值的无缓存 fallback 请求校准，单列预期。

新增 opt-in HTTP exchange v1：实际连接四元组、当前 Socket／HttpExchange 本地身份、实际 wire traceparent、方法路径、方向、完成、原始 JSON 字节、hash、DTO 快照、固定适配器类哈希。跨 JVM 只用实际连接和具体消息证据连接；对象号只在各自 capture/process 内解释。字段映射来自已审核默认 JSON schema 与实际 bytes/property，不接受任意配置正确映射或相同值选边。

session history v1 和 direct-B 源边界保持。v2 只把 B 入站字段当 HTTP 中间依赖，最终图查询只接受 A 外部输入，未匹配通信必须 unknown／拒绝。链条须覆盖 A 输入→实际发送字段→B 入站→历史写→后续读→B 输出→A 接收→A 响应。来源和历史对象／版本／完成分开评分。原 process 限制保留。

先 plain，再 TF，再 MirrorTaint，每组至少两次。完整 known 正例通过后派生合成负例：同值 value/fallback 错映射、消息实例和捕获身份错配、删必要通信／字段映射／历史写，原序列损坏与重新编号分别检查；另保存故意错报来源包装并由独立预期检出。原始文件不改，原始正例复算仍通过。

MirrorTaint 分两种配置：A-only 外部原生标签；论文式各服务局部输入／输出关系＋离线拼接。后者的 B 请求、A RPC 返回标签仅是局部接口坐标，不是新外部 source；不传输原始标签，不根据预期搬运，不替基线传播。公开 API 的输入标记／输出查询和离线坐标组合须披露，原生传播与组合结果分列；无法获取的作者后分析器不得冒充运行。严格版本和离线缺证 API 继续 N/A，不能用作优势。论文 IV-E 与固定公开构件核验单列保存。

预测进程不得打开预期／workload；评分器独立根据请求序号、字段和符号版本核验。新建输出目录，记录实际源码／运行时／依赖／计划哈希，保存首次失败、原始 HTTP 与事件，逐文件封包。旧 170 项和 direct-B 捕获在当前核心下回归。没有创新、性能或普遍基线能力结论。
