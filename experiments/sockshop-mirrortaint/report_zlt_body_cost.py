"""Render retained per-deployment measurements; never changes raw results."""
import argparse,csv,statistics
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save,sha
from run_zlt_body_cost import COMMIT


def run(home):
    data=load(home/'results-before-report.json');rows=data['rows'];assert len(rows)==40
    numeric=sorted({k for r in rows for k,v in r.items()if isinstance(v,(int,float))and not isinstance(v,bool)}-{'round'})
    medians={};paired=[]
    for task in('orders','mall'):
        medians[task]={m:{k:statistics.median(r[k]for r in rows if r['task']==task and r['mode']==m and k in r)
            for k in numeric if any(k in r for r in rows if r['task']==task and r['mode']==m)}for m in('original','full','selective','mirrortaint')}
        for a,b in[('selective','full'),('selective','original'),('mirrortaint','original'),('selective','mirrortaint')]:
            for key in numeric:
                ratios=[]
                for repeat in range(1,6):
                    x=next(r for r in rows if r['task']==task and r['mode']==a and r['round']==repeat)
                    y=next(r for r in rows if r['task']==task and r['mode']==b and r['round']==repeat)
                    if key in x and key in y and y[key]:ratios.append(x[key]/y[key])
                if len(ratios)==5:paired.append({'task':task,'comparison':a+'/'+b,'metric':key,'median_change_percent':100*(statistics.median(ratios)-1),'min_ratio':min(ratios),'max_ratio':max(ratios),'ratios':ratios})
    summary={'algorithm':COMMIT,'tasks':2,'deployments':40,'medians':medians,'paired':paired,'rows':rows,
        'source_boundary_unchanged':True,'online_new_capture':True,'shared_index_full_selective':True,
        'cost_protocol_sha256':sha(home/'protocol-before-calibration.json'),
        'calibration_scope':'Short calibrations are correctness only and excluded from performance summaries; first sampling failure retained.',
        'scope':'Two specified tasks, separate environments. No general cross-application performance claim.'}
    out=home/'report';out.mkdir(exist_ok=False);save(out/'summary.json',summary)
    flat=[]
    for r in rows:
        row={k:v for k,v in r.items()if not isinstance(v,dict)}
        row.update({'phase_'+k:v for k,v in r.get('phases_seconds',{}).items()});flat.append(row)
    fields=['task','round','mode']+sorted(set().union(*(r.keys()for r in flat))-{'task','round','mode'})
    with(out/'rounds.csv').open('w',newline='')as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(flat)
    save(HERE/'zlt-body-cost-results-20261031.json',summary);(HERE/'zlt-body-cost-rounds-20261031.csv').write_bytes((out/'rounds.csv').read_bytes())
    metrics=[('p50 ms','p50_ms',1),('p95 ms','p95_ms',1),('p99 ms','p99_ms',1),('完成请求/秒','completed_rps',1),('错误率','error_rate',1),
        ('业务 CPU，单核%','business_cpu_one_core_percent',1),('业务平均 RSS MiB','business_RSS_MiB',1),('业务采样峰值 RSS MiB','business_peak_RSS_MiB',1),
        ('整部署 CPU，单核%','deployment_cpu_one_core_percent',1),('整部署平均 RSS MiB','deployment_RSS_MiB',1),
        ('可配对测量事件','measure_events',1),('可配对测量字节 MiB','measure_bytes',2**20),('整批协议事件','batch_events',1),('整批协议字节 MiB','batch_bytes',2**20),
        ('未配对／共享事件','shared_unattributed_events',1),('全部 capture 文件 MiB','all_capture_file_bytes',2**20),
        ('离线核心 s','offline_core_seconds',1),('离线总进程墙时 s','offline_process_wall_seconds',1),('离线进程 CPU s','offline_process_cpu_seconds',1),('fresh-exec VmHWM MiB','offline_VmHWM_MiB',1)]
    lines=['# 同一新候选的两任务成本：Orders.total 与 Mall 登录','',
        '算法冻结为 `'+COMMIT+'`，参照 `c1a4e5c`。两条任务各作 original、TF full、TF selective、固定原生 MT＋适配器的五轮独立部署，共40份新在线捕获。任务和配置顺序在校准前固定，full/selective共用当前索引、事件格式和必要核验。结果只适用于这两个指定任务。','',
        '业务、来源和依赖先校准；原版短运行曾因8秒窗口缺少RabbitMQ资源样本报错，24次已完成业务事实单独验收，失败记录保留。之后短校准关闭资源计量，只验正确性；其时间和资源值均不进入本表。正式60秒资源核验保持。','',
        '正式每部署预热30秒、测量60秒、2请求/秒、并发上限2，正确性覆盖180请求，在线指标只覆盖120次测量请求。每业务JVM1CPU/768MiB，`-Xms32m -Xmx256m -XX:ParallelGCThreads=1 -XX:CICompilerCount=2`；每任务内部原JAR、JDK、镜像、数据准备和客户端一致。两应用的原运行时与部署组成分别保留，不跨任务合并绝对成本。全部正式负载顺序运行，不与正确性验收并行。','',
        'Orders使用当前代码保留的mapped-reduction规划入口及原Carts JSON响应字段边界；Mall使用统一执行内核及AuthService.getAccessToken实际调用返回字段边界。没有根据成本结果切换profile。MT原生传播未改，Orders适配器单独锁定版本，Mall沿用B0；一部署只评分同一个字段，额外导出仍计入成本，不累计TF多字段部署作比较。','',
        'MT实际ObjectMapper定义与各原业务库逐项核验；Orders探针重叠738个Jackson类字节相同，Mall实际使用原2.13.3。校准证明当前任务的来源、目标和依赖可对应，不是任意MT插桩透明性的证明。','']
    for task,title in [('orders','Orders.total：既有专用路径'),('mall','Mall /data/expiresIn：通用内核收缩')]:
        lines+=['## '+title,'','| 五轮中位数 | original | full | selective | MT＋固定适配器 |','| --- | ---: | ---: | ---: | ---: |']
        for name,key,scale in metrics:
            vals=[('%.3f'%(medians[task][m][key]/scale))if key in medians[task][m]else'N/A'for m in('original','full','selective','mirrortaint')]
            lines.append('| '+name+' | '+' | '.join(vals)+' |')
        lines+=['','| 配对比较 | 指标 | 变化中位数 | 五轮比值范围 |','| --- | --- | ---: | --- |']
        selected={'p95_ms':'p95','business_cpu_one_core_percent':'业务CPU','batch_bytes':'整批协议字节','measure_bytes':'可配对测量字节','offline_process_wall_seconds':'离线总墙时','offline_process_cpu_seconds':'离线CPU','offline_VmHWM_MiB':'VmHWM'}
        for p in paired:
            if p['task']==task and p['metric']in selected:
                lines.append('| '+p['comparison']+' | '+selected[p['metric']]+' | %+.2f%% | %.4f–%.4f |'%(p['median_change_percent'],p['min_ratio'],p['max_ratio']))
        lines+=['','| 正确性，含预热 | 目标正确 | 正来源 | 已知空来源 |','| --- | ---: | ---: | ---: |']
        for mode in('full','selective','mirrortaint'):
            rs=[r for r in rows if r['task']==task and r['mode']==mode];n=sum(r['targets']for r in rs);c=sum(r['correct']for r in rs);pos=sum(r['positive']for r in rs)
            lines.append('| '+mode+' | %s/%s | %s | %s |'%(c,n,pos,n-pos))
        lines.append('')
    lines+=['## 归因和计量边界','',
        '配置列为五次部署中位数，配对变化为同轮比值中位数；两者不能相除替代。范围跨1不称稳定改善，五轮不是请求级独立重复，不宣称显著性。2请求/秒不是最大吞吐；p99仅作描述。','',
        '事件和字节只按实际Frame、调用、消息及明确RPC父关系配对；同trace的多个根不合并，无父关系的不猜补。可配对测量量不是全部稳态采集量；未配对、预热、启动和关闭记录全部保留，整批协议与全部capture文件另列。MT诊断和class dump不是协议JSON，仍计入全部capture文件；这些是保存字节，不是最大磁盘I/O。','',
        '离线均为fresh-exec的一次正常流程。TF核心包含必要证书消费、解释／图还原及查询，MT核心是原生标签解码；解码、独立评分和导出阶段另在逐轮CSV列出，不能把两个核心定义视为同一种操作。独立评分仅使用本JVM原始调用与字段事实索引，未用图或标签生成真值。','',
        'Mall原始HTTP旁路完整性为false的记录继续保留；本任务认证的是声明的调用返回字段，不认证完整wire字节到字段投影。关闭局部性证书的精度消融不能作为同答案低成本配置。新增方法体收缩只省略受保护区域的读取值与分支，全部写入、版本、别名、发布、异常和必要契约仍保留；条件不成立回退采全。','',
        '新增收缩的短开／关观测对照、同捕获证书精度消融及静态规划数据在主工件内单列，不把旧索引提速或既有字段选择全部归于新机制。没有改写旧在线数据或旧正式成本表。','',
        '主目录为`artifacts/zlt-body-cost-20261031/`；逐轮原始资源、请求、真实调用、独立评分、计划与二进制哈希均保留。完整工件及镜像另行备份。能力保持另见[ZLT与观测收缩报告](ZLT-COMPLETION-AND-BODY-SLICE-20261031.md)，不同集合不合成整体准确率。没有push。','']
    (HERE/'ZLT-BODY-COMMON-COST-20261031.md').write_text('\n'.join(lines))
    print('Rendered 40 deployments',home)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);a=p.parse_args();run(a.home.resolve())
