# 同版本共同任务成本：目标相关观测

算法冻结 `130858947f3eabc1dbee8693f11c926f37f289e9`，能力参照 `7e4ad0b`。四个查询任务和联合判据均在正式结果前固定；不按请求数投票，不更换失败或没有优势的任务。以下是新的在线捕获及同版本正常离线单次流程，不覆盖旧成本表。

**预设内部判据通过 4/4；统一内核子集通过 3/3。** 这是selective相对full的内部判据，不能推出多数应用优于 MT，也不等于相对原版低开销。ZLT两个任务相对原版p95的配对中位增幅仍约131%。Orders 是既有专用路径，另外三项是统一内核。新应用完整候选的能力覆盖另见首次复用报告。

判据要求完整批次协议字节和正常离线进程 CPU 同时下降，且业务 CPU／p95 配对中位比值不超过 1.05、每轮不超过 1.10。五轮不是请求级独立重复，不声称统计显著性；2 请求／秒完成率不代表最大吞吐。

每任务比较原版、TF full、selective、固定 MT；同 JAR、JDK、资源限制和原输入。五轮独立部署、轮内随机配置顺序；预热 30 秒、测量 60 秒、2 请求／秒、并发上限 2。正确性包含预热，在线指标排除预热。正式在线实验顺序执行，原有非实验容器未操作，不宣称独占物理机。

| 共同任务 | 所选返回路径 | 原声明来源边界 |
| --- | --- | --- |
| Mall 管理员登录 | `/data/expiresIn` | 本次 `AuthService.getAccessToken` 调用返回字段 |
| ZLT Client 列表 | `/data/*/clientId` | 本次 `ClientMapper.findList(Page,Map)` 返回字段 |
| ZLT User 列表 | `/data/*/username` | 本次 `SysUserMapper.findList(Page,Map)` 返回字段 |
| Orders 创建 | `/total` | 本次 Carts 响应的 quantity／unitPrice，沿用原固定任务 |

短校准覆盖原版与三种工具的业务行为、真实来源调用、目标及独立物理坐标；依赖校准核对实际 ObjectMapper 定义与原业务 JAR 字节码。MT 使用既有固定适配器，原生传播 JAR 未改；这不是任意库的传播等价性证明。Mall 跨 JVM 仅规范化新 token 和 86400 秒有效期的时钟舍入；各 JVM 内来源／目标值与实例坐标仍精确核对，每部署另查 180 条登录日志。ZLT 完整 JSON 按原分页模板核对，原始数据库事实保留。

机器为 Ryzen 9 7950X／32 逻辑 CPU 的 WSL2。Mall／ZLT采用固定 OpenJDK 8u504，Orders保留锁定原镜像的运行时；各任务内部四配置JDK一致。JVM32/256MiB、GC1/CI2，各 JVM 1CPU/768MiB；资源采样间隔2秒，RSS峰值为采样峰值。Mall业务组为admin/auth/portal，ZLT为user/uaa，Orders业务组为orders/carts/shipping；部署组另含其依赖。MySQL512MiB、Redis128MiB、Mongo／Rabbit384MiB，ZLT Nacos768MiB，实际角色、限制、镜像ID及原有四个容器清单见环境与compose文件。负载客户端不计入业务或部署资源，curl HTTP时间排除Docker exec调度及评分。

## orders

| 配置 | 含预热请求 | 独立实例正确／实际目标 |
| --- | ---: | ---: |
| original | 900 | N/A，不运行还原 |
| full | 900 | 900/900 |
| selective | 900 | 900/900 |
| mirrortaint | 900 | 900/900 |

