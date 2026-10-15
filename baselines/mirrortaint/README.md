# MirrorTaint＋披露适配器

上游：[MirrorTaint/MirrorTaint](https://github.com/MirrorTaint/MirrorTaint)，固定提交
`54fcbfc5bb3a0d7cd30309098355d999553a861b`，原始文件`mirrorTaint.jar`。
公开构件不包含完整传播核心源码，因此直接获取作者JAR；不将本仓库适配器称为其源码。
文件SHA见[版本锁](../tools.lock.json)。

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

```bash
python3 experiments/sockshop-mirrortaint/run_sockshop_cost.py run \
  --out artifacts/baseline-common-cost --build artifacts/baseline-field-build \
  --correctness artifacts/baseline-field-run --query-scope total \
  --modes original tracefusion mirrortaint --rounds 5 --warmup 30 --seconds 60 \
  --rate 2 --concurrency 2 --cpus 1 --memory 768m \
  --mt-bundle artifacts/baseline-mt-build \
  --mt-calibration artifacts/baseline-mt-calibration \
  --tf-calibration artifacts/baseline-tf-calibration
```

当前Item、Shipment、Train Ticket的MirrorTaint实例查询没有共同成本校准，保持N/A。
日志、诊断产物和适配器计入测量；批次答案等待时间不是流式延迟。共同查询成本优势
不自动归因于少采，事件格式、标签历史及计算位置等仍需要消融区分。
