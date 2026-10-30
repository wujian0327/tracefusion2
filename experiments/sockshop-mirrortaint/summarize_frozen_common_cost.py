#!/usr/bin/env python3
"""Final common-task report with normal single-pass offline measurements."""
import argparse,collections,csv,json,statistics
from pathlib import Path
from run_frozen_zlt_reuse import ROOT,load,save,sha
from run_frozen_locality_cost import verify,AGENT

def run(home):
 verify();original=load(home/'summary/results.json');normalized=load(home/'common-offline-single-pass/results.json');assert normalized['complete']and len(normalized['results'])==15
 oldrows=list(csv.DictReader((home/'summary/rounds.csv').open()));bytrial={r['trial']:r for r in normalized['results']};rows=[]
 for r in oldrows:
  row={k:(v if k=='mode'else float(v))for k,v in r.items()if v!=''};row['round']=int(row['round']);mode=row['mode']
  if mode!='original':
   n=bytrial['round-%02d-%s'%(row['round'],mode)];row['audit_inclusive_process_wall_seconds']=row['offline_process_wall_seconds'];row['audit_inclusive_process_cpu_seconds']=row['offline_process_cpu_seconds']
   row.update(offline_core_seconds=n['core_seconds'],offline_process_wall_seconds=n['process_wall_seconds'],offline_process_cpu_seconds=n['process_cpu_seconds'],offline_VmHWM_MiB=n['VmHWM_KiB']/1024)
   t=n['phases_seconds'];row.update(offline_export_seconds=t['export'],offline_score_seconds=t.get('independent_score',t.get('independent_score_and_signature_check')),offline_decode_validate_seconds=t.get('decode_validate_bind',t.get('decode_complete_capture')))
  rows.append(row)
 fields=sorted(set().union(*(r.keys()for r in rows)));medians={mode:{k:statistics.median(r[k]for r in rows if r['mode']==mode and k in r)for k in fields if k not in('mode','round')and any(k in r for r in rows if r['mode']==mode)}for mode in('original','full','selective','mirrortaint')};pairs=[]
 for a,b in [('selective','full'),('selective','original'),('full','original'),('mirrortaint','original'),('selective','mirrortaint'),('full','mirrortaint')]:
  for key in fields:
   if key in('round','mode'):continue
   ratios=[]
   for i in range(1,6):
    x=next(r for r in rows if r['round']==i and r['mode']==a);y=next(r for r in rows if r['round']==i and r['mode']==b)
    if key in x and key in y and y[key]!=0:ratios.append(x[key]/y[key])
   if len(ratios)==5:pairs.append({'comparison':a+'/'+b,'metric':key,'median_percent_change':(statistics.median(ratios)-1)*100,'min_ratio':min(ratios),'max_ratio':max(ratios),'ratios':ratios})
 out=home/'summary-common';out.mkdir(exist_ok=False);summary={**original,'medians':medians,'paired':pairs,'offline_measurement':'Fresh-exec normal pipeline, one internal frozen certificate validation; duplicate external audit retained separately, not charged twice to core/normal process.','normal_measurements':15,'normal_source_signatures_preserved':True}
 save(out/'results.json',summary)
 with(out/'rounds.csv').open('w',newline='')as f:
  w=csv.DictWriter(f,fieldnames=['round','mode']+[k for k in fields if k not in('round','mode')]);w.writeheader();w.writerows(rows)
 folder=ROOT/'experiments/sockshop-mirrortaint';save(folder/'frozen-common-cost-results-20261030.json',summary);(folder/'frozen-common-cost-rounds-20261030.csv').write_bytes((out/'rounds.csv').read_bytes())
 def val(mode,key,scale=1):
  v=medians[mode].get(key);return 'N/A'if v is None else '%.3f'%(v/scale)
 specs=[('p50 ms','p50_ms',1),('p95 ms','p95_ms',1),('p99 ms','p99_ms',1),('完成请求/秒','completed_rps',1),('错误率','error_rate',1),('业务CPU，单核%','business_cpu_one_core_percent',1),('业务平均RSS MiB','business_RSS_MiB',1),('业务采样峰值RSS MiB','business_peak_RSS_MiB',1),('整部署CPU，单核%','deployment_cpu_one_core_percent',1),('整部署平均RSS MiB','deployment_RSS_MiB',1),('可归属测量消息的事件','measure_events',1),('可归属测量消息的字节 MiB','measure_bytes',2**20),('整批协议事件','batch_events',1),('整批协议字节 MiB','batch_bytes',2**20),('各自离线核心 s','offline_core_seconds',1),('离线进程总墙时 s','offline_process_wall_seconds',1),('离线进程CPU s','offline_process_cpu_seconds',1),('fresh-exec VmHWM MiB','offline_VmHWM_MiB',1),('解码／独立完整性与绑定 s','offline_decode_validate_seconds',1),('独立评分 s','offline_score_seconds',1),('答案导出 s','offline_export_seconds',1),('含额外重复证书审计的旧进程墙时 s','audit_inclusive_process_wall_seconds',1)]
 lines=['# 同版本共同任务成本：Mall管理员登录','',
 '**本报告只评价冻结版c1a4e5c的一项共同正确任务。** 原版、TF full、TF selective、固定MirrorTaint＋B0各五次独立部署，四配置轮内随机顺序，20次在线实验均新采集。没有改变核心、Agent或公共契约，不由这些数据新增通用性能优势结论。',
 '', '## 共同任务与校准', '',
 '目标为`UmsAdminController.login`的`/data/expiresIn`，正来源为本次实际`AuthService.getAccessToken`调用返回中的相应字段。原声明边界没有移到原始wire字节或仓储status。用户名admin及密码macro123来自原版公开SQL种子，正常OAuth签发；不读取私有签名材料、不伪造身份。',
 '', '短校准原版24次业务正常，TF full/selective及MT各24/24正来源匹配。TF关闭证书消费后均0个已知答案，证明该字段依赖局部性机制。入口、显式来源集合、任务输入及目标粒度一致；实际MT ObjectMapper来自业务JAR的Jackson2.13.3，字节码哈希与业务清单一致。挂载的MT Agent／适配器JAR未发现与该业务模型清单冲突的类定义。完整校准证据在`common-task-calibration-final.json`。',
 '', 'MT一次部署会导出其他字段；本批仍只评分这一字段，每次部署只跑同一任务，不把TF多字段部署成本累加后比较。外部成本对应**固定原生MT＋B0适配器的完整审计配置**，不是去除适配器后的原生传播裸成本，也不是所有任务的排名。',
 '', '## 正式正确性与严格消融', '',
 '| 配置 | 总请求，含预热 | 正常完成 | 目标实例来源匹配 | 正来源 | 已知空来源 |',
 '| --- | ---: | ---: | ---: | ---: | ---: |',
 '| original | 900 | 900 | 不运行还原 | N/A | N/A |',
 '| TF full | 900 | 900 | 900/900 | 900 | 0 |',
 '| TF selective | 900 | 900 | 900/900 | 900 | 0 |',
 '| MT＋B0 | 900 | 900 | 900/900 | 900 | 0 |',
 '', '各部署另核对原DB中新增180条登录日志，三种工具没有改变本次保存次数。每请求使用本JVM原始源调用、字段、对象、版本与实际响应映射独立评分，不跨JVM比较对象编号，也不由标签或图生成真值。',
 '', '局部性证书**消费开／关**使用同一完整捕获作精度消融：两种TF模式各900个已知正来源关闭后均失去已知答案。此配置不参加同答案成本比较。full／selective保留相同的必要局部性、来源调用、通信身份、完成与完整性核验，使用同一Agent、事件格式及全局工程开关；不切回旧快速路径，不混入格式压缩。',
 '', '来源边界是实际RPC返回字段。额外HTTP旁路的响应`document_complete=false`事实保留，不认证完整wire字节到字段的投影；它不替代也不自动否定已闭合的调用返回来源边界。',
 '', '## 计量协议', '',
 '每部署预热30秒、测量60秒，2请求/秒、并发上限2；正确性覆盖300次预热＋600次测量，在线性能仅测量期。所有模式使用相同业务JAR、主机OpenJDK8u504、镜像ID和SQL种子，数据卷独立；JVM为`-Xms32m -Xmx256m -XX:ParallelGCThreads=1 -XX:CICompilerCount=2`。每业务JVM1CPU/768MiB，MySQL512MiB、Redis128MiB、Mongo384MiB、Rabbit384MiB，各1CPU；三个业务JVM均计入业务组，七服务计入部署组。',
 '', '隔离网络不发布宿主机端口，负载来自同网独立load-client容器。延迟使用curl的HTTP time_total，排除Docker exec调度、Python解析／评分／导出；客户端CPU不混入业务或部署组。资源采样间隔2秒，RSS峰值是采样峰值。已有四个非实验容器保持，机器及初始清单保存在environment-before.json，不宣称独占物理机。',
 '', '第一份短原版端口尝试失败并保留；第二次原版24请求均正常，其独立DB文件写入因stderr为None失败，原始命令日志中的24条保存事实另存补充。一次离线消融驱动误用answer.frame导致派生失败，随后在新目录修正评分驱动；原捕获和失败目录不覆盖。没有据正式成本结果更换任务或算法。',
 '', '## 五轮绝对值', '', '| 五轮中位数 | original | full | selective | MT＋B0 |','| --- | ---: | ---: | ---: | ---: |']
 for title,key,scale in specs:lines.append('| '+title+' | '+' | '.join(val(m,key,scale)for m in('original','full','selective','mirrortaint'))+' |')
 lines+=['', '**事件／字节的归属有边界。** 只按实际根Frame、消息及共同trace祖先关联测量请求，不按日志可见窗口、数值或时间接近猜配。认证服务回调可能产生不能连接到选定入口根的消息，这些与共享启动／关闭记录单列；整批协议总量仍全部保留。可归属部分不是全部稳态采集量，不能把未配对部分删除后声称整体缩减。逐轮CSV同时保留TF未配对／共享事件及字节。',
 '', 'MT协议字节包含native-capability、instances和native-library三类JSON记录；原生诊断日志和class dump另在各轮capture_files_bytes及all_capture_files_bytes保留，不能把协议JSON总量说成全部写入量。TF整批JSON不等于最大磁盘I/O；所有表均指保存的记录／文件字节。',
 '', '## 配对变化', '', '| 比较 | 指标 | 同轮变化中位数 | 五轮比值范围 |','| --- | --- | ---: | --- |']
 titles={'p95_ms':'p95','business_cpu_one_core_percent':'业务CPU','measure_bytes':'可归属测量字节（非全部）','batch_bytes':'整批协议字节','offline_process_wall_seconds':'单次离线总墙时','offline_process_cpu_seconds':'单次离线CPU','offline_VmHWM_MiB':'VmHWM'}
 for comp in('selective/full','selective/original','mirrortaint/original','selective/mirrortaint'):
  for metric in titles:
   p=next((p for p in pairs if p['comparison']==comp and p['metric']==metric),None)
   if p:lines.append('| '+comp+' | '+titles[metric]+' | %+.2f%% | %.4f–%.4f |'%(p['median_percent_change'],p['min_ratio'],p['max_ratio']))
 lines+=['', '配置列是五次部署中位数，配对列是五个同轮比值的中位数，不能用前者相除代替。范围跨1的指标不称稳定改善；5轮不是请求级独立重复，不宣称显著性。完成2请求/秒只表示完成当前负载，不表示最大吞吐相同；p99仅作描述。',
 '', '## 离线阶段与静态规划', '',
 '各自核心的定义不同：TF为冻结图还原（含其必要证书消费）＋目标恢复，MT为原生标签解码。解码／验证／绑定、独立评分、导出分别列出。外部任务应同时看正常流程总墙时、CPU与内存，不把不同核心阶段直接解释成同一种操作的速度比。',
 '', '最初驱动在正常Reconstruction之外又重复执行一次完整证书审计，导致审计批次总耗时增加。原计时和精度消融完整保留。正式在线全部结束后，使用相同捕获，在独立common-offline-single-pass目录对三种工具各五份捕获fresh-exec复算；TF只去除**正常流程之外的重复审计调用**，冻结还原器内部全部条件及检查保持，180项答案及实例签名逐份相同。上表离线总墙时／CPU／VmHWM采用单次正常流程，额外审计旧计时另列；这不是核心优化或新版本能力。']
 planning=load(home/'static-planning/summary.json')['repeats'];lines+=['', '| 静态规划，5次fresh-exec | 中位值 |','| --- | ---: |']
 for title,key,scale in [('工作进程内规划墙时 s','wall_seconds',1),('工作进程内CPU s','cpu_seconds',1),('新进程全流程墙时 s','process_wall_seconds',1),('新进程全流程CPU s','process_cpu_seconds',1),('VmHWM MiB','VmHWM_KiB',1024)]:lines.append('| '+title+' | %.4f |'%(statistics.median(r[key]for r in planning)/scale))
 lines+=['', '五次生成计划与实际部署计划完全相同；固定同一逻辑CPU，未清OS页缓存。这里复用已冻结的业务模型，计时包含模型JSON载入及规划，不含先前JAR提取、库清单建立和首次运行时探针；这些准备成本本轮未复测，不能把本表说成完整冷启动建模成本。Agent编译、服务启动也不混入规划时间，不摊作每请求成本。',
 '', '## 适用范围与工件', '',
 '本批没有把Mall98项结果或原62／29／15／Account40混入性能正确性分母。它们是冻结参照，本轮无核心变化，因此没有机械重复部署全部历史集。5项管理员更新真值不足任务保持原样。ZLT直接复用的负结果另见[FROZEN-REUSE-20261030.md](FROZEN-REUSE-20261030.md)，不能用本任务成功抵消。',
 '', '主目录`artifacts/frozen-locality-cost-20261030/`包含运行前协议、四配置短校准、固定随机顺序、20份正式捕获、逐轮资源原始值、独立SQL事实、源坐标／答案、精度消融、原审计计时、正常单次流程复算和静态规划。完整工件及所用镜像另归档，备份SHA见本批清单。',
 '', '冻结Agent SHA256：`'+AGENT+'`。原生MT SHA256：`e4c679206993b45c6727a4ace1d4dcff6df0ded2b80b56b27b8c86741be63fe7`。小型[逐轮CSV](frozen-common-cost-rounds-20261030.csv)和[结果快照](frozen-common-cost-results-20261030.json)随Git；配置、评分及计量源码另锁定哈希。没有push。']
 (folder/'FROZEN-COMMON-TASK-COST-20261030.md').write_text('\n'.join(lines)+'\n');print('Final common report written',out)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--home',required=True,type=Path);a=p.parse_args();run(a.home.resolve())