| 五轮中位数 | original | full | selective | MT |
| --- | ---: | ---: | ---: | ---: |
| p50 ms | 12.113 | 14.267 | 13.469 | 62.950 |
| p95 ms | 14.193 | 24.278 | 16.684 | 76.124 |
| p99 ms | 17.521 | 29.170 | 25.743 | 85.367 |
| 完成请求/秒 | 2.000 | 2.000 | 2.000 | 2.000 |
| 错误率 | 0.000 | 0.000 | 0.000 | 0.000 |
| 业务 CPU，单核% | 6.113 | 8.124 | 7.706 | 19.771 |
| 业务平均 RSS MiB | 814.283 | 836.425 | 830.744 | 834.511 |
| 业务采样峰值 RSS MiB | 816.047 | 838.387 | 833.297 | 839.969 |
| 整部署 CPU，单核% | 8.327 | 10.368 | 9.964 | 22.085 |
| 整批协议事件 | N/A | 42124.000 | 9574.000 | 9485.000 |
| 整批协议 MiB | N/A | 17.040 | 7.201 | 27.310 |
| 可归属测量事件 | N/A | 3720.000 | 3720.000 | 5280.000 |
| 可归属测量 MiB | N/A | 3.282 | 3.275 | 17.260 |
| 未归属／共享 MiB | N/A | 12.119 | 2.289 | 1.412 |
| 全部 capture 文件 MiB | N/A | 17.040 | 7.201 | 105.543 |
| 各自离线核心墙时 s | N/A | 0.488 | 0.245 | 0.469 |
| 各自离线核心 CPU s | N/A | 0.487 | 0.245 | 0.469 |
| 正常离线总墙时 s | N/A | 1.515 | 0.558 | 0.978 |
| 正常离线进程 CPU s | N/A | 1.514 | 0.553 | 0.977 |
| fresh-exec VmHWM MiB | N/A | 149.121 | 90.918 | 171.336 |
| 正常还原图节点 | N/A | 17282.000 | 17282.000 | 0.000 |
| 正常还原边列表 | N/A | 5595.000 | 5595.000 | 0.000 |

| 配对 | 指标 | 中位变化 | 五轮比值范围 |
| --- | --- | ---: | --- |
| selective/full | batch_bytes | -57.74% | 0.4226–0.4226 |
| selective/full | offline_core_CPU_s | -49.98% | 0.4821–0.5393 |
| selective/full | offline_CPU_s | -64.72% | 0.3317–0.3766 |
| selective/full | offline_wall_s | -64.09% | 0.3372–0.3747 |
| selective/full | offline_VmHWM_MiB | -38.96% | 0.6097–0.6105 |
| selective/full | business_CPU | -5.15% | 0.8556–0.9932 |
| selective/full | p95_ms | -8.59% | 0.6201–0.9353 |
| selective/original | business_CPU | +27.19% | 1.0414–1.2917 |
| selective/original | p95_ms | +12.40% | 1.1045–1.5441 |
| mirrortaint/original | business_CPU | +224.92% | 2.6961–3.3268 |
| mirrortaint/original | p95_ms | +436.35% | 5.0236–6.1178 |
| selective/mirrortaint | batch_bytes | -73.63% | 0.2637–0.2637 |
| selective/mirrortaint | offline_core_CPU_s | -47.07% | 0.5147–0.5400 |
| selective/mirrortaint | offline_CPU_s | -44.30% | 0.5502–0.5806 |
| selective/mirrortaint | offline_wall_s | -43.60% | 0.5544–0.5905 |
| selective/mirrortaint | offline_VmHWM_MiB | -46.95% | 0.5299–0.5320 |
| selective/mirrortaint | business_CPU | -61.17% | 0.3843–0.3915 |
| selective/mirrortaint | p95_ms | -79.28% | 0.1959–0.3074 |

| 离线阶段墙时，五轮中位数 s | full | selective | MT |
| --- | ---: | ---: | ---: |
| decode_and_validate | 0.2319 | 0.0848 | 0.2786 |
| graph_reconstruction | 0.3765 | 0.1370 | 0.0000 |
| query_or_native_origin_restore | 0.1116 | 0.1085 | 0.4687 |
| oracle_score_and_background_accounting | 0.6765 | 0.1130 | 0.0868 |
| answer_export | 0.0236 | 0.0233 | 0.0463 |
## mall

| 配置 | 含预热请求 | 独立实例正确／实际目标 |
| --- | ---: | ---: |
| original | 900 | N/A，不运行还原 |
| full | 900 | 900/900 |
| selective | 900 | 900/900 |
| mirrortaint | 900 | 900/900 |

