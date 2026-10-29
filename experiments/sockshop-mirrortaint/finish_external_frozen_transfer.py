#!/usr/bin/env python3
"""Finish the frozen transfer audit without modifying captures or algorithms."""
import argparse,collections,datetime,hashlib,json,subprocess,sys,time
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save,sha
HOME=ROOT/'artifacts/external-frozen-transfer-20261029'

def closed(path):
 return path.exists() and load(path).get('complete',False)

def audit_B1(out):
 rows=[]
 for api in ['apollo-1','mall-swarm-2','mall-swarm-4','mall-swarm-5']:
  home=HOME/'MT-B1/tool-runs'/api/'mirrortaint/fixed-adapter';p=home/'capture/boundary-facts.jsonl'
  result=load(home/'results.json') if(home/'results.json').exists() else {}
  facts=[json.loads(s)for s in p.open()] if p.exists()else[]
  begin=[r for r in facts if r['kind']=='call-begin'];end=[r for r in facts if r['kind']=='call-end'];pairs=[]
  assert len({r['call_id']for r in begin})==len(begin),'Repeated raw call ID'
  for b in begin:
   ends=[e for e in end if e['call_id']==b['call_id']]
   paired=len(ends)==1 and ends[0]['callee']==b['callee'] and ends[0]['seq']>b['seq']
   pairs.append({'call_id':b['call_id'],'effect_kind':b['effect_kind'],'callee':b['callee'],'root':b.get('root'),'message':b.get('context',{}).get('message'),'actual_site':b['site'],'paired':paired,'arguments':b['arguments'],'completion':ends[0]['completion']if paired else None,'source_answer':None,'target_definition_only':True})
  diagnostics=[r for r in facts if r['kind']=='problem'];footers=[r for r in facts if r['kind']=='closed'];bodies=[r for r in facts if r['kind']=='gson-body-fact']
  old=HOME/'ae7fe8d/tool-runs'/api/'mirrortaint/fixed-adapter/results.json';original=load(old)if old.exists()else{}
  status_equal=all(next((x['http_status']for x in original.get('cases',[])if x['case']==c['case']),None)==c['http_status']for c in result.get('cases',[])) and len(result.get('cases',[]))==len(original.get('cases',[]))
  messages={c.get('message')for c in result.get('cases',[])};official=[p for p in pairs if p['message']in messages]
  record={'api':api,'cases':len(result.get('cases',[])),'HTTP_statuses_match_B0':status_equal,'business_output_and_native_propagation_equivalence_claimed':False,'begin_calls':len(begin),'completed_calls':len(end),'all_observed_calls_paired':all(p['paired']for p in pairs)and len(begin)==len(end),'source_calls':sum(p['effect_kind']=='source-read'for p in pairs),'sink_calls':sum(p['effect_kind']=='sink'for p in pairs),'official_request_source_calls':sum(p['effect_kind']=='source-read'for p in official),'official_request_sink_calls':sum(p['effect_kind']=='sink'for p in official),'complete_sink_argument_snapshots':sum(p['effect_kind']=='sink'and all(a.get('complete')for a in p['arguments'])for p in pairs),'problems':diagnostics,'closed_once':len(footers)==1,'capture_invalid':footers[0]['capture_invalid']if len(footers)==1 else True,'gson_body_facts':len(bodies),'gson_code_sources':sorted({b.get('gson_code_source','unknown')for b in bodies}),'certified_projection_answers':0,'library_write_coverage_guarantee':False,'source_answers':0}
  save(out/(api+'-B1-raw-call-targets.json'),pairs);rows.append(record)
 save(out/'B1-summary.json',rows)
 return rows

