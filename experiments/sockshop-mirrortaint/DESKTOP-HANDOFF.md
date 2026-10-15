# 台式机接续实验

## 当前主实验机与历史快照

新电脑已实际通过部署、两应用正确性校准及共同查询五轮成本比较，作为后续主实验机。
后续以新电脑工作区的最新 `main` 为准，直接在 `main` 开发和提交。2026-10-15已核对
远端与本地 `bb8d068` 一致，包含共同查询校准、成本驱动及结果摘要；下一次改动仍需
提交并核对推送，不能把这个确认当作未来提交也已同步。

完整共同查询证据和旧版成本报告已另行归档于
`artifacts/mirrortaint-handoff-20261015/`：Git bundle、冻结输入包、实验工件包及
逐文件SHA-256清单。工件包51,253个文件已校验，保留原始事件/日志、逐请求独立
真值、输入/计划、构建、镜像digest、机器配置和逐轮数据。`artifacts/`不随Git同步，
需将整个归档目录另存备份；同盘归档不能替代独立介质备份。

此前旧电脑生成的 `desktop-handoff-main-20261015` 等包均为历史快照，不作为后续
更新源。旧机只保留代码和证据备份；不同机器的绝对成本分开报告。本文件下方旧迁移
步骤仅供重建历史环境时参考。当前阶段优先严格观测消融，不自动续跑已取消的高负载扫描。

当前已完成W3C通信关联替换：Sock Shop 198/198、Train Ticket 31/31个指定字段查询
完全匹配，TP分别258/30、FP和FN为0。代码基线为`0bb0e92`；本文件所在提交补充
迁移工具与跨目录路径处理，不改变采集器或字段还原算法。结果不代表全应用准确率。

## 迁移包

本机生成目录`artifacts/desktop-handoff-main-20261015/`，把整个目录复制到台式机。
当前及后续工作分支为`main`；早期`desktop-handoff-20261015`包记录的是旧工作分支。

- `tracefusion2.bundle`：当前已提交分支及其历史，可直接clone，不依赖远端已更新。
- `experiment-inputs.tar.gz`：六个原版JAR、五个构建依赖、当前构建/证据、旧基线的
  案例/评分结果/计划及镜像清单。只含本轮必要数据，不是整个artifacts目录。
- `handoff.json`：提交、包SHA-256与大小；`START-HERE.txt`：入口命令。
- Docker镜像没有放进包里：运行时按清单中的digest拉取。MirrorTaint等外部工具的
  旧构建与完整成本实验环境也没有包含，不能据此声称已能跑所有外部基线。

本机重新生成包：

```bash
python3 experiments/sockshop-mirrortaint/prepare_desktop_handoff.py \
  --out artifacts/desktop-handoff-new
```

台式机在包目录操作：

```bash
git clone -b main tracefusion2.bundle tracefusion2
cd tracefusion2
tar -xzf ../experiment-inputs.tar.gz
```

先验证输入文件：

```bash
python3 - <<'PY'
import hashlib,json
from pathlib import Path
manifest=json.loads(Path('artifacts/desktop-inputs/input-files.json').read_text())
for name,expected in manifest.items():
    assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==expected,name
print('输入校验通过：',len(manifest),'个文件')
PY
```

## 环境和镜像

使用Linux或WSL2内的Linux工作目录，Docker Engine/Docker Desktop及Compose v2、
Python 3、完整JDK（含java/javac/javap）。本机已验证Python 3.13.9、JDK 21，
采集器按Java 8字节码构建，服务使用原镜像里的JRE。Python执行路径只用标准库。

确认`docker version`、`docker compose version`、`java -version`、`javac -version`
正常。当前工作负载只绑定回环端口18580–18583、18600–18602；网络固定为
10.254.249.0/24。两应用顺序运行，确保这些端口/子网没有被其他服务占用。

拉取本轮已固定的镜像（不是latest）：

```bash
python3 - <<'PY'
import json,subprocess
from pathlib import Path
images=json.loads(Path('artifacts/desktop-inputs/images-lock.json').read_text())
for reference in images:
    subprocess.run(['docker','pull','--platform','linux/amd64',reference],check=True)
print('镜像就绪：',len(images))
PY
```

