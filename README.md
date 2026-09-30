# TraceFusion 2

当前阶段：**面向微服务聚合 API 敏感响应的调用链溯源**。

先采集 trace/span，核验请求关联和跨服务调用关系。字段编号、字段传播埋点和完整血缘图暂缓；当前不报告算法溯源准确率。

11 组件基础版已经通过一次用户主机订单验证。新增追踪版保留业务镜像，增加 2 个入口代理与 1 个采集器，共 14 个容器；Java、Node 和消息传播的完整部署仍待实际运行验证。

## 本轮：采集订单调用链

```bash
git pull
python3 scripts/sockshop_trace.py run
```

默认运行 2 个并发测试流程，检查真实 span 的父子关系、订单分支与发货消息关联。
成功或失败都请返回 `artifacts/sockshop-trace-*.zip`。
第一次下载官方 Java agent 1.32.0，需要能访问 GitHub。

详细范围、命令、14 组件组成、结果解释及真值隔离见 [调用链采集说明](docs/sockshop-tracing.md)。

```bash
python3 scripts/sockshop_trace.py down
python3 scripts/sockshop_trace.py check
```

## 基础版：仅验证订单场景

需要 Docker Engine、Docker Compose v2 和 Python 3.9+。当前镜像固定为历史版本，并使用 `linux/amd64`；建议先在 x86-64 Linux 上运行。ARM 机器需要 Docker 支持 amd64 模拟。

```bash
git clone https://github.com/wujian0327/tracefusion2.git
cd tracefusion2
python3 scripts/sockshop.py run
```

脚本依次检查 Docker、拉取镜像、记录 registry digest、生成 digest 固定的 Compose 文件、启动 11 个组件、等待应用与配送消费者就绪，然后创建一个全新测试用户、地址、卡片与购物项，并调用原有前端的 `POST /orders`。

完成或失败都会输出 `RESULT BUNDLE: ...zip`。**把该 ZIP 发回即可**，其中包括本次订单响应、测试夹具、镜像信息和诊断结果。镜像拉取失败也会保留错误原因，不会自动换镜像或伪造成功结果。

默认端口只绑定本机：

| 端口 | 用途 |
| --- | --- |
| `127.0.0.1:18080` | 原有 Front-end HTTP 接口 |
| `127.0.0.1:18081` | Carts 数据初始化接口 |

端口冲突时先设置 `TF2_FRONT_PORT` / `TF2_CART_PORT` 环境变量。前端的商品浏览页面不属于裁剪场景，不应以首页能否完整展示判断部署成功。

```bash
# 停止本项目容器，保留测试数据库卷
python3 scripts/sockshop.py down

# 不需要 Docker 的静态检查与响应判定测试
python3 scripts/sockshop.py check
python3 -m unittest discover -s tests -v
```

运行会新增合成数据，不清空已有数据库；每次生成唯一用户。请使用本包创建的独立 Compose 项目，不接入真实用户数据。上游日志会记录合成卡号和本次随机测试账户信息，结果包只应用于本实验。

## 结果含义

`result.json` 中 `status: passed` 表示本次订单成功，并且客户、购物项、金额与夹具匹配。**它不表示漏洞已修复、不表示所有服务调用已采集，也不表示血缘重建正确。**

每个目标字段单独报告：

- `full_value_returned`：与合成源值完全相同。
- `last_four_only_or_masked`：仅后四位或前缀由掩码字符构成。
- `absent_or_empty`：字段不存在或为空。
- `different_value_needs_review`：返回其他值，需检查，不直接当作脱敏成功。

脚本额外检查原有 `GET /card` 的后四位预览，与 `POST /orders` 的卡片字段进行比较；不修改上游业务代码。地址与姓名的返回仅记录可见性，不自动认定为越权暴露。

## 文档与验证状态

- [当前调用链采集范围](docs/sockshop-tracing.md)
- [原始场景与候选字段路径（字段级设计暂缓）](docs/sockshop-scenario.md)
- [部署配置](scenarios/sockshop/compose.json)（JSON 是 Compose 支持的 YAML 子集）
- [源码版本与镜像依据](scenarios/sockshop/sources.json)
- [本地验证记录](docs/validation.md)

本阶段保留原项目业务路径，未创建受控缺陷/修复版本。下一步根据真实 trace 的覆盖情况完善调用链采集。
