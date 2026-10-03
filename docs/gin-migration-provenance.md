# Gin 请求执行中的线程迁移

## 当前状态

新增 `gin-migration-provenance` 入口，保留每批 4 个、共 28 个请求，以及真实文件读取、业务计算和 `c.JSON` 输出。

请求处理 goroutine 不再调用 `LockOSThread`。采集读取状态按实际 G 地址查找，计算调用状态按请求实例号保存。**本地编译、真实 HTTP、迁移事件重建与原生采集器模拟已经通过；新的 eBPF 内核采集仍待用户主机验证。**本地模拟不能替代 BCC 编译、内核 verifier、实际挂接和丢事件检查。

## 运行

使用已验证的 Go 1.25.4、Gin 1.11.0、BCC 和系统 Python，无需 Docker：

```bash
git pull --ff-only origin main
sudo env "PATH=$PATH" GOPROXY=https://goproxy.cn,direct \
  /usr/bin/python3 scripts/gin_migration_provenance.py run
```

返回整个 `artifacts/gin-migration-provenance-*.zip`，失败时也返回。旧串行和固定线程并发入口无需重跑。

## 状态如何跨线程接续

1. 在 PID 限定的请求入口探针中学习宿主机 TGID，防止 PID namespace 差异。一个采集器只接收一个目标进程。
2. 请求进入时，以实际 R14 中的 G 地址登记活动请求，并分配递增的请求实例号。活动 G 不允许重入请求范围。
3. 业务指令、Gin 边界探针从当次寄存器取 G；系统调用从当次保存的用户寄存器取 G。没有 TID→G 缓存，也不通过数值或客户端发送顺序判断归属。
4. 同一个 G 换到另一线程时仍找到同一个活动请求。两个 G 先后在同一个线程执行时，读取和计算状态仍独立。
5. 请求结束时删除 G 映射和计算状态。以后复用相同 G 地址时获得新的请求实例号。

每条原始事件保留真实 `pid_tid`。共用核心新增可选执行身份策略，用请求实例归组；新结果使用 `execution_id` 和 `observed_pid_tids`，不会把请求号伪装成线程号。原 C、Go 和固定线程 Gin 入口的默认策略与输出保持兼容。

单次 `pread64` 的内核进入/返回仍要求相同 TID；支持的是系统调用之间、计算观测之间及框架边界之间的 goroutine 线程迁移。若计算过程中实际进入扩栈/抢占慢路径，已有指令重放仍拒绝该路径，不会通过换一个身份键声称支持栈重定位。

## 如何保证测试真的覆盖迁移

单纯删掉 `LockOSThread` 后跑通，可能恰好一次都没换线程。本场景加入明确的调度夹具：

- `GOMAXPROCS(1)` 使调度更可重复；4 个请求的范围仍交错重叠，本轮不测多核吞吐量。
- 在第一次读取后，以及业务计算后，辅助 goroutine 尝试占住请求刚使用的线程，并一直等待到该请求范围接近结束。**只有辅助 goroutine 使用 `LockOSThread`，处理请求的 goroutine 从未固定线程。**辅助者不接收业务数据或溯源标签。
- 每批保留三处阶段汇合，保证 4 个请求实际重叠。
- 服务器在观测范围外写出独立的 `phase_tids` 评估记录。本地 HTTP 测试用它检查调度确实换过线程；算法推断不读取这份记录。主机验收以原始 eBPF 事件中的线程号为准。

这是主动构造的迁移正确性实验，不代表一般生产调度下的迁移频率或性能。

## 验收条件

`evaluation.json` 分开记录两类结果：

- `provenance_checks_passed`：28 个响应、36 次计算、56 次读取；全部来源关系和正文正确，7 批满足 4 请求重叠与阶段顺序，采集无报告错误。
- `migration_coverage_passed`：28 个请求都在原始事件中出现至少两个 TID，且两次读取使用不同线程，最后一次计算与 JSON render 入口使用不同线程。

两者同时满足才能 `passed=true`。值和来源都正确但未观察到迁移，会标记覆盖不足，不能算迁移验证通过。`migration.requests` 保留各请求的 G、线程集合和相邻已观测事件间的线程变化；这不是完整调度轨迹，也不是 OS 上下文切换次数。

## 本地检查与边界

见 [本地验证记录](gin-migration-local-validation.json)。检查包括真实 Go 指令执行后构造线程迁移历史、同线程交错 G、调用未结束时换线程、G 地址跨请求复用、错误 G/进程/请求号/局部序号、单次 syscall 错误换线程、缺失边界、同值错误读取位置和采集错误。另有执行完整生成采集器的 C++ shim 和真实 HTTP 检查。

```bash
python3 scripts/gin_migration_provenance.py build --out "$PWD/artifacts/gin-migration-test-build"
GIN_MIGRATION_BUILD="$PWD/artifacts/gin-migration-test-build" \
  python3 -m unittest discover -s tests -p test_gin_migration_provenance.py -v
```

本地检查需要 Unicorn、g++ 和 loopback socket 权限。本轮真实 HTTP 主动诱发的是读取阶段之间与计算到 JSON 之间的迁移；计算调用内部跨线程状态由合成事件和采集器模拟检查，不声称真实主机已覆盖这一种时机。

继续限定 Go 1.25.4/linux-amd64、关闭内联、请求私有对象、不可变文件和固定 `balance` uint32 JSON 摘要。未扩展子 goroutine 数据传播、共享可变内存、任意 JSON、数据库、socket 字节级血缘或性能评估。
