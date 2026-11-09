"""Recompute deployment-level CPU overhead; retain negative deltas and failures."""
import argparse,csv,json,math,statistics
from pathlib import Path
from run_unrelated_work_scaling import H,HERE,ROOT,TIERS,MODES,load,save,sha,verify

def percentile(values,p):
 s=sorted(values);return s[max(0,math.ceil(p*len(s))-1)]if s else None

def summarize(out):
 verify();out.mkdir(parents=True,exist_ok=False);records=[]
 for job in load(H/'formal-order-before-timing.json')['jobs']:
  trial=H/'formal'/('%02d-%s-%s-%s'%(job['round'],job['task'],job['tier'],job['mode']))
  if not(trial/'formal-job.json').exists():continue
  cases=load(trial/'measure.json');good=[c for c in cases['requests']if c['business_passed']];before=load(trial/'measure-cpu-before.json');after=load(trial/'measure-cpu-after.json');roles=['app']if job['task']=='controlled'else['admin','auth','portal'];cpu=sum(after[r]['cpu_ns']-before[r]['cpu_ns']for r in roles)/1e9;assert cpu>=0
  rss=load(trial/'resource-summary.json')['observed_jvms'];a=load(trial/'audit/summary.json');normal=load(trial/'normal-offline/summary.json')if(trial/'normal-offline/summary.json').exists()else{}
  process=load(trial/'normal-offline-process.json')if(trial/'normal-offline-process.json').exists()else{}
  record={**job,'completed':len(good),'attempted':len(cases['requests']),'completion_fraction':len(good)/len(cases['requests']),'achieved_rps':len(good)/((cases['end_ns']-cases['start_ns'])/1e9),'business_cpu_seconds':cpu,'cpu_seconds_per_completed_request':cpu/len(good),'p95_ms':percentile([c['http_seconds']*1000 for c in good],.95),'rss_mean_MiB':rss['rss_bytes_mean']/2**20,'rss_sample_peak_MiB':rss['rss_bytes_peak']/2**20,'batch_protocol_bytes':a.get('batch_bytes',0),'attributed_measure_bytes':a.get('measure_bytes',0),'all_capture_files_bytes':a.get('all_capture_file_bytes',0),'targets':a['targets']if job['mode']!='original'else None,'correct':a['correct']if job['mode']!='original'else None,'normal_offline_wall_seconds':process.get('wall_seconds'),'normal_offline_cpu_seconds':process.get('cpu_seconds'),'normal_offline_VmHWM_MiB':normal.get('VmHWM_KiB',0)/1024 if normal else None,'independent_oracle_and_score_wall_seconds':a.get('independent_validation_seconds'),'cpu_measurement_window_min_seconds':min((after[r]['monotonic_ns']-before[r]['monotonic_ns'])/1e9 for r in roles),'cpu_measurement_window_max_seconds':max((after[r]['monotonic_ns']-before[r]['monotonic_ns'])/1e9 for r in roles),'trial':str(trial.relative_to(ROOT))}
  records.append(record)
 bykey={(r['round'],r['task'],r['tier'],r['mode']):r for r in records}
 for r in records:
  base=bykey.get((r['round'],r['task'],r['tier'],'original'));r['extra_cpu_seconds_per_completed_request']=r['cpu_seconds_per_completed_request']-base['cpu_seconds_per_completed_request']if base else None
 if records:
  with(out/'rounds.csv').open('w',newline='')as f:w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
 else:(out/'rounds.csv').write_text('round,task,tier,mode,extra_cpu_seconds_per_completed_request\n')
 medians=[]
 for task,tier in sorted({(r['task'],r['tier'])for r in records}):
  for mode in MODES:
   rr=[r for r in records if(r['task'],r['tier'],r['mode'])==(task,tier,mode)]
   if not rr:continue
   row={'task':task,'tier':tier,'mode':mode,'rounds':len(rr)}
   for k in('business_cpu_seconds','cpu_seconds_per_completed_request','extra_cpu_seconds_per_completed_request','p95_ms','rss_mean_MiB','batch_protocol_bytes','attributed_measure_bytes','normal_offline_wall_seconds','normal_offline_cpu_seconds','normal_offline_VmHWM_MiB','independent_oracle_and_score_wall_seconds'):
    v=[r[k]for r in rr if r[k]is not None];row[k]={'median':statistics.median(v),'min':min(v),'max':max(v)}if v else None
   medians.append(row)
 growth=[]
 if load(H/'controlled-gate.json')['passed']:
  for round_ in range(1,6):
   v={}
   for mode in('full','selective','mirrortaint'):
    a=bykey[(round_,'controlled','low',mode)];b=bykey[(round_,'controlled','high',mode)];v[mode]=b['extra_cpu_seconds_per_completed_request']-a['extra_cpu_seconds_per_completed_request']
   growth.append({'round':round_,**v,'selective_minus_MT_increment':v['selective']-v['mirrortaint']})
 controlled=load(H/'controlled-pilot-results.json');pilot=[]
 for tier,modes in controlled.items():
  for mode,v in modes.items():
   a=v.get('audit',{});r=v.get('run',{});pilot.append({'tier':tier,'fields':TIERS[tier],'mode':mode,'business_passed':r.get('business_passed'),'requests':r.get('requests'),'correct':a.get('correct'),'targets':a.get('targets'),'scalar_omissions':a.get('actual_scalar_omissions',0),'batch_protocol_bytes':a.get('batch_bytes'),'state':v.get('state')or a.get('states')or a.get('error'),'error':v.get('planning',{}).get('error')or a.get('error'),'actual_deployment':v.get('actual_business_deployment',True)})
 with(out/'pilot-capability-and-work.csv').open('w',newline='')as f:w=csv.DictWriter(f,fieldnames=list(pilot[0]));w.writeheader();w.writerows(pilot)
 save(out/'results.json',{'frozen_TF':load(H/'protocol-before-tools.json')['TF_commit'],'controlled_gate':load(H/'controlled-gate.json'),'mall_gate':load(H/'mall-gate.json'),'pilot':pilot,'formal_deployments':len(records),'formal_medians':medians,'growth':growth,'slower_growth_established':bool(growth)and all(g['selective_minus_MT_increment']<0 for g in growth),'primary':'baseline-subtracted business CPU seconds / completed measurement request, per round and tier','old_online_results_unchanged':True,'source_files':{str(p):sha(p)for p in[H/'protocol-before-tools.json',H/'formal-order-before-timing.json',H/'controlled-gate.json',H/'mall-gate.json']}})
 import matplotlib;matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 fig,axes=plt.subplots(1,3,figsize=(13,3.7))
 colors={'full':'#3874b9','selective':'#009e73','mirrortaint':'#d55e00','original':'#777777'}
 for mode in('full','selective','mirrortaint'):
  rr=[next(r for r in pilot if r['tier']==t and r['mode']==mode)for t in('low','medium','high')]
  axes[0].plot([r['fields']for r in rr],[r['batch_protocol_bytes']/1024 if r['batch_protocol_bytes']else float('nan')for r in rr],'-o',color=colors[mode],label=mode)
 axes[0].set(xlabel='Non-target scalar fields',ylabel='Complete pilot protocol (KiB)',title='Pilot: data volume, NOT speed');axes[0].legend(fontsize=8)
 if not growth:
  axes[1].text(.5,.5,'Controlled CPU growth: N/A\n\nRelated-high control rejected\nby frozen TF (LADD / opcode 97).\nNo formal timing for this group.',ha='center',va='center',transform=axes[1].transAxes,fontsize=9);axes[1].set_axis_off()
 else:
  for mode in('full','selective','mirrortaint'):
   for tier in('low','medium','high'):
    rr=[r for r in records if(r['task'],r['tier'],r['mode'])==('controlled',tier,mode)];axes[1].scatter([TIERS[tier]]*len(rr),[r['extra_cpu_seconds_per_completed_request']*1000 for r in rr],color=colors[mode],alpha=.5)
  axes[1].set(xlabel='Non-target scalar fields',ylabel='Extra business CPU (ms/request)',title='Controlled: five deployments')
 for mode in('full','selective','mirrortaint'):
  rr=[r for r in records if r['task']=='mall'and r['mode']==mode];rates=sorted({r['rate']for r in rr})
  means=[]
  for rate in rates:
   values=[r['extra_cpu_seconds_per_completed_request']*1000 for r in rr if r['rate']==rate];means.append(statistics.median(values));axes[2].scatter([rate]*len(values),values,color=colors[mode],alpha=.4,s=14)
  if rates:axes[2].plot(rates,means,'-o',color=colors[mode],label=mode)
 axes[2].axhline(0,color='#888888',lw=.6);axes[2].set(xlabel='Mall scheduled requests/s',ylabel='Extra business CPU (ms/request)',title='Mall: five deployments per point')
 if records:axes[2].legend(fontsize=8)
 fig.tight_layout();fig.savefig(out/'cost-by-tier.png',dpi=170);fig.savefig(out/'cost-by-tier.svg');plt.close(fig)
 print('SUMMARIZED',len(records),flush=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();summarize(a.out.resolve())
