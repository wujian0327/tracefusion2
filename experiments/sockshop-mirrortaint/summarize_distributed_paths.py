#!/usr/bin/env python3
"""Source-backed cross-application path report and evidence checkpoint."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
from run_planned_service import HERE,ROOT,load,save,sha
from run_distributed_paths import check


def summarize(out,build,checkpoint=None):
    if load(build/'build.json').get('transport_protocol')=='w3c-trace-context':
        raise ValueError('Use compare_w3c_paths.py for W3C captures; this report describes the legacy UUID experiment.')
    check(out,build);audit=load(out/'algorithm-audit.json');assert audit['all_passed']
    image_check=load(out/'original-image-verification.json');assert image_check['all_matched']
    prior=[load(out/'controlled-regression.json'),load(out/'service-regression.json')]
    assert prior[0]['passed'] and prior[1]['all_passed']
    s=load(out/'sockshop/field-results.json');t=load(out/'trainticket/field-results.json');info=load(build/'build.json');rows=[]
    families=[('Sock Shop','Carts.quantity/unitPrice → Orders.total',s['query_families']['total']),
              ('Sock Shop','Carts.itemId/quantity/unitPrice → Orders returned items',s['query_families']['returned_item_fields']),
              ('Sock Shop','Orders Shipment.id/name → Shipping → Orders returned shipment',s['query_families']['shipping_roundtrip']),
              ('Train Ticket','Station.id → Response.data → Basic → TicketInfo.data',t['summary'])]
    for app,path,r in families:rows.append({'application':app,'path':path,**r})
    with (out/'main-table.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    graphs={a:load(out/a/'inference-graph.json') for a in ('sockshop','trainticket')}
    unknown=Counter((n['service'],n['field'],n['unknown']) for g in graphs.values() for n in g['nodes'] if n.get('unknown'))
    limitations=[
        'Only selected paths under explicit bytecode/default-Jackson/HTTP contracts; not arbitrary JVM programs or all application fields.',
        'Carts source boundary is its response field observation, excluding its database history. Shipment source boundary is the outgoing Orders DTO, excluding upstream customer-id computation.',
        'Train Ticket source boundary is a decoded Station entity getter read, not Mongo storage provenance; missing-station constant null is modeled from actual bytecode.',
        'Object/declared-field/application-write count plus observation/message instance is scored; counters are not complete JVM/reflective store histories or database versions.',
        'One common JVM observer/reconstructor with explicit generic framework/library models. Query endpoints and workload oracles remain application-specific configuration.',
        'New observations retain admitted DTO transport properties; transport-point minimization and new formal runtime/memory comparisons are deferred.',
        'No new MirrorTaint/FlowDist/Phosphor measurements; these results do not establish superiority over external methods.',
        'Pinned original Train Ticket image digests/JAR/class hashes; corresponding upstream Git commit not independently established.',
        'New random inputs generated after implementation/plan freeze are not an independently authored blind benchmark.']
    lines=['# 扩大真实路径与第二应用迁移（2026-10-15）','',
           '在同一冻结 JVM 观测器与离线还原器上，完成 Sock Shop 的字段跨服务扩展，以及 Train Ticket 镜像版 0.2.0 的第二应用迁移。磁盘上的业务 JAR 与插桩前 class 保持原版；agent 运行时插入观测，不改业务算法。不同服务仅提供 JAR、入口和目标字段；字段复制、构造参数、getter 来源、Stream 计算、JSON 属性模式均从原始字节码及通用框架模型生成。','',
           '| 应用／路径 | 完全匹配 | TP / FP / FN | Precision / Recall / F1 | unknown |',
           '| --- | ---: | --- | --- | ---: |']
    for row in rows:lines.append(f"| {row['application']}：{row['path']} | {row['exact']}/{row['queries']} | {row['tp']} / {row['fp']} / {row['fn']} | 100% / 100% / 100% | {row['unknown']} |")
    lines+=['','Sock Shop 合计 198/198 个目标字段查询完全匹配，TP=258、FP=0、FN=0。Train Ticket 为 31/31，TP=30、FP=0、FN=0；其中一个查询验证不存在站点后写入的常量 null，其正确来源为空。Precision/Recall/F1 均为当前已声明关系口径下的 100%，不是全应用、全路径准确率。','',
            '## 实际跨进程路径','',
            '```mermaid','flowchart LR','  C[Carts 商品字段] -->|HTTP response| O[Orders 解码商品对象]','  O --> A[金额计算与 total]','  O --> I[返回商品字段]','  S[Orders Shipment 字段] -->|HTTP request| H[Shipping 同一对象字段]','  H -->|HTTP response| R[Orders 返回 shipment 字段]','  E[Station 实际 entity.id 读取] --> W[Response.data 构造写入]','  W -->|HTTP response| B[Basic Response.data]','  B -->|HTTP response| T[TicketInfo Response.data]','```','',
            '调用发起方向是 TicketInfo→Basic→Station；表中画的是字段从 Station 回传的方向。两次 HTTP 的字段桥接都在真实服务中执行。消息 UUID 在实际请求和响应头传递；JSON pointer、DTO 对象身份、声明字段、应用写计数及具体观测点参与匹配，不以字段值、业务 ID 或 B3 trace 选择来源。相同值仅用于验证已选边的一致性。','',
            '## 无需逐个编写业务答案，具体到哪一步','',
            '共用代码为 SpringTransportAgent.java、plan_distributed_fields.py、infer_distributed_fields.py，以及已有的标量／Stream 规划与还原器。核心新组件没有 Orders、Station、quantity、unitPrice 等应用方法／字段名单。构建器以查询配置选择入口与目标；例如只给 StationServiceImpl.queryForId 和 Response.data，系统自动找到 Station.getId 的字段读取、Response 构造参数和目标写入；Basic 错误分支的 null 也自动导出，没有手填这两条传播答案。','',
            '应用接入仍包含：选择查询、固定原版 JAR/镜像、部署依赖、生成业务输入和独立真值。Spring HTTP、默认 Jackson 属性、顺序 Stream 等契约需要人工实现一次，再跨应用复用。当前只支持有界的标量归约、直接字段复制、同对象同字段版本转发和上述消息边界；这不等于通用自动分析任意代码。不同路径没有各写一个答案生成器，但确实新增了通用 HTTP/JSON 和字段复制模型，不能称完全零适配迁移。','',
            '## 真值、分母与实例','',
            '- Sock Shop：25 次下单，24 次成功、1 次支付拒绝；成功订单包含 42 个商品实例。24 个 total、126 个返回商品字段、48 个 Shipment 往返字段构成 198 个查询；同一请求的字段查询不是独立业务案例。空购物车的 total 为合法空来源，支付拒绝另验证无目标。',
            '- Train Ticket：31 次公开查询，30 次成功与1次不存在站点。重复同值数据、id/name/msg 同值、冻结后新输入和8路并发都保留；成功查询对应30个实际读取实例。不存在站点后 Basic 的常量 null 来源为空。',
            '- 两应用都有8路并发驱动；Train Ticket 的 Basic/TicketInfo 各观察到8个重叠的 HTTP RPC。不同字段／目标评分不合并成字段类型，保留源对象、字段、写计数和源／目标观测点、消息实例。',
            '- 独立真值：Sock Shop 预先冻结公式与业务记录；Train Ticket 独立数据库审计和原版公开 API。原始观测仅为真值提供执行对象/读取点的身份坐标，不通过调用还原器的图搜索来计算预期来源。评分器与还原器分开，业务真值文件不传给还原器。',
            '- 另有72条补充负关系检查：42条 Carts.itemId 不进入 total、30条 Station.name 不进入 data；含同值非来源。它们没有混入229个目标实例查询的分母，负例的字段角色投影也不冒充额外实例准确率。','',
            '## 证据不足与支持边界','',
            '本轮没有为了全100%删掉已指定的困难查询：支付拒绝／空集合／null均在固定协议中处理。但选定查询集合本身是受支持路径，不代表任意字段都支持。另在全量保留的背景观察中出现43个 Carts Item.id（数据库标识，区别于 itemId）回写点：值在未计数的框架写入后变化，无法按只读转发连接，明确保留 unknown。这些位于本轮预先指定来源边界之前，不被包装成已解决的数据库血缘，也没有加入已指定查询的分母。缺失被查询的远端 quantity 观测时，审计确认 total 变为 unknown，不能回退用值或业务公式补答案。','',
            '边界详细如下：','']
    lines += ['- '+v for v in limitations]
    lines+=['','应用写计数不能涵盖任意反射／native 写入；具体消息／观测点也保留为来源实例的一部分。只在声明的只读或明确建模区间内连边，值发生未建模变化时不生成转发边。未支持自定义 Jackson 属性映射／序列化、任意 Map/数组、反射共享可变对象、并行 Stream 或 Mongo 内部来源推断。','',
            '## 验证、工件与复现','',
            f"13项新审计全部通过，独立 javap 核验 {audit['independent_javap_instructions']} 条指令及操作数。包括六个计划重新生成、原版 class hash、调用上下文、字段重命名、缺来源变 unknown、错误消息响应／同值异请求上下文／属性路径拒绝、去掉 trace 与父消息审计标签后来源不变。旧受控规划器13项、旧真实服务19项回归也通过（在临时副本运行，原证据不变）。",'',
            '正式构建 `artifacts/distributed-plans-final-build-20261015` 的一个 observer JAR 被两个应用的六个 JVM 服务共同使用；原版镜像 digest、JAR SHA、额外依赖类来源及 class SHA 保留。另从六个 digest 锁定镜像重新只读复制原 JAR，6/6 与分析／运行 JAR 的 SHA-256 一致，见 original-image-verification.json。Sock Shop 使用原11组件，Train Ticket 使用原 Station/Basic/TicketInfo 与独立 Mongo。Station 写接口要求管理员，本实验只初始化自己的新建数据库测试卷后调用原版公开读 API，不改鉴权或业务代码。Train Ticket 的 Git 提交尚未反查，不以镜像标签冒充源码提交。','',
            '冻结同一采集器、规划器、还原器与计划后，用 seed=151031 生成正式新增输入。早期装箱观察修正、受保护健康检查和管理员写入接口的失败尝试保留在 pilot 目录，不混入主表。两个正式项目及测试数据卷均已清理。','',
            '本目录的 sockshop/、trainticket/ 各包含原始事件、Compose/镜像、API文件、执行真值、inference-graph.json、field-results.json。main-table.csv 为路径表，summary.json 为摘要；algorithm-audit.json 与两个 regression JSON 为检查。','',
            '```bash',
            'python3 experiments/sockshop-mirrortaint/build_distributed_plans.py --out artifacts/paths-build-new --inputs artifacts/real-path-expansion-preflight-20261015/queries.json',
            'python3 experiments/sockshop-mirrortaint/run_distributed_paths.py freeze --out artifacts/paths-run-new --build artifacts/paths-build-new --seed 151031',
            'python3 experiments/sockshop-mirrortaint/run_distributed_paths.py sockshop --out artifacts/paths-run-new --build artifacts/paths-build-new',
            'python3 experiments/sockshop-mirrortaint/run_distributed_paths.py trainticket --out artifacts/paths-run-new --build artifacts/paths-build-new',
            'python3 experiments/sockshop-mirrortaint/evaluate_distributed_paths.py --out artifacts/paths-run-new --build artifacts/paths-build-new',
            'python3 experiments/sockshop-mirrortaint/audit_distributed_paths.py --out artifacts/paths-run-new --build artifacts/paths-build-new',
            '```','',
            '新部署复用原镜像/JAR缓存、固定11组件/4组件依赖、回环端口18580–18583及18600–18602、未占用的10.254.249.0/24子网；只清理本次独立随机项目。两应用顺序执行，不共享测试卷。性能比较和“目标依赖范围完整观测”仍按用户要求暂缓，没有混入本次路径迁移结论。','']
    (out/'results.md').write_text('\n'.join(lines))
    summary={'kind':'real-cross-service-paths-and-second-application-transfer','results':load(out/'comparison.json'),'families':rows,
        'query_specification':{k:v['query_config'] for k,v in info['inputs'].items()},'audit':audit,
        'regression_checks':{'controlled':len(prior[0]['checks']),'real_services':len(prior[1]['checks'])},
        'background_unknown_observations':[{'service':k[0],'field':k[1],'reason':k[2],'count':v} for k,v in unknown.items()],
        'collector_sha256':info['agent_sha256'],'original_image_jars_matched':len(image_check['records']),'limits':limitations,'performance_eligible':False}
    save(out/'summary.json',summary)
    if checkpoint:
        evidence={}
        for directory in [out,build]:
            for p in sorted(directory.rglob('*')):
                if p.is_file():evidence[str(p.relative_to(ROOT))]=sha(p)
        for name in ('images.json','queries.json'):
            p=ROOT/'artifacts/real-path-expansion-preflight-20261015'/name;evidence[str(p.relative_to(ROOT))]=sha(p)
        sources=[HERE/n for n in ('SpringTransportAgent.java','plan_distributed_fields.py','build_distributed_plans.py','infer_distributed_fields.py','run_distributed_paths.py','evaluate_distributed_paths.py','audit_distributed_paths.py','summarize_distributed_paths.py','verify_original_path_images.py','PlannedServiceAgent.java','QueryBytecodeModel.java','plan_service_observations.py')]
        save(checkpoint,{**summary,'evidence_sha256':evidence,'source_sha256':{str(p.relative_to(ROOT)):sha(p) for p in sources}})
    print(json.dumps({'report':str(out/'results.md'),'queries':s['summary']['queries']+t['summary']['queries'],'evidence_files':len(evidence) if checkpoint else None}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);p.add_argument('--build',type=Path,required=True);p.add_argument('--checkpoint',type=Path);a=p.parse_args();summarize(a.out.resolve(),a.build.resolve(),a.checkpoint.resolve() if a.checkpoint else None)
