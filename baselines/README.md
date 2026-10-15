# 对比算法与复现入口

这里统一管理本仓库使用的外部基线：**MirrorTaint、Phosphor、FlowDist**。
固定上游版本、校验工具文件、获取依赖，并链接本仓库的适配器和实验入口。
所有命令均在仓库根目录执行，默认在`main`工作。

当前公平性复核及更精简输出配置的比较见
[2026-10-15至16报告](../experiments/sockshop-mirrortaint/FAIRNESS-EXPANSION-20261015.md)。
默认诊断、quiet、来源标识导出属于分别披露的配置，不能拼接各块绝对开销。

| 工具 | 固定版本 | 已有比较及范围 | 具体说明 |
| --- | --- | --- | --- |
| MirrorTaint＋披露适配器 | `54fcbfc5bb3a0d7cd30309098355d999553a861b`公开JAR | 已校准Carts实际响应字段→Orders.total，并完成共同查询五轮成本比较 | [说明](mirrortaint/README.md) |
| Phosphor＋来源/采集适配器 | 官方`Phosphor-0.0.4`，`6c15c9b2bb609b790cacfc9297d9f18724dcb1d6` | 五方法的11个聚合语句关系；未校准最新跨服务字段实例成本任务 | [说明](phosphor/README.md) |
| FlowDist＋披露适配器 | 作者Bitbucket仓库`9a683606aa42289e045cdbfa9391b55e79a3ac05` | 五方法的11个聚合语句关系，另有披露HTTP/Stream模型的跨服务补充实验；未校准最新共同字段实例成本任务 | [说明](flowdist/README.md) |

`doctor`通过仅说明固定工具文件完整；编译/JRE启动通过也不等于业务或准确性校准。
字段实例、聚合语句关系和不同来源边界的结果分别报告；未校准配置保持N/A。

## 目录与Git边界

```text
baselines/
  manage.py                  获取、校验、构建及应用原件准备
  tools.lock.json            作者仓库、固定版本与工具SHA-256
  build-deps.lock.json       ASM/Jackson构建依赖的地址与SHA-256
  images.lock.json           14个固定镜像的digest和image ID
  apps.lock.json             六个原版业务JAR的镜像位置与SHA-256
  queries.json               从原版JAR生成字段计划的查询配置
  mirrortaint/README.md
  phosphor/README.md
  phosphor/source-hashes.json 固定归档中的上游文件哈希
  flowdist/README.md
```

本仓库自己的适配器仍在`experiments/sockshop-mirrortaint/`，以免移动文件破坏既有
实验和冻结来源记录。这里引用同一份代码，不复制算法实现。

Git保存上述入口、锁文件、适配器、测试和结果摘要。上游源码副本、JAR、插桩JRE、
构建结果和原始事件保存在被忽略的`artifacts/`；clone后由下面的命令重新准备。
下载内容仍属上游项目，来源和版权信息沿用上游；本仓库不把外部工具声明为自身算法。
要重放某一次历史采集，还需那一次的原始工件；结果摘要里的SHA不是日志本体。

## clone后的公共准备

环境：Linux/WSL2，Python 3标准库、Git、完整JDK（含javac/javap）、Docker和
Compose v2；从源码构建Phosphor另需Maven。历史入口验证机使用JDK 21；新主实验机
使用JDK 8完成字段构建、成本与Log4j复现。部分历史Phosphor/FlowDist脚本仍使用
`--release 8`，完整执行这些脚本需宿主JDK 9以上。
服务仍用镜像里的Java8；Phosphor核心编译固定调用原版镜像里的javac8。

```bash
python3 baselines/manage.py fetch --tool all
python3 baselines/manage.py deps

# 拉取清单中的固定镜像，处理终端代理但daemon未配置代理的环境。
python3 experiments/sockshop-mirrortaint/prepare_pinned_images.py \
  --manifest baselines/images.lock.json --out artifacts/baseline-images

# 只读提取原版JAR：创建不启动的临时容器，核验JAR后删除临时容器。
python3 baselines/manage.py apps
python3 baselines/manage.py build-phosphor
python3 baselines/manage.py build-jre --out artifacts/baseline-phosphor-jre
python3 baselines/manage.py smoke-phosphor \
  --jre artifacts/baseline-phosphor-jre/jre --out artifacts/baseline-phosphor-smoke
python3 baselines/manage.py doctor
```

也可自行按`images.lock.json`执行`docker pull --platform linux/amd64 <digest引用>`。
`prepare_pinned_images.py`需要能访问镜像仓库；版本锁定不代表无需网络。

默认工具缓存：

- `artifacts/external-tools/mirrortaint/mirrorTaint.jar`
- `artifacts/external-tools/flowdist/`，保留`.git`以验证作者提交。
- `artifacts/external-tools/phosphor-0.0.4/`，包含原版源码、构建日志、JAR及本机manifest。

