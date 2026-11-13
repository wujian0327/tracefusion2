# 后续基线接入条件

本轮主对照是固定公开 MirrorTaint JAR `54fcbfc5bb3a0d7cd30309098355d999553a861b`，SHA-256 为 `e4c679206993b45c6727a4ace1d4dcff6df0ded2b80b56b27b8c86741be63fe7`。在两个 JVM 加载原版 Agent，配置 `taint.env=remote`、`taint.app=lineage.business`。`MirrorBoundary` 仅在 A 外部请求解码后对 `/value`、`/fallback` 分别调用公开 `TaintTagger.tagManually`，在输出查询 `TaintHeap.queryTaint` 并导出原生 source ID。没有应用传播模型、HTTP 标签传送、缓存打标、清空 heap 或跨请求推断。来源粒度与 TF 相同，为请求出现加 JSON 字段。op/key 只参与控制，不列入显式数据来源。

原版 API 的存在由固定 JAR 的 `javap` 核验，实际标签安装由每次 source 的原生 ID 核验。公开上游的 [运行说明](https://github.com/MirrorTaint/MirrorTaint/tree/54fcbfc5bb3a0d7cd30309098355d999553a861b) 给出 Agent 与应用前缀配置；这不等于宣称上游支持本实验的 JDK HttpServer/HttpURLConnection/Jackson 通路。来源成功但 HTTP 后为空，需要按“该协议配置尚未贯通”解释，不能直接称为其一般缓存传播错误。空标签对公开常量可以碰巧正确，不能据此证明消除了旧版本。

| 工具 | 当前证据与状态 | 接入所需条件 | 验收方式 |
|---|---|---|---|
| MirrorTaint | 本实验真实运行，固定 JAR＋公开 source/sink 薄适配；原生标签和业务日志保留 | 查明上游原生跨 HTTP 能力及公开接入点；若仅有 RPC 重新设 source，无法满足本轮原始来源要求 | 先让不经过缓存的 A 外部输入到 B 响应贯通；不能在 B 人工搬标签。再比较持续进程中的覆盖、替换与版本查询 |
| DisTA | 只完成资料与可获取性检查，未运行，不能记作 FN | 从作者取得可构建、可固定版本的工件；确认其修改的 Phosphor/JRE/native socket 组件与本机 JDK/OS、双节点协议兼容；对各外部字段设置独立请求出现标签 | 先校准同值异字段、Jackson、普通 HTTP 和 native 通信；再跑完全相同 workload，禁止代理补传播；确认源请求和字段版本能否查询 |
| Galette | 本轮未运行；仓库已有官方版本及明确标记修改版的历史校准，均不移用为本实验成绩 | 固定官方提交与 JDK/JCL 插桩产物；先通过普通 HTTP/Jackson/MethodHandle 的业务兼容，再用原生 Tainter API 配置源与汇；需确认跨 JVM 字节来源通路 | 先直接复制／公开常量／同值字段 API 控制，再 HTTP 无缓存贯通，最后持续进程缓存；原生标签成功不等于对象字段历史可查询 |

[DisTA 作者论文](https://gaoyu-cn.github.io/paper/2022-dsn-dista.pdf)描述在修改的 Java 网络/native 层传递字节标签，并通过方法描述符设置 source/sink。论文给出的 [工件地址](https://github.com/tcse-iscas/DisTA) 在本轮 2026-11-13 检查返回 404，raw README 同样未获取；这是可获取性障碍，不是传播实验失败，也未将 FlowDist 或 DistTaint 当作 DisTA 替代。

[Galette 官方文档](https://github.com/neu-se/galette)要求用 Java 17 与 Maven 构建，再用插桩后的 Java 安装、bootclasspath 和 Agent 运行；来源与汇可用 `Tainter.setTag/getTag`。本仓库已有[官方固定版本兼容性和独立修改版说明](../sockshop-mirrortaint/GALETTE-COMPATIBILITY-SELECTION-20261111.md)：8u504 上的 hosted 模板问题必须与修改版成绩分开。该历史结果没有检验本实验的 HTTP、跨请求缓存和严格版本查询。

分类规则：配置错误指 source/sink 没有安装或运行时契约不匹配；无法运行指业务启动或兼容性失败；传播错误要求已经通过同粒度 source、sink 和通信校准后仍返回错误源；查询能力不足指原生结果不能回答请求出现、字段或版本义务。传播层空标签与查询层无法回答分别记录，不用 N/A 冒充正确。