| 五轮中位数 | original | full | selective | MT |
| --- | ---: | ---: | ---: | ---: |
| p50 ms | 113.319 | 119.809 | 119.975 | 117.034 |
| p95 ms | 120.897 | 128.032 | 129.909 | 124.221 |
| p99 ms | 137.279 | 135.673 | 146.118 | 131.249 |
| 完成请求/秒 | 2.000 | 2.000 | 2.000 | 2.000 |
| 错误率 | 0.000 | 0.000 | 0.000 | 0.000 |
| 业务 CPU，单核% | 24.447 | 26.724 | 26.940 | 25.610 |
| 业务平均 RSS MiB | 857.470 | 917.239 | 915.195 | 898.302 |
| 业务采样峰值 RSS MiB | 863.109 | 926.707 | 926.324 | 909.652 |
| 整部署 CPU，单核% | 29.401 | 31.445 | 31.951 | 30.363 |
| 整批协议事件 | N/A | 60607.000 | 52687.000 | 1987.000 |
| 整批协议 MiB | N/A | 38.677 | 35.188 | 3.648 |
| 可归属测量事件 | N/A | 27000.000 | 23040.000 | 1080.000 |
| 可归属测量 MiB | N/A | 19.824 | 17.820 | 2.205 |
| 未归属／共享 MiB | N/A | 8.983 | 8.491 | 0.342 |
| 全部 capture 文件 MiB | N/A | 38.677 | 35.188 | 23.421 |
| 各自离线核心墙时 s | N/A | 1.397 | 1.133 | 0.036 |
| 各自离线核心 CPU s | N/A | 1.396 | 1.132 | 0.036 |
| 正常离线总墙时 s | N/A | 2.256 | 1.925 | 0.171 |
| 正常离线进程 CPU s | N/A | 2.256 | 1.925 | 0.171 |
| fresh-exec VmHWM MiB | N/A | 290.477 | 263.355 | 47.125 |
| 正常还原图节点 | N/A | 9360.000 | 6660.000 | 0.000 |
| 正常还原边列表 | N/A | 1800.000 | 900.000 | 0.000 |

| 配对 | 指标 | 中位变化 | 五轮比值范围 |
| --- | --- | ---: | --- |
| selective/full | batch_bytes | -9.02% | 0.9098–0.9098 |
| selective/full | offline_core_CPU_s | -18.33% | 0.7787–0.8315 |
| selective/full | offline_CPU_s | -14.31% | 0.8320–0.8701 |
| selective/full | offline_wall_s | -14.33% | 0.8285–0.8702 |
| selective/full | offline_VmHWM_MiB | -9.35% | 0.9062–0.9071 |
| selective/full | business_CPU | +0.78% | 0.9671–1.0637 |
| selective/full | p95_ms | +2.57% | 0.9866–1.0415 |
| selective/original | business_CPU | +10.20% | 1.0489–1.1850 |
| selective/original | p95_ms | +5.18% | 1.0449–1.1437 |
| mirrortaint/original | business_CPU | +4.72% | 1.0138–1.0930 |
| mirrortaint/original | p95_ms | +2.15% | 0.9987–1.0644 |
| selective/mirrortaint | batch_bytes | +864.50% | 9.6443–9.6453 |
| selective/mirrortaint | offline_core_CPU_s | +3035.29% | 25.0144–32.4959 |
| selective/mirrortaint | offline_CPU_s | +1000.16% | 10.4342–11.3819 |
| selective/mirrortaint | offline_wall_s | +998.20% | 10.4045–11.3578 |
| selective/mirrortaint | offline_VmHWM_MiB | +458.71% | 5.5795–5.6056 |
| selective/mirrortaint | business_CPU | +6.51% | 1.0016–1.0843 |
| selective/mirrortaint | p95_ms | +3.01% | 1.0148–1.0938 |

| 离线阶段墙时，五轮中位数 s | full | selective | MT |
| --- | ---: | ---: | ---: |
| decode_complete_capture | 0.5391 | 0.5050 | 0.0446 |
| reconstruction_with_required_certificates | 1.3574 | 1.1031 | N/A |
| query | 0.0370 | 0.0299 | N/A |
| export | 0.0058 | 0.0056 | 0.0026 |
| independent_score_raw_index | 0.0193 | 0.0177 | N/A |
| native_tag_decode | N/A | N/A | 0.0361 |
| independent_score | N/A | N/A | 0.0149 |
## zlt-client

| 配置 | 含预热请求 | 独立实例正确／实际目标 |
| --- | ---: | ---: |
| original | 900 | N/A，不运行还原 |
| full | 900 | 900/900 |
| selective | 900 | 900/900 |
| mirrortaint | 900 | 900/900 |

