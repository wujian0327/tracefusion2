# Sock Shop 有限读取模型、独立来源事实与冻结后字段覆盖

> 后续勘误：下文Cart首次创建保护的“入口参数来源”解释有误；原版先保存再重新读取，
> 在既定边界上应为第二次仓储返回。原记录与计数保留，修正证据见
> [62查询能力对照报告](BASELINE-CAPABILITY-20261020.md#独立真值与勘误)。

**本轮打通了已有 Cart 的只读来源链，并复用于一个封存新字段；没有打通 Orders 的完整保存/异步链。** 原22查询中的 Sock Shop 24个目标仍为 unknown，但独立真值已可获得。新增字段测试还暴露了 Basic 异常路径的调用配对限制，14个目标按证据无效保留。

本轮不做性能实验，不把旧成本表移用于新版本。业务始终使用原版 JAR。算法细节见[有限模型说明](SOCKSHOP-MODEL-ALGORITHM-20261020.md)，执行规则见[协议](SOCKSHOP-MODEL-PROTOCOL-20261020.md)。

## 版本与测试边界

| 阶段 | 版本 | 说明 |
| --- | --- | --- |
| 首次自动规划覆盖 | `a84ce9d` | 原0/20结果保持不变 |
| 上轮响应绑定冻结 | `803b92f` | 上轮结果保持不变，现有查询已成为开发资料 |
| 新字段封存 | `0dca193` | 本轮任何核心修改之前提交选择规则和20个字段 |
| 有限模型开发检查点 | `3f35e8d` | 新模型、独立真值、语义保护 |
| **本轮最终算法冻结** | **`c3e6739ca92f870821ce264f8ae1eb32cb681477`** | 核心与必要回归通过后冻结，随后首次规划和执行新字段 |

[冻结清单](sockshop-model-freeze-20261020.json)记录27个核心源码/契约文件、Agent、依赖、九个业务 JAR、基础配置、镜像锁和源码归档哈希。冻结后核心和已列实验驱动哈希保持一致；额外核对的旧驱动亦与冻结 Git 树一致。后续整理审计、报告和补充开发控制没有修改核心。

原91个候选不变。此前20+22个查询现在均是开发资料；剩余49个中，Sock Shop 17、Train Ticket 32。按预先 SHA256 排序和入口轮转，各选择10个字段，来自4和8个入口；另外29个没有尝试规划。已经没有完全未用入口，所以本轮只称**旧入口新字段**，不称新入口验证。

封存文件仍为[sockshop-model-heldout-20261020.json](sockshop-model-heldout-20261020.json)。没有根据规划结果替换查询。开发时一次查看文件头部意外显示了前两个ID（Cart addToCart.itemId、get.unitPrice）；未对它们试规划或据此调试，提前查看已写入协议和日志。本轮不是第三方盲测，不能把封存解释成作者对业务完全不知情。

## 首先补齐了 Orders 的原始事实与独立真值

原 User RPC 的返回值是 HATEOAS Resource，旧 HTTP 快照没有展开 content，因此旧24个目标缺少原始来源坐标。本轮旁路记录 Jackson 实际消耗的 HTTP 字节、完整性与哈希、具体 RPC/父消息、content 对象、字段和版本。读取完成须满足完整单文档及 EOF/Content-Length 条件；不额外耗尽业务流。原始事实本身不注册为来源答案。

独立程序 **不加载 TF Agent**，使用原版 JAR 内的 RestTemplate/Jackson 库重新解码18次 User 响应，全部与实际解码字段一致。原 AsyncGetService 虽构造另一套 HAL template，真实读取使用的是 RestProxyTemplate 中的默认 RestTemplate。

| 原22中的查询族 | 实际目标 | 独立预期来源 | TF的第一个断点 |
| --- | ---: | --- | --- |
| Orders.card.id | 6 | 原默认解码忽略 wire id，null 的数据来源为空 | 缺少该解码默认值的来源语义 |
| Orders.customer.id | 6 | 同上，不能连接原始 `/id` | 同上 |
| Orders.address.id | 6 | 同上，不能连接原始 `/id` | 同上 |
| Orders.customer.username | 6 | 该次具体 User RPC 的 `/username` 字段 | 尚无已接纳的 HATEOAS 解码字段来源提供者 |

原始 JSON 中的三个 id 都存在且非空，content.id 却为 null；独立解码和原库注解/字节码核验了这个区别。因此不能按同名或同值猜连字段，也不能把返回快照当来源。对 username 等实际解码标量，独立真值使用原业务的引用投影、实际消息和字段坐标，不运行 TF 的传播、别名或跨服务连接。

四族的原始事实、缺口与调用清单保存在 `orders-source-breakpoints.json`。后续仍有 StringBuilder.append(Object)、CustomerOrder.toString、HTTP POST/异步 helper、Mongo save 和未证明的根构造效果阻断。**独立真值可得不等于 TF 已经回答**：这24个目标仍全部 unknown。

独立真值以所审阅的原业务和默认库行为为前提，不把同值保存视作任意 save 的保持证明。TF 没有因此把保存、异步或所有 helper 声明为只读。

## 四个空列表的业务可达性

一次合法关联实验记录：上游客户原已有1个地址和1张卡，进一步通过 User API 的 `userID` 关联后为2个地址、2张卡；关联端点明确非空。主 Customer 响应仍只提供 `_links`，原 Orders 代码没有继续跟随链接填充这些列表，最终 customer.addresses/cards 仍为空。原 DTO 构造器的空 ArrayList 与独立解码结果一致。

因此，在当前默认端点/原代码路径下，这些查询没有元素目标。保留 N/A，不修改 JAR 制造目标，也不把其他位置的 Card/Address 冒充这些列表元素。新一轮固定回归没有扩大重复空列表输入；额外合法关联诊断只做一次。此结果不是元素来源正确性证据，也不是对任意上游 JSON 的不可达证明。

API 字段参考[原项目请求定义](https://github.com/microservices-demo/user/blob/master/api/endpoints.go)，最终行为以固定镜像的实际请求和响应为准。

## 打通的有限模型：已有 Cart 的只读转发

真实链为 `findByCustomerId → DAO转发 → stream.findFirst → 非空Optional → Cart.contents → 响应元素字段`。规划器从固定字节码生成候选组合方法；Agent 核验实际实现、子调用、对象身份和相关字段版本；离线核对调用配对及固定 JDK 模型。**效果核验只消除不透明阻断，不创建来源**，来源仍须来自原已声明的仓储读取返回等边界。

支持限定为具体 List 类型的新顺序流、实际首元素和同一非空 Optional。任意 stream、并行流、自定义 List、空 Optional 的创建/保存回退均不由此获得支持。根方法的 invokedynamic、一般循环和数组支持没有扩大。嵌套标准 Supplier 创建只作为分配效果核验，不能据此假设回退体只读。

| 原20中的开发目标 | selective | full | 关系TP/FP/FN（各模式） |
| --- | ---: | ---: | --- |
| Cart.customerId | 6/6 | 6/6 | 6/0/0 |
| getItems 中各 Item.quantity | 6/6 | 6/6 | 6/0/0 |
| getItems 中各 Item.unitPrice | 6/6 | 6/6 | 6/0/0 |

三族来自两个入口，各模式18个指定请求、18个实际字段实例，另有2次空 items 请求 N/A。空 items 测试仍有已保存的 Cart，不等于仓储中完全没有 Cart。这些是开发回归，不作为新字段泛化证据；原20的其余查询没有在本轮被声称全部重新部署。

补充的原版 Cart 两请求控制单列：同一 ID 首次 GET 触发创建/保存，预期来源为入口参数，TF 保持 unknown；第二次 GET 从仓储读取，1/1来源匹配。两次输出 customerId 完全相同，来源边界和实例不同。首访不是正确空来源；若计入这一补充测试的全部关系，为TP1、FP0、FN1。该测试是旧查询的开发保护，不是封存新查询。

每查询有三类声明、四个具体值：入口、目标 JVM 字段、响应 JSON 路径、来源边界；本轮另统一启用两个全局开关。新增公共 JDK 效果模型和 HATEOAS 原始事实契约均需人工审阅、版本固定和检查。没有为单个新字段新增传播代码、业务公式或 helper 白名单。封存文件沿用的旧候选元数据并不意味着本轮没有新增公共模型；实际接口为显式 profile 路由，不是旧元数据描述的两轮尝试。

## 原22个查询的重新回归

| 指标 | Sock Shop | Train Ticket |
| --- | ---: | ---: |
| 查询族：选中 / 接纳 / 拒绝 | 10 / 8 / 2 | 12 / 10 / 2 |
| 入口：选中 / 接纳 / 有已知答案 | 3 / 1 / 0 | 5 / 3 / 3 |
| 指定真实请求 | 48 | 60 |
| 实际目标：已知 / unknown / 无效 | 0 / 24 / 0 | 71 / 0 / 0 |
| N/A请求 | 24 | 9 |
| oracle unavailable | **0** | 0 |
| 已知答案完全匹配 | N/A：空样本 | 71/71 |
| 已知答案关系TP/FP/FN | N/A：空样本 | 71/0/0 |

Sock Shop 改进的是原始事实和真值，端到端可回答率仍0/24；独立真值中的18个默认 null 预期为空来源、6个 username 有正关系。因此含 unknown 的关系为TP0/FP0/FN6，不能据此把18个未回答的 null 算作正确。Train Ticket 的10个接纳族集中在3个入口，不能当成10个独立入口。

## 冻结后20个新字段的首次结果

以下都在 `c3e6739` 冻结后首次运行，核心未按结果修改。

| 指标 | Sock Shop | Train Ticket |
| --- | ---: | ---: |
| 选中查询族 | 10 | 10 |
| 绑定计划接纳 / 拒绝 | 7 / 3 | 6 / 4 |
| 入口：选中 / 接纳 / 有已知答案 | 4 / 2 / 1 | 8 / 5 / 4 |
| 指定真实请求 | 42 | 40 |
| 实际目标实例 | 24 | 49 |
| 已知 / unknown / 证据无效 | **6 / 18 / 0** | **35 / 0 / 14** |
| N/A请求 | 19 | 6 |
| 实际目标可回答率 | **6/24（25%）** | **35/49（71.43%）** |
| 已知答案实例完全匹配 | 6/6 | 35/35 |
| 已知答案关系TP/FP/FN | 6/0/0 | 35/0/0 |
| 全部独立真值关系TP/FP/FN，含unknown及无效 | **6/0/18** | **35/0/14** |
| 至少一个已知答案的查询族 | **1/10** | **4/10** |
| oracle unavailable | 0 | 0 |

Sock Shop 的新 `getItems/*/itemId` 6/6正确，没有为它增加模型。三个实际产目标的 Orders 字段仍有18个unknown；三个列表字段未产元素。Train Ticket 的已知结果来自 Train列表字段、Route列表字段、Station.stayTime、PriceConfig.trainType，共四个入口。

“接纳”只表示产生了目标绑定计划，不能视作完整来源计划：六个 Orders 和两个 Basic 接纳项在计划里已标出根效果未证明等条件。查询族按通配选择，实际实例按元素计数；空列表和未生成目标按请求计 N/A，JSON 中实际存在的 null 仍算目标。各应用和阶段不合并成一个总体准确率。

### 保留的 Basic 调用配对失败

两个 Basic 新字段各用8个固定请求，7个实际产目标、1个上游失败未产目标。short-distances、missing-price、missing-station 的异常路径各留下未完成的正常调用配对，另有中止路径；新监测器没有完整记录这些完成/清理事实。离线按整批失败，因而每族7个目标均记为证据无效，包括批次中的正常请求。

**14个无效实例不代表14次独立来源错误**，而是两个批次各7个目标没有有效答案。它们不能算unknown、N/A或正确结果。原始调用记录、首次错误与 `heldout-basic-call-pairing-diagnostic.json` 已保留；未通过删除必要证据或放宽审计来消除失败。此处是新增调用监测的实现限制，不能只称为业务语义不支持。后续修复必须建立新版本并与本次首次结果分开。

### 首道规划拒绝

| 应用 | 数量 | 原因 |
| --- | ---: | --- |
| Sock Shop | 2 | Root invokedynamic/opcode186；定位为Supplier创建，但未扩展根数据/控制规划及其回退效果 |
| Sock Shop | 1 | 目标Date类型不支持，字段实际存在 |
| Train Ticket | 2 | opcode189/ANEWARRAY |
| Train Ticket | 1 | 目标UUID类型不支持 |
| Train Ticket | 1 | 循环/回边 |

这些是第一道阻断，不意味着补一条指令后对应查询一定成功。拒绝项没有运行，不计入运行unknown或N/A。

## 语义、拒绝与历史保护

- 新9组小程序：full/selective共96次有效语义查询，36次预期已知且来源匹配，60次预期unknown；另各一次自定义List拒绝。覆盖同值不同对象、重复调用、重叠来源边界、空回退、反射写、异步、构造器隐藏效果和同值常量覆盖。小程序不替代真实应用结果。
- 新小程序14项证据扰动，以及真实 Cart 捕获上的9项扰动，均拒绝或unknown；包含缺运行时清单、缺调用结束/汇总/来源、错对象/版本/选择身份、重复来源。原始捕获不改写。
- 原9组语义54查询：48次预期已知匹配、6次必要未建模helper保持unknown；原6项嵌套/序列化保护和5项异常/写版本扰动继续通过。
- 原集合控制full/selective各10/10，索引篡改、修改接收集合与虚调用保护通过；32项相关单元检查通过；历史4个规划正控制4/4。
- 本轮重新部署历史原版业务：Sock Shop **198/198、TP258**；Station链路 **31/31、TP30**；多来源票价full/selective各 **38/38、TP92**，另各2目标 N/A。均无FP/FN/unknown。输入复用既有冻结回归集，不称新的覆盖样本或性能重复。

开发过程的编译失败、重叠参数的首个语义预期错误、未完成的早期回归等均单独保留。重叠参数的同一物理字段出现多个来源边界时，当前策略仍保守unknown；没有为通过测试删掉这类输入，而是另列歧义保护。

首个Cart开发捕获使用旧评分器，oracle缺失的原评分副本保留；独立真值按原代码和仓储返回位置补齐后另行评分。最终开发回归及封存测试前，该真值逻辑已经固定。后续补充的声明字段坐标审计只核验原字段名，不修改预测或预期来源集合。

## 工件、复核与后续

完整目录：`artifacts/sockshop-model-revision-20261020/`。关键项：

- `algorithm-freeze.json`、`candidate-code-frozen.tar.gz`、`heldout-runtime-protocol.json`；
- `previous22-final-{sockshop,trainticket}/`、`cart-final-{full,selective}/`、`cart-create-guard/`；
- `heldout-first-{sockshop,trainticket}/` 的计划、原始事件、客户端响应、逐实例预测与首次错误；
- `independent-decoding-final/`、`orders-source-breakpoints.json`、`source-diagnostic-final/`；后者是冻结前诊断阶段，保留其实际build哈希，不冒充最终部署；
- `semantics-final/`、`legacy-semantics-final/`、`collection-controls-final/`、`historical-business/`、`price-business/`；
- `audit.json`、`supplemental-driver-integrity-audit.json`、`logs/00…10`、各部署commands/compose/images和机器配置。

小型[snapshot](sockshop-model-results-20261020.json)随Git保存。审计通过只表示工件、分母和已知答案检查一致，**不表示全部查询可回答**。

```bash
python3 experiments/sockshop-mirrortaint/audit_sockshop_model_revision.py \
  --root artifacts/sockshop-model-revision-20261020 --heldout
python3 experiments/sockshop-mirrortaint/audit_read_forward_faults.py \
  --query artifacts/sockshop-model-revision-20261020/cart-final-selective/sockshop-carts-getItems-each-quantity
```

本机备份入口：`artifacts/sockshop-model-backup-20261020/START-HERE.txt`。备份核对文件内容哈希，包含当前原始工件、原版JAR、依赖、镜像/输入清单和Git bundle；旧0/20与803b92f原始证据继续保留在此前独立备份。它是同盘副本，不含Docker镜像层。迁移须在新目录重建，不能盲用旧绝对路径。推送由用户手动完成。

这轮达到“至少一类真实Sock Shop非空读取链可复用，并有独立实例真值”的有限停止条件；没有达到“Orders链已可回答”或“自动规划适用于全部响应字段”。Basic配对缺陷需要另版修复，不能用当前已知样本的100%条件匹配率掩盖。

下一步应先独立修复调用异常/中止配对，保留本次首次结果；随后若恢复成本实验，选择新增绑定和读取模型实际参与的 Cart 查询，重新冻结测量配置，继续同步独立真值与full/selective检查。当前原始事实诊断开关与新增调用配对都有成本，旧表中的优势不能当作新版本结果。
