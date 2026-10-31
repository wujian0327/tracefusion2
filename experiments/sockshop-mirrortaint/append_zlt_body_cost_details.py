"""Post-measurement report details, separate from frozen timed workers."""
import argparse,json,statistics
from pathlib import Path
from run_planned_service import HERE,load,save


def run(home):
    planning=load(home/'static-planning/summary.json');ablation=load(home/'short-body-observation-ablation.json');precision=load(home/'precision-ablation/summary.json')
    result=load(home/'report/summary.json');target=HERE/'ZLT-BODY-COMMON-COST-20261031.md';text=target.read_text()
    additions=['## 新机制的短观测对照与证书消融','',
        '短对照每配置24次正常请求及24个正确正来源目标，来源边界和必要核验一致；这里没有短窗口的速度结论。仅关闭本轮收缩时，既有selective机制继续启用。','',
        '| 配置 | 可配对测量事件/请求 | 可配对测量字节 | 整批实际省略读取值／分支 |','| --- | ---: | ---: | ---: |']
    for key,title in [('cal-mall-full','full'),('cal-mall-selective-without-body-cut','selective，关闭本轮收缩'),('cal-mall-selective','selective')]:
        c=ablation['modes'][key]['counts'];additions.append('| '+title+' | %.0f | %s | %s／%s |'%(c['measure_events']/16,c['measure_bytes'],c['omitted_field_reads'],c['omitted_branches']))
    additions+=['','本轮收缩每请求实际减少5次字段读取值与6次分支记录，共11条事件。full/selective的其余差异属于既有选择性机制；不把整个差异归给新机制。未删原始日志，也未以增加unknown换记录减少。','',
        '同一完整正式full捕获关闭局部性证书消费后，%s个目标中%s个仍为已知；实际发生收缩的%s份selective捕获在缺少必要证书时全部拒绝。精度消融单列，不作为同答案的低成本参照。'%(precision['full_targets'],precision['full_known_without_certificate'],precision['selective_cut_batches_rejected_without_proof']),'',
        '## 静态规划','', '| 5次fresh-exec中位数 | Orders.total | Mall登录字段 |','| --- | ---: | ---: |']
    for name,key,scale in [('进程内墙时 s','wall_seconds',1),('进程内CPU s','cpu_seconds',1),('新进程总墙时 s','process_wall_seconds',1),('新进程CPU s','process_cpu_seconds',1),('VmHWM MiB','VmHWM_KiB',1024)]:
        values=[statistics.median(r[key]for r in planning['rows']if r['task']==task)/scale for task in('orders','mall')]
        additions.append('| '+name+' | %.4f | %.4f |'%tuple(values))
    additions+=['','固定同一逻辑CPU，OS页缓存未清；五次计划均与部署计划相同。只含已冻结模型JSON载入和规划，不含JAR提取、模型建立、运行时探针、Agent编译和服务启动，不称完整冷启动成本。','',
        '## 采样与部署范围','',
        'Mall业务组为admin/auth/portal，整部署另计MySQL、Redis、Mongo、RabbitMQ；Orders业务组为orders/carts/shipping，整部署计入其11个服务，观测只接入共同任务需要的orders/carts。load-client不计入业务／部署CPU。','',
        '资源采样目标间隔2秒，Docker API读取和top执行另耗时，实际时间戳与每角色样本数保留在resource-cadence.json。RSS为容器内进程RSS求和，可能重复共享页；峰值是采样峰值。两任务分别使用curl HTTP time_total及原urllib完整HTTP读取计时，都排除业务JSON解析／评分，不跨任务直接比较延迟绝对值。','',
        '固定原始业务模板和相关读取状态；Orders准备过程生成的客户、地址及订单ID按每个试次的实值记录。不称跨JVM对象编号、随机盐、时钟或全库字节相同。物理来源坐标分别由各JVM自身原始调用和字段事实核验。','',
        '宿主机仍有四个非实验容器，未操作，不宣称独占物理机。CPU、p95和离线时间的结论以五轮配对范围为限。','']
    text+='\n'.join(additions)
    target.write_text(text)
    cadence=[]
    for job in load(home/'protocol-before-calibration.json')['jobs']:
        trial=home/('round-%02d-%s-%s'%(job['round'],job['task'],job['mode']));phase=load(trial/('measure.json'if job['task']=='mall'else'steady.json'))
        start=phase['start_ns'];end=phase.get('scheduled_end_ns',phase.get('end_ns'))
        rows=[json.loads(s)for s in(trial/'resources.jsonl').read_text().splitlines()];roledata={}
        for role in rows[0]:
            values=[r[role]['monotonic_ns']for r in rows if start<=r[role]['monotonic_ns']<=end]
            gaps=[(b-a)/1e9 for a,b in zip(values,values[1:])];assert len(values)>=2
            roledata[role]={'samples':len(values),'interval_min_seconds':min(gaps),'interval_median_seconds':statistics.median(gaps),'interval_max_seconds':max(gaps)}
        cadence.append({**job,'roles':roledata})
    save(home/'resource-cadence.json',{'nominal_wait_seconds':2,'actual_timestamps_retained':True,'trials':cadence})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);a=p.parse_args();run(a.home.resolve())
