#!/usr/bin/env python3
"""Exact closed-file event bytes by role, not speculative redundant evidence.

Reuse existing fixed-load deployments. Identity-only cohort membership is
cross-checked against the published meter; no propagation or value matching.
"""
import argparse,json,csv,statistics
from pathlib import Path
from collections import Counter,defaultdict
from run_planned_service import load,save,sha

CATEGORIES={
 'enter':'frame_and_call','exit':'frame_and_call','abort':'frame_and_call','collection-call-enter':'frame_and_call','collection-call-exit':'frame_and_call','collection-call-throw':'frame_and_call',
 'read':'field_state','write':'field_state','execution-constructor-enter':'construction','execution-constructed':'construction','execution-object-birth':'construction',
 'branch':'path_and_choice','exception-handler':'path_and_choice','execution-lambda':'path_and_choice',
 'binding-source':'source_boundary','binding-input':'source_boundary',
 'binding-return':'target_binding','http-json':'transport_and_serialization','http-server-context':'transport_and_serialization',
 'http-source-fact':'raw_http_audit','binding-opaque-result':'effect_and_alias','binding-opaque-touch':'effect_and_alias','mongo-save-effect':'effect_and_alias'}


def selected(path,messages):
    rows=[];parent={}
    def find(x):
        parent.setdefault(x,x)
        if parent[x]!=x:parent[x]=find(parent[x])
        return parent[x]
    def union(a,b):
        a,b=find(a),find(b)
        if a!=b:parent[b]=a
    for line in path.read_bytes().splitlines(keepends=True):
        assert line.endswith(b'\n');r=json.loads(line);rows.append((r,len(line)))
        if r.get('frame'):
            f=('frame',r['frame']);find(f)
            if r['kind']=='enter'and r.get('parent'):union(f,('frame',r['parent']))
            if r.get('message'):union(f,('message',r['message']))
        if r.get('message')and r.get('parent_message'):union(('message',r['message']),('message',r['parent_message']))
    roots={find(('message',m))for m in messages}
    assert len(roots)==len(messages)
    return [(r,n)for r,n in rows if any(find(k)in roots for k in ([('frame',r['frame'])]if r.get('frame')else [])+[('message',r[k])for k in ('message','parent_message')if r.get(k)])]


