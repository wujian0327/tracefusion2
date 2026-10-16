# Train Ticket 真实多来源价格路径：2026-10-16

原版 `BasicServiceImpl.queryForTravel` 的跨服务价格来源已接通，并在冻结后新增输入上通过 full/selective 验证。本轮把此前的单字段复制扩展到原应用实际存在的列表索引、整数距离差、双精度乘法、字符串转换、Map 写入和异常回退；没有修改业务 JAR 或在还原器里写入价格公式。

## 结果与结论范围

| 指标 | full | selective |
| --- | ---: | ---: |
| 业务请求（含一个预期的上游失败） | 20 | 20 |
| 实际产生价格字段的请求 | 19 | 19 |
| 指定字段查询 exact | 38/38 | 38/38 |
| 来源关系 TP / FP / FN | 92 / 0 / 0 | 92 / 0 / 0 |
| 已产生目标的 unknown | 0 | 0 |
| 未产生价格目标 | 2 个 N/A | 2 个 N/A |
| 五个业务 JVM 的采集事件 | 5,216 | 2,496 |
| 五个业务 JVM 的日志字节 | 1,894,722 | 1,286,154 |
| 实际最大重叠根调用 | 8 | 8 |

selective 在保持这批查询答案一致时，事件减少 **52.15%**，日志字节减少 **32.12%**。这是两次独立部署的正确性和记录量验证；每策略一次部署，顺序 full→selective，没有预热/稳态/五轮统计。本轮在线延迟、CPU、RSS、纯还原耗时、离线峰值内存及答案等待成本均为 **N/A**，不能从记录量推导这些成本改善。旧 Sock Shop / MirrorTaint 成本仍对应各自冻结提交，不能套给这版扩展核心。

两个 N/A 来自同一个缺失 Train 输入：原版 Train 接口返回 HTTP 404，Basic 的 RestTemplate 随之报错，在价格生成之前返回 HTTP 500。这是已核验的业务失败控制；既不计为正确的空来源，也不混进 38 个已产生字段查询。所有失败尝试、异常和原始采集均保留。

## 真实路径和来源口径

部署原版 Station、Train、Route、Price、Basic 五个 JVM 和四个独立 Mongo。补齐 Train/Route/Price 的固定镜像；五个业务 JAR 均独立从镜像重新提取并逐一匹配 SHA。所有依赖服务为原版服务，测试只向本轮新建数据库写入合成事实，认证和业务代码没有替换。两策略均使用 `-Xms32m -Xmx256m`，关闭 Zipkin，业务容器各 1 CPU/768 MiB、Mongo 各 1 CPU/384 MiB；完整启动参数在 compose 与 commands.log 中。

目标是实际响应的 `/data/prices/economyClass`、`/data/prices/confortClass`（原应用拼写为 confort）。数据来源边界是 Route 响应实际序列化的 `distances[index]` 和 Price 响应中的对应费率，不是数据库历史或所有框架内部写入。

正常计算会读两个实际距离元素及一项费率。相同距离值、同值费率、重排站点和重复请求均保留具体对象、列表位置及 RPC 消息实例，不能靠结果数值关联。缺失 Route 时，距离是业务常量 0，仍保留参与乘法的费率数据依赖；短距离列表、缺失站点和缺失 Price 分别触发原有 catch，返回原版 `95.0` / `120.0` 常量，数据来源集合为空。整批请求共用一个 trace-id，各请求和 RPC 使用不同 span；两策略均实际观察到 8 个根调用重叠。

本查询区分**数值操作数的数据来源**与**选择证据**。Station ID、Route.stations、分支与索引决定取哪个元素，相关选择坐标保留在本地还原结果中，但不计入本表的数据来源 TP；没有声称完整恢复这些选择字段的跨服务来源，也不是包含隐式控制依赖的安全污点查询。乘以 0、相减得 0 不删除实际读取的操作数来源。

## 迁移时改了什么

- **配置和实验驱动**：声明入口、目标字段和显式启用的 `collection-computation` profile；固定镜像、JVM 参数和资源；根据原版 `@Document` 注解准备 `routes` / `price_config` 等集合及 Java legacy UUID；独立业务与来源真值只在驱动/审计器中使用。
- **通用核心扩展**：显式异常表；在 CFG 汇合点合并 reaching definitions，避免枚举全部完整路径；根据目标 setter 反向选择计算及可能别名的本地 Map/StringBuilder 操作；按实际根调用的分支和 handler 重放原字节码；将局部依赖接入原有 `Reconstruction` 字段实例图。
- **通用库规则与观测**：List.indexOf/get/size、Integer 拆箱装箱、当前支持的整数/双精度操作、StringBuilder append/toString、String 键 Map.put；HTTP/JSON 增加列表原始元素和 Map 键坐标。Map/StringBuilder 须是可追踪的本地分配，相关 getter/setter 须通过直接字节码和具体运行类型校验，未知效果保持失败或 unknown。
- **新增显式库摘要**：原应用共用库的 `JsonUtils.conveterObject` 使用默认 Jackson 将 Map 经 JSON 转成 DTO。按实际转换调用及相对 JSON pointer 连接输入/输出字段，类 SHA 固定，数值只验证连接。该库摘要经原版 javap 审查；它是手工声明的库契约，不是自动证明 Jackson 任意配置正确，也没有加入业务价格推断。

因此，迁移并非“旧核心一个字没改”；本轮增加了通用操作与库模型。full/selective 的这次比较使用**同一个新构建、同一组计划、事件格式和离线核心**，仅 mode 不同。规划选中原方法 81 个非构造调用中的 37 个；方法有 264 条指令，CFG 工作表处理 820 步。计划保守地保留根方法分支，不声称观测集合最小。