| 五轮中位数 | original | full | selective | MT |
| --- | ---: | ---: | ---: | ---: |
| p50 ms | 5.275 | 9.116 | 8.914 | 8.907 |
| p95 ms | 6.384 | 15.352 | 14.365 | 13.865 |
| p99 ms | 11.505 | 16.411 | 16.207 | 16.363 |
| 完成请求/秒 | 2.000 | 2.000 | 2.000 | 2.000 |
| 错误率 | 0.000 | 0.000 | 0.000 | 0.000 |
| 业务 CPU，单核% | 5.868 | 7.770 | 7.620 | 8.529 |
| 业务平均 RSS MiB | 621.962 | 661.025 | 676.739 | 961.246 |
| 业务采样峰值 RSS MiB | 624.738 | 666.230 | 681.711 | 965.012 |
| 整部署 CPU，单核% | 7.706 | 9.656 | 9.673 | 10.283 |
| 整批协议事件 | N/A | 51648.000 | 46368.000 | 1448.000 |
| 整批协议 MiB | N/A | 23.160 | 19.592 | 3.797 |
| 可归属测量事件 | N/A | 34300.000 | 30780.000 | 960.000 |
| 可归属测量 MiB | N/A | 15.469 | 13.082 | 2.534 |
| 未归属／共享 MiB | N/A | 0.026 | 0.026 | 0.001 |
| 全部 capture 文件 MiB | N/A | 23.160 | 19.592 | 16.185 |
| 各自离线核心墙时 s | N/A | 0.679 | 0.543 | 0.049 |
| 各自离线核心 CPU s | N/A | 0.679 | 0.542 | 0.048 |
| 正常离线总墙时 s | N/A | 1.205 | 0.960 | 0.171 |
| 正常离线进程 CPU s | N/A | 1.205 | 0.960 | 0.170 |
| fresh-exec VmHWM MiB | N/A | 185.973 | 157.355 | 52.859 |
| 正常还原图节点 | N/A | 6300.000 | 1440.000 | 0.000 |
| 正常还原边列表 | N/A | 360.000 | 360.000 | 0.000 |

| 配对 | 指标 | 中位变化 | 五轮比值范围 |
| --- | --- | ---: | --- |
| selective/full | batch_bytes | -15.41% | 0.8459–0.8460 |
| selective/full | offline_core_CPU_s | -20.99% | 0.7893–0.8388 |
| selective/full | offline_CPU_s | -19.45% | 0.7786–0.8114 |
| selective/full | offline_wall_s | -19.43% | 0.7788–0.8114 |
| selective/full | offline_VmHWM_MiB | -15.41% | 0.8452–0.8462 |
| selective/full | business_CPU | -2.08% | 0.9219–1.0144 |
| selective/full | p95_ms | -3.72% | 0.9049–1.0072 |
| selective/original | business_CPU | +28.29% | 1.1005–1.3365 |
| selective/original | p95_ms | +130.67% | 2.0949–2.3525 |
| mirrortaint/original | business_CPU | +41.63% | 1.0894–1.4900 |
| mirrortaint/original | p95_ms | +117.18% | 2.0731–2.4788 |
| selective/mirrortaint | batch_bytes | +416.05% | 5.1599–5.1605 |
| selective/mirrortaint | offline_core_CPU_s | +1029.31% | 10.8761–11.6588 |
| selective/mirrortaint | offline_CPU_s | +470.43% | 5.4767–5.8385 |
| selective/mirrortaint | offline_wall_s | +468.33% | 5.4609–5.8145 |
| selective/mirrortaint | offline_VmHWM_MiB | +197.69% | 2.9728–2.9889 |
| selective/mirrortaint | business_CPU | -9.42% | 0.8533–1.0424 |
| selective/mirrortaint | p95_ms | +4.11% | 0.9305–1.0788 |

每种配置的900次请求中，150次为空列表、未产生所选成员目标；它们仍参与业务与成本统计，不能将其算作150个来源答案。其余请求共生成900个实际成员目标。


| 离线阶段墙时，五轮中位数 s | full | selective | MT |
| --- | ---: | ---: | ---: |
| decode_complete_capture | 0.3397 | 0.2577 | 0.0403 |
| required_source_protocol | N/A | N/A | 0.0008 |
| independent_raw_fact_index_and_pairing | 0.0169 | 0.0143 | 0.0009 |
| native_tag_decode | N/A | N/A | 0.0487 |
| export | 0.0056 | 0.0053 | 0.0031 |
| independent_score_raw_index | 0.0016 | 0.0012 | 0.0016 |
| reconstruction_with_required_certificates | 0.6545 | 0.5394 | N/A |
| query | 0.0245 | 0.0034 | N/A |
## zlt-user

