# 第三轮 A→B：采集与独立复核

协议与实现范围见 [PROTOCOL-ROUND-THREE.md](PROTOCOL-ROUND-THREE.md)、[HTTP-EXCHANGE-HISTORY.md](../sockshop-mirrortaint/HTTP-EXCHANGE-HISTORY.md)。只推进顺序进程内缓存，不运行 CVE。Cache、第一轮 workload 和前两轮预期、结果不改。新增普通 HTTP 适配器采用每 RPC 一个阻塞 Socket、HTTP/1.1 close，B 为 JDK HttpServer；这不表示原 HttpURLConnection／任意框架已支持。

完整入口（输出目录必须不存在），使用原来获准的 8u504、原 ASM/Jackson 依赖和原版 MirrorTaint JAR：

```bash
python3 experiments/cross-request-lineage/round_three.py \
  --out artifacts/cross-request-lineage-round-three-new --repeats 2
```

所有 plain 先运行，再 TF、MirrorTaint A-only 在线原生 API、MirrorTaint＋披露局部接口标识／论文式离线组合。每组两 JVM、单工作线程、连续不同请求。新增同 trace 校准单列。先封存预期、源码与计划，保留异常／unknown；再离线预测、独立评分和合成缺证测试。无缓存初始态缺少 Cache.cell@0 初始化证明的四个 unknown 不进入 known 正例负测分母。

不启动业务 JVM 的复算：

```bash
python3 experiments/cross-request-lineage/replay_round_three.py \
  --run artifacts/cross-request-lineage-round-three-new \
  --out artifacts/cross-request-lineage-round-three-replay-new
python3 experiments/cross-request-lineage/score_round_three.py \
  --run artifacts/cross-request-lineage-round-three-new \
  --predictions artifacts/cross-request-lineage-round-three-replay-new \
  --out artifacts/cross-request-lineage-round-three-score-new
python3 experiments/cross-request-lineage/check_round_three.py \
  --run artifacts/cross-request-lineage-round-three-new \
  --predictions artifacts/cross-request-lineage-round-three-replay-new \
  --scores artifacts/cross-request-lineage-round-three-score-new \
  --out artifacts/cross-request-lineage-round-three-negatives-new
python3 experiments/cross-request-lineage/audit_round_three.py \
  --run artifacts/cross-request-lineage-round-three-new \
  --predictions artifacts/cross-request-lineage-round-three-replay-new \
  --scores artifacts/cross-request-lineage-round-three-score-new \
  --negatives artifacts/cross-request-lineage-round-three-negatives-new \
  --out artifacts/cross-request-lineage-round-three-audit-new
```

最后的完整交付审计固定核验本轮两重复的 224 项义务，还检查运行时、二进制、源码和计划；精简审查包只用于前三项离线复算。预测进程的文件审计钩子禁止 expected* 与 workload，不导入评分器。同值错字段包装单列由独立预期检出。负例原序列损坏与合成重新编号分开；不改原始事件，不统计 unknown→unknown。

旧 170 项与新增 18 项通信核验测试：

```bash
PYTHONPATH=experiments/sockshop-mirrortaint python3 -m unittest \
  test_control_dependencies test_call_write_effects test_application_call_status \
  test_jvm_semantic_rules test_http_instance_sources test_response_binding \
  test_exception_completion test_exception_dispatch test_field_value_protocol \
  test_method_value_protocol test_identity_lifecycle_protocol \
  test_session_field_history test_http_exchange_protocol -v
```

direct-B 的无 JVM 回归命令仍见 [第二轮 README](README-ROUND-TWO.md)，第一轮用 `replay_round_one_current.py --out 新目录` 保留明确 current-core 审计。第一轮缺失写入仍不能补造。

为了审查时不依赖本机 artifacts，Git 中另带两个逐字节保真的精简原始包：

- [第二轮原始离线输入](evidence-round-two-review/offline-review.tar.gz)：足够重新得到 32 检查点及 90 缺证／身份义务＋2 错标签。
- [第三轮原始离线输入](evidence-round-three-review/offline-review.tar.gz)：足够重新得到 40 检查点和 224 缺证／身份／字段义务＋2 错标签。

两个目录的 `receipt.json` 与 `files.sha256.json` 记录原始位置、归档 SHA、逐文件 SHA 和排除项。它们不包含 Agent/JDK/依赖二进制，也不替代完整原始归档。解包到**新目录**后，`capture/` 可直接作为上述 `--run`，选择对应轮的 replay/score/check 脚本；独立核验包内文件：

```bash
mkdir artifacts/review-three-new
tar -xzf experiments/cross-request-lineage/evidence-round-three-review/offline-review.tar.gz \
  -C artifacts/review-three-new
python3 - <<'PY'
import hashlib, json
from pathlib import Path
p = Path('artifacts/review-three-new')
for name, digest in json.loads((p/'files.sha256.json').read_text()).items():
    assert hashlib.sha256((p/name).read_bytes()).hexdigest() == digest, name
print('All raw bytes verified')
PY
```

完整本机原始归档可用既有 `package_round_two.py --out 新目录 --include 第三轮目录 ...`（显式指定每个目录）封包，或查第三轮结果 JSON 的最终 delivery receipt。保留源码、全部首次失败和中间收据。
