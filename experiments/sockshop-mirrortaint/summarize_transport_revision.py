#!/usr/bin/env python3
"""Publish source-backed final summaries after every acceptance gate passes."""
import argparse,csv,io,json,shutil
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save,sha


def summarize(capability,cost):
    a=load(capability/'capability-audit/audit.json');c=load(cost/'cost-audit.json');u=load(ROOT/'artifacts/heldout29-first-20261023/audit-final-reviewed/audit.json')
    assert a['all_passed']and c['all_passed']and load(cost/'pipeline-complete.json')['all_passed']
    s=c['summary'];p=c['paired'];ratio=lambda pair,key:f"{(p[pair][key]['median']-1)*100:+.2f}%";span=lambda pair,key:f"{p[pair][key]['min']:.4f}–{p[pair][key]['max']:.4f}"
    graph=load(cost/'graph-work-audit.json');assert graph['all_passed']and load(cost/'figures/sources.json')['SVG_XML_semantics_preserved']
    cost_text=(cost/'results.md').read_text().replace('本报告所在工件目录',f"`{cost.relative_to(ROOT)}`").replace('逐轮表见deployments.csv','逐轮表见[CSV](transport-cart-cost-deployments-20261023.csv)')
    gm=graph['medians'];extra=f"整批图节点中位数：full {gm['full']['nodes']:.0f}、selective_base {gm['selective_base']['nodes']:.0f}、selective {gm['selective']['nodes']:.0f}。来源边界节点均{gm['full']['source_boundary_nodes']:.0f}、执行结果节点均{gm['full']['execution_result_nodes']:.0f}、依赖边均{gm['full']['edges']:.0f}；相差{gm['full']['nodes']-gm['selective']['nodes']:.0f}个非目标响应节点。此处包含准备/预热，不作为额外评分目标。"
    cost_text+='\n## 图工作量解释\n\n'+extra+'\n\n当前infer_distributed_fields.py的alias会为非目标序列化字段重复扫描binding-return记录。字段输出投影减少了这些非目标节点及连接工作，分阶段结果与这一结构相符；未单独剖析该函数的时间占比，不能把3.25%字节缩减解释为执行重放本身快一倍，也不能假定该比例适用于索引优化后的还原器。复算脚本为diagnose_transport_graph_work.py，逐轮计数见工件graph-work-audit.json。\n\n![五配置原始部署点与中位数](transport-cart-cost-20261023.png)\n\n[SVG导出](transport-cart-cost-20261023.svg)；图中每个点是一份独立部署，没有置信区间。\n'
    (HERE/'TRANSPORT-CART-COST-20261023.md').write_text(cost_text)
    for suffix in ('png','svg'):shutil.copyfile(cost/'figures'/('cart-transport-ablation.'+suffix),HERE/('transport-cart-cost-20261023.'+suffix))
    csv_source=(cost/'deployments.csv').read_bytes();csv_dest=HERE/'transport-cart-cost-deployments-20261023.csv';csv_dest.write_bytes(csv_source.replace(b'\r\n',b'\n'))
    assert list(csv.reader(io.StringIO(csv_source.decode())))==list(csv.reader(io.StringIO(csv_dest.read_text())))
    save(cost/'delivery-csv-audit.json',{'all_passed':True,'raw_sha256':sha(cost/'deployments.csv'),'delivery_sha256':sha(csv_dest),'only_CRLF_to_LF':True,'parsed_rows_identical':True})
    small={k:v for k,v in c.items()if k not in ('trials','scope_checks')};save(HERE/'transport-cart-cost-results-20261023.json',small)
    rows=['# TraceFusion 2：冻结后覆盖与公平观测消融进展','','本轮完成29个未测字段的首次覆盖、Cart证据分解、共享传输核验清理及查询输出投影、同版本能力保持复验和新的五配置成本实验。推送由用户完成。','','## 当前方法','',
      '输入为原版业务JAR、入口、目标响应字段/Map条目及来源边界。静态分析绑定实际返回结构，沿有限控制流和调用图生成保守观测计划；复制、归约等profile保留快速路径，统一执行内核处理当前支持的调用、循环、容器、数组、lambda和有限框架效果。公共库契约仍需人工审阅和版本/类哈希核验。',
      'Java Agent记录事实：实际Frame/调用及实现、实参/返回、对象字段和写入版本、元素位置与阶段、分支/异常、解码/序列化及通信坐标。来源集合在离线计算；还原器按原字节码和实际路径维护依赖状态，再用具体W3C调用span与JSON路径连接跨服务字段实例。相同数值不用于猜来源，返回快照不充当新来源。',
      '必要语义不透明保留unknown；证据缺失或矛盾保留evidence_invalid；完整证据下预算耗尽为analysis_limited；业务未生成目标为N/A。已证明的空来源与unknown不同。当前仍是Java及声明模型范围的方法，没有任意语言或任意Java程序的完备性保证。',
      '最新变化见[算法](TRANSPORT-OBSERVATION-ALGORITHM-20261023.md)：full/selective共同删除不消费的服务端响应出站请求证明；selective再投影持久化目标字段。前后完整声明投影仍采集并核验，应用帧、调用、字段写入、容器和异常观测未切片，不能把工程清理当查询选择性收益。','','## 首次未测字段覆盖：核心76d2050','',
      '91个候选中62个已用于开发，剩余29个在任何新规划/执行前固定协议dfd9195，随后全部纳入。它们来自8个旧入口，属于旧入口新字段，不是新入口盲测。业务JAR和核心不改，未因失败替换查询。','',
      '| 应用 | 规划接纳 | 实际目标 | TF正确 | TF unknown | 真值不足 |','| --- | ---: | ---: | ---: | ---: | ---: |',
      '| Sock Shop | 7/7 | 30 | 18 | 12 | 12 |','| Train Ticket | 22/22 | 214 | 214 | 0 | 0 |','| 合计 | 29/29 | 244 | 232 | 12 | 12 |','',
      'full/selective相同：正确可回答率232/244＝95.08%，已知答案232/232匹配，24/29查询族至少一个正确答案。190次查询请求中41次未生成目标。TP225/FP0/FN0仅针对真值充分目标，不能据此说全部244个目标无漏检。',
      '新固定配置MirrorTaint为210正确、17错误、5unknown、12个已知但真值不足的答案。可核验的210个基线正确目标全部被TF正确回答，另17个错误和5个unknown由TF正确回答；剩余12个无法判断双方能力优劣。原作者传播JAR与固定适配器二进制不变，仅隔离导出器私有Jackson，8个当前入口的原生Mapper定义均核验。未据此声称全部旧62查询的基线已在新配置复验。',
      '12个TF unknown来自Orders生成ID与self-link派生customerId，独立物理坐标尚不足。两个始终空的关联列表与TicketInfo未产字段单列N/A。Route的_id评分键修正在独立目录复算，首次评分与原始失败都保留，不记作算法提升。',
      '一个代表差异是同值距离列表：基线把实际位置1连到位置0，TF保留容器与元素位置坐标；另一个是Basic字段来源标签丢失。结论限于固定适配器与本任务粒度，详细表见[首次报告](HELDOUT29-FIRST-20261023.md)。','','## 最终观测版本能力保持','',
      f"冻结 `{a['algorithm_commit']}`，同一新Agent实际运行126个目标JVM配置。full/selective各428/431正确（99.30%）、3unknown、0错误确定答案；TP397/FP0/FN3（计unknown）。两模式431个目标逐项状态一致。",
      '与76d2050逐项对照，所有428个正确状态及独立来源签名保持，3个unknown保持；历史固定MirrorTaint正确368/368、旧TF正确213/213及联合382/382都保留。实际原版Mapper、9个原业务JAR和Agent类字节核验。854类中仅Transport类改变，执行计划除传输策略外与父版完全一致。',
      '15项策略检查、实际Jackson嵌套绑定/同值自定义serializer拒绝、调用/数组/lambda、Date/Mongo、集合修改及真实HTTP保护通过。期望unknown保护不计作来源准确率。旧HTTP控制程序清空实际Frame的真值错误在单独目录修正。',
      '新版本没有新增语义能力，也不把已启封29个查询再次当未见证据。原3个Cart新建商品依赖缺口保持。','','## 新Cart成本：先分公共清理，再看查询专门化','',
      '五配置各五轮，25次随机顺序独立部署、顺序运行；每次预热30秒、测量60秒、2请求/秒、并发2，业务JVM32/256MiB、GC1/CI2，1CPU/768MiB，Mongo1CPU/384MiB。来源配置各900请求、1350/1350来源正确；性能只用600个测量请求。全部成本来自最终版本新捕获。','',
      '| 指标 | 公共清理 full/旧full | 读取位点 selective_base/full | 输出投影 selective/selective_base | 严格selective/full | 严格逐轮范围 |','| --- | ---: | ---: | ---: | ---: | --- |']
    for key,label in [('capture_events','稳态事件'),('capture_bytes','稳态原始字节'),('offline_core_seconds','整批离线核心'),('offline_child_cpu_seconds','离线CPU'),('offline_child_peak_rss_bytes','离线VmHWM'),('online_cpu_percent','在线JVM CPU'),('p95_ms','在线p95')]:
        pairs=('full/full_legacy','selective_base/full','selective/selective_base','selective/full');rows.append('| '+label+' | '+' | '.join(ratio(v,key)for v in pairs)+' | '+span('selective/full',key)+' |')
    rows+=['',f"相对无来源输出的原版，最终selective的配对中位数：p95 {ratio('selective/original','p95_ms')}，在线CPU {ratio('selective/original','online_cpu_percent')}。原版/最终selective的JVM CPU绝对中位数为单核{s['original']['online_cpu_percent']['median']:.3f}% / {s['selective']['online_cpu_percent']['median']:.3f}%；p95为{s['original']['p95_ms']['median']:.3f} / {s['selective']['p95_ms']['median']:.3f}ms。相对与绝对数值均需保留，配对比值不能用汇总中位数相除替代。",
      '这是顺序消融，每项收益条件于参照配置，不相加百分比。严格full/selective共享方向清理及必要验证。临时快照依然完整，字段投影主要减少持久化与离线节点；这不是通用执行切片完成的证据。',
      extra,
      '为什么字节只减少3.25%，离线核心却减少49.63%：当前alias实现会为非目标序列化字段重复扫描binding-return记录，投影减少了这些节点及连接工作。计数与阶段时间支持这一解释，但未隔离该函数耗时，不能称执行重放本身快了一倍；索引优化后的还原器需要另做公平验证。公共清理的在线CPU点估计反而增加18.91%、逐轮范围跨1，也不宣称CPU收益。',
      'CPU/p95以五轮比值范围描述，范围跨1的项目不能称稳定改善；不宣称显著性、最大吞吐或跨机器普适优势。2rps完成仅说明当前固定负载完成。p99每轮仅120个请求，作描述。离线处理含预热和准备证据；20次fresh-exec VmHWM复算含评分及导出，不是算法核心单独峰值。5次固定CPU规划计量与部署计划完全一致。批次答案等待含剩余窗口和关闭流程，不是固有流式延迟。',
      '早期423199f的6次探索采样在发现公共清理被混入选择性收益后停止，完整保留，不进入这25次正式表。成本准备漏建父目录的失败没有业务采样，也保留。完整绝对值与逐轮范围见[新成本报告](TRANSPORT-CART-COST-20261023.md)，事件诊断见[Cart分解](CART-EVIDENCE-DECOMPOSITION-20261023.md)。','','## 历史证据与当前结论边界','',
      'Sock Shop198/198、Station31/31、五服务票价full/selective各38/38等历史业务结果继续按各冻结版本保存；本轮126配置能力结果不能冒充这些路径的新部署。原0/20负结果、多次修订及首次失败不改写。',
      '旧共同Orders.total成本比较的TF相对MirrorTaint优势只对应旧固定版本与负载。当前未重新校准外部工具的最终版本成本，本轮外部成本N/A；Phosphor、FlowDist也未完成本次实例任务成本校准。旧Train/票价成本不填入新版本表。',
      'Log4j仍为受控验证：22个泄露查询TP9/FP0/FN1/TN12，含一个必要helper unknown作为FN；漏洞/缓解/修复各5个用例。没有LDAP、远程加载或RCE；真实Solr仅源码预检，没有新增真实安全路径验证。',
      '下一阶段需要真正的目标相关执行闭包：跨方法返回、字段写入与别名、容器效果、实际异常/成员选择共同决定保守观测范围，不能只删未使用返回值的调用。多查询与跨服务需求合并尚需单独验证；原29已暴露，新的泛化测试必须另建候选。',
      '',f"原始根目录：`{capability.relative_to(ROOT)}`、`{cost.relative_to(ROOT)}` 和 `artifacts/heldout29-first-20261023/`。完整事件、独立真值、冻结计划、镜像digest、环境、命令、首次失败与各轮数据另行备份；Git仅保存小型摘要。"]
    rendered=[]
    for line in rows:
        if line and rendered and rendered[-1]and not line.startswith(('|','#'))and not rendered[-1].startswith(('|','#')):rendered.append('')
        rendered.append(line)
    (HERE/'PROGRESS-20261023.md').write_text('\n'.join(rendered)+'\n')
    save(cost/'final-summary-source.json',{'capability_audit_sha256':sha(capability/'capability-audit/audit.json'),'cost_audit_sha256':sha(cost/'cost-audit.json'),'graph_work_audit_sha256':sha(cost/'graph-work-audit.json'),'figure_sources_sha256':sha(cost/'figures/sources.json'),'heldout_audit_sha256':sha(ROOT/'artifacts/heldout29-first-20261023/audit-final-reviewed/audit.json'),'renderer_sha256':sha(Path(__file__))})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--capability',type=Path,required=True);p.add_argument('--cost',type=Path,required=True);a=p.parse_args();summarize(a.capability.resolve(),a.cost.resolve())