full 记录冻结根调用活动期间的已纳入应用类实例字段读写、条件分支和根方法调用；selective 使用上述计划。公共 HTTP/JSON、转换观测、DTO 写计数与输出格式相同。full 仍不是所有 JVM/第三方库/本地指令的完全追踪。两者的语义相同，不将弱化能力的 boundary 纳入此表。

## 冻结、反例与回归

实现初次提交 `cf58728`；full 辅助方法分支过滤修复提交 `166fa3e`。最终使用 `build-09`，随后生成 `validation-02` 的新输入，seed=161133。冻结内容包括源码副本和 SHA、构建/模型/计划、输入、数据库事实和驱动；采集开始和结束均检查源码未变。开发期间的 validation-01 仅作探索记录，修复后没有复用其数字充当最终验证。

独立审计不调用规划器或还原器：从实际数据库读回重新计算业务结果及预期来源，使用根调用的具体 RPC span 和服务端原始 JSON 字段核对每个预测的 owner/field/version/message/path。两策略通过，N/A 和异常不被隐去。五个真实服务镜像 JAR 校验通过。

通用 JVM 控制用例两策略各 10/10：同值缓存 Integer 的不同列表位置、不同索引、List.get 失败及 catch、分支常量、Map 覆盖、输入对象复用、重复根调用、辅助方法分支。篡改 indexOf 结果被拒绝；接收集合上的写操作以及 getter 虚分派均被明确拒绝。另有 4 项 CFG 测试，包括 64 个连续分支汇合、显式异常表和循环拒绝。相关旧驱动/字段/HTTP/消融/验收单元测试 22 项通过。

用新编译观测器重新部署旧两应用路径：Sock Shop **198/198，TP258**；Train Ticket Station 路径 **31/31，TP30**；FP/FN/unknown 均为 0。完整验收还通过 13 项算法/负控制、872 条 javap 指令审计、W3C/异步上下文及六个原镜像 JAR 核验。旧原始工件未改写；另有只读历史重放结果。

接收的集合在已纳入应用字节码内按只读规则保护；集合 epoch 表示被观察到的内容阶段，**不是任意集合写入的完整版本历史**。反射/native 写、任意并发共享可变集合、自定义 List 实现、自定义 JSON serializer、一般循环或未建模 JVM 操作不在保证内。当前 List 规则限 ArrayList/Arrays.asList 的已检查运行类型。新输入在规则冻结后生成，但用例结构由本项目设计，不是第三方盲测。

## 复现与工件

原始目录：`artifacts/trainticket-multisource-20261016/`。最终证据为 `build-09/`、`validation-02/`、`controls-08/`、`legacy-correctness/`、`legacy-acceptance/`；重要节点在 `logs/00-*.json` 至后续节点日志，实际 Docker 命令、镜像和清理输出在各部署 `commands.log`。`image-jar-verification.json`、`machine.json`、`docker-machine.json`、`jsonutils-summary-evidence.javap.txt` 保留环境与库模型依据。开发失败目录仍保留，不纳入最终成功计数。

Git 包含代码和小型摘要，原始工件另行归档。归档入口预留于 `artifacts/trainticket-multisource-backup-20261016/START-HERE.txt`；同盘归档仍需用户复制到其他磁盘或机器。Docker 镜像不包含在工件归档内。

已有桌面依赖包须先解压（ASM/Jackson 与 `artifacts/desktop-inputs/images-lock.json`）；镜像须另备，Mongo 沿用该锁文件的 digest。以下在仓库根运行，所有输出目录必须全新。不同目录必须重新 prepare/build/freeze，不能修改旧冻结清单绕过绝对路径核验。

```bash
python3 experiments/sockshop-mirrortaint/prepare_train_multisource.py --out artifacts/train-price-inputs-new --pull
python3 experiments/sockshop-mirrortaint/build_distributed_plans.py --out artifacts/train-price-build-new --inputs artifacts/train-price-inputs-new/inputs.json
python3 experiments/sockshop-mirrortaint/run_train_multisource.py freeze --out artifacts/train-price-run-new --build artifacts/train-price-build-new --inputs artifacts/train-price-inputs-new/inputs.json --seed 161201
for mode in full selective; do
  python3 experiments/sockshop-mirrortaint/run_train_multisource.py capture --out artifacts/train-price-run-new --build artifacts/train-price-build-new --inputs artifacts/train-price-inputs-new/inputs.json --mode "$mode"
  python3 experiments/sockshop-mirrortaint/run_train_multisource.py evaluate --out artifacts/train-price-run-new --build artifacts/train-price-build-new --inputs artifacts/train-price-inputs-new/inputs.json --mode "$mode"
done
python3 experiments/sockshop-mirrortaint/audit_train_multisource.py --out artifacts/train-price-run-new --build artifacts/train-price-build-new
```

需要 Docker 使用权限。prepare 脚本已在本机独立复核五个 JAR SHA；上述新目录命令用于另一次重建实验，不声称已经运行名为 `*-new` 的这些目录。独立审计需使用冻结源码版本。

## 下一步

本阶段真实多来源路径的正确性与记录量扩展已完成。若优先论文证据，先整理这条路径的支持范围、人工库摘要与反例；若要声称该新 profile 的计算或在线成本改善，再按现有低负载协议补独立部署统计，无需高负载扫描。真实 Solr 安全路径仍只有预检，尚未部署验证，保留为后续任务。
