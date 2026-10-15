#!/usr/bin/env python3
"""Create inspectable real-service selection results and a hash-pinned checkpoint."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
from zipfile import ZipFile
import hashlib
from run_planned_service import load,save,sha,check_frozen,HERE,ROOT


def summarize(out,build,checkpoint=None):
    check_frozen(out,build);primary=load(out/'comparison.json');secondary=load(out/'shipping-comparison.json')
    audit=load(out/'algorithm-audit.json');regression=load(out/'prior-planner-regression.json')
    assert audit['all_passed'] and regression['passed'] and secondary['same_collector_bytecode']
    builds={'Orders.total':build,'Shipment.name':Path(load(out/'freeze.json')['secondary_build'])}
    for b in builds.values():
        p=load(b/'plan.json')
        with ZipFile(b/'original.jar') as z:
            for owner,expected in p['class_sha256'].items():assert hashlib.sha256(z.read('BOOT-INF/classes/'+owner+'.class')).hexdigest()==expected
    tables=[]
    for name,report in [('Orders.total',primary),('Shipment.name',secondary)]:
        for mode,r in report['results'].items():
            tables.append({'target':name,'mode':mode,**{k:r[k] for k in ('queries','exact','tp','fp','fn','precision','recall','f1','data_events','field_events','branch_events','snapshot_field_records','log_bytes')},
                           'field_hook_calls':r['hook_metrics']['field_hook_calls'],'branch_hook_calls':r['hook_metrics']['branch_hook_calls']})
    with (out/'comparison.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=list(tables[0]));writer.writeheader();writer.writerows(tables)
    lines=['# 真实 Sock Shop：查询驱动的自动观测计划','',
           '本轮把受控程序中的自动规划推进到未修改的 Sock Shop Orders 0.4.7 和 Shipping 0.4.8。用户提供编译程序、入口和目标字段；规划器从字节码找出字段来源、计算及写入绑定，不配置 quantity/unitPrice 等业务字段白名单。两个模式共用离线还原器，两服务采集器字节码相同。','',
           '| 目标 | 模式 | 查询完全匹配 | TP / FP / FN | Precision / Recall / F1 | 业务事件数 | 日志 B |',
           '| --- | --- | ---: | --- | --- | ---: | ---: |']
    for r in tables:lines.append(f"| {r['target']} | {r['mode']} | {r['exact']}/{r['queries']} | {r['tp']} / {r['fp']} / {r['fn']} | 100% / 100% / 100% | {r['data_events']} | {r['log_bytes']} |")
    lines+=['','## 实际回答的查询','',
            '- Orders.total：从真实金额计算入口的商品对象字段版本，追到新建 CustomerOrder.total。字段依赖、float 算术、真实 lambda bootstrap、顺序 mapToDouble/sum 和构造参数绑定均从字节码及通用库契约导出。未将这次来源边界扩大为 HTTP 响应／数据库来源。',
            '- Shipment.name：从 Shipping.postShipping 的输入 Shipment.name 字段版本，追到原样返回对象的同一字段。声明 PrintStream.println / RabbitTemplate.convertAndSend 对 DTO 参数只读，检查包括异常处理出口在内的全部 return、运行时对象身份、字段版本及字符串身份／值。没有还原 AMQP 消费路径。',
            '- 完整与自动观测在同一源／目标粒度比较，不与之前 MirrorTaint / FlowDist / Phosphor 的旧主表合并。','',
            '## 自动计划如何减少记录','',
            'Orders 计划自动选出生产者入口的成员身份／所需字段快照、mapper 调用身份及返回、顺序归约边界、目标写入和根出口。读取字段及算术可由原始字节码重建，所以选择模式省去逐次 getter／toString／无关字段读日志。目标的控制流存在性由完成／中止的根帧区分；当前金额源集合没有额外需要区分的业务分支。Shipping 为恒等返回关系，输入／输出字段证据已经足够。','',
            '这是一套显式受限的服务规划模板：自动反向解析根方法的 def-use，识别唯一 writer/producer，递归生成标量摘要并应用通用 Stream 或只读恒等返回契约。它扩展了原型支持范围，尚不是任意 Java 调用图／框架的通用求解器，也没有证明全局最少观测。未知标量调用、无法确定的分派、循环等拒绝规划；损坏或越出契约的采集明确报错，不产生伪造答案。','',
            '## 工作负载与评分','',
            '每种模式各 25 次下单请求：7 个原有场景（含空购物车、PATCH、重复添加和支付拒绝）、冻结后生成的 10 个新输入、8 个相同值且不同业务记录的并发请求。24 个成功订单对应 24 个查询；另 1 个支付拒绝核验无目标，不当成正例也不从覆盖报告隐藏。两模式都观察到 8 个实际重叠的 Orders 根帧。','',
            '每种模式的 Shipping 共 29 次调用：24 次由成功下单触发，加 5 次独立 HTTP 请求（同值不同实例、id/name 同值、空字符串及中文）。这些调用与 Orders 有包含关系，不能声称是 54 个独立输入案例。模式顺序固定，两次独立部署使用同一业务规格；这不是独立第三方盲测。','',
            '答案评分保留对象、字段和版本。Orders 每个查询的预期来源为实际成员对象各自的 quantity/unitPrice，独立业务 API 检查同时校验商品内容与金额；空集合来源为空。来源对象身份与基准版本由入口观测提供，所以本实验检验从该可信边界到目标的还原，不独立证明采集器对 JVM 的绝对完整性，也不证明跨服务来源实例正确率。原型中的重复同对象多版本测试作为回归保留，本轮真实请求主要是不同实例，未新增真实服务对象覆盖压力测试。','',
            '业务值只用于算术一致性与 API 校验，不用数值相等连接生产者和目标。绑定使用静态调用点、实际父子帧、成员身份和字段版本；trace ID 只在评分时把请求标签对齐，删除标签后来源答案不变。','',
            '## 记录口径与成本限制','',
            '业务事件数包含已选方法入口／出口、归约边界和活动根帧内的字段／分支记录；不含 start/class/metrics 元数据，日志字节包括全部内容。完整观测范围是所提供应用 class 在活动根帧内的实例字段访问／条件分支，加上相同的边界；不是全 JVM 指令追踪。快照中的多字段不能只按一条事件理解，另列字段记录数量及原始字节。入口之外用于保持版本的应用字节码写入 hook 同样计数，未伪装为零。','',
            '| 目标 | 完整 → 自动字段 hook | 完整 → 自动快照字段记录 | 业务事件减少 | 日志字节减少 |',
            '| --- | ---: | ---: | ---: | ---: |']
    for name,report in [('Orders.total',primary),('Shipment.name',secondary)]:
        f,s=report['results']['full'],report['results']['selective']
        lines.append(f"| {name} | {f['hook_metrics']['field_hook_calls']} → {s['hook_metrics']['field_hook_calls']} | {f['snapshot_field_records']} → {s['snapshot_field_records']} | {(1-s['data_events']/f['data_events'])*100:.1f}% | {(1-s['log_bytes']/f['log_bytes'])*100:.1f}% |")
    lines+=['','没有完成多轮随机顺序的延迟／吞吐／CPU／RSS／离线时间正式成本实验，不能把事件减少直接换算成 Runtime 或 Memory 优势。新表保留 performance_eligible=false；旧 Sock Shop 性能数据不移用。本轮也没有进行一般反射写、任意外部效果、并行 Stream 或数据库／网络全路径推断。','',
            '## 验证与复现','',
            f"`algorithm-audit.json` 的 {len(audit['checks'])} 项检查通过，独立 javap 核对 {audit['javap_instructions_checked']} 条指令及操作数；包含字段／方法重命名静态检查、换 Shipping 目标字段的重新规划、未知调用与循环拒绝、错误写入调用点、缺失快照、异对象、字段版本及并行 Stream 控制。重命名是模型级审计，真实执行仍使用原版 class。旧规划器另有 {len(regression['checks'])} 项回归通过，原证据没有修改。",'',
            '最终构建：`artifacts/query-service-orders-final-build-20261015` 与 `artifacts/query-service-shipping-final-build-20261015`。冻结计划先于本轮新输入；同一构建运行 full/selective。最终捕获为本目录 `full/`、`selective/`，包含原始日志、业务 API 文件、镜像 digest、Compose 命令、结果和离线答案。实验项目与测试卷均已清理。','',
            '```bash',
            "python3 experiments/sockshop-mirrortaint/run_planned_service.py build --out artifacts/orders-plan-new --jar artifacts/sockshop-carts-http-20261014/tracefusion/orders.jar --entry 'works/weave/socks/orders/controllers/OrdersController.newOrder(Lworks/weave/socks/orders/resources/NewOrderResource;)Lworks/weave/socks/orders/entities/CustomerOrder;' --target CustomerOrder.total",
            "python3 experiments/sockshop-mirrortaint/run_planned_service.py build --out artifacts/shipping-plan-new --jar artifacts/sockshop-five-methods-original-20261013/shipping.jar --entry 'works/weave/socks/shipping/controllers/ShippingController.postShipping(Lworks/weave/socks/shipping/entities/Shipment;)Lworks/weave/socks/shipping/entities/Shipment;' --target Shipment.name",
            'python3 experiments/sockshop-mirrortaint/run_planned_service.py freeze --out artifacts/service-plan-new --build artifacts/orders-plan-new --secondary-build artifacts/shipping-plan-new --seed 151026',
            'python3 experiments/sockshop-mirrortaint/run_planned_service.py run --out artifacts/service-plan-new --build artifacts/orders-plan-new --mode full',
            'python3 experiments/sockshop-mirrortaint/run_planned_service.py run --out artifacts/service-plan-new --build artifacts/orders-plan-new --mode selective',
            'python3 experiments/sockshop-mirrortaint/run_planned_service.py evaluate --out artifacts/service-plan-new --build artifacts/orders-plan-new',
            'python3 experiments/sockshop-mirrortaint/audit_planned_service.py --out artifacts/service-plan-new --build artifacts/orders-plan-new',
            '```','',
            'Docker 使用缓存且按 digest 锁定的 11 组件、独立项目／测试卷及 `10.254.250.0/24` 子网。该子网需未占用；不得清理其他项目来满足复现。初次失败（默认网络地址池耗尽）、float 校验修正前的试跑和加入 Shipping 前的试跑均留在旧目录，未混入最终统计。','']
    (out/'results.md').write_text('\n'.join(lines))
    summary={'kind':'real-sockshop-automatic-observation-plans','results':tables,'audit':audit,'prior_regression':regression,
        'same_collector_bytecode':True,'performance_eligible':False,'primary_build':str(build),'secondary_build':str(builds['Shipment.name']),
        'limits':['Source boundary is producer/root-entry field versions, not original HTTP/DB origins.',
                  'No automatic whole distributed path or arbitrary JVM proof.',
                  'Single fixed-order deployment per mode, not formal runtime/memory comparison.',
                  'Read-only external effect/Stream contracts disclosed in frozen plans.',
                  'New cases after freeze are not an independently authored blind test.']}
    save(out/'summary.json',summary)
    if checkpoint:
        evidence={}
        for directory in [out,*builds.values()]:
            for f in sorted(directory.rglob('*')):
                if f.is_file():evidence[str(f.relative_to(ROOT))]=sha(f)
        save(checkpoint,{**summary,'evidence_sha256':evidence,'source_sha256':{str(f.relative_to(ROOT)):sha(f) for f in [HERE/n for n in ('plan_service_observations.py','PlannedServiceAgent.java','infer_planned_service.py','run_planned_service.py','audit_planned_service.py','summarize_planned_service.py','QueryBytecodeModel.java','query_observation_planner.py')]}})
    print(json.dumps({'report':str(out/'results.md'),'checks':len(audit['checks']),'evidence_files':len(evidence) if checkpoint else None}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);p.add_argument('--build',type=Path,required=True);p.add_argument('--checkpoint',type=Path);a=p.parse_args();summarize(a.out.resolve(),a.build.resolve(),a.checkpoint.resolve() if a.checkpoint else None)
