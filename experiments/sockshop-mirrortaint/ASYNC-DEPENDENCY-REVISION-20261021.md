# 工作Frame依赖传递：控制验证通过，Orders仍有库契约阻断

**本轮实现了有限的工作Frame→AsyncResult→Future.get依赖传递。full/selective控制各30个目标中，18个已知答案来源完全匹配、12个按预期unknown；原版Orders的24个目标仍全部unknown。** 新增真实基线差距修复0，开发台账累计97、剩余72。不能把控制程序成功或工作Frame能执行算作真实应用来源查询成功。

没有新增性能实验，业务仍使用原版JAR；没有启封29个候选。原431目标首轮、各阶段首次结果和旧成本表不改写。实现及有限条件见[机制](ASYNC-DEPENDENCY-ALGORITHM-20261021.md)。

## 冻结及修订顺序

| 阶段 | 提交 | 用途 |
| --- | --- | --- |
| 协议预先提交 | `d90e1cd` | 固定范围、原边界、开发查询及保护条件 |
| 初始实现冻结 | `35055fb` | 完成工作重放；实际业务捕获版本 |
| 最终核心冻结 | **`6a2e1ca4cf6ec0dc1b76703dd1ef7bd3f0221646`** | 补共享数组发布保护，最终离线复算 |

工作依赖来自原字节码及实际调用，不是逐业务helper摘要。新增人工公共契约是固定Spring AsyncResult构造/解包，与上一阶段任务/Future协议组合使用。借用可变堆、一般容器结果和任意并发未获得支持。

## 控制程序：按原入口参数实例判分

使用真实Spring拦截器、两线程执行器和FutureTask，15种行为各运行两次。入口参数的String对象即使值相同也独立分配。预期参数位置或常量由测试程序原逻辑独立列出，不调用TF传播或基线标签决定；输出来源必须指回原入口Frame，不能指向工作方法参数。

| 检查 | full | selective |
| --- | ---: | ---: |
| 有效目标 | 30 | 30 |
| 已知来源完全匹配 | 18/18 | 18/18 |
| 预期unknown | 12 | 12 |
| 缺失/矛盾证据拒绝 | 6项 | 6项 |
| 父线程与工作Frame共享预算 | analysis_limited检查通过 | 同左 |

已知项包含直接复制、应用helper创建DTO、常量、同值任务选择右侧实例、不可变标量返回、`pre:SAME`字符串转换、异常捕获常量回退，以及调用者同值常量覆盖或改写成右侧来源后再次get。它们检验实际依赖传递及版本更新，而不是数值相同即匹配。

六类预期unknown各两次：工作方法必要不透明调用、借用对象字段读取、直接返回共享对象、把结果写到共享字段、调用者不透明修改后重读，以及通过共享数组发布结果。预期unknown是保守保护，不与已知项合并为“30/30准确”。本组小程序不替代真实应用结果，也不是未见查询泛化测试。

构造payload证据缺失、错误对象、错误wrapper哈希、工作字段写入缺失、错误get对象及缺失get证据均拒绝。上一阶段混合生命周期控制仍各15任务、14项扰动通过；原应用调用控制各26已知匹配/8预期unknown/2异常，构造器静态字符串控制各18已知匹配/12预期unknown/2异常保持。

## 保留的共享数组失败

`shared-array-first/`暴露了初始35055fb的接纳缺陷：工作方法新建DTO，再存入已有共享数组slot[0]，仅检查非本地字段写入没有发现这次发布，仍导出了“私有”字段。这个输入的来源集合恰好与真值一致，但违反声明的私有结果前提，不能作为安全接纳成功。

最终版将对非任务创建数组的store纳入外向效果检查，保留unknown。原失败捕获在最终离线代码上再次回归，两次发布目标均unknown；原失败没有删除或改写。另保留首次评价驱动使用错误argument键的失败，修正为公开坐标`@argument:N`/root_frame；这是评价字段修正，没有为已知答案补源。

## 原版Orders：实际工作方法已执行，端到端仍未答