def analyze(root,out):
    out.mkdir(parents=True,exist_ok=False);home=root/'cost-cart';deployments=[];table=[]
    for name,mode in load(home/'config.json')['order']:
        if mode=='original':continue
        d=home/name;p=d/'capture/carts/events.jsonl';messages={r['message']for r in load(d/'steady.json')['requests']};records=selected(p,messages)
        expected=load(d/'measured-request-records.json')['request_records']['carts']
        assert len(records)==expected['events']and sum(n for _,n in records)==expected['bytes']
        kinds=defaultdict(lambda:{'events':0,'bytes':0});groups=defaultdict(lambda:{'events':0,'bytes':0});sites=defaultdict(lambda:{'events':0,'bytes':0});payload=defaultdict(lambda:{'records':0,'fields':0,'compact_json_bytes':0})
        for r,n in records:
            k=r['kind'];category=CATEGORIES.get(k,'unclassified')
            for target in (kinds[k],groups[category],sites[k+'|'+str(r.get('callee',r.get('site',r.get('method',''))))]):target['events']+=1;target['bytes']+=n
            for key in ('fields','args','input_projections','observed','result','receiver','request_serialization'):
                if key in r:
                    v=payload[key];v['records']+=1;v['fields']+=len(r[key])if isinstance(r[key],list)else 0;v['compact_json_bytes']+=len(json.dumps(r[key],ensure_ascii=False,separators=(',',':')).encode())
        assert not groups.get('unclassified')
        for k,v in kinds.items():table.append({'deployment':name,'mode':mode,'kind':k,'category':CATEGORIES[k],**v,'events_per_request':v['events']/len(messages),'bytes_per_request':v['bytes']/len(messages)})
        deployments.append({'deployment':name,'mode':mode,'measured_requests':len(messages),'events':len(records),'bytes':sum(n for _,n in records),'raw_sha256':sha(p),'kinds':dict(kinds),'categories':dict(groups),'sites':dict(sites),'payload_structure_estimates':dict(payload),'offline_entire_batch_phases':load(d/'offline.json')['phases']})
    paired=[]
    for i in range(1,6):
        pair={d['mode']:d for d in deployments if d['deployment'].startswith(f'round-{i:02d}-')};f,s=pair['full'],pair['selective'];removed={}
        for k in set(f['kinds'])|set(s['kinds']):
            a=f['kinds'].get(k,{'events':0,'bytes':0});b=s['kinds'].get(k,{'events':0,'bytes':0})
            if a!=b:removed[k]={'full':a,'selective':b,'event_delta':b['events']-a['events'],'byte_delta':b['bytes']-a['bytes']}
        paired.append({'round':i,'differences':removed})
    result={'source_root':str(root),'scope':'120 measured requests per deployment, exact raw UTF-8 line bytes including newline; whole-batch offline phases include warmup and setup. Categories describe roles and do not prove individual records removable.','payload_note':'Compact JSON serialization estimates are descriptive and are neither raw token spans nor a compression experiment; nested values overlap across categories and must not be added to exact bytes.','deployments':deployments,'paired_differences':paired,'source_meter_crosscheck':True,'no_new_deployments':True}
    save(out/'decomposition.json',result)
    with (out/'event-kinds.csv').open('w',newline='')as f:
        w=csv.DictWriter(f,fieldnames=list(table[0]));w.writeheader();w.writerows(table)
    lines=['# Cart 统一执行内核：事件与离线阶段分解','','复用 `76d2050` 五轮成本捕获，没有新增部署或更改事件格式。按稳态120次请求的实际消息/Frame坐标归组，十份捕获的事件数和原始字节均与已发布计量逐项一致。','', '| 事件种类 | full 每请求 | selective 每请求 | full 字节/请求，中位数 | selective 字节/请求，中位数 |','| --- | ---: | ---: | ---: | ---: |']
    for kind in deployments[0]['kinds']:
        cells=[]
        for mode in ('full','selective'):
            ds=[d for d in deployments if d['mode']==mode];cells.append(statistics.median(d['kinds'].get(kind,{}).get('events',0)/d['measured_requests']for d in ds))
        for mode in ('full','selective'):
            ds=[d for d in deployments if d['mode']==mode];cells.append(statistics.median(d['kinds'].get(kind,{}).get('bytes',0)/d['measured_requests']for d in ds))
        lines.append('| '+kind+' | '+' | '.join(f'{x:.2f}'for x in cells)+' |')
    lines+=['','每请求68→67条，差异全部来自read；构造、字段写入、调用开始/完成、来源及不透明效果记录的条数均未减少。字节差异还受动态ID长度影响，不能把每轮字节变化都解释为位点变化。','','| 整批离线阶段 | full 中位数，秒 | selective 中位数，秒 |','| --- | ---: | ---: |']
    for phase in deployments[0]['offline_entire_batch_phases']:
        vals=[statistics.median(d['offline_entire_batch_phases'][phase]for d in deployments if d['mode']==mode)for mode in ('full','selective')];lines.append('| '+phase+' | '+' | '.join(f'{v:.6f}'for v in vals)+' |')
    lines+=['','该表把独立评分与解码、图还原等阶段分开；它不隔离各类事件的因果耗时。整批阶段包含预热和准备记录，不能除以120解释为每个稳态请求的算法时延。','','调用、构造与字段状态是优先审查的成本来源；来源快照、返回绑定和不透明效果快照还会重复携带对象投影。但内容重叠不等于证据冗余：它们可能分别核验不同时间和版本。删减前必须建立目标数据、成员/路径选择、别名、写入与异常效果的闭包，并回归全部431个状态。当前未宣称其中任何类别可以整体删除，也未把格式压缩当作选择性观测收益。']
    proof_bytes=statistics.median(d['payload_structure_estimates'].get('request_serialization',{}).get('compact_json_bytes',0)/d['measured_requests']for d in deployments)
    lines+=['',f'另一个可定位的观测项是响应中的request_serialization：其紧凑JSON值重编码估计约{proof_bytes:.0f}字节/请求。它包含固定库/运行时证明，实际还原器仅在出站request的写记录上使用该证明（infer_application_execution.py的RequestEntity分支）；响应目标另有独立的verifySerialization和前后快照核验。该估计不是原始字节节省或已完成优化。后续将“取消无必要方向的证明采集”与“目标字段投影”分开验证，保持出站请求证明及目标序列化保护。']
    (out/'report.md').write_text('\n'.join(lines)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();analyze(a.root.resolve(),a.out.resolve())
