"""Independent resource/count aggregation; no source truth inferred from metrics."""
import argparse,csv,json,statistics
from collections import Counter
from pathlib import Path
from run_planned_service import HERE,load,save,sha


def paired(records,metrics):
 result={}
 for task,mode in sorted({(r['task'],r['mode'])for r in records}):
  rows=[r for r in records if r['task']==task and r['mode']==mode];d={}
  for metric in metrics:
   old=[r[metric]for r in rows if r['version']=='old'];new=[r[metric]for r in rows if r['version']=='new'];ratios=[]
   assert len(old)==len(new)==5
   for repeat in range(1,6):
    a=next(r for r in rows if r['version']=='old'and r['repeat']==repeat)[metric];b=next(r for r in rows if r['version']=='new'and r['repeat']==repeat)[metric]
    if a:ratios.append(b/a)
   d[metric]={'old_median':statistics.median(old),'new_median':statistics.median(new),'median_ratio':statistics.median(ratios)if ratios else None,'min_ratio':min(ratios)if ratios else None,'max_ratio':max(ratios)if ratios else None}
  result[task+'-'+mode]=d
 return result


def offline(folder):
 result=load(folder/'results.json');assert result['answers_full_graph_and_root_audits_equal'];rows=[]
 for r in result['records']:
  row={k:r[k]for k in('task','mode','version','repeat','targets','correct','process_wall_seconds','process_cpu_seconds','VmHWM_KiB')}
  assert not r['profile']and r['targets']==r['correct']and not r['diagnostic_graph_export']
  for k,v in r['phases_seconds'].items():row[k+'_wall_seconds']=v
  for k,v in r['cpu_phases_seconds'].items():row[k+'_cpu_seconds']=v
  row['core_cpu_seconds']=r['cpu_phases_seconds']['reconstruction']+r['cpu_phases_seconds']['query'];rows.append(row)
 return {'rows':rows,'paired':paired(rows,[k for k in rows[0]if k.endswith(('_seconds','KiB'))]),'whole_graph_versions_selectors_root_audits_equal':True}


def online(home):
 from run_sockshop_cost import Sampler,percentiles
 from audit_zlt_body_cost import attributable
 from run_shared_work_business import verify_business
 folder=home/'online-paired';assert load(folder/'complete.json')['complete'];records=[]
 for repeat,task,version,mode in load(folder/'order-before-runs.json')['jobs']:
  trial=folder/('%02d-%s-%s-%s'%(repeat,task,version,mode));warm=load(trial/'warmup.json')['requests'];phase=load(trial/'measure.json');cases=phase['requests'];result=load(trial/'result.json');summary=load(trial/'offline/summary.json');verify_business(trial,task)
  assert len(warm)==60 and len(cases)==120 and result['requests']==result['business_passed']==180
  assert summary['correct']==summary['targets']==(270 if task=='zlt-user'else 360)
  assert not summary['profile']and not summary['diagnostic_graph_export']and not(trial/'capture/snapshot-work.json').exists()
  samples=[json.loads(x)for x in(trial/'resources.jsonl').read_text().splitlines()];observed=('zlt-user','zlt-uaa')if task=='zlt-user'else('system','auth')
  sampler=Sampler({r:None for r in samples[0]},2,trial/'unused-audit.jsonl',observed_roles=observed);sampler.rows=samples;resources=sampler.summary(phase['start_ns'],phase['end_ns']);assert resources==load(trial/'resource-summary.json')
  lines=(trial/'capture/events.jsonl').read_bytes().splitlines(keepends=True);events=[json.loads(s)for s in lines];parents={}
  for r in events:
   if r.get('message')and r.get('parent_message'):
    assert parents.get(r['message'],r['parent_message'])==r['parent_message'];parents[r['message']]=r['parent_message']
  counts=attributable(events,lines,{r['message']for r in cases},{r['message']for r in cases+warm},parents)
  p=percentiles([r['http_seconds']*1000 for r in cases]);row={'repeat':repeat,'task':task,'version':version,'mode':mode,'targets':summary['targets'],'correct':summary['correct'],'business_CPU':resources['observed_jvms']['cpu_one_core_percent_mean'],'business_RSS_MiB':resources['observed_jvms']['rss_bytes_mean']/2**20,'business_peak_RSS_MiB':resources['observed_jvms']['rss_bytes_peak']/2**20,'deployment_CPU':resources['deployment']['cpu_one_core_percent_mean'],'p50_ms':p['p50'],'p95_ms':p['p95'],'p99_ms':p['p99'],'offline_VmHWM_KiB':summary['VmHWM_KiB'],**counts,**{'offline_'+k:v for k,v in load(trial/'offline-process.json').items()if k.endswith('_seconds')}}
  row.update({'offline_'+k+'_wall_seconds':v for k,v in summary['phases_seconds'].items()});row.update({'offline_'+k+'_cpu_seconds':v for k,v in summary['cpu_phases_seconds'].items()});records.append(row)
 return {'rows':records,'paired':paired(records,[k for k in records[0]if k not in('repeat','task','version','mode','targets','correct')]),'raw_resource_summaries_exact':True,'requests_per_deployment':180,'online_cpu_and_latency_are_new_deployments':True}


def run(home,out):
 out.mkdir(parents=True,exist_ok=False);data={'small_complete_capture':offline(home/'offline-paired-formal'),'standard_volume_same_capture':offline(home/'offline-standard-volume/paired'),'online':online(home)}
 counters=[]
 for repeat,task,version,mode in load(home/'business-work-diagnostics-02/order-before-runs.json')['jobs']:
  d=home/'business-work-diagnostics-02'/('%02d-%s-%s-%s'%(repeat,task,version,mode));s=load(d/'offline-clean-exec/summary.json');assert s['correct']==s['targets']==(9 if task=='zlt-user'else 12);counters.append({'task':task,'version':version,'mode':mode,**load(d/'capture/snapshot-work.json')})
 data['actual_business_diagnostic_counts']=counters
 for key in('small_complete_capture','standard_volume_same_capture','online'):
  rows=data[key]['rows']
  with(out/(key+'.csv')).open('w')as f:w=csv.DictWriter(f,list(rows[0]));w.writeheader();w.writerows(rows)
  save(out/(key+'-paired.json'),data[key]['paired'])
 save(out/'summary.json',data);print('Shared-work summaries validated',flush=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.home.resolve(),a.out.resolve())