| 配置 | 含预热请求 | 独立实例正确／实际目标 |
| --- | ---: | ---: |
| original | 900 | N/A，不运行还原 |
| full | 900 | 1350/1350 |
| selective | 900 | 1350/1350 |
| mirrortaint | 900 | 1350/1350 |

| 五轮中位数 | original | full | selective | MT |
| --- | ---: | ---: | ---: | ---: |
| p50 ms | 5.966 | 11.519 | 11.192 | 11.752 |
| p95 ms | 7.077 | 16.985 | 16.822 | 15.931 |
| p99 ms | 11.584 | 17.785 | 18.634 | 17.435 |
| 完成请求/秒 | 2.000 | 2.000 | 2.000 | 2.000 |
| 错误率 | 0.000 | 0.000 | 0.000 | 0.000 |
| 业务 CPU，单核% | 6.161 | 9.254 | 9.101 | 9.715 |
| 业务平均 RSS MiB | 626.545 | 664.198 | 675.636 | 665.031 |
| 业务采样峰值 RSS MiB | 632.875 | 671.922 | 682.859 | 669.246 |
| 整部署 CPU，单核% | 7.990 | 11.073 | 10.730 | 11.553 |
| 整批协议事件 | N/A | 76563.000 | 70233.000 | 1449.000 |
| 整批协议 MiB | N/A | 37.971 | 32.676 | 5.175 |
| 可归属测量事件 | N/A | 49840.000 | 45620.000 | 960.000 |
| 可归属测量 MiB | N/A | 25.180 | 21.639 | 3.454 |
| 未归属／共享 MiB | N/A | 0.294 | 0.294 | 0.001 |
| 全部 capture 文件 MiB | N/A | 37.971 | 32.676 | 22.174 |
| 各自离线核心墙时 s | N/A | 14.400 | 12.777 | 0.079 |
| 各自离线核心 CPU s | N/A | 14.399 | 12.770 | 0.079 |
| 正常离线总墙时 s | N/A | 15.226 | 13.531 | 0.230 |
| 正常离线进程 CPU s | N/A | 15.225 | 13.524 | 0.230 |
| fresh-exec VmHWM MiB | N/A | 287.734 | 243.363 | 63.340 |
| 正常还原图节点 | N/A | 9810.000 | 1890.000 | 0.000 |
| 正常还原边列表 | N/A | 540.000 | 540.000 | 0.000 |

| 配对 | 指标 | 中位变化 | 五轮比值范围 |
| --- | --- | ---: | --- |
| selective/full | batch_bytes | -13.94% | 0.8605–0.8606 |
| selective/full | offline_core_CPU_s | -7.72% | 0.8610–0.9673 |
| selective/full | offline_CPU_s | -7.93% | 0.8631–0.9630 |
| selective/full | offline_wall_s | -7.96% | 0.8631–0.9629 |
| selective/full | offline_VmHWM_MiB | -15.41% | 0.8448–0.8464 |
| selective/full | business_CPU | +1.02% | 0.9254–1.0527 |
| selective/full | p95_ms | +2.12% | 0.9365–1.0630 |
| selective/original | business_CPU | +45.16% | 1.2932–1.6137 |
| selective/original | p95_ms | +131.53% | 2.2604–2.6001 |
| mirrortaint/original | business_CPU | +54.74% | 1.3904–1.6635 |
| mirrortaint/original | p95_ms | +125.11% | 2.0938–2.3317 |
| selective/mirrortaint | batch_bytes | +531.42% | 6.3141–6.3143 |
| selective/mirrortaint | offline_core_CPU_s | +16220.24% | 145.8562–172.8873 |
| selective/mirrortaint | offline_CPU_s | +5856.43% | 52.6547–62.5866 |
| selective/mirrortaint | offline_wall_s | +5847.23% | 51.5363–62.5052 |
| selective/mirrortaint | offline_VmHWM_MiB | +284.04% | 3.8350–3.8517 |
| selective/mirrortaint | business_CPU | -6.99% | 0.8726–1.0027 |
| selective/mirrortaint | p95_ms | +7.63% | 0.9930–1.1391 |

