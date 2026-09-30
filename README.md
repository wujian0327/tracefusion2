# TraceFusion 2

研究方向：**面向微服务聚合 API 敏感数据暴露的跨服务字段血缘重建**。

当前阶段是实验场景验证。仓库提供 Sock Shop 的 11 组件部署包、合成数据初始化和订单响应检查。
尚未实现血缘重建算法、跨服务字段采集或独立执行级真值，也不报告溯源准确率。

## 快速运行

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

- [场景范围、数据流与后续真值设计](docs/sockshop-scenario.md)
- [部署配置](scenarios/sockshop/compose.json)（JSON 是 Compose 支持的 YAML 子集）
- [源码版本与镜像依据](scenarios/sockshop/sources.json)
- [本地验证记录](docs/validation.md)

本阶段保留原项目业务路径，未创建受控缺陷/修复版本。先确认固定镜像实际行为，再决定边界过滤补丁和真值采集位置。