若台式机访问镜像仓库慢，可在源机器docker save、目标docker load搬运缓存层；
仍需确认digest引用和RepoDigests就绪。save/load不能被假定保留所有registry digest
元数据；现有运行器会拒绝缺少固定digest的镜像，不会自动改用未核验的同名标签。

若终端有 HTTPS 代理、Docker daemon 没有代理，可使用不重启 daemon 的准备工具：

```bash
python3 experiments/sockshop-mirrortaint/prepare_pinned_images.py \
  --out artifacts/desktop-proxy-images
```

工具通过终端代理获取固定 manifest/config/layer，逐项验证 SHA-256 和清单中的
image ID，再通过临时回环 registry 填充 Docker 层缓存，最后拉取原始引用并核验
原始 RepoDigests。临时 registry 退出时关闭；不改写镜像清单、不使用本地标签代替
digest。缓存、上游 manifest 和每个镜像的命令/验证结果保存在指定输出目录。
构建和协议测试同时支持完整 JDK 8（source/target 8）及 JDK 9+（release 8）。
镜像选择同时显式设置 `dns_search: ["."]`，避免宿主机搜索域被旧 Go 服务优先查询，
造成 User 到 MongoDB 的 `no reachable servers`；正确性和两种成本配置使用同一设置。
独立字节码审计识别 JDK 8 与新版 javap 的两种静态方法句柄显示格式。

## 第一步：重新构建并做正确性复现

旧构建包含源机器绝对路径和源码哈希；不要修改旧freeze/build文件绕过校验。
用包内原版JAR重新生成台式机自己的构建：

```bash
python3 experiments/sockshop-mirrortaint/build_distributed_plans.py \
  --out artifacts/desktop-w3c-build \
  --inputs artifacts/desktop-inputs/queries-portable.json

python3 experiments/sockshop-mirrortaint/run_distributed_paths.py freeze \
  --out artifacts/desktop-w3c-run --build artifacts/desktop-w3c-build \
  --cases-from artifacts/distributed-paths-final-20261015 --seed 151031

python3 experiments/sockshop-mirrortaint/run_distributed_paths.py sockshop \
  --out artifacts/desktop-w3c-run --build artifacts/desktop-w3c-build

python3 experiments/sockshop-mirrortaint/run_distributed_paths.py trainticket \
  --out artifacts/desktop-w3c-run --build artifacts/desktop-w3c-build

python3 experiments/sockshop-mirrortaint/evaluate_distributed_paths.py \
  --out artifacts/desktop-w3c-run --build artifacts/desktop-w3c-build

python3 experiments/sockshop-mirrortaint/audit_distributed_paths.py \
  --out artifacts/desktop-w3c-run --build artifacts/desktop-w3c-build

python3 experiments/sockshop-mirrortaint/check_w3c_protocol.py \
  --out artifacts/desktop-w3c-run --build artifacts/desktop-w3c-build

python3 experiments/sockshop-mirrortaint/verify_original_path_images.py \
  --out artifacts/desktop-w3c-run --build artifacts/desktop-w3c-build

python3 experiments/sockshop-mirrortaint/compare_w3c_paths.py \
  --out artifacts/desktop-w3c-run --build artifacts/desktop-w3c-build \
  --baseline artifacts/distributed-paths-final-20261015 \
  --baseline-build artifacts/distributed-plans-final-build-20261015
```

验收：198/198和31/31、FP/FN为0、检查全部通过。结果在
`artifacts/desktop-w3c-run/results.md`。两个部署各有finally清理，只清理自己的
随机项目及测试卷；强制杀进程/断电可能跳过清理，应按run.json中的project处理。
需要再跑时换一个新的输出目录，不能覆盖已有冻结结果。

## 第二步：④正式成本比较

上述脚本是正确性复现，重复运行不能直接当作稳定负载的吞吐/延迟实验。
专用成本驱动为 `run_sockshop_cost.py`，必须先通过两应用的台式机复现、算法审计、
协议测试、原镜像 JAR 校验和 W3C 对照验收，不能用旧机器的成绩替代本机验收。

