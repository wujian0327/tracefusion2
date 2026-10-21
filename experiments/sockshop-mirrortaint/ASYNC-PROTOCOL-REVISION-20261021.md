# 异步任务实例配对：事实链完成，来源传播尚未完成

**原版Orders四个配置共144个异步任务、264次Future读取已通过实例配对核验，但24个响应目标仍全部unknown。** 本阶段没有新增基线差距修复：开发台账仍为累计97、剩余72，不能用配对通过率替代来源可回答率。

算法冻结为`cb693c1959f075ec38436c89822d78a514b0aa51`。协议先在`d67658a`提交，随后修订采集和离线核验。业务继续使用原版九个JAR，实际Orders、Cart、Station/Route、TicketInfo捕获都由本轮新Agent完成；没有新增性能实验，29个未测候选继续封存。机制及支持前提见[算法说明](ASYNC-PROTOCOL-ALGORITHM-20261021.md)。

## MirrorTaint并不是所有任务100%正确

已核对[原论文](https://zhangyuqun.github.io/publications/icse2023c.pdf)：开源评估报告97.9%精确率、100%召回率，工业案例报告100%精确率、99%召回率。这些是声明数据集和任务上的关系指标，不是任意查询、每个实例来源集合都100%正确。

本项目的[同任务431目标对照](BASELINE-CAPABILITY-20261020.md)中，**MirrorTaint＋披露适配器为368正确、35错误、28无法回答**；368/431约85.38%。此前共同total任务的900/900只对应那个校准子集。TF首轮213正确、88unknown及130个规划拒绝目标仍保留原冻结版本口径，不用后续开发套件拼成新版整体正确率。

我们参考了论文中的镜像栈、堆和跨Frame传播组织。公开构件没有完整传播核心源码，实际基线使用固定作者JAR及本仓库适配器，不能称为复制了原生工具全部实现。

具体差别不只是观测量：MirrorTaint原生传播覆盖更广的实际指令和跨方法操作，本地[线程适配器](MirrorTaintThreadAdapter.java)还在任务提交时捕获标签堆、执行后保存返回对象可达的标签、在Future.get时带回提交者。TF此前在Spring异步提交处只传播W3C上下文。**full和selective一起unknown，说明必要还原语义与框架协议尚未闭合，不能归因于选择性观测少采。** 这不抹去基线自己的错误，也不抹去TF在其正确目标上的真实缺口。

## 本轮完成的范围

新增固定Spring 4.3.6的任务协议：

```text
实际父调用/实参 → 唯一task/原Callable → 工作Frame
               → 内层AsyncResult → 实际解包结果
               → 外层FutureTask → 某次Future.get的实际返回
```

核对四个Spring类、两种已登记JDK的相关Future类哈希。允许工作执行早于提交返回；记录提交失败、工作异常、超时、取消和重复get。引用身份、Frame/call-id、线程及真实完成顺序共同参与核验，不按相同数值或相同trace连接。HTTP收据按已核验工作任务的实际线程和执行区间归属。

`async_evidence`对本轮两个Orders查询统一启用，没有逐字段匹配表或业务来源公式。旧profile默认关闭该开关，路由保持；当前不是最终统一策略自动选择的全量验收。

本阶段显式为`observation_only`：协议不注册来源，也不替代工作Frame的依赖解释、解码契约、字段版本或保存效果核验。配对成功只说明“哪次任务返回了哪个对象”，尚不能证明这个对象所有字段的来源。

## 原版Orders结果

每个配置沿用六组已暴露合法输入；四配置共用实际数据库、请求体、原消息坐标，仅轮换目标JVM与清空本实验输出库。每配置独立执行，full先于selective，共四次Orders目标JVM部署。

| 查询/模式 | 目标实例 | 已知 / unknown / 无效 | 任务 / Future.get | 关系TP / FP / FN（含unknown阳性） |
| --- | ---: | ---: | ---: | ---: |
| Date / full | 6 | 0 / 6 / 0 | 36 / 66 | 0 / 0 / 0 |
| username / full | 6 | 0 / 6 / 0 | 36 / 66 | 0 / 0 / 6 |
| Date / selective | 6 | 0 / 6 / 0 | 36 / 66 | 0 / 0 / 0 |
| username / selective | 6 | 0 / 6 / 0 | 36 / 66 | 0 / 0 / 6 |

每个实际工作任务恰好对应一次RPC，包含被反复get的任务及未join的shipping任务。144和264是四配置中的实际执行计数，不是144种未见输入或264个来源查询。

两查询的目标可回答率均0/6；没有已知答案，条件匹配率为N/A。各配置N/A请求、错误确定答案、证据无效、oracle unavailable均为0。Date在本次字段边界内预期数据来源为空，但它仍是未回答目标，不能把关系FN0当成已答对。独立真值仍依据原业务、实际Calendar调用/ISO投影，或原始HTTP消息与真实解码字段坐标；不由任务配对或TF图决定。

## 控制与兼容性

| 检查 | full | selective |
| --- | ---: | ---: |
| 真实Spring混合控制 | 9次根调用、15任务 | 9次根调用、15任务 |
| 其中正常工作 / 异常工作 / 取消前未执行 / 提交拒绝 | 12 / 1 / 1 / 1 | 12 / 1 / 1 / 1 |
| 必要证据扰动拒绝 | 14项 | 14项 |
| 原版Station/Route实例来源匹配 | 60/60 | 60/60 |
| 原版TicketInfo实例来源匹配 | 21/21 | 21/21 |
| 原版Cart创建与重复GET实例来源匹配 | 2/2 | 2/2 |
| 原应用调用控制 | 26已知匹配、8预期unknown、2根异常 | 同左 |
| 原构造器/静态/字符串控制 | 18已知匹配、12预期unknown、2根异常 | 同左 |

混合控制使用原Spring拦截器及真实线程池/FutureTask，含同值不同对象、两个任务、重复get、工作抛异常后正常调用、超时后再次get、未执行任务取消和提交拒绝后正常调用。它验证协议，不是15个来源答案的准确率。当前未验证运行中取消、任意调度竞争或自定义Executor/Future。

四份实际Orders捕获另各做8项身份、Frame、内外Future、get记录及类哈希扰动拒绝。旧301个目标在原捕获上复算保持213正确、88unknown；这是旧证据离线兼容，不是新Agent对原213目标的新部署验收。

Station/Route八次、TicketInfo六次、Cart两次，加Orders四次，共20个已观测业务配置。正确性部署在独立端口/数据卷上部分并行，不能据运行时间评价性能。没有用旧成本数据评价新开关。

## 首次失败和工件

保留三次开发尝试：测试root包含不支持的静态写，后将测试准备移出root而未扩展指令；测试运行classpath误含旧Observer工具，移除运行期旧工具路径；检查器误把断言式`same_value`的None返回当布尔值，改为明确身份及基本类型核验。原编译产物和失败捕获没有覆盖。最终混合控制为`semantics-final-02/`。

原始根目录：`artifacts/async-protocol-revision-20261021/`。包括协议/冻结及源码包、两个JDK无网络探针、原版JAR、部署命令、镜像digest/限制、同输入记录、原事件、独立真值、unknown预测、失败、逐节点日志和清理记录。`audit-final/`保留首次审计；`audit-final-v2/`补关系计数并在新派生目录复算，不覆盖原始捕获。

关键审计输出为`task-receipts.json`、`business-mutations.json`、`orders-instances.json`及`raw-sha256.json`。小型[结果快照](async-protocol-results-20261021.json)随Git保存。

```bash
python3 experiments/sockshop-mirrortaint/audit_async_protocol_revision.py \
  --root artifacts/async-protocol-revision-20261021 \
  --out artifacts/async-protocol-revision-20261021/audit-recheck-new-directory
```

备份入口：`artifacts/async-protocol-backup-20261021/START-HERE.txt`。完整工件不随Git同步；同盘副本不含Docker镜像层，迁移仍需在新目录重新构建。所有push由用户完成。

下一步接入工作Frame依赖与Future结果传递，再按有限解码契约连接实际写入content的字段，并处理必要保存效果。不能通过把Future结果快照注册为来源、统一宣告save只读，或放宽损坏证据检查来消除unknown。整体至少382/431的联合条件，仍须同一个新冻结版本重新部署全部62查询的full/selective后验证。