沿用两个已暴露查询和六组合法输入，四配置共用实际输入库、请求体和消息坐标；轮换目标JVM，仅停服清空本实验Orders输出库。full先于selective，原始字节码不变，`source_evidence`对四配置统一启用，只用于既有独立真值/原始事实，不直接创建来源。

| 配置 | 目标 | 已知 / unknown / 无效 | 关系TP / FP / FN（含unknown阳性） |
| --- | ---: | ---: | ---: |
| Date full | 6 | 0 / 6 / 0 | 0 / 0 / 0 |
| username full | 6 | 0 / 6 / 0 | 0 / 0 / 6 |
| Date selective | 6 | 0 / 6 / 0 | 0 / 0 / 0 |
| username selective | 6 | 0 / 6 / 0 | 0 / 0 / 6 |

各配置N/A、错误确定答案和oracle unavailable均为0；可回答率均0/6，已知条件匹配率N/A。Date的字段边界内预期来源为空仍不代表已经回答，不能用FN0掩盖unknown。

四配置共144个任务、264次get，配对核验保持。每配置实际get已进入工作重放，工作结果仍为`unsupported-or-opaque-result`。诊断记录实际工作方法Frame及执行的不透明调用，包括：

- RequestEntity.get/post、accept、build/body等请求构建；
- `RestTemplate.exchange(RequestEntity, ParameterizedTypeReference)`；
- ResponseEntity.getBody及Resource/集合的未解释渲染。

现有HTTP契约针对另一种String/Class/空varargs重载，不能套给这些调用。根方法的HATEOAS内容连接、必要helper及保存效果也尚未闭合。这里列的是实际执行的不透明调用，不是最小因果切片，不能声称补一项即可恢复全部72个目标。

独立真值仍依据原业务、实际源HTTP消息/解码字段坐标，或Calendar调用与ISO日期投影；不从工作重放或Future快照推导预期来源。

## 新Agent兼容验证及捕获复用

| 原版业务 | full | selective |
| --- | ---: | ---: |
| Station/Route循环 | 60/60 | 60/60 |
| TicketInfo转发 | 21/21 | 21/21 |
| Cart首次创建、再次GET | 2/2 | 2/2 |

这三套共16个实际配置，加四个Orders配置，共20个新Agent业务配置；独立端口/数据卷上的正确性部署部分并行，不据此测性能。原301个已执行目标的旧捕获复算保持213正确、88unknown，只是离线兼容，不是新Agent全量213部署。

最终共享数组修正仅改离线检查与控制程序。`final-validation-build/`在新目录重新构建，逐份核对业务计划完全相同、全部Agent class字节码哈希相同，因此保留35055fb的20份实际捕获，用6a2e1ca复算；实际捕获版本、计划/构件哈希和复用证明都保留，不将复算计为新增部署。

## 工件与复核

原始根目录`artifacts/async-dependency-revision-20261021/`包含双冻结、源码包、原业务JAR与依赖、镜像digest/资源配置、固定输入、运行命令、原事件、真值、预测、失败、控制和逐节点日志。关键目录为`business-frozen-first/`、`semantics-final-safe/`、`shared-array-first/`、`audit-final/`及`logs/`。

审计另存`capture-reuse.json`、`worker-diagnostics.json`、`transfer-counts.json`、`shared-array-regression.json`、`orders-instances.json`和原事件SHA。诊断重放不是另一次部署。小型[结果快照](async-dependency-results-20261021.json)随Git保存。

```bash
python3 experiments/sockshop-mirrortaint/audit_async_dependency_revision.py \
  --root artifacts/async-dependency-revision-20261021 \
  --out artifacts/async-dependency-revision-20261021/audit-recheck-new-directory
```

备份入口`artifacts/async-dependency-backup-20261021/START-HERE.txt`。完整工件需另备，同盘副本不含Docker镜像层；迁移须新目录重建。推送由用户完成。

下一步应补固定版本的RequestEntity/参数化RestTemplate读取与解码契约，然后处理必要保存字段效果。不会把返回快照当来源、移动来源边界、统一声明save只读，或以这批控制程序结果替代至少382/431的同一冻结版本全62查询验收。
