"""Replace only inherited rusage peaks in a new derived report directory."""
import argparse,copy,shutil
from pathlib import Path
from run_planned_service import HERE,load,save,sha


def run(home):
    memory=load(home/'current-exec-memory/summary.json');assert memory['complete']and len(memory['measurements'])==30
    index={r['trial']:r for r in memory['measurements']};initial=home/'report-initial-rusage';initial.mkdir(exist_ok=False)
    for name in('ZLT-BODY-COMMON-COST-20261031.md','zlt-body-cost-results-20261031.json','zlt-body-cost-rounds-20261031.csv'):
        shutil.copyfile(HERE/name,initial/name)
    data=copy.deepcopy(load(home/'results-before-report.json'));changed=[]
    for row in data['rows']:
        if row['mode']=='original':continue
        name='round-%02d-%s-%s'%(row['round'],row['task'],row['mode']);m=index[name]
        assert m['answers_and_physical_source_signatures_identical']and m['targets']==m['correct']==180
        old=row['offline_VmHWM_MiB'];row['original_preexec_rusage_maxrss_MiB']=old;row['offline_VmHWM_MiB']=m['current_exec_VmHWM_KiB']/1024
        changed.append({'trial':name,'old_rusage_MiB':old,'current_exec_VmHWM_MiB':row['offline_VmHWM_MiB']})
    view=home/'report-current-exec-memory';view.mkdir(exist_ok=False);save(view/'results-before-report.json',data)
    for name in('protocol-before-calibration.json','static-planning','short-body-observation-ablation.json','precision-ablation'):
        (view/name).symlink_to((home/name).resolve(),target_is_directory=(home/name).is_dir())
    for p in home.glob('round-*'):(view/p.name).symlink_to(p.resolve(),target_is_directory=True)
    from report_zlt_body_cost import run as render
    from append_zlt_body_cost_details import run as details
    render(view);details(view)
    note=('内存口径另经校正：原`ru_maxrss`部分带入fork／exec前映像的高水位；原值与初始派生表保留在`report-initial-rusage/`。'
          '在线全部结束后，对同一30份完整工具捕获作fresh-exec内存复算，读取当前`/proc/self/status`的VmHWM；每份180个答案及物理来源签名逐项相同。'
          '本表只替换内存列，原在线CPU／延迟及有效离线墙时／CPU全部保持，不称新Agent部署或新速度实验。')
    p=HERE/'ZLT-BODY-COMMON-COST-20261031.md';text=p.read_text();paragraph=text.index('\n\n',text.index('\n\n')+2);text=text[:paragraph]+'\n\n'+note+text[paragraph:]
    text=text.replace('没有push。\n##','没有push。\n\n##')
    text+='\nOrders的整批full/selective字节差异集中在未配对／共享记录，可配对测量字节仅减少约0.21%。未配对部分可能包含准备、启动及无法归属的稳态内部观测，不能全部解释成准备成本，也不能把整批57.74%直接称为稳态查询观测收益。\n'
    p.write_text(text)
    for path in(view/'report/summary.json',HERE/'zlt-body-cost-results-20261031.json'):
        summary=load(path);summary['memory_measurement']={'basis':'Current-exec /proc/self/status VmHWM; same complete captures, exact physical answers/signatures',
            'original_timings_preserved':True,'original_rusage_peaks_preserved':True,'repeat_source_sha256':sha(home/'current-exec-memory/summary.json')};save(path,summary)
    save(view/'memory-correction-receipt.json',{'all_passed':True,'original_results_sha256':sha(home/'results-before-report.json'),'only_memory_metric_changed':True,
        'measurements':changed,'same_online_captures':True,'new_online_deployments':0,'valid_original_wall_and_CPU_preserved':True})
    print('Current-exec memory corrected for 30 captures; original timings retained')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);a=p.parse_args();run(a.home.resolve())
