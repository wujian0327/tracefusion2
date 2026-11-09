"""Three version-labelled paper tables, CSV + LaTeX + inspectable source hashes."""
import argparse
from collections import Counter
import csv
from pathlib import Path

from run_planned_service import ROOT, load, save, sha

EXP=Path(__file__).resolve().parent
REF=ROOT/'artifacts/pruning-contribution-audit-20261106'
REJECT={'planning_refused','planning_rejected','runtime_contract_rejected','evidence_invalid',
        'instrumented_business_failure','validation_rejected','semantic_rejected','analysis_limited'}


def counts(states):
    result={'targets':sum(states.values()),'correct':states.get('known_correct',0),
            'unknown':states.get('unknown',0),'rejected_invalid':sum(v for k,v in states.items()if k in REJECT),
            'wrong':states.get('known_wrong',0)}
    result['other_unscored']=result['targets']-sum(result[k]for k in ('correct','unknown','rejected_invalid','wrong'))
    assert result['other_unscored']>=0
    return result


def emit(out,name,rows):
    fields=list(dict.fromkeys(k for r in rows for k in r))
    with(out/(name+'.csv')).open('w')as f:
        writer=csv.DictWriter(f,fields,lineterminator='\n');writer.writeheader();writer.writerows(rows)
    def tex(value):
        value='--'if value is None else str(value)
        return ''.join({'\\':r'\textbackslash{}','_':r'\_','%':r'\%','&':r'\&','#':r'\#','{':r'\{','}':r'\}'}.get(c,c)for c in value)
    # Wide CSV is the machine-readable table; compact selected columns form
    # publication snippets. XeLaTeX/CJK font setup belongs to the paper template.
    chosen={'capability':['stage','version','group','targets','correct','unknown','rejected_invalid','wrong','other_unscored'],
            'mt-paired':['version','group','targets','TF_correct','TF_unknown','TF_rejected_invalid','TF_other_unscored',
                         'MT_correct','MT_wrong','MT_unknown','MT_rejected_export','MT_other_unscored'],
            'pruning-ablation':['version','task','mechanism','trigger','batch_bytes','trace_CPU','business_CPU','p95']}[name]
    body=['% Generated; no cross-version aggregate. F/S counts are per mode.',
          '\\begin{tabular}{'+'l'*len(chosen)+'}', '\\hline',
          ' & '.join(tex(c)for c in chosen)+r' \\',r'\hline']
    body+=[' & '.join(tex(row.get(k,''))for k in chosen)+r' \\'for row in rows]
    body += [r'\hline',r'\end{tabular}']
    (out/(name+'.tex')).write_text('\n'.join(body)+'\n')


