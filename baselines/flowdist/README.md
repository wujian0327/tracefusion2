# FlowDist＋披露适配器

作者仓库：[wsucailab/flowdist](https://bitbucket.org/wsucailab/flowdist)，固定提交
`9a683606aa42289e045cdbfa9391b55e79a3ac05`。
`tool/FLOWDIST.jar`及`tool/soot-trunk.jar`的SHA见[版本锁](../tools.lock.json)。
获取时保留Git元数据，核对提交及工作树，保持原工具JAR不变。

```bash
python3 baselines/manage.py fetch --tool flowdist
python3 baselines/manage.py doctor --tool flowdist
```

作者提交和GitHub镜像提交不是同一个SHA；默认使用作者Bitbucket源，不静默切换版本。
网络受限时使用`fetch --tool flowdist --from /保留.git的旧缓存`，仍需通过提交及JAR检查。

## 原生示例兼容性入口

先准备公共Java8固定镜像。以下调用原作者Thrift业务与方法分析，所有输出使用同一个
新的工作目录，不修改作者源码或JAR：

```bash
python3 experiments/sockshop-mirrortaint/flowdist_preflight.py prepare \
  --repo artifacts/external-tools/flowdist --out artifacts/baseline-flowdist-thrift
python3 experiments/sockshop-mirrortaint/flowdist_preflight.py source-sink \
  --repo artifacts/external-tools/flowdist --out artifacts/baseline-flowdist-thrift
python3 experiments/sockshop-mirrortaint/flowdist_preflight.py scope \
  --repo artifacts/external-tools/flowdist --out artifacts/baseline-flowdist-thrift
python3 experiments/sockshop-mirrortaint/flowdist_preflight.py instrument \
  --repo artifacts/external-tools/flowdist --out artifacts/baseline-flowdist-thrift
python3 experiments/sockshop-mirrortaint/flowdist_preflight.py runtime \
  --repo artifacts/external-tools/flowdist --out artifacts/baseline-flowdist-thrift
python3 experiments/sockshop-mirrortaint/flowdist_preflight.py method-analysis \
  --repo artifacts/external-tools/flowdist --out artifacts/baseline-flowdist-thrift
```

这是工具兼容性检查。默认边界可能产生客户端本地路径，不能把一次业务成功或
方法候选列表报告成已验证的跨进程字段路径。

## 本仓库Sock Shop配置

入口、构建器和审计代码在`experiments/sockshop-mirrortaint/`：

- `build_flowdist_spring_apps.py`、`flowdist_service_static.py`：Spring边界与静态构件。
- `build_flowdist_branch_adapter.py`、`flowdist_service_methods.py`：实际执行方法/分支观察。
- `build_flowdist_resumptions.py`、`build_flowdist_field_launcher.py`：正常返回与原生查询入口。
- `flowdist/FlowDistHttpClock.java`、`FlowDistSpringHooks.java`、`FlowDistStreamModel.java`：
  披露的通信及顺序Stream模型。
- `compare_two_grains.py`、`compare_flowdist_total_queries.py`：历史共同端点与评分。

原作者查询引擎和all-query builder仍参与推断；不把TraceFusion的答案或独立真值
喂给FlowDist，也不将适配器的模型扩展隐去。当前五方法结果是11个聚合语句关系
TP6/FP0/FN0/TN5；旧跨服务金额结果采用聚合来源类型口径，不等同于W3C字段实例主表。

完整五方法复现还需业务原件、静态ServiceGraph、方法/分支映射、实际捕获、launcher
和Stream模型。历史评分器中固定输入的路径是可见的，但这些大型工件不在Git内。
具体阶段、命令及曾经失败的版本见[实验记录](../../experiments/sockshop-mirrortaint/README.md)，
最终检查点见[两口径摘要](../../experiments/sockshop-mirrortaint/two-grain-comparison-20261014.json)。
单独获取工具后不能直接重放旧结果；可迁移旧工件后验哈希，或按已有构建器重建并
重新冻结端点和评分。最新Orders.total逐实例共同成本表中的FlowDist保持N/A。
