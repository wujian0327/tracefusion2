"""Describe complete exposed-task records; never infer speed from pilots."""
import argparse
from collections import Counter
from pathlib import Path
from run_planned_service import ROOT,load,save,sha


def describe(path):
    import json
    values=Counter();types=Counter();bytes_by_type=Counter();omissions=Counter();body=Counter()
    for line in path.read_bytes().splitlines(keepends=True):
        r=json.loads(line);types[r['kind']]+=1;bytes_by_type[r['kind']]+=len(line)
        for key in ('scalar_fields','container_values'):
            omissions[key]+=sum(r.get('target_observation',{}).get(key,{}).values())
        for key in ('field_reads','branches'):body[key]+=r.get('body_observation_omissions',{}).get(key,0)
        for f in r.get('fields',[]):values[f.get('field','unknown')]+=1
    return {'path':str(path.relative_to(ROOT)),'sha256':sha(path),'complete_bytes':path.stat().st_size,
        'events':sum(types.values()),'types':dict(types),'bytes_by_type':dict(bytes_by_type),
        'persisted_field_values':sum(values.values()),'snapshot_omissions_by_kind':dict(omissions),
        'skipped_existing_body_hooks':dict(body),'short_capture_not_performance':True}


def run(home,out):
    out.mkdir(parents=True,exist_ok=False)
    files=list((home/'pilot-01/mall/tool-runs/mall-swarm-3').glob('*/query-002/capture/events.jsonl'))
    rows=[describe(p)for p in files]
    prior=load(home/'prior-cost-inventory/inventory.json')
    save(out/'summary.json',{'complete_prior_capture_decomposition':prior,'development_pilots':rows,
        'attribution':'Projection-only on/off new captures are required for the independent mechanism ablation. Full/selective pilot differences also contain existing body and transport choices.',
        'retention':'Calls, writes, effects, locality/source/transport proofs and completeness remain necessary; categories are descriptive, not deletion permissions.'})
    lines=['# 开发集证据成本与机制消融','',
        '本表分解完整捕获，不截断或过滤记录。历史捕获只用于定位记录成本；开发短捕获只验证实际省略和答案，不用于速度结论。独立机制消融与最终正式成本另行追加。','',
        '| 参照捕获 | 完整字节 | 事件 | 最大记录类型（按字节） |','| --- | ---: | ---: | --- |']
    for r in prior:
        top=sorted(r['record_types'].items(),key=lambda x:x[1]['bytes'],reverse=True)[:4]
        lines.append('| '+r['path']+' | '+str(r['complete_file_bytes'])+' | '+str(r['total_events'])+' | '+'；'.join(k+' '+format(v['byte_share']*100,'.2f')+'%'for k,v in top)+' |')
    lines+=['','Mall 的调用完成／开始、opaque 快照和局部性协议占据主要部分。ZLT 还有较大的字段／容器快照成本。因此本轮将可证明无关的边界快照值纳入统一字段需求闭包；没有删除整个调用或移除证书。','',
       '| Mall 开发捕获 | 完整字节 | 事件 | 跳过标量取值 | 省去 Map 叶记录 |','| --- | ---: | ---: | ---: | ---: |']
    for r in rows:lines.append('| '+r['path']+' | '+str(r['complete_bytes'])+' | '+str(r['events'])+' | '+str(r['snapshot_omissions_by_kind'].get('scalar_fields',0))+' | '+str(r['snapshot_omissions_by_kind'].get('container_values',0))+' |')
    lines+=['','标量计数是实际 Agent 在反射取值前跳过的次数；Map 计数是省去的叶记录，迭代和已有值读取仍保留；没有把离线过滤记录当作在线节省。完整 full/selective 差异还包括此前已有的观测选择，不能全部归因于新增值投影。当前不报告短窗口的 CPU 或延迟改善。','',
       '保留理由：数据事件为目标计算提供依赖；分支与异常确定实际路径；引用、版本、发布和效果协议保护别名及局部性；来源调用、目标／通信绑定和闭合协议认证实例；启动元数据、共享事件和诊断另列。尚未分类的记录继续保留。',
       '', '共享索引、协议编码和诊断开关没有作为新增剪枝贡献。本轮主要省略发生在反射取值／装箱和字段事件构建之前，而非改变序列化编码。']
    (out/'report.md').write_text('\n'.join(lines)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.home.resolve(),a.out.resolve())
