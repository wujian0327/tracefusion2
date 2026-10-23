#!/usr/bin/env python3
"""Read-only audit/report of sealed first captures, including all failures."""
import argparse,json,csv,shutil
from pathlib import Path
from collections import Counter
from run_planned_service import ROOT,HERE,load,save,sha


def audit(root,out):
    out.mkdir(parents=True,exist_ok=False);protocol=load(root/'protocol-before-first.json');qs=protocol['queries'];records=[];table=[];coverage={};failures=[]
    for mode in ('full','selective','mirrortaint'):
        inventory={}
        for app in ('train-first','orders-first'):
            home=root/app
            for p in home.glob('*/evaluation.json'):
                x=load(p)
                for r in x if isinstance(x,list)else [x]:
                    if r['mode']!=mode:continue
                    assert r['query']not in inventory;r={**r,'evaluation_file':str(p)};inventory[r['query']]=r
        correction=root/'native-orders-packaging-correction/native/evaluation.json'
        if mode=='mirrortaint'and correction.exists():
            for r in load(correction):
                assert r['query']not in inventory;inventory[r['query']]={**r,'evaluation_file':str(correction),'packaging_failure_preserved':str(root/'orders-first/native/failure.json')}
        for p in (root/'independent-id-projection-correction').glob('*/evaluation.json'):
            r=load(p)
            if r['mode']!=mode:continue
            first=inventory[r['query']];assert first['targets']==r['targets']
            inventory[r['query']]={**r,'evaluation_file':str(p),'initial_evaluation_file':first['evaluation_file'],'evaluation_only_correction':True}
        for q in qs:
            r=inventory.get(q['id'])
            if r:
                r['application']=q['application'];records.append(r)
                for t in r['predictions']:table.append({'tool':mode,'application':q['application'],'query':q['id'],'case':t['case'],'path':t['path'],'state':t['state'],'oracle_available':'oracle_error'not in t,'tp':t.get('tp'),'fp':t.get('fp'),'fn':t.get('fn'),'evidence':r['evaluation_file']})
            else:failures.append({'tool':mode,'query':q['id'],'state':'not_evaluated','possible_receipts':[str(p)for app in ('train-first','orders-first')for p in (root/app).glob('*'+q['id']+'/failure.json')]})
        for app in ('sockshop','trainticket','all'):
            rs=[r for r in inventory.values()if app=='all'or next(q for q in qs if q['id']==r['query'])['application']==app];ts=[t for r in rs for t in r['predictions']];states=Counter(t['state']for t in ts)
            coverage[mode+'/'+app]={'evaluated_queries':len(rs),'requests_including_NA':sum(r['requests']for r in rs),'N/A_requests':sum(r['N/A_requests']for r in rs),'targets':len(ts),'states':dict(states),'independently_correct_fraction':states['known_correct']/len(ts)if ts else None,'oracle_unavailable':sum('oracle_error'in t for t in ts),'families_with_correct_answer':sum(any(t['state']=='known_correct'for t in r['predictions'])for r in rs),'relations':{k:sum(t.get(k,0)for t in ts)for k in ('tp','fp','fn')}}
    disagreements=[]
    for q in qs:
        rs={r['mode']:r for r in records if r['query']==q['id']}
        if not all(m in rs for m in ('full','selective')):continue
        pair={m:{(t['case'],t['path']):t for t in rs[m]['predictions']}for m in ('full','selective')};assert pair['full'].keys()==pair['selective'].keys()
        for k,a in pair['full'].items():
            b=pair['selective'][k]
            if a['state']!=b['state']or (a.get('tp'),a.get('fp'),a.get('fn'))!=(b.get('tp'),b.get('fp'),b.get('fn')):disagreements.append({'query':q['id'],'case_path':k,'full':a['state'],'selective':b['state']})
    mapper_audits=[str(p)for p in root.rglob('native-library-audit.json')if 'baseline-packaging-calibration'not in str(p)]
    paired=Counter();initial=Counter()
    lookup={(r['mode'],r['query'],t['case'],t['path']):t for r in records for t in r['predictions']}
    for r in records:
        if r['mode']!='mirrortaint':continue
        for t in r['predictions']:
            a=lookup[('selective',r['query'],t['case'],t['path'])]
            paired[(t['state'],a['state'])]+=1
    for p in (root/'train-first').glob('*/evaluation.json'):
        r=load(p)
        if isinstance(r,dict)and r.get('mode')=='selective':initial.update(r['states'])
    for p in (root/'orders-first').glob('*/evaluation.json'):
        r=load(p)
        if isinstance(r,dict)and r.get('mode')=='selective':initial.update(r['states'])
    for p in mapper_audits:assert load(Path(p))['passed']
    for p,h in load(root/'algorithm-freeze.json')['sources'].items():assert sha(root/'frozen-source-snapshot'/Path(p).name)==h
    plan=load(root/'frozen-plans/planning.json');result={'algorithm':'76d2050','protocol_commit':'dfd9195','queries':len(qs),'entries':protocol['entry_count'],'novelty':protocol['novelty'],'planning_accepted':sum(r['accepted']for r in plan),'coverage':coverage,'not_evaluated':failures,'full_selective_state_or_relation_disagreements':disagreements,'source_coordinates_note':'Independent physical instance truth is evaluated within each fresh JVM. Across JVMs, object/call IDs are different; agreement below compares aligned query/case/path states and relation counts, not literal object IDs.','baseline_mapper_audits':mapper_audits,'records':records}
    result['baseline_selective_pairing']={a+' -> '+b:n for (a,b),n in paired.items()};result['initial_selective_scoring_before_document_key_correction']=dict(initial)
    assert not sum(n for (a,b),n in paired.items()if a=='known_correct'and b!='known_correct')
    save(out/'audit.json',result)
    with (out/'target-states.csv').open('w',newline='')as f:
        w=csv.DictWriter(f,fieldnames=list(table[0]));w.writeheader();w.writerows(table)
    save(HERE/'heldout29-results-20261023.json',{k:v for k,v in result.items()if k!='records'})
    lines=['# 冻结后的29个新字段首次覆盖验证','','核心保持 `76d2050`，先提交协议 `dfd9195`，随后规划和首次执行。原91个候选（Sock Shop37、Train Ticket54）中62个已用于开发，本轮纳入剩余全部29个（Sock Shop7、Train Ticket22），不按结果替换。它们来自8个已见入口，全部属于“旧入口新字段”，不作为新入口或第三方盲测证据。','','## 端到端结果','','| 配置 / 应用 | 查询族 | 请求（含N/A） | N/A请求 | 目标实例 | 已独立核验正确 | unknown | 已知错误 | 证据无效 | 真值不足 |','| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for key,c in coverage.items():
        if key.endswith('/all'):continue
        s=c['states'];lines.append('| '+key+' | '+' | '.join(str(v)for v in (c['evaluated_queries'],c['requests_including_NA'],c['N/A_requests'],c['targets'],s.get('known_correct',0),s.get('unknown',0),s.get('known_wrong',0),s.get('evidence_invalid',0),c['oracle_unavailable']))+' |')
    lines+=['','计数单位为查询族－请求及实际元素实例；MirrorTaint按入口一次捕获可评多字段，因此表中基线请求为查询请求数，不能当作独立HTTP部署请求数。固定null若出现在响应中仍是目标，空列表无元素才记N/A。真值不足不等于unknown：已知但未核验的答案单列known_unchecked，不计为正确。','']
    for key,c in coverage.items():
        if key.endswith('/all'):
            s=c['states'];known=sum(s.get(k,0)for k in ('known_correct','known_wrong','known_unchecked'));verified_known=s.get('known_correct',0)+s.get('known_wrong',0)
            lines.append(f"- {key}: {s.get('known_correct',0)}/{c['targets']}目标得到独立正确答案；已知答案率{known}/{c['targets']}（含错误及未核验答案），已知且可核验答案匹配{s.get('known_correct',0)}/{verified_known}；{c['families_with_correct_answer']}/29查询族至少一个正确答案；关系TP/FP/FN={c['relations']['tp']}/{c['relations']['fp']}/{c['relations']['fn']}（真值不足目标不计关系分母）。")
    lines+=['','## 逐查询结果','','| 查询 | full：正确/目标 | selective：正确/目标 | MirrorTaint：正确/目标 |','| --- | ---: | ---: | ---: |']
    for q in qs:
        cells=[]
        for mode in ('full','selective','mirrortaint'):
            r=next((r for r in records if r['query']==q['id']and r['mode']==mode),None);cells.append(f"{r['states'].get('known_correct',0)}/{r['targets']} {r['states']}"if r else '未完成，见失败清单')
        lines.append('| `'+q['id']+'` | '+' | '.join(cells)+' |')
    lines+=['','## 实验有效性与边界','','所有29个计划均由冻结规则选择；没有新增业务传播公式、库摘要或核心语义。单查询仍需入口、目标和来源边界三类声明，运行策略由公共静态规则选择。','',f'full/selective在已完成的对齐目标上，状态或关系数量差异为{len(disagreements)}；这不能以跨部署同值代替物理实例检查，正确答案均先在各自捕获中独立核验。',f'实际业务ObjectMapper定义有{len(mapper_audits)}份原生类哈希审计。MirrorTaint原作者传播JAR与v09适配器二进制未变，仅隔离导出器私有Jackson；本组为新固定配置结果，历史368个正确实例集合仍单列。','','Orders生成ID与self-link的独立物理坐标在预注册协议中明确未获保证，若不足继续报告oracle_unavailable，不能把未知来源当空。嵌套字段沿实际解码对象与版本核验。Basic percent按原代码的默认值/常量赋值评空输入数据来源；TicketInfo字段沿实际Basic响应投影。来源规则不调用TF传播或基线标签。','','Orders基线首次启动因驱动移除业务JAR挂载而退出，未执行测试请求；失败目录永久保留。修正仅恢复同一原版JAR挂载，在native-orders-packaging-correction单独捕获，未改算法、输入规则或真值，不覆盖首轮。','','未根据这批查询结果修改核心。旧62查询428/431及旧成本结果原样保留；本组不是最终优化版能力复验，也不建立当前版本外部成本排名。','','原始工件见 `artifacts/heldout29-first-20261023/`；首次捕获、失败、计划、独立真值、预测、机器/镜像及类加载证据保留。Git只保存小型摘要，完整数据需单独备份。']
    lines+=['','Route过滤id首次评分因真值函数将数据库_id写成id而报KeyError。原始捕获和首次known_unchecked评分保留，independent-id-projection-correction仅按预注册仓储字段投影修正评分键，不调用TF传播、不重新部署、不改核心，不记作算法提升。',f'原始selective首次评分状态（修正前）：{dict(initial)}；full相同。评分修正影响每模式10个目标，其余评分未替换。','全部analysis_limited、known_unchecked等状态详见JSON/CSV，不合并成N/A或正确。','','## 逐实例能力差异','',f'按相同查询、输入case及实际目标路径对齐：{result["baseline_selective_pairing"]}。本组基线正确的210个目标全部被TF正确回答；另17个基线错误和5个基线unknown目标由TF正确回答。12个真值不足目标仍无法作能力优劣判断。该结论仅限本轮固定任务及适配配置。','','两个可复核的差异：Route同值距离列表中，基线将/data/0/distances/1连到了源/0/distances/0（实际应为/0/distances/1）；Basic.confortClass的7个实例给出空来源而实际应来自Train响应字段。这里记录观测到的错位/漏关系，不据此断言其全部内部成因。基线的5个unknown属于PriceConfig.id，不能按空来源算成功。']
    if failures:lines+=['',f'尚有{len(failures)}个工具－查询未完成评价，详见audit.json；未将其排除后宣称全覆盖。']
    (out/'report.md').write_text('\n'.join(lines)+'\n')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();r=audit(a.root.resolve(),a.out.resolve());print(json.dumps({k:v for k,v in r.items()if k in ('coverage','not_evaluated')},ensure_ascii=False))
