# 验证记录

日期：2026-09-30。

## 已执行

- `python3 scripts/sockshop.py check`：通过。检查 11 个组件、镜像版本、loopback 端口和无 Docker socket 挂载。
- `python3 -m unittest discover -s tests -v`：6 项响应判定测试通过，覆盖 HTTP 200 内含应用错误、错误客户、错误购物项、订单缺失/金额错误、完整值与脱敏值区分，以及同后缀其他卡号不能误判为脱敏。
- `python3 scripts/sockshop.py run --out artifacts/no-docker-validation`：按预期以退出码 1 结束，记录 `status=failed` / `stage=deployment` / `Docker is not installed`，并生成诊断 ZIP。

## 尚未验证

当前执行环境没有 Docker。因此尚未运行 `docker compose config`、拉取镜像、启动服务、验证 ARM 模拟，也未观测真实订单响应。不能据此声称 11 组件部署已经跑通，或者已复现敏感字段暴露。

部署程序会在用户主机运行时补充上述验证。历史镜像不支持当前 Docker、拉取失败、内存不足、端口冲突、服务启动失败等情况会保留诊断；本包不自动替换应用版本。

## 数据与版本边界

源码标签已核对，但旧镜像与源码提交的构建对应关系尚未全部验证。运行结果中的 `images.json` 和 `compose.lock.json` 是实际镜像版本的记录。测试夹具与客户端响应不能代替独立执行级血缘真值。
