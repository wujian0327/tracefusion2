# 第二轮：direct-B 历史来源闭环

本轮定义见 [PROTOCOL-ROUND-TWO.md](PROTOCOL-ROUND-TWO.md)，协议实现见 [SESSION-FIELD-HISTORY.md](../sockshop-mirrortaint/SESSION-FIELD-HISTORY.md)，结果见 [RESULTS-ROUND-TWO-20261113.md](RESULTS-ROUND-TWO-20261113.md)。第一轮入口、workload、expected、报告和原始工件保持不变。本轮只启动 B，普通 Cache 业务源码不改。

仓库根目录运行新的完整入口，目录必须不存在：

```bash
python3 experiments/cross-request-lineage/round_two.py \
  --out artifacts/cross-request-round-two-new --repeats 2
```

它使用既有 8u504，先采 plain，再采新 TF Agent 和计划，最后采同粒度 MirrorTaint；每组内 JVM 持续处理所有请求。随后分别启动离线预测、独立评分及缺证／身份／错误来源包装检查。原始事件、请求／响应、状态、PID、命令、namespace、构件和计划哈希、预测及支持链都保存在新目录。`--capture-only` 可只采集并预测，不代替完整验收。

无需启动任何业务 JVM 的离线复算，预测进程禁止读取 expected 和 workload：

```bash
python3 experiments/cross-request-lineage/replay_round_two.py \
  --run artifacts/cross-request-round-two-new \
  --out artifacts/cross-request-round-two-replay-new
python3 experiments/cross-request-lineage/score_round_two.py \
  --run artifacts/cross-request-round-two-new \
  --predictions artifacts/cross-request-round-two-replay-new \
  --out artifacts/cross-request-round-two-score-new
python3 experiments/cross-request-lineage/check_round_two.py \
  --run artifacts/cross-request-round-two-new \
  --predictions artifacts/cross-request-round-two-replay-new \
  --scores artifacts/cross-request-round-two-score-new \
  --out artifacts/cross-request-round-two-negatives-new
python3 experiments/cross-request-lineage/audit_round_two.py \
  --run artifacts/cross-request-round-two-new \
  --predictions artifacts/cross-request-round-two-replay-new \
  --scores artifacts/cross-request-round-two-score-new \
  --negatives artifacts/cross-request-round-two-negatives-new \
  --out artifacts/cross-request-round-two-audit-new
```

最后一项审计按本轮六组、各两次重复的 90 项缺证／身份义务和两个错误包装义务核验。负例全部在标记为 synthetic 的副本中，删除事件的原始序号版本和重新编号／重算总事件数的版本分列；原始捕获不改。

旧单测和新增索引测试：

```bash
PYTHONPATH=experiments/sockshop-mirrortaint python3 -m unittest \
  test_control_dependencies test_call_write_effects test_application_call_status \
  test_jvm_semantic_rules test_http_instance_sources test_response_binding \
  test_exception_completion test_exception_dispatch test_field_value_protocol \
  test_method_value_protocol test_identity_lifecycle_protocol test_session_field_history -v
```

原方法／生命周期 147 项与新增 23 项共 170 项。更多旧捕获和真实 JVM 组件回归，均输出新目录：

```bash
python3 experiments/cross-request-lineage/replay_round_one_current.py \
  --out artifacts/cross-request-old-round-one-new
python3 experiments/sockshop-mirrortaint/audit_exception_completion.py \
  --current-core --out artifacts/cross-request-old-core-audit-new
python3 experiments/sockshop-mirrortaint/check_exception_completion_old_captures.py \
  --out artifacts/cross-request-old-business-new
python3 experiments/sockshop-mirrortaint/run_lifecycle_state_controls.py \
  --agent "$PWD/artifacts/cross-request-round-two-new/build/tf/distributed-observer.jar" \
  --out artifacts/cross-request-lifecycle-new
python3 experiments/sockshop-mirrortaint/run_method_observation_controls.py \
  --agent "$PWD/artifacts/cross-request-round-two-new/build/tf/distributed-observer.jar" \
  --out artifacts/cross-request-methods-new
env PATH="$PWD/artifacts/galette-static-baselines-20261111/runtime-base/java-8-openjdk-amd64/bin:$PATH" \
  python3 experiments/sockshop-mirrortaint/run_monitor_reliability_fixture.py \
  --build artifacts/cross-request-round-two-new/build/tf \
  --out artifacts/cross-request-monitor-new
```

环境依赖仍按第一轮 README 准备 ASM/Jackson、原版 MirrorTaint 和固定 8u504 安装。不改运行时或 native／构造许可。旧组件测试中的线程、Future、GC 控制仅复核既有退役行为，不代表本会话历史支持并发／异步。会话历史 v1 仅在显式计划、full、顺序根调用下启用；原 process 限制、A→B、存储服务、GC 复活和性能不在本轮范围。

本轮全部新目录的原始数据和源码快照可另行打包到新目录；会生成逐文件哈希、归档哈希并重新流式校验：

```bash
python3 experiments/cross-request-lineage/package_round_two.py \
  --out artifacts/cross-request-lineage-round-two-delivery-new
```

也可重复传入 `--include artifacts/实际输出目录` 选择需归档的目录。最终本机归档和 SHA-256、逐项评分及所有回归收据在 [results-round-two-20261113.json](results-round-two-20261113.json)。
