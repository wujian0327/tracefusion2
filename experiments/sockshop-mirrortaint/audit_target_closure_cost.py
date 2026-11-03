"""Whole-capture accounting and the predeclared task-level joint criterion."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import statistics
from run_planned_service import ROOT,load,save,sha
from run_target_closure_cost import FINAL,verify


def counts(trial,task,mode):
    import audit_zlt_body_cost as previous
    if not task.startswith('zlt-'):return previous.counts(trial,task,mode)
    warm=load(trial/'warmup.json')['requests'];measure=load(trial/'measure.json')['requests']
    measured={c['message']for c in measure};messages=measured|{c['message']for c in warm}
    files=[trial/'capture'/name for name in(('native-capability.jsonl','instances.jsonl','native-library.jsonl')if mode=='mirrortaint'else('events.jsonl',))]
    parents={};rows=[]
    for file in files:
        lines=file.read_bytes().splitlines(keepends=True);events=[json.loads(line)for line in lines];rows.append((lines,events))
        for r in events:
            message=r.get('message');parent=r.get('parent_message')
            if message and parent:assert parents.get(message,parent)==parent;parents[message]=parent
    result=Counter();kinds=Counter()
    for lines,events in rows:
        normalized=[dict(r,kind=r.get('kind','native-'+str(r.get('phase'))),context=r.get('context',r.get('instance_context',{})))for r in events]
        result.update(previous.attributable(normalized,lines,measured,messages,parents));kinds.update(r['kind']for r in normalized)
    capture=trial/'capture';allfiles={str(p.relative_to(capture)):p.stat().st_size for p in capture.rglob('*')if p.is_file()}
    result['all_capture_file_bytes']=sum(allfiles.values())
    return {'counts':dict(result),'kind_counts':dict(kinds),'capture_files':allfiles,
            'scope':'Concrete Frame/call/message ancestry only. Shared/unmatched retained; saved bytes, not maximum I/O.'}


def resource_audit(trial,task,start,end,reported):
    from run_sockshop_cost import Sampler
    rows=[json.loads(line)for line in(trial/'resources.jsonl').read_text().splitlines()]
    # Group addition order is part of the original sampler's exact arithmetic.
    # Recover its explicit service order rather than alphabetically sorting it.
    cfg=load(trial/('compose.json'if task!='orders'else'sockshop/compose.json'))
    if task=='mall':observed=('admin','auth','portal')
    elif task.startswith('zlt-'):observed=('zlt-user','zlt-uaa')
    else:
        from run_sockshop_cost import ROLES
        observed=ROLES
    roles=([r['Config']['Labels']['com.docker.compose.service']for r in load(trial/'sockshop/containers.json')]
           if task=='orders'else[r for r in cfg['services']if r in rows[0]])
    assert roles==list(rows[0]),'Sampler role-order receipt differs'
    sampler=Sampler({r:None for r in roles},2,trial/'unused-resource-audit.jsonl',observed_roles=observed)
    sampler.rows=rows
    actual=sampler.summary(start,end);assert actual==reported,'Resource summary differs from raw aligned samples'
    return {'resources_sha256':sha(trial/'resources.jsonl'),'exact':True,'role_order':roles,'observed_order':list(observed)}


def audit(home,out):
    verify();protocol=load(home/'protocol-before-calibration.json');complete=load(home/'formal-complete.json')
    assert complete['complete'];out.mkdir(parents=True,exist_ok=False);rows=[];receipts=[]
    from run_sockshop_cost import percentiles
    for job in protocol['jobs']:
        task,mode=job['task'],job['mode'];name='round-%02d-%s-%s'%(job['round'],task,mode);trial=home/name
        status=next(r for r in complete['results']if r['trial']==name)
        row={**job,'trial':name,'completed':status['completed']}
        if not row['completed']:
            row['failure']=status.get('error');rows.append(row);continue
        if task=='orders':
            metrics=load(trial/'metrics.json');resources=metrics['resources'];latency=metrics['online_latency_ms']
            row.update(p50_ms=latency['p50'],p95_ms=latency['p95'],p99_ms=latency['p99'],completed_rps=metrics['throughput_rps'],error_rate=metrics['error_rate'])
            # The original Orders driver writes separate phase bounds.
            phase=load(trial/'steady.json');start=phase['start_ns'];end=phase['scheduled_end_ns']
            assert len(load(trial/'sockshop/run.json')['cases'])==180
        else:
            phase=load(trial/'measure.json');cases=phase['requests'];resources=load(trial/'resource-summary.json')
            latency=percentiles([c['http_seconds']*1000 for c in cases]);assert len(cases)==120
            row.update(p50_ms=latency['p50'],p95_ms=latency['p95'],p99_ms=latency['p99'],completed_rps=len(cases)/60,
                       error_rate=sum(not c['business_passed']for c in cases)/len(cases))
            start=phase['start_ns'];end=phase['end_ns']
            all_cases=load(trial/'warmup.json')['requests']+cases
            assert len(all_cases)==180 and all(c['business_passed']for c in all_cases)
            if task=='mall':
                lines=(trial/'database-after.txt').read_text().splitlines();at=lines.index('login_log_count');assert int(lines[at+1])==180
                row['login_log_rows']=180
            else:
                row['database_after_sha256']=sha(trial/'independent-database.tsv')
        row['requests_including_warmup']=180
        receipts.append({'trial':name,**resource_audit(trial,task,start,end,resources)})
        for label,group in [('business','observed_jvms'),('deployment','deployment')]:
            row[label+'_CPU']=resources[group]['cpu_one_core_percent_mean']
            row[label+'_RSS_MiB']=resources[group]['rss_bytes_mean']/2**20
            row[label+'_peak_RSS_MiB']=resources[group]['rss_bytes_peak']/2**20
        if mode!='original':
            measured=counts(trial,task,mode);save(trial/'target-cost-attribution.json',measured);row.update(measured['counts'])
            summary=load(trial/'offline-single-pass'/('summary.json'if task=='orders'else'process.json'))
            assert summary['correct']==summary['targets']and summary['correct']>0
            row.update(targets=summary['targets'],correct=summary['correct'],positive=summary.get('positive'),
                       offline_core_s=summary['core_seconds'],offline_VmHWM_MiB=summary['VmHWM_KiB']/1024,
                       offline_core_CPU_s=summary['core_cpu_seconds'],
                       offline_CPU_s=summary['process_cpu_seconds'],
                       offline_wall_s=metrics['offline']['subprocess_wall_seconds']if task=='orders'else summary['process_wall_seconds'])
            row['phases_seconds']=summary['phases_seconds']
            row['core_cpu_phases_seconds']=summary['core_cpu_phases_seconds']
            row['graph_nodes']=sum(v['nodes']for v in summary['graph_work_counts'])
            row['graph_edge_lists']=sum(v['edge_lists']for v in summary['graph_work_counts'])
        rows.append(row)
    comparisons={};joint={};absolute={}
    metrics=['p50_ms','p95_ms','p99_ms','completed_rps','error_rate','business_CPU','business_RSS_MiB','business_peak_RSS_MiB',
             'deployment_CPU','deployment_RSS_MiB','batch_events','batch_bytes','measure_events','measure_bytes','shared_unattributed_bytes',
             'all_capture_file_bytes','offline_core_s','offline_core_CPU_s','offline_CPU_s','offline_wall_s','offline_VmHWM_MiB','graph_nodes','graph_edge_lists']
    for task in protocol['tasks']:
        group=[r for r in rows if r['task']==task];absolute[task]={}
        if task.startswith('zlt-'):
            assert len({r['database_after_sha256']for r in group if r['completed']})==1,'ZLT read-task final DB content differs across arms'
        for mode in('original','full','selective','mirrortaint'):
            arms=[r for r in group if r['mode']==mode and r['completed']]
            absolute[task][mode]={m:statistics.median(r[m]for r in arms)for m in metrics if arms and all(m in r for r in arms)}
        comparisons[task]={}
        for a,b in [('selective','full'),('selective','original'),('mirrortaint','original'),('selective','mirrortaint')]:
            aa={r['round']:r for r in group if r['mode']==a and r['completed']};bb={r['round']:r for r in group if r['mode']==b and r['completed']}
            if set(aa)!=set(bb)or len(aa)!=5:
                comparisons[task][a+'/'+b]={'complete':False};continue
            pair={}
            for m in metrics:
                if not all(m in aa[i]and m in bb[i]and bb[i][m]>0 for i in aa):continue
                ratios=[aa[i][m]/bb[i][m]for i in sorted(aa)]
                pair[m]={'median_ratio':statistics.median(ratios),'min_ratio':min(ratios),'max_ratio':max(ratios),'ratios':ratios}
            comparisons[task][a+'/'+b]={'complete':True,'metrics':pair}
        p=comparisons[task]['selective/full'];m=p.get('metrics',{})
        needed=('batch_bytes','offline_CPU_s','business_CPU','p95_ms')
        passed=p['complete']and all(k in m for k in needed)
        if passed:passed=m['batch_bytes']['median_ratio']<1 and m['offline_CPU_s']['median_ratio']<1 and all(m[k]['median_ratio']<=1.05 and m[k]['max_ratio']<=1.10 for k in('business_CPU','p95_ms'))
        joint[task]={'passed':passed,'criterion':protocol['primary_criterion'],'complete':p['complete']}
    summary={'candidate':verify()['commit'],'reference':protocol['reference'],'absolute_medians':absolute,'paired':comparisons,'joint_internal':joint,
        'preselected_tasks':list(protocol['tasks']),'task_wins':sum(v['passed']for v in joint.values()),
        'majority_all_four':sum(v['passed']for v in joint.values())>2,
        'unified_stratum':{k:joint[k]for k in('mall','zlt-client','zlt-user')},
        'unified_task_wins':sum(joint[k]['passed']for k in('mall','zlt-client','zlt-user')),
        'all_trials_completed':all(r['completed']for r in rows),'single_target_deployments_not_multitarget':True,
        'formal_rows':rows,'scope':'Fixed common independently correct tasks only; new-app first coverage is reported separately and cannot be replaced by these successes.'}
    save(out/'summary.json',summary);save(out/'resource-receipts.json',receipts)
    with(out/'rounds.csv').open('w')as f:
        columns=list(dict.fromkeys(k for row in rows for k in row if k not in ('phases_seconds','core_cpu_phases_seconds')));w=csv.DictWriter(f,columns,extrasaction='ignore');w.writeheader();w.writerows(rows)
    print({'tasks':len(joint),'wins':summary['task_wins'],'majority':summary['majority_all_four']})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();audit(a.home.resolve(),a.out.resolve())