def immutability(out):
 first=ROOT/'artifacts/portability-first-20261028';protected=load(ROOT/'artifacts/monitor-reliability-account-20261028/protected-first-evidence.json')['files']
 for name,h in protected.items():assert sha(first/name)==h,name
 checks={}
 for version,p,key in [('ae7fe8d',first/'protocol-start.json','core_sources'),('78a9534',ROOT/'artifacts/account-semantics-20261028/final-candidate-01/algorithm-freeze.json','sources')]:
  files=load(p)[key]
  for name,h in files.items():assert sha(HOME/'sources'/version/Path(name).relative_to(ROOT))==h,name
  if version=='78a9534':
   for name,h in files.items():assert sha(Path(name))==h,name
  checks[version]=len(files)
 before=load(HOME/'first-matrix-manifest-before-B1.json')['files']
 for name,h in before.items():assert sha(HOME/name)==h,name
 result={'old_protected_files_unchanged':len(protected),'frozen_source_files':checks,'new_first_matrix_files_unchanged_after_B1':len(before),'TF_agent_sha256':sha(ROOT/'artifacts/account-semantics-20261028/final-candidate-01/frozen-base/distributed-observer.jar'),'MT_native_sha256':sha(ROOT/'artifacts/external-tools/mirrortaint/mirrorTaint.jar'),'B0_adapter_sha256':sha(ROOT/'artifacts/heldout29-first-20261023/native-bundle/capability.jar')}
 save(out/'immutability.json',result);return result