| 离线阶段墙时，五轮中位数 s | full | selective | MT |
| --- | ---: | ---: | ---: |
| decode_complete_capture | 0.5586 | 0.4860 | 0.0512 |
| required_source_protocol | N/A | N/A | 0.0008 |
| independent_raw_fact_index_and_pairing | 0.1100 | 0.0250 | 0.0007 |
| native_tag_decode | N/A | N/A | 0.0793 |
| export | 0.0086 | 0.0091 | 0.0045 |
| independent_score_raw_index | 0.0027 | 0.0018 | 0.0025 |
| reconstruction_with_required_certificates | 14.3409 | 12.7708 | N/A |
| query | 0.0589 | 0.0056 | N/A |

## 静态规划

| 任务，五次 fresh-exec 中位数 | 进程墙时 s | 进程 CPU s | 进程内规划 s | 当前 exec VmHWM MiB |
| --- | ---: | ---: | ---: | ---: |
| orders | 0.0583 | 0.0578 | 0.0069 | 26.2695 |
| mall | 3.2586 | 3.2533 | 3.1918 | 212.5156 |
| zlt-client | 0.2141 | 0.2116 | 0.1590 | 47.6367 |
| zlt-user | 0.1612 | 0.1607 | 0.1110 | 41.6992 |

## 口径和限制

full/selective 共享工程开关、索引、协议编码和所有必要证书／来源／绑定／完整性核验。新增值投影开／关是本轮独立短消融；此前局部性证书关闭的精度消融单独保留，本轮没有重跑成正式便宜参照。不能拿丢失答案的配置比较同答案成本。没有压缩协议或少导出诊断来冒充目标剪枝。

事件与字节只按实际 Frame、调用、消息及明确父关系归属，不凭 trace-id、值或可见时间窗猜配。未配对／共享记录保留；可归属量不是全部稳态写入。协议 JSON 与全部 capture 文件分列，后者还包含 MT 诊断和 class dump，均不是最大磁盘 I/O。

离线核心：TF 为必要核验、依赖还原及目标查询；MT 为相应原生标签解码。它们不是相同操作。完整正常进程 CPU、墙时及当前 exec VmHWM 同时报告；独立事实索引／评分、解码／核验、导出阶段在每轮 JSON 中分别保存，不混称核心。计数复用同一次图构建，没有追加完整证书审计或第二次还原。

静态规划每任务五次 fresh-exec、固定逻辑 CPU。计时含模型 JSON 载入及实际规划；排除原 JAR 提取、初次依赖清单／JDK探针、Agent编译及服务启动，不能叫完整冷启动建模成本。OS页缓存未清空。

本轮只有单目标接口，未将多次单字段部署相加称多目标实验。MT 即使导出多个字段，每部署也只评分同一固定任务；其他导出及必要适配成本仍计入。未回答的新应用任务不参加性能排名，其失败由能力表完整保留。

相对原版和相对 MT 的在线开销、绝对 CPU 与延迟均如表；收益范围跨 1 时不能称稳定改善。不能由专用 Orders 的局部收益概括统一内核，不能将共同工程或独立评分提速算成选择性贡献。

配置表是五次部署各指标的中位数；配对表是同轮比值的中位数，不能用前者相除替代。通过在线约束不等于在线稳定加速：Mall及ZLT的若干CPU／p95范围仍跨1。Orders整批字节缩减主要来自未归属／共享部分，可归属测量字节只小幅减少；不将整批57.74%说成每个目标请求少采57.74%。

最终完整性审计核对111项核心源码、23份公共契约、10份计量源码、1774份新应用首次文件和1746份复用Mall文件；80份资源汇总与原始样本严格相同。首次派生审计误写构建器文件名，其失败目录保留，修正只在审计驱动。最终审计与交付源码见 `delivery-integrity-04/`；03之后只补充报告的时间顺序说明及跨配置业务JAR哈希复核，没有改测量、评分或算法。

本批备份位置为 `artifacts/backups/target-closure-20261103/`，CRC和SHA256以[备份回执](target-observation-backup-receipt-20261103.json)为准。保留符号链接及其外部引用清单，旧JDK／依赖和历史捕获继续使用原备份，不将本批归档称为全部历史工件的独立包或异机备份。

全部逐轮原始值、源坐标／答案、环境与镜像、静态计划、当前 exec 内存、失败及校准见 `/home/wujian/tracefusion2/artifacts/target-closure-revision-20261103/common-cost-01`。原始与派生结果分目录；算法、驱动、评分和报告分别锁定哈希。未 push。
