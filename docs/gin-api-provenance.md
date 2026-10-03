# Gin Web API 动态来源验证

## 本轮目标与状态

在真实 Gin 服务上使用普通响应结构体和 `c.JSON`，验证固定字段 `$.balance` 从文件读取、计算到 HTTP 响应写入的来源。沿用已有 C/Go 的机器指令重放与读取实例绑定核心，新增 Go/Gin 边界适配和请求分组。

**2026-10-03 用户主机真实 BCC/eBPF 采集通过，原始事件已完整重放核验。**环境为 WSL2 Linux amd64、Go 1.25.4、Gin 1.11.0、BCC 0.29.1。共 446 条事件、14 个请求、18 次计算、28 次读取；最终输出来源关系 TP=14/FP=0/FN=0，全部客户端正文与重建结果及独立预期一致。报告丢失、提交、状态和内存读取错误均为 0。详见 [主机核验记录](gin-api-host-20261003.json)。本轮无需重跑。

核查了同值覆盖确实由 a.bin 切换到 b.bin、常量覆盖消除外部来源，以及加工合并保留两个来源。探针计划、BPF 源码、二进制/源文件哈希、全部推断结果和评估结果均重新核对；结果图的边端点存在且跨请求节点 ID 不冲突。

本次各请求内 TID/G 地址一致，请求间出现 4 个 TID，而观测到的 G 地址相同。这说明不能把 G 地址当作请求 ID，也不能仅凭地址认定 goroutine 生命周期相同；当前按明确的请求范围分组。串行固定线程条件仍然保留，不据此声称支持请求内迁移或一般并发。

## 运行

固定 Linux amd64、Go **1.25.4**、Gin **1.11.0**。沿用主机已有的 BCC、binutils 和系统 Python；无需 Docker。Go 必须出现在运行脚本的用户 PATH 中，第一次构建需要下载 go.mod/go.sum 锁定的依赖。

```bash
git pull --ff-only origin main
go version
sudo env "PATH=$PATH" /usr/bin/python3 scripts/gin_api_provenance.py run
```

如果下载依赖时访问 `proxy.golang.org` 超时，可在本次命令中显式传入模块代理，确保 sudo 后的构建进程也收到该配置。本轮首次失败停在这一下载阶段，换代理后才完成采集。

```bash
sudo env "PATH=$PATH" GOPROXY=https://goproxy.cn,direct \
  /usr/bin/python3 scripts/gin_api_provenance.py run
```

runner 拒绝其他 Go 版本，避免未经验证的 ABI/编译差异被当成兼容。构建使用 `CGO_ENABLED=0`、PIE、`-gcflags=all=-l` 和 `nomsgpack`，标准库 JSON 后端；没有启用其他 JSON 编译标签。保持正常优化，只禁用内联以保留边界。

脚本会启动临时 loopback HTTP 服务、挂接探针、自动发送 14 个串行请求、停止服务、重建来源并评估。端口由系统选择，不占用固定端口。成功或失败均返回：

```text
artifacts/gin-api-provenance-*.zip
```

请返回整个 ZIP。构建、BCC 日志和事件都在包内；即使失败也无需手工挑选文件。旧场景无需重跑。输入文件在结束时删除，不需要部署数据库。

只检查构建与静态位置规划可使用：

```bash
python3 scripts/gin_api_provenance.py build
```

## 场景

接口为 `GET /account/summary?mode=...`。通过 `syscall.Pread` 从两个预打开的只读常规文件读入两个 uint32。文件内容在实验期间不可变。业务计算后正常执行 `c.JSON(http.StatusOK, dst)`，返回如 `{"balance":424242}` 的正文，不带换行。

| 模式 | 业务行为 | 最终数据来源 |
| --- | --- | --- |
| left | 对 a.bin 的值做 XOR 与加法 | a.bin 的本次读取 |
| right | 读取 b.bin | b.bin 的本次读取 |
| merge | 加工 a，再与 b 相加 | 本次 a、b 两个读取 |
| overwrite | 先加工 a，再常量覆盖为 42 | 无外部数据来源；保留常量计算路径 |
| same | 先复制 a，再用数值相同的 b 覆盖 | 仅 b；不能按值相同合并来源 |
| zero | 从另一个文件偏移读取 0 | b.bin 偏移 8 的本次读取 |
| max | 读取 UINT32_MAX | b.bin 偏移 12 的本次读取 |