```bash
python3 -m unittest discover -s experiments/sockshop-mirrortaint \
  -p test_sockshop_cost.py -v

python3 experiments/sockshop-mirrortaint/run_sockshop_cost.py run \
  --out artifacts/sockshop-cost-new --build artifacts/desktop-w3c-build \
  --correctness artifacts/desktop-w3c-run \
  --rounds 5 --warmup 30 --seconds 60 --rate 2 --concurrency 2 \
  --cpus 1 --memory 768m --sample-interval 2 --seed 151031
```

每轮部署使用相同原版 JAR、JVM 参数及 11 个组件的资源限制，仅 TraceFusion
配置增加观测器/计划/采集目录。固定成功案例模板轮转；独立用户及购物车在预热前
准备，随机数据库 ID 不当作算法证据关联键。在线计时仅覆盖 POST /orders 的 HTTP
调用至响应体读完，另保存计划到达至响应的延迟及调度滞后；预热与准备请求不混入
稳态分位数。每轮每个目标请求均检查原业务输出，TraceFusion 对预热和稳态的全部
指定字段查询做实例级独立评分；unknown 和背景 unknown 原样保留。

报告分别给出稳态与总采集日志、各组件 CPU/RSS、离线图构建时间、还原/评分/导出
总时间及独立子进程峰值 RSS。答案延迟按整批答案写出时间计算，含等待当前批次
结束和采集器关闭，不代表流式增量查询。固定到达率下的吞吐不能解释为最大吞吐。
RSS 为容器进程 RSS 之和，不代表每请求分配，存在共享页重复计数。

输出 `results.md`、`comparison.json`、环境/配置/源码与输入哈希、每次原始请求、
采样、事件、答案、评分和清理结果。试验少于 5 轮不标记 performance_eligible；
失败的配置保留 N/A，不纳入有效轮次的数值。运行中不修改已冻结源码；重跑使用新
输出目录。重新汇总已有原始结果可使用 `run_sockshop_cost.py report --out ...`。

建议先固定Sock Shop的共同查询与工作负载：原版服务、TraceFusion自动选择观测、
MirrorTaint加已披露适配器。MirrorTaint需先确认共同查询能完成，不能把本轮新增
跨服务路径直接视为已接入的MirrorTaint能力，也不能混用旧开销表。

成本驱动需要：固定JVM/资源/输入；预热；每轮重新部署；随机配置顺序；从5轮起步
检查波动；固定并发/请求速率与稳态采样窗口；每轮核验业务和来源答案。此前暂缓的
“目标依赖范围完整观测”优化仍保持暂缓，不将它解释为已完成的算法消融。

输出：在线p50/p95/p99延迟、吞吐、CPU、服务RSS；事件数和日志字节；离线还原
耗时与峰值内存；请求完成到答案可用的延迟。分别报告各项成本，区分整进程RSS和
每请求分配。先完成Sock Shop，再扩展Train Ticket；Phosphor/FlowDist只在共同口径
和兼容性已确认的范围另测。未运行配置保留N/A，不复用旧百分比填表。

新机器的CPU、内存、磁盘、操作系统、Docker/JDK版本和资源限制要随结果保存。
不同机器的绝对耗时分开报告，在同一台机器内比较开销比例。

## MirrorTaint 同口径接续：Orders.total

`mirrortaint_instances.py` 使用固定公开 JAR（来源与 SHA-256 见 `sources.json`）
及明确披露的适配器。原版 JAR 可从固定提交的原始文件 URL 下载并按清单验哈希；
不以重新编译的替代核心或旧开销数字补齐结果。

共同边界为 **Carts 实际序列化响应中的字段到 Orders.total**。每次运行先独立按
服务、序号、JSON pointer、对象身份、字段及应用写计数评分，再跨运行比较逻辑字段。
不能要求不同 JVM 的对象 ID 相等，也不能按相同数值、整条 trace 或数据库记录 ID
合并来源。数据库/反射内部写历史不在此来源边界内。

