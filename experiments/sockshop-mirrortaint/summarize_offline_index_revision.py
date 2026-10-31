"""Durable report from unprofiled paired processes, never online extrapolation."""
import csv,json,pstats,statistics
from pathlib import Path
from run_planned_service import HERE,ROOT,load,save

def run(home):
 data=load(home/'paired-cost-v2/paired-cost/results.json')['measurements'];assert len(data)==30
 median=statistics.median;med={};paired={}
 for mode in ('full','selective','mirrortaint'):
  for version in ('old','indexed'):
   rows=[r for r in data if r['mode']==mode and r['version']==version];assert len(rows)==5 and all(r['correct']==r['targets']==180 for r in rows)
   med[mode+'-'+version]={k:median(r[k]for r in rows)for k in ('process_wall_seconds','process_cpu_seconds','core_seconds','VmHWM_KiB')}
   med[mode+'-'+version]['phases']={k:median(r['phases_seconds'][k]for r in rows)for k in rows[0]['phases_seconds']}
  old={r['repeat']:r for r in data if r['mode']==mode and r['version']=='old'};new={r['repeat']:r for r in data if r['mode']==mode and r['version']=='indexed'}
  paired[mode]={}
  for k in ('process_wall_seconds','process_cpu_seconds','core_seconds','VmHWM_KiB'):
   values=[new[i][k]/old[i][k]for i in range(1,6)];paired[mode][k]={'median_change_percent':(median(values)-1)*100,'ratio_range':[min(values),max(values)]}
 selective={r['repeat']:r for r in data if r['mode']=='selective'and r['version']=='indexed'};full={r['repeat']:r for r in data if r['mode']=='full'and r['version']=='indexed'}
 paired['indexed-selective/full']={k:{'median_change_percent':(median([selective[i][k]/full[i][k]for i in range(1,6)])-1)*100,'ratio_range':[min(selective[i][k]/full[i][k]for i in range(1,6)),max(selective[i][k]/full[i][k]for i in range(1,6))]}for k in('process_wall_seconds','process_cpu_seconds','core_seconds','VmHWM_KiB')}
 profiles={}
 for directory in ('profiles-before/full','profiles-before/selective','profiles-before/mirrortaint','profiles-after/full','profiles-after/selective','profiles-final-selective'):
  s=pstats.Stats(str(home/directory/'function.pstats'));profiles[directory]={'calls':s.total_calls,'profiler_seconds':s.total_tt,'functions':[{'file':Path(k[0]).name,'line':k[1],'name':k[2],'calls':v[1],'self_seconds':v[2],'cumulative_seconds':v[3]}for k,v in sorted(s.stats.items(),key=lambda item:item[1][3],reverse=True)[:40]]}
 result={'reference':'c1a4e5ceb60a276cc3651e4cdb413aa29d7f8d5d','shared_optimization_commits':['278896a','2609d70'],'source_freeze':str(home/'offline-index-v2-source-freeze.json'),'no_semantics_or_agent_change_in_cost_snapshot':True,'fresh_processes':30,'complete_captures':15,'paired_targets_per_version':2700,'known_states_and_normalized_origins_equal':True,'medians':med,'paired':paired,'profiles_diagnostic_only':profiles,'online_metrics_unchanged':True,'captures':'Original five rounds; new offline reconstruction only'}
 save(home/'offline-final-summary.json',result);save(HERE/'offline-index-results-20261031.json',result)
 with(HERE/'offline-index-rounds-20261031.csv').open('w')as f:
  keys=['repeat','mode','version','targets','correct','process_wall_seconds','process_cpu_seconds','core_seconds','VmHWM_KiB'];w=csv.DictWriter(f,fieldnames=keys,extrasaction='ignore');w.writeheader();w.writerows(data)
 table=[]
 for mode in ('full','selective','mirrortaint'):
  a,b=med[mode+'-old'],med[mode+'-indexed'];p=paired[mode]['process_wall_seconds'];table.append(f"| {mode} | {a['process_wall_seconds']:.3f} → {b['process_wall_seconds']:.3f} | {a['process_cpu_seconds']:.3f} → {b['process_cpu_seconds']:.3f} | {a['core_seconds']:.3f} → {b['core_seconds']:.3f} | {a['VmHWM_KiB']/1024:.2f} → {b['VmHWM_KiB']/1024:.2f} | {p['median_change_percent']:+.2f}%；{p['ratio_range'][0]:.4f}–{p['ratio_range'][1]:.4f} |")
 phase=[]
 for mode in ('full','selective'):
  a,b=med[mode+'-old']['phases'],med[mode+'-indexed']['phases']
  phase.append(f"| {mode} | {a['decode_complete_capture']:.3f} → {b['decode']:.3f} | {a['graph_reconstruction_including_required_locality_validation']:.3f} → {b['reconstruction']:.3f} | {a['query_restore']:.3f} → {b['query']:.3f} | {a['independent_score_and_signature_check']:.3f} → {b['independent_score']:.3f} | {a['export']:.3f} → {b['export']:.3f} |")
 text='''# Mall完整捕获：离线热点与共享索引修订

**32秒主要消耗在重复扫描，而非字节码执行本身。** 保留`c1a4e5c`参照，只对既有完整捕获复算；没有重新部署Mall，没有更新在线CPU、延迟或写入字节。离线快照仅增加共享索引，未混入ZLT的I2L、新Agent或B2适配器。

修改前协议和旧源码归档先于改动保存。先各选round-01 full/selective/MT完整180请求捕获做函数剖析；TF分别60607/54667条协议事件，没有截断、过滤或缩小成功批次。带profiler结果仅用于诊断，累计时间相互包含，不能加总为阶段墙时。

| 实际函数／工作 | 原版调用数及累计秒，full／selective | 结论与修改 |
| --- | --- | --- |
| 局部性`validate` | 1次，21.844／18.918s | 每份540次ownership族查找、540次开始和完成查找，另180次源字段查找反复扫整批。一次建立保留全部候选的索引；首轮修订后约0.081／0.072s |
| 字节码`execute` | 2520次，0.402／0.408s | 原180根请求内确实执行的方法；没有通过跳过解释提速 |
| 字段来源`origin` | 2160次，0.037／0.036s | 保留原来源核验与保守效果 |
| 通信`validate_protocol` | 1次，0.065／0.057s | 非主热点，条件保留 |
| `bind_outputs` | 1次，1.882／1.733s | 原180根退出查找重复扫描；索引后约0.046／0.041s |
| 事件族与根完成查找 | 各180次；full约2.482／2.153s | 按Frame和原始行位置索引，保留重复、顺序与区间核验 |
| 独立`tf_expected` | 180次，5.893／5.432s | 原始源事实和父关系重复扫描；独立RawFactIndex只读原始事实，不调用传播或复制预测 |
| 目标图查询`query` | 180次，0.046／0.038s | 已非主热点 |

第一版共享索引后，selective仍较慢。补充剖析确认`validate_application_writes`对180次省略写入重复扫描整批返回／写入，累计约2.544s，其中最终写版本列表推导180次约2.121s。第二项共享索引按Frame及对象/字段分组，保留原区间、唯一性及最终版本检查；最终selective该函数约0.188s。两次剖析及第一版五轮结果全部保留，没有覆盖后只展示最好结果。

索引均限一次捕获处理／核验调用，保存原始记录列表和全部歧义候选；不是认证结论缓存。没有按数值、trace-id或类哈希跨捕获复用认证。RawFactIndex还核对同一rows对象。闭包、局部性配置、调用、完成、字段版本及problem/footer/sidecar条件不删减。

最终正式复算使用同一逻辑CPU、fresh-exec、无profiler；原五轮每种工具完整捕获各跑旧／新流程，轮内版本顺序固定随机，共30进程。各版本2700个目标全部正确，状态和规范化来源签名逐项相同。MT两列运行相同算法，仅作环境与正常流程对照。已有非实验容器保持，不宣称独占物理机；ZLT在线回归在本批计时全部结束后才启动。

| 配置 | 进程墙时s，旧→新 | CPU s | 各自核心s | VmHWM MiB | 墙时配对变化；五轮比值范围 |
| --- | ---: | ---: | ---: | ---: | --- |
'''+ '\n'.join(table)+'''

核心为还原（含必要核验）＋查询；MT核心是原生标签解码，操作不同。进程总墙时含模块载入、解码、独立评分和导出。内存略增，来自保留索引；不能只报告加速。

| 阶段，中位秒旧→新 | 完整解码／初始检查 | 图还原及必要证书 | 目标查询 | 独立评分 | 导出 |
| --- | ---: | ---: | ---: | ---: | ---: |
'''+ '\n'.join(phase)+'''

最终selective/full的配对中位变化为：进程墙时−8.46%（比值0.9128–0.9609）、核心−9.59%（0.8880–0.9534）、VmHWM−4.65%（0.9525–0.9553）。这是相同共享优化下当前任务的离线差异；五轮不宣称统计显著性，不能推算在线改善。

评分提速与核心提速分别列出。正式表采用第二项修订后的新一轮30进程复算；第一次结果留在`paired-cost/`，最终在`paired-cost-v2/paired-cost/`。第二项只改变写入核验查找，没有增加选择性语义。full/selective同享两项优化；选择性贡献只能比较最终两模式的同轮比值，不能将约30秒降幅归于selective。

原严格控制两模式各48目标的状态和来源保持，24类证书扰动分别拒绝；实际同对象泄露最终unknown、同值覆盖新版本保持。原Recipient四份整批无效捕获在移除problem的派生保护中仍拒绝。新Agent的监测可靠性27场景及嵌套状态检查保持；这些是控制回归，不是新业务部署成绩。

**优化后的TF离线流程仍慢于本共同任务的固定MT配置，且内存更高。** 本表不能支持跨任务性能排名；在线表保持原结果。旧来源和通信边界没有移动。

共享优化提交`278896a`与`2609d70`；成本使用独立`indexed-repository-v2`快照，仅六个文件相对旧源码不同（其中一份新增实验worker）。算法修订和实验源码另锁哈希。

工件：`artifacts/offline-zlt-revision-20261031/`。原3464份成本及412份ZLT工件哈希复核不变。函数统计、原始pstats、两次正式复算、严格保护、源码快照及失败尝试均保留。小型[逐轮CSV](offline-index-rounds-20261031.csv)和[结果快照](offline-index-results-20261031.json)随Git；完整数据与备份以本轮清单为准。push由用户完成。
'''
 (HERE/'OFFLINE-INDEX-REVISION-20261031.md').write_text(text)
 print('Saved report; all 30 fresh processes and 2700 paired targets verified')

if __name__=='__main__':run(ROOT/'artifacts/offline-zlt-revision-20261031')