每组 7 个请求；第一组使用 keep-alive，第二组每次关闭连接。共 14 个请求、18 次计算根调用、28 次读取。最终输出预期有 14 个文件读取来源关系；这是固定夹具的正确性检查，不是论文最终精度或图边召回率。

`balance` 键来自结构体标签 `json:"balance"`；值来自实际计算。另一个字段 `Audit` 使用 `json:"-"`，不输出。本轮没有动态键、字符串、嵌套对象或任意字段映射支持。

## 采集与重建

1. 对实际编译二进制进行反汇编，复用已有 Go 适配器识别业务函数的指令、控制流和直接 helper 调用。
2. 请求范围由 `main.serveAccount` 的执行实例界定。每次进入分配一个新的观测序号，并重置该请求的计算/读取计数。线程和 goroutine 只作一致性检查，不能充当请求 ID。
3. 在该范围采集真实 pread 入口/返回、返回字节和业务指令。来源依赖沿用读取实例、字节版本、执行指令和动态调用实例重建，不按数值相等推断来源。
4. 在 `render.WriteJSON` 入口记录响应对象地址、动态类型、字段快照和 writer 身份；在 `encoding/json.Marshal` 入口核对同一对象，在返回处记录结果 slice 地址、长度、容量、字节和 error。
5. 在 `(*gin.responseWriter).Write` 入口核对 writer 身份及同一个 slice，并验证返回长度和 error；再检查外层 WriteJSON 成功返回。
6. 最后一个完成的计算必须写到同一响应对象；JSON 字节必须符合明确的 uint32/固定键规则。反序列化后的数值只用于核对，来源由地址与操作版本关系连接。
7. 推断完成后，评估才读取客户端收到的状态、正文和独立模式列表，核对预期来源。推断函数不接收请求参数、预期来源或客户端正文。

JSON 边是**显式序列化摘要**，不声称逐指令跟踪反射、Go 标准库或整个框架。业务字段布局有编译期检查，构建会保存工具链、二进制、源文件、框架关键文件的哈希及具体探针偏移。该摘要仅适用于本仓库已审计的 `*output` 类型；不能直接套用到带自定义 MarshalJSON 方法的任意业务类型。

所有 Go 返回观测均挂在实际 RET 指令上；入口挂在栈检查的快速分支之后，避免 morestack 重试被记为多次边界。不使用 Go uretprobe。业务计算中的实际扩栈/抢占慢路径仍沿用旧核心的拒绝策略。

## 本轮边界

- 一个服务、串行请求。夹具在 handler 外围使用互斥和 `runtime.LockOSThread`；在事件中检查实际 G/TID。这里没有证明一般并发、线程迁移、异步 worker 或多服务拼接。
- 请求身份是一次被观测的业务 handler 范围。串行夹具中按顺序与客户端请求对齐；没有通过 HTTP header 注入 trace ID，也未实现一般连接到请求实例的解析算法。
- 输出终点是 **Gin ResponseWriter 接受完整正文**。客户端独立验证真实收包；尚未逐层连接 net/http 缓冲、socket syscall 和网络包，不把 writer 成功当作网络交付保证。
- 指令范围之外的输入写入、任意响应对象变更及数据库驱动均未建模。仅预置不可变文件、pread 作为输入字段唯一写入者、同一输出对象进入固定序列化流程。
- JSON 只允许固定 `balance` uint32 表示、长度小于 32；采集严格限制在 slice 长度内，不盲读 32 字节。
- 丢失/重复事件、上下文变化、对象或缓冲区不匹配、序列化错误、短写和写入错误不能通过评估。异常路径首先用于验证“不能错误声称成功”，没有定义通用失败响应溯源。

## 本地验证复现

```bash
python3 scripts/gin_api_provenance.py build --out "$PWD/artifacts/gin-test-build"
GIN_PROVENANCE_BUILD="$PWD/artifacts/gin-test-build" \
  python3 -m unittest discover -s tests -p test_gin_api_provenance.py -v
```

独立机器执行测试需要安装 Unicorn；真实 HTTP 测试需要允许 loopback socket。测试直接执行本次编译的业务机器指令，但边界传输事件是合成的。另有原生 C++ shim 检查生成的 Go ABI 处理函数解码与有界内存读取；这同样不代替 BPF verifier 和真实挂接。具体结果见 [本地验证记录](gin-api-local-validation.json)。