def report(out,b1,locked):
 summary=load(out/'summary.json');apis=load(out/'per-api.json');rows=load(out/'instances.json');lines=[]
 def add(s=''):lines.append(s)
 def states(d):return '；'.join(k+' '+str(n)for k,n in sorted(d.items()))or'无实际字段目标'
 add('# Apollo / Mall：两个冻结 TF 版本的直接迁移结果')
 add()
 add('本批保持 `ae7fe8d`、`78a9534` 的核心、Agent 和公共契约不变，按固定顺序执行 Apollo 五 API、Mall 五 API。全部 40 项总清单继续保留。本报告只描述本批十 API，不能称为完成全部 40 API 的共同任务能力对照。没有性能实验或 push。')
 add()
 add('第一次高层路由没有把已封存的显式来源声明传给 TF 计划。原计划、首次捕获及评分全部保留于 `audit-final-01`，归为接入限制；不能据此评价来源能力。主表使用单列 **C1 配置校准**：经同一个冻结路由选择 profile，再使用该快照已有 `plan_response(source_calls=...)` 接口传入原声明，并调用同版后处理。全十 API、59 个查询族、输入、来源边界与真值规则不变，没有逐字段传播规则、增加库模型或放宽检查。C1 的 TF 使用新部署；原版和 MT 的输入、二进制及来源配置未变，复用其原捕获。')
 add()
 add('来源正确必须同时满足实际目标绑定和独立实例真值。规划接纳、HTTP 200、原生标签或保存参数快照分别只是准备或事实，均不直接计作来源正确。')
 add()
 add('| API | 查询族 | 无 Agent 请求 | MT B0 字段状态 | TF ae7 full | TF 78 full |')
 add('| --- | ---: | --- | --- | --- | --- |')
 for a in apis:
  q=next(q for q in load(HOME/'task-seal.json')['entries']if q['id']==a['api']);p=HOME/'ae7fe8d/original'/q['application']/('sealed-'+q['id'])/'results.json';original=load(p)if p.exists()else{};http=collections.Counter(c['http_status']for c in original.get('cases',[]))
  add('| '+a['api']+' | '+str(a['queries'])+' | '+', '.join(str(k)+'×'+str(v)for k,v in sorted(http.items()))+' | '+states(a['MT'])+' | '+states(a['TF']['ae7fe8d-full'])+' | '+states(a['TF']['78a9534-full'])+' |')
 add()
 add('表内保留冻结驱动的状态；细分诊断在逐实例 CSV 和逐配置原始事件中。`evidence_invalid` 不全部等于日志损坏：包括未建立响应字段绑定、库投影不支持，以及真正的监测失败。正式请求未执行与原版未生成目标分开。')
 add()
 add('| 工具 | 本批实际字段目标状态 | 具有本工具原始实例真值 |')
 add('| --- | --- | ---: |')
 for tool,d in summary['states'].items():add('| '+tool+' | '+states(d)+' | '+str(summary['oracle_adequate'].get(tool,0))+' |')
 add()
 for tool in summary['states']:
  good=[r for r in rows if (r['tool']if r['tool']=='MT-B0'else r['version']+'-'+r['tool'])==tool and r['state']=='known_correct'];pos=sum(bool(r.get('expected'))for r in good)
  add('- '+tool+'：已核验正确 '+str(len(good))+'，其中正来源 '+str(pos)+'、已知空来源 '+str(len(good)-pos)+'。')
 add()
 add('双方逐项状态及差距见 [配对表](external-transfer-paired-20261029.csv)。基线导出和独立事实不足时，不填完整关系 FP/FN 为零，也不由“未发现基线领先项”推断能力相等。当前未完成完整 API 的返回＋保存／消息 sink 验收。')
 add()
 add('## 主要诊断')
 add()
 add('Apollo 原业务配置使用 GsonHttpMessageConverter；冻结 TF 与 B0 的实际响应字段记录没有为这些 Gson 路径建立足够绑定。Apollo1 还暴露了未支持的 Map 监测路径：旧 Agent 可改变业务完成，新 Agent 保持业务执行后仍用 problem／失败 footer 拒绝损坏批次。早期因插桩准备请求 500 而未发出正式请求的捕获原样保留，另列准备失败；环境驱动后来识别该具体错误并尝试正式输入，没有修改算法。')
 add()
 add('独立 B1 Apollo 诊断观察到实际 Gson 对象代码来自 `file:/tf2/mirrorTaint.jar`，与应用声明的 Gson 2.10.1 不同。这个依赖差异需要后续隔离或语义校准，不能直接算作 MT 原生传播错误。B0 已有标签不能替代缺失的 wire 字段实例；本轮不加入 Gson 来源规则使其通过。')
 add()
 add('Apollo3 的原始 long 返回与 Apollo4 的方法 null／空 HTTP body 另列。空 body 不是 JSON null 字段；空列表没有元素目标，实际 null 字段则仍是字段目标。原静态候选、实际 wire 叶及持久化义务分开保存，没有因工具不支持而删除 API。')
 add()
 add('## 共同任务与独立观测适配器')
 add()
 add('原先仅在应用服务接口处停止的来源扫描不适合评价 DB 来源。本批实验清单沿实际应用实现审阅，声明具体仓储／mapper／RPC 读取边界，业务 helper 不重新当来源。逻辑真值规则在新工具运行前封存；评分 Python 实现随后编写，二者时间分别保留，不宣称完整评分代码预注册。')
 add()
 add('B1 在首次矩阵封存后另行采集实际源调用与保存／删除参数的开始、正常或异常完成、对象和字段坐标。它只补原始事实，不输出来源答案，也没有实现 TF 保存 sink 查询。原生 MT JAR 与 B0 二进制不变；新增插桩的透明性仍按下表的实际检查范围陈述，不宣称任意库写入覆盖或原生传播等价。')
 add()
 add('下表调用数覆盖整批准备与正式请求；JSON 另列按实际消息配对的正式请求调用数。不能把准备阶段的调用数当成评分目标。')
 add()
 add('| B1 API | 整批源调用 | 整批 sink 调用 | 参数完整快照 | 调用配对 | 失败标记 |')
 add('| --- | ---: | ---: | ---: | --- | --- |')
 for b in b1:add('| '+b['api']+' | '+str(b['source_calls'])+' | '+str(b['sink_calls'])+' | '+str(b['complete_sink_argument_snapshots'])+' | '+str(b['all_observed_calls_paired'])+' | '+str(b['capture_invalid'] or bool(b['problems']))+' |')
 add()
 add('旧 Piggy 保存前事实另外审计：每模式 36 项可定义为具体 save 调用前实参字段目标，五项错配保护通过，不需要为这 36 项重新采集。冻结 TF 缺少保存 sink 查询入口，MT 旧捕获缺相应完整导出，因此仍不把返回字段答案代作保存答案。另四项 currency 事实缺口保留。')
 add()
 add('## 迁移工作量与剩余环境')
 add()
 add('本批新增 TF 公共模型 0、TF 核心与 Agent 修改 0；新增的是任务配置、环境驱动、独立评分与单列的 B1 原始事实观测器。迁移台账记录入口、审阅方法、边界和阻断；文件数不等于人工工时，没有虚构工时。必须分别记录“模型在计划中出现”“运行时调用发生”和“帮助产生经独立核验答案”，不能用前两项宣称复用成功。')
 add()
 add('ZLT 的两个无 Agent 原版服务已在本地原 SQL／MySQL／Redis／Nacos 配置下启动，尚未验证目标入口和正常认证请求。FEBS 归档替代、goodsKill、SuperMarket 的其余环境阻断继续保留；Sock Shop 本批整 API／sink 任务仍待执行。它们不记 TF 失败或业务 N/A，不用历史 62 查询填入本批。Station 403 的既定决定不变。')
 add()
 add('## 版本与工件')
 add()
 add('原应用使用已封存历史候选，不是已确认的论文原版本；源码、反射、旧静态规划和环境诊断已经暴露，不称第三方盲测。')
 add()
 add('- 算法：`ae7fe8d8b9e23d8ce197870ff0069c7f1bee84eb`、`78a95343c127fcc5732174b783e9d528b354a9d7`。')
 add('- 源码校验：旧 '+str(locked['frozen_source_files']['ae7fe8d'])+' 项、新 '+str(locked['frozen_source_files']['78a9534'])+' 项，均未改动；旧首次 '+str(locked['old_protected_files_unchanged'])+' 文件及本批 B0 首次 '+str(locked['new_first_matrix_files_unchanged_after_B1'])+' 文件哈希保持。')
 add('- 新 TF Agent SHA256：`'+locked['TF_agent_sha256']+'`。')
 add('- 原生 MT JAR SHA256：`'+locked['MT_native_sha256']+'`。')
 add('- 主工件：`artifacts/external-frozen-transfer-20261029/`。首次输入／逻辑真值、计划、镜像、独立网络和 DB、调用日志、源事件、B0／B1 版本和失败尝试均保留；C1 位于独立 `source-config-C1/`。')
 add()
 add('完整工件和 Docker 镜像需另行备份；Git 仅保存代码及小型结果。原 Account40 和旧成本结果不改写。本轮不据这些能力捕获主张性能优势。')
 (HERE/'EXTERNAL-FROZEN-TRANSFER-20261029.md').write_text('\n'.join(lines)+'\n')
 for source,dest in [('instances.csv','external-transfer-instances-20261029.csv'),('paired-gaps.csv','external-transfer-paired-20261029.csv'),('summary.json','external-transfer-results-20261029.json'),('all40-ledger.json','external-transfer-all40-20261029.json')]:
  (HERE/dest).write_bytes((out/source).read_bytes())

