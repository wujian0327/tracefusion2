# 台式机接续实验

当前已完成W3C通信关联替换：Sock Shop 198/198、Train Ticket 31/31个指定字段查询
完全匹配，TP分别258/30、FP和FN为0。代码基线为`0bb0e92`；本文件所在提交补充
迁移工具与跨目录路径处理，不改变采集器或字段还原算法。结果不代表全应用准确率。

## 迁移包

本机生成目录`artifacts/desktop-handoff-20261015/`，把整个目录复制到台式机。

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
git clone -b perf/payment-steady-state tracefusion2.bundle tracefusion2
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

当前上述脚本是正确性复现，**正式成本测试驱动尚未实现**，重复运行它不能直接
当作稳定负载的吞吐/延迟实验。台式机复现通过后，下一项编码任务是专门的成本驱动。

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
