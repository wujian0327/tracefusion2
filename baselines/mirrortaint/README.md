# MirrorTaint＋披露适配器

2026-10-20已新增[62查询同任务能力对照](../../experiments/sockshop-mirrortaint/BASELINE-CAPABILITY-20261020.md)。
这是覆盖全部已测候选的实例来源评估，包含TF拒绝与unknown，不能只引用共同成功子集。
含Cart创建补充输入时，已发现169个“该基线配置正确、TF未答”目标；保守排除空标签后仍有145个。
本轮包含新的源标记、原生collector输出及实例绑定适配，不测成本；下文旧total成本配置保持历史口径。

上游：[MirrorTaint/MirrorTaint](https://github.com/MirrorTaint/MirrorTaint)，固定提交
`54fcbfc5bb3a0d7cd30309098355d999553a861b`，原始文件`mirrorTaint.jar`。
公开构件不包含完整传播核心源码，因此直接获取作者JAR；不将本仓库适配器称为其源码。
文件SHA见[版本锁](../tools.lock.json)。

最新诊断关闭及来源标识导出复核见
[当前汇总](../../experiments/sockshop-mirrortaint/FAIRNESS-EXPANSION-20261015.md)。
下面的默认配置成本是对应冻结版本的历史结果；不能当作调优后最低成本。

```bash
python3 baselines/manage.py fetch --tool mirrortaint
python3 baselines/manage.py doctor --tool mirrortaint
```

按[公共准备](../README.md)获取镜像、原业务JAR和ASM/Jackson，完成字段构建及两应用
验收后，使用同一组冻结输入校准共同查询：

```bash
python3 experiments/sockshop-mirrortaint/mirrortaint_instances.py build \
  --agent artifacts/external-tools/mirrortaint/mirrorTaint.jar \
  --build artifacts/baseline-field-build --out artifacts/baseline-mt-build
python3 experiments/sockshop-mirrortaint/calibrate_mirrortaint_total.py \
  --mode mirrortaint --out artifacts/baseline-mt-calibration \
  --build artifacts/baseline-field-build --bundle artifacts/baseline-mt-build \
  --correctness artifacts/baseline-field-run
python3 experiments/sockshop-mirrortaint/calibrate_mirrortaint_total.py \
  --mode tracefusion --out artifacts/baseline-tf-calibration \
  --build artifacts/baseline-field-build --bundle artifacts/baseline-mt-build \
  --correctness artifacts/baseline-field-run
```

共同任务：Carts本次实际序列化响应的quantity/unitPrice字段→Orders.total。
来源按具体HTTP调用、JSON pointer、对象、声明字段和应用写计数区分；不按相同值连接。
既有校准包括双方24/24、空总额、无目标、同trace不同span、8路并发，以及临时证据的
过期版本、错误对象、缺失来源检查。新机器/新构件必须重新校准。

适配器原件在`experiments/sockshop-mirrortaint/`：`MirrorTaint*Adapter.java`、
`CommonHttpInstanceAgent.java`、`build_integration_adapter.py`、`mirrortaint_instances.py`。
它们承担兼容、来源配置、库/顺序Stream、异步状态、日志和W3C消息字段关联。
原作者JAR哈希保持，但运行时插桩和模型确有扩展，结果名称必须保留“＋披露适配器”。
具体分工见[台式机说明](../../experiments/sockshop-mirrortaint/DESKTOP-HANDOFF.md)。

校准通过后才运行原版、TraceFusion、MirrorTaint三配置的五轮成本：

以下运行要求[公共准备](../README.md)中的当前验收回执及匹配构件的重新校准。
它不依赖旧迁移对照的核心源码不变前提。

```bash
python3 experiments/sockshop-mirrortaint/run_sockshop_cost.py run \
  --out artifacts/baseline-common-cost --build artifacts/baseline-field-build \
  --correctness artifacts/baseline-field-run --query-scope total \
  --acceptance artifacts/baseline-field-acceptance \
  --modes original tracefusion mirrortaint --rounds 5 --warmup 30 --seconds 60 \
  --rate 2 --concurrency 2 --cpus 1 --memory 768m \
  --mt-bundle artifacts/baseline-mt-build \
  --mt-calibration artifacts/baseline-mt-calibration \
  --tf-calibration artifacts/baseline-tf-calibration
```

当前Item、Shipment、Train Ticket的MirrorTaint实例查询没有共同成本校准，保持N/A。
日志、诊断产物和适配器计入测量；批次答案等待时间不是流式延迟。

## 已完成的共同查询成本与消融

共同成本测量代码为`2853a59`，结果见
[版本化摘要](../../experiments/sockshop-mirrortaint/mirrortaint-total-cost-20261015.json)，
本机原始报告为`artifacts/common-total-cost-formal-20261015/results.md`。
两种观测配置均为900/900个查询完全匹配、TP3750、FP/FN/目标unknown均为0。
固定2请求/秒、五轮独立部署下，各轮指标中位数为：

| 指标 | TraceFusion自动选择性观测 | MirrorTaint＋披露适配器 |
| --- | ---: | ---: |
| 在线p95延迟（ms） | 18.520 | 107.228 |
| 三个业务JVM的CPU（单核百分比之和） | 8.258 | 22.375 |
| 稳态请求对应采集事件数 | 5298 | 5280 |
| 稳态请求对应采集字节 | 4,042,178 | 69,756,296 |
| 离线还原/评分/导出（秒） | 0.621 | 0.917 |

这些数值限定于冻结查询、输入、机器和配置；完成相同固定负载不代表最大吞吐相同。
MirrorTaint的默认原生诊断输出计入成本，没有验证其最低开销调优配置。
两者事件格式不同且事件数接近，不能将这张表的成本差异解释为少采事件的收益。

另已完成同采集器、同JSONL格式、同离线还原器的
[严格观测消融](../../experiments/sockshop-mirrortaint/observation-ablation-20261015.json)，
测量代码为`5836f0a`，本机报告为`artifacts/observation-ablation-formal-20261015/results.md`。
full与selective均900/900完全匹配；按同轮比值的中位数，selective的事件减少80.37%、
采集字节减少63.03%、离线进程墙时减少66.91%、离线峰值内存减少54.61%，
但在线CPU增加8.36%。full限于已纳入应用类、冻结查询帧内的实例字段读写和条件跳转。
boundary仅保留HTTP/JSON及DTO写计数，900个查询全部unknown，不能作为同准确率方案。
该消融支持选择性观测的采集和离线收益，仍不能分解MirrorTaint的事件格式、
标签历史、适配器和计算位置对跨工具差距的各自贡献。

## 可选的来源标识/查询目标导出配置

公开JAR的配置/日志类检查未发现原生诊断关闭属性。`QuietDiagnosticAgent`是单独
披露的运行时适配器，只关闭三个agent-info方法，保留专用错误通道及原生传播。
`--source-ids-only`另将导出标签投影为原生来源标识，保留所有RPC候选来源字段，
sink仅导出声明的查询目标。没有输入预期来源列表，内部传播和历史构造不变。
它不输出完整内部传播历史；原对象扫描仍执行，不称最低开销实现。

完成公共准备和当前验收后，用新目录重新构建、校准；不得沿用默认配置的旧回执：

```bash
python3 experiments/sockshop-mirrortaint/build_quiet_mirrortaint.py \
  --agent artifacts/external-tools/mirrortaint/mirrorTaint.jar \
  --build artifacts/baseline-field-build --out artifacts/baseline-mt-sourceids-build \
  --source-ids-only
python3 experiments/sockshop-mirrortaint/calibrate_mirrortaint_total.py \
  --mode mirrortaint --build artifacts/baseline-field-build \
  --bundle artifacts/baseline-mt-sourceids-build --correctness artifacts/baseline-field-run \
  --out artifacts/baseline-mt-sourceids-calibration
python3 experiments/sockshop-mirrortaint/calibrate_mirrortaint_total.py \
  --mode tracefusion --build artifacts/baseline-field-build \
  --bundle artifacts/baseline-mt-sourceids-build --correctness artifacts/baseline-field-run \
  --out artifacts/baseline-tf-sourceids-calibration
python3 experiments/sockshop-mirrortaint/run_sockshop_cost.py run \
  --out artifacts/baseline-sourceids-cost --build artifacts/baseline-field-build \
  --correctness artifacts/baseline-field-run --acceptance artifacts/baseline-field-acceptance \
  --query-scope total --modes mirrortaint tracefusion \
  --mt-bundle artifacts/baseline-mt-sourceids-build \
  --mt-calibration artifacts/baseline-mt-sourceids-calibration \
  --tf-calibration artifacts/baseline-tf-sourceids-calibration \
  --rounds 5 --warmup 30 --seconds 60 --rate 2 --concurrency 2 \
  --cpus 1 --memory 768m --sample-interval 2 --seed 151061
```

本入口仍只校准当前Orders.total来源集合与实例坐标查询，其他任务保持N/A。
原来boundary策略的unknown只说明其与原还原器的组合；完整边界重放在额外契约下
可恢复同批答案，见汇总中的条件性检查，不能声称任何边界方法都不够。