缓存地址可用`python3 baselines/manage.py --cache /绝对路径 ...`更改，后续实验
也要显式传入相同路径。已存在的文件先校验，不覆盖不匹配缓存；新构建JAR的ZIP
时间戳可能不同，记录实际哈希并重新校准，不冒充历史二进制。

网络受限时，可复制原机器的工具缓存，或先导入经过校验的单个工具目录：

```bash
python3 baselines/manage.py --cache artifacts/imported-tools fetch \
  --tool phosphor --from /复制来的/phosphor-0.0.4
python3 baselines/manage.py --cache artifacts/imported-tools fetch \
  --tool flowdist --from /复制来的/flowdist
```

FlowDist导入目录须保留`.git`；Phosphor的插桩JRE是单独工件，不能只复制其源码。
首次构建需要Maven插件及依赖；可用`build-phosphor --maven-repo /已复制的/m2`复用缓存。

## 新运行的字段实验，不依赖旧电脑目录

完成公共准备后，生成新机器自己的绝对路径和冻结计划：

```bash
python3 experiments/sockshop-mirrortaint/build_distributed_plans.py \
  --inputs baselines/queries.json --out artifacts/baseline-field-build
python3 experiments/sockshop-mirrortaint/run_distributed_paths.py freeze \
  --build artifacts/baseline-field-build --out artifacts/baseline-field-run --seed 151031
python3 experiments/sockshop-mirrortaint/run_distributed_paths.py sockshop \
  --build artifacts/baseline-field-build --out artifacts/baseline-field-run
python3 experiments/sockshop-mirrortaint/run_distributed_paths.py trainticket \
  --build artifacts/baseline-field-build --out artifacts/baseline-field-run
python3 experiments/sockshop-mirrortaint/evaluate_distributed_paths.py \
  --build artifacts/baseline-field-build --out artifacts/baseline-field-run
python3 experiments/sockshop-mirrortaint/audit_distributed_paths.py \
  --build artifacts/baseline-field-build --out artifacts/baseline-field-run
python3 experiments/sockshop-mirrortaint/check_w3c_protocol.py \
  --build artifacts/baseline-field-build --out artifacts/baseline-field-run
python3 experiments/sockshop-mirrortaint/verify_original_path_images.py \
  --build artifacts/baseline-field-build --out artifacts/baseline-field-run
```

这部分完成TraceFusion两应用的评分、算法审计、协议测试和原镜像JAR校验。
继续生成当前版本的验收回执（在副本上重评分、重审计、检查实际wire及镜像）：

```bash
python3 experiments/sockshop-mirrortaint/audit_current_acceptance.py \
  --build artifacts/baseline-field-build --correctness artifacts/baseline-field-run \
  --out artifacts/baseline-field-acceptance
```

成本运行显式传入`--acceptance artifacts/baseline-field-acceptance`，回执绑定当前
构建、原始捕获、审计源码和审计证据，变化后必须重新验收。它不要求旧电脑捕获，
也不声称本地核心源码未改变。未指定此参数的旧调用仍要求历史`w3c-comparison.json`；
`compare_w3c_paths.py`保留源码不变条件，不能复制旧回执或伪造迁移对照通过。
当前种子和业务注册表下，参考结果为Sock Shop 198/198、Train Ticket 31/31。
运行使用回环端口18580–18583、18600–18602及10.254.249.0/24子网，两应用顺序运行。
已有输出目录保留为证据，重跑应更换目录名。只清理本次随机部署项目，不清理其他项目。

## 实验报告入口

- [最新共同字段查询成本摘要](../experiments/sockshop-mirrortaint/mirrortaint-total-cost-20261015.json)
- [同格式、同还原器的严格观测消融](../experiments/sockshop-mirrortaint/observation-ablation-20261015.json)
- [五方法、字段与语句两种口径摘要](../experiments/sockshop-mirrortaint/two-grain-comparison-20261014.json)
- [完整实验记录及历次适配说明](../experiments/sockshop-mirrortaint/README.md)
- [台式机迁移与已有正式成本命令](../experiments/sockshop-mirrortaint/DESKTOP-HANDOFF.md)

当前固定2请求/秒的正式成本与高负载容量实验不同；高负载扫描已按用户要求停止，
此入口不自动继续扫描。工具下载/构建和原生自检也不重新计为正式准确率或性能结果。

开发检查：`python3 -m unittest discover -s baselines -p 'test_*.py' -v`。

本轮[入口验证摘要](validation-20261015.json)：三套工具的官方获取及校验、6项完整性
测试、Phosphor源码重建/JRE启动/原生标签样例、六个镜像JAR提取均通过；干净源码
目录中重新获取依赖、生成六服务计划/冻结输入和编译作者Thrift示例也通过。
这轮未重新运行完整业务或正式成本实验；相关历史准确性仍引用各自原始证据。
该摘要的源码哈希对应入口验证当时的文件，保留为历史记录；本次补充结果和复现限制
没有重写该回执，也不代表重新完成新clone的整套成本运行。