| 层 | 承担的功能 |
| --- | --- |
| 固定 MirrorTaint JAR | 本地污点标签、算术/字段传播 |
| 既有兼容适配器 | 修复字段 receiver/构造处理、启用库规则、清理来源前空槽 |
| stream / thread 适配器 | 对实际 mapper 返回标签求顺序 sum；捕获异步状态并只合并返回对象可达标签 |
| 日志适配器 | 输出原生标签和有界对象图，补对象/字段/写计数及调用上下文 |
| CommonHttpInstanceAgent | 记录 W3C 具体调用、两端 JSON 属性、对象身份和应用写计数；不计算业务依赖 |
| 离线绑定 | 将原生标签解码到实际响应实例，再按同一调用 span 和 JSON pointer 绑定 Carts 发送端；缺证据保留 unknown |

MirrorTaint 原版 JAR 哈希不变，但运行时插桩、库、流、线程、来源前处理、日志及
通信绑定均有适配，配置名必须保留“MirrorTaint＋披露适配器”。本轮仅 Orders 装载
MirrorTaint 核心，Orders/Carts 装载边界探针；两侧 Shipping 均保持原版业务服务。
TraceFusion 使用同一原版 JAR 的冻结 Orders.total 计划及 Orders/Carts 观测器。
未校准的返回 Item、Shipment 和 Train Ticket 查询保持 N/A。

构建与真实校准（每次使用新的输出目录）：

```bash
python3 experiments/sockshop-mirrortaint/mirrortaint_instances.py build \
  --agent artifacts/external-tools/mirrortaint/mirrorTaint.jar \
  --build artifacts/desktop-portable-build --out artifacts/mt-instance-build-new

python3 experiments/sockshop-mirrortaint/calibrate_mirrortaint_total.py \
  --mode mirrortaint --out artifacts/mt-total-cal-new \
  --build artifacts/desktop-portable-build --bundle artifacts/mt-instance-build-new \
  --correctness artifacts/desktop-portable-acceptance

python3 experiments/sockshop-mirrortaint/calibrate_mirrortaint_total.py \
  --mode tracefusion --out artifacts/tf-total-cal-new \
  --build artifacts/desktop-portable-build --bundle artifacts/mt-instance-build-new \
  --correctness artifacts/desktop-portable-acceptance
```

校准覆盖同值记录、购物车更新、空总额、无目标检查、同 trace 不同 span 和8路并发。
实例审计另外修改临时证据，检查过期来源/目标版本、错误来源/目标对象、缺少远端
字段返回 unknown，以及错误具体调用 span 被拒绝。它不是任意共享对象/反射写入的
全程序版本证明。成本入口校验校准成绩、适配器/分析器/原应用/输入哈希，失配拒绝运行。

五轮成本入口沿用 `run_sockshop_cost.py run`，额外指定：

```bash
--query-scope total --modes original tracefusion mirrortaint \
--mt-bundle artifacts/mt-instance-build-new \
--mt-calibration artifacts/mt-total-cal-new --tf-calibration artifacts/tf-total-cal-new
```

当前优先交付固定2请求/秒、相同查询和资源配置的五轮成本比较；用户已明确无需
继续高负载实验。主报告为 `artifacts/common-total-cost-formal-20261015/results.md`，
可提交摘要为 `mirrortaint-total-cost-20261015.json`。测量代码固定于 `2853a59`；
测量后的修改仅补报告展示、扫描取消标记和默认参数类型修复，不重写原始指标。
后续不要自动继续扫描。已有部分数据保留在
`artifacts/common-total-load-scan-20261015/`，作为补充材料而非必要验收项。

如以后明确需要容量研究，可选工具为 `scan_sockshop_load.py`，传入相同的 build、correctness、bundle 和校准
路径，默认到达率2/4/8/16/32、预热10秒、稳态20秒、最大并发32。每点重新部署并随机
配置顺序。单点扫描不冒充五轮正式成本估计；成功吞吐、错误率、HTTP分位数、计划
到达至响应分位数、调度滞后及资源一起解释。采集/兼容性失败不是服务饱和的证明，
错误请求的来源答案为 N/A；原始在线数据仍保留。