def run(home,out,include_new):
    out.mkdir(parents=True,exist_ok=False);manifest={}
    def read(path):
        path=Path(path);manifest[str(path.relative_to(ROOT))]=sha(path);return load(path)
    ability=[];paired=[];ablation=[]
    def cap(stage,version,group,states,source,notes=''):
        row={'stage':stage,'version':version,'group':group,'modes':'full=selective, each mode',**counts(states),'states':str(states),'source':str(source),'notes':notes};ability.append(row);return row
    def mt(version,group,tf,baseline,source,adapter,notes):
        a,b=counts(tf),counts(baseline);assert a['targets']==b['targets']
        paired.append({'version':version,'group':group,'targets':a['targets'],
                       **{'TF_'+k:a[k]for k in ('correct','unknown','rejected_invalid','wrong','other_unscored')},
                       'MT_correct':b['correct'],'MT_wrong':b['wrong'],'MT_unknown':b['unknown'],
                       'MT_rejected_export':b['rejected_invalid'],'MT_other_unscored':b['other_unscored'],
                       'adapter':adapter,'MT_run':'historical fixed reference','source':str(source),'notes':notes})
    path=EXP/'baseline-capability-results-20261020.json';first=read(path)['with_first_creation_challenge']
    cap('原开发集首轮','2b3b929','原62查询',first['tf_states'],path,'原18入口；不是未见查询。')
    histpath=REF/'capability-pass-01/audit-historical/summary.json';hist=read(histpath)
    cap('原开发集最终回归','bcdf059','原62查询',hist['historical62']['full']['states'],histpath,'431实际目标，3 unknown保持。')
    mt('bcdf059','原62查询',hist['historical62']['full']['states'],first['baseline_states'],path,
       '披露适配器校准05/07/08/09；原生JAR e4c6792', 'TF为bcdf059新部署；MT为原同输入/边界历史参考。空原生标签敏感性：31个空来源匹配单列，不声称任意MT配置。')
    cap('已启封开发拓展回归','bcdf059','29字段',hist['fields29']['modes']['full']['states'],histpath,'12项独立真值不足，不能补空来源或计算完整Recall。未列MT对照，缺少校准。')
    cap('开发写入口回归','bcdf059','15写入口',hist['write15']['full']['states'],histpath,'96目标；不当作新保存sink接口验收；MT未校准。')
    pigpath=EXP/'piggy-first-capability-results-20261028.json';pig=read(pigpath)
    cap('冻结首次迁移/回溯评分','ae7fe8d','Piggy Account返回',pig['per_tool']['full']['states'],pigpath,'40返回目标；不替代其余361项任务。')
    acct=hist['Account40']['modes']['full'];astates={k:acct[k]for k in ('known_correct','unknown','known_wrong')if acct[k]}
    cap('适配后回归','bcdf059','Piggy Account返回',astates,histpath,'4正来源、36已知空来源。')
    mt('bcdf059','Piggy Account返回',astates,pig['per_tool']['baseline']['states'],pigpath,'原固定隔离JSON适配器/原生传播不变','MT历史同40任务；其余361任务未配对，不填FP/FN。')
    extpath=EXP/'external-transfer-results-20261029.json';ext=read(extpath)
    for v in ('ae7fe8d','78a9534'):
        cap('冻结迁移C1来源配置校准',v,'Apollo+Mall十API',ext['states'][v+'-full'],extpath,'299声明入口返回目标；7 handler叶另列，非完整HTTP/sink验收。')
    mallpath=REF/'capability-pass-01/audit-mall/summary.json';mall=read(mallpath)
    cap('适配后回归','bcdf059','Mall五API',mall['modes']['full']['states'],mallpath,'98联合门槛保持；5项真值不足。')
    mt('bcdf059','Mall五API',mall['modes']['full']['states'],{'known_correct':88,'known_wrong':5,'unknown':5,'known_unchecked':5},extpath,
       '固定MT+B0','同原103任务；88正确(62正/26空)，5确定错误，5无答及5真值缺口；MT未新跑。')
    firstzpath=EXP/'frozen-zlt-reuse-results-20261030.json';firstz=read(firstzpath)
    cap('冻结首次迁移','c1a4e5c','ZLT两入口',firstz['states']['full'],firstzpath,'15正来源任务；初始物理调用配对不足。')
    zpath=REF/'capability-pass-01/audit-zlt/summary.json';z=read(zpath)
    cap('适配后回归','bcdf059','ZLT两入口',z['states']['full'],zpath,'15/15正来源；B0初始Class导出失败未覆盖。')
    zmtpath=EXP/'zlt-foundation-results-20261031.json';zmt=read(zmtpath)
    mt('bcdf059','ZLT两入口',z['states']['full'],zmt['states']['mirrortaint'],zmtpath,
       'B2.2 Class有限导出，原生JAR不变','历史B2.2同输入/mapper来源；首次B0导出失败15项仍单列。')
    firstpath=EXP/'target-external-first-results-20261103.json';firstext=read(firstpath)
    for app,label in [('ruoyi','RuoYi六查询'),('teastore','TeaStore六查询')]:
        tf=Counter();native=Counter()
        for api in firstext['APIs']:
            if api['application']==app:
                tf.update(api['tools']['full']['states']);native.update(api['tools']['mirrortaint']['states'])
        cap('冻结首次迁移','1308589',label,dict(tf),firstpath,'RuoYi95含动态code6；TeaStore46含生成状态缺口；未绑定/未评分不当作正确。')
        mt('1308589',label,dict(tf),dict(native),firstpath,'固定MT+B2.2',
           '该批双方均为当时新运行；表在本轮复用历史结果。TeaStore目标/来源导出缺口不是原生传播错误。')
    for config in ('C1','C2'):
        rp=REF/('final-'+config+'-score/summary.json');r=read(rp)
        cap('适配后回归','bcdf059','RuoYi '+config,r['states']['full'],rp,
            'C1:4冷启动+5原来源声明缺口；原dynamic code仍未扩展。'if config=='C1'else'C2实际mapper声明双方一致，单列不替代C1。')
        mt('bcdf059','RuoYi '+config,r['states']['full'],{'known_correct':84,'oracle_or_target_unavailable':5}if config=='C1'else{'known_correct':5},rp,
           '固定MT+B2.2，历史同配置参考','MT不新跑；C1的5项声明/真值缺口不当作传播错误。C2另任务配置。')
    ability.append({'stage':'未完成范围','version':'原协议保留','group':'原8应用/40 API共同任务','modes':'--',
                    **{k:None for k in ('targets','correct','unknown','rejected_invalid','wrong','other_unscored')},
                    'notes':'尚未完成全部返回+保存/消息sink及真值封存；不以旧62/29/15或本轮子集填补。'})
    if include_new:
        for folder,label in [(home,'A0'),(home/'calibration-C2','列表C2接入校准'),(home/'post-metadata-C2','详情C2接入校准')]:
            sp=folder/'audit-final/summary.json';summary=read(sp)
            for q in dict.fromkeys(r['query']for r in summary['queries']):
                f=next(r for r in summary['queries']if r['query']==q and r['mode']=='full')
                s=next(r for r in summary['queries']if r['query']==q and r['mode']=='selective')
                assert f['states']==s['states']
                n=next(r for r in summary['queries']if r['query']==q and r['mode']=='mirrortaint')
                cap('冻结后新查询/'+label,'bcdf059',q,f['states'],sp,'本轮预先固定两个逻辑查询；A0及C1配置失败保留，C2仅元数据/坐标校准，无核心修订。')
                if label!='A0' or q=='fresh-post-detail':
                    mt('bcdf059',q+'/'+label,f['states'],n['states'],sp,'同一固定MT+B2.2',
                       '本轮同任务新运行；若MT为兼容捕获复用，见部署收据。不将A0错误坐标任务作为校准完成的基线排名。')
                    paired[-1]['MT_run']='new this round'if n['new_deployment']else'compatible capture from this round A0'
    costpath=EXP/'pruning-contribution-results-20261106.json';cost=read(costpath)
    for task in ('mall','zlt-user','ruoyi-dictionary'):
        for arm in ('boundary_only','write_only','body_only','all'):
            key=task+'-'+arm
            actual=cost['diagnosis'][task][arm]['requests']
            vector=[actual['boundary_scalar_values_omitted']+actual['boundary_container_values_omitted'],
                    actual['constructor_write_values_omitted']+actual['application_write_values_omitted'],
                    actual['body_field_reads_omitted']+actual['body_branches_omitted']]
            trigger=str(vector)+' /16 requests'
            if key not in cost['formal']['paired']:
                ablation.append({'version':'bcdf059','task':task,'mechanism':arm,'trigger':trigger,
                                 'batch_bytes':'--','trace_CPU':'--','business_CPU':'--','p95':'--',
                                 'notes':'无新增触发或全开与单开向量重复；未重复速度测量。','source':str(costpath)})
                continue
            d=cost['formal']['paired'][key]
            def ratio(k):
                v=d[k];return f"{(v['median_ratio']-1)*100:+.2f}% [{v['min_ratio']:.4f},{v['max_ratio']:.4f}]"
            ablation.append({'version':'bcdf059','task':task,'mechanism':arm,'trigger':trigger,
                             'batch_bytes':ratio('batch_bytes'),'trace_CPU':ratio('trace_process_cpu_seconds'),
                             'business_CPU':ratio('business_CPU'),'p95':ratio('p95_ms'),
                             'trace_wall':ratio('trace_process_wall_seconds'),'trace_VmHWM':ratio('trace_VmHWM_KiB'),
                             'RSS':ratio('business_RSS_MiB'),'measure_bytes':ratio('measure_bytes'),
                             'body_eligible_calls':actual['body_guard_eligible_calls'],
                             'body_selected_calls':actual['body_selected_calls'],
                             'notes':'共同selective计划，三类全关基线；5轮同轮比值。范围跨1无稳定改善。','source':str(costpath)})
    # Non-pruning references are deliberately separate records, never new
    # bcdf059 online/offline columns or rows in the ablation table.
    engineering=[]
    for filename,scope in [('zlt-user-offline-results-20261103.json','共享初始化查找索引；旧捕获离线复算，非剪枝。'),
                           ('shared-work-results-20261106.json','独立评分索引及共享查找；不归选择性。'),
                           ('zlt-body-cost-results-20261031.json','7e4ad0b Orders专用路径/旧共同任务成本，不拼入bcdf059消融。'),
                           ('ruoyi-postcopy-payload-results-20261108.json','720候选仅分析，阶段草案净增；紧凑方案许可未闭合，无Agent试点。')]:
        p=EXP/filename;v=read(p);engineering.append({'source':str(p),'sha256':sha(p),'scope':scope})
    references=[]
    index=read(EXP/'zlt-user-offline-results-20261103.json')
    for mode,v in index['paired_capture_results'].items():
        w=v['wall_seconds'];references.append({'category':'shared-initialization-index','version':index['reference']+' -> '+index['index_commit'],
            'task':'zlt-user-'+mode,'metric':'old-report process wall seconds','before':w['reference_median'],'after':w['indexed_median'],
            'paired_change_percent':w['paired_change_percent'],'ratio_range':w['ratio_range'],
            'scope':'Same original capture offline only; old report stages, not bcdf059 online or pruning.', 'source':str(EXP/'zlt-user-offline-results-20261103.json')})
    shared=read(EXP/'shared-work-results-20261106.json')
    for component,values in shared['offline_core_and_score'].items():
        for task,v in values['paired'].items():
            w=v['process_wall_seconds'];references.append({'category':'independent-score-index'if component=='score-only'else'shared-core-lookup',
                'version':'4cb5943 core / df977b7 score'if component=='score-only'else'5f0c647 -> 4cb5943, same df977b7 score',
                'task':task,'metric':'old-report process wall seconds','before':w['old_median'],'after':w['new_median'],
                'paired_change_percent':(w['median_ratio']-1)*100,'ratio_range':[w['min_ratio'],w['max_ratio']],
                'scope':'Same capture; old total includes independent score. Not pruning or a new online experiment.', 'source':str(EXP/'shared-work-results-20261106.json')})
    specialized=read(EXP/'zlt-body-cost-results-20261031.json')
    for metric in ('p95_ms','business_cpu_one_core_percent'):
        w=next(r for r in specialized['paired']if r['task']=='orders'and r['comparison']=='selective/mirrortaint'and r['metric']==metric)
        references.append({'category':'old-specialized-path','version':specialized['algorithm'],'task':'Orders.total selective / fixed MT',
            'metric':metric,'before':specialized['medians']['orders']['mirrortaint'][metric],
            'after':specialized['medians']['orders']['selective'][metric], 'paired_change_percent':w['median_change_percent'],
            'ratio_range':[w['min_ratio'],w['max_ratio']], 'scope':'Old common task and sending-side Carts source boundary; not bcdf059.',
            'source':str(EXP/'zlt-body-cost-results-20261031.json')})
    save(out/'engineering-references.json',references)
    for name,rows in [('capability',ability),('mt-paired',paired),('pruning-ablation',ablation)]:emit(out,name,rows)
    save(out/'tables.json',{'capability':ability,'mt_paired':paired,'pruning_ablation':ablation,
                           'separate_non_pruning_references':engineering,'engineering_reference_numbers':references,'no_cross_group_or_version_total':True})
    save(out/'source-hashes.json',manifest)
    print({'capability_rows':len(ability),'MT_rows':len(paired),'ablation_rows':len(ablation),'include_new':include_new})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--home',required=True,type=Path);p.add_argument('--out',required=True,type=Path);p.add_argument('--include-new',action='store_true');a=p.parse_args();run(a.home.resolve(),a.out.resolve(),a.include_new)
