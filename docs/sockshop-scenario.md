# Sock Shop：订单确认响应中的字段暴露验证

> 范围更新（2026-09-30）：当前只做调用链溯源；本文后续字段血缘设计是候选方向，暂不实施。当前实现见 [调用链采集说明](sockshop-tracing.md)。

## 固定范围

主要入口是原有 Front-end 的 `POST /orders`，目标是其响应中的 `card.longNum`、`card.ccv`，并记录 `address.street`、`customer.firstName` 作为辅助传播字段。当前只提交一笔订单，未测试并发或计算准确率。

系统来自开源 Sock Shop。MirrorTaint（ICSE 2023）在该应用上评估过 `Orders.newOrder`；本包参考作者部署配置，但不宣称复现其论文实验或其历史二进制。

## 11 个组件

- 应用：front-end、user、carts、orders、payment、shipping。
- 存储：user-db、carts-db、orders-db。
- 消息：rabbitmq、queue-master。

移除 edge-router（直接发布 Front-end 的 8079 端口）、catalogue / catalogue-db（经原有 Carts API 初始化购物项）、user-sim（由本包脚本发起请求）。不挂载 Docker socket。后续追踪发现 queue-master 消费消息后还会通过该 socket 启动演示 worker，因此当前裁剪未满足该分支依赖；“收到任务”不能作为完整配送成功的依据。

保留真实 payment、shipping 和队列消费者，不使用 mock 代替服务。就绪检查验证五个内部应用的 health 状态，以及 `shipping-task` 队列存在消费者；这并不是对每条配送消息已被处理的证明。

默认 MongoDB 命名卷保留数据。停止命令不删除卷。所有依赖镜像先使用版本标签拉取，然后保存镜像 ID、摘要、架构与标签，实际 `up` 使用本次生成的 `compose.lock.json`。不同日期初次拉取的标签仍可能指向不同摘要；复现实验应保留并复用结果包中的锁定配置。

## 源码支持的数据路径

1. Front-end 读取客户与地址/卡片列表，选出第一个地址和卡片的链接。
2. Orders 并发请求 customer、address、card、items。
3. Orders 把地址、卡片、客户和金额发送给 Payment；Payment 返回授权结果。
4. Orders 调用 Shipping，并将各对象组装成 CustomerOrder。
5. Orders 执行保存后返回对象；Front-end 转发 JSON。

`GET /card` 仅返回卡号后四位；Orders 的卡片 DTO 含 `longNum`、`expires`、`ccv`。实际镜像是否返回完整值，由运行结果确认，不能把源码推断代替观测。

## 当前采集与限制

`http-client-observations.json` 仅是测试客户端与服务的 HTTP 交互，不是服务间抓包、数据库读取日志或分布式追踪。`fixture.json` 包含测试用户、卡片、地址 ID 与原始值，供验证响应使用；它不是独立的执行级血缘真值。

数据库源头是 MongoDB 文档字段，不是 SQL 列。源头至少应支持：服务、数据库、集合、文档 ID、字段路径、读取事件 ID；版本信息只在实际可观测时记录。

两个不能省略的正确性问题：

- Front-end 预读卡片列表与 Orders 正式读取卡片可能得到相同值，只有值相等不足以确定读取来源。
- Payment 收到卡片，不表示订单中的卡片来自 Payment。支付结果可能构成控制依赖，应与字段值依赖分开标注。

源码没有在订单保存后显式重新查询，当前响应不能无依据地标成一次订单数据库读取。历史订单查询可以另设实验，但本阶段不包含。

## 下一阶段的独立真值

先确认真实响应，再在隔离的 oracle 运行模式中记录数据库读取、HTTP 序列化/反序列化和订单字段赋值的实际关联；oracle 标识不提供给待测算法。标注依据不能复用待测算法的值匹配或时序推断。

后续评估需要分别报告字段来源集合准确率、血缘边 precision/recall 和整条血缘重建正确率。未返回、分析失败、歧义与超时单独记录，不能只统计成功样本。

该场景包含 Go、Java、Node.js。只在 Orders 内启用 Java 插桩不能声称已经覆盖数据库到外部响应的全链路字段血缘。

## 参考

- https://github.com/microservices-demo/microservices-demo
- https://github.com/MirrorTaint/MirrorTaint
- https://lingming.cs.illinois.edu/publications/icse2023d.pdf