def run(out,wait):
 if wait:
  while not closed(HOME/'matrix-progress.json') or not closed(HOME/'MT-B1/progress.json') or not closed(HOME/'source-config-C1/progress.json'):time.sleep(10)
  # Reload the final experiment scorer/report, rather than retaining a Python
  # definition from hours before matrix completion. Frozen cores stay pinned.
  subprocess.run([sys.executable,__file__,'--out',str(out)],check=True)
  return
 assert closed(HOME/'matrix-progress.json') and closed(HOME/'MT-B1/progress.json') and closed(HOME/'source-config-C1/progress.json'),'Do not publish final before all matrices close'
 with(HOME/'logs/final-score.log').open('w')as f:subprocess.run([sys.executable,str(HERE/'audit_external_frozen_transfer.py'),'--out',str(out)],stdout=f,stderr=subprocess.STDOUT,check=True)
 calibrated=HOME/'audit-C1-final-01'
 with(HOME/'logs/final-score-C1.log').open('w')as f:subprocess.run([sys.executable,str(HERE/'audit_external_frozen_transfer.py'),'--source-calibrated','--out',str(calibrated)],stdout=f,stderr=subprocess.STDOUT,check=True)
 b1=audit_B1(calibrated);locked=immutability(calibrated);report(calibrated,b1,locked)
 save(calibrated/'finish.json',{'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'report':'EXTERNAL-FROZEN-TRANSFER-20261029.md','complete_selected_ten_API_first_matrix':True,'all40_complete':False,'configuration_correction_separate_from_first_results':True,'new_TF_semantics':False,'performance':False,'push':False})
 print(load(calibrated/'summary.json'),flush=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--wait',action='store_true');a=p.parse_args();run(a.out.resolve(),a.wait)
