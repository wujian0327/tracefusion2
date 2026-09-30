# 验证记录

日期：2026-09-30。

## 基础版：已由用户主机验证

输入结果包：`sockshop-20260930-172440-405c.zip`。

- `result.json` 为 passed；11 个容器采集时均 running。
- `POST /orders` 返回 201；客户、购物项和金额 9.99 与夹具匹配。
- `/card` 返回后四位，订单响应含完整合成卡号与 CCV。
- 日志显示支付授权成功，queue-master 收到该测试客户的发货任务。
- 运行镜像摘要已在输入结果包中保存。

因此可称“11 组件订单路径已完成一次运行验证”，不能称最小部署，也不能据此声称已有完整调用链真值或字段血缘真值。

## 追踪版：本地已执行

- `python3 scripts/sockshop.py check`：原 11 组件静态检查通过。
- `python3 scripts/sockshop_trace.py check`：14 组件追踪配置静态检查通过。
- `python3 -m unittest discover -s tests -v`：16 项测试通过。
- 其中 HTTP 集成测试使用真实本机 HTTP 服务与子进程：8 个并发 Node 请求，每个发起并行和嵌套下游调用，验证 32 个 span 及 Header 关联未混串；代理保持响应与重复 Set-Cookie，正确替换不同大小写的旧 traceparent；真实采集器接受 gzip Zipkin 批次并保存、导出记录。
- 图检查测试覆盖缺失父节点、环、冲突 ID、重复导出、错误 trace、错误客户 ID、缺少消息 producer 关联、HTTP 错误及空集合不能通过。
- 原有 6 项响应判定测试保持通过。
- Python 编译和 Node 语法检查通过。
- `python3 scripts/sockshop_trace.py run --out artifacts/trace-no-docker-check`：在无 Docker 环境按预期返回失败，保留诊断 ZIP。

Node 集成测试运行时为 **v24.19.0**，hook 使用 Node 4 兼容语法/API；这不能替代实际 Node 4 镜像的运行验证。

## 追踪版：尚未验证

当前编写环境没有 Docker，尚未启动 14 组件追踪部署。Java agent 在固定旧镜像内的加载、异步执行器上下文、RabbitMQ producer→consumer、旧版前端 request 库与 hook 的组合、Docker 挂载和实际完整 trace 均待用户主机验证。

官方 agent 1.32.0 库支持表已经核对，但支持表不能替代本应用运行结果。追踪脚本遇到未覆盖路径时会保留 incomplete，不创建推断的真值边。

## 边界

源码标签与旧镜像的构建对应关系尚未全部验证。运行的 `images.json` / `compose.lock.json`、agent SHA-256、采集代码 SHA-256 用于记录实际组合。user/payment 记录的是入口代理边界，不是 Go 内部或数据库 span。当前不包含字段传播真值、不包含链路重建算法、不报告算法准确率。
