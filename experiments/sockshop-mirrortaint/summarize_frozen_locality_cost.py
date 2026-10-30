#!/usr/bin/env python3
"""Paired round summaries; retain absolute metrics and small/no-benefit results."""
import argparse,collections,csv,json,statistics,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
from run_frozen_zlt_reuse import load,save,sha
from run_frozen_locality_cost import verify

def percentile(xs,p):
 import math
 return sorted(xs)[max(0,math.ceil(len(xs)*p)-1)]

def run(home):
 verify();rows=[]
 for i,modes in enumerate(load(home/'formal-order-before-measurement.json')['round_order']):
  for mode in modes:
   d=home/('round-%02d-%s'%(i+1,mode));r=load(d/'result.json');a=load(d/'warmup.json');b=load(d/'measure.json');assert r['state']=='captured'and r['cleanup_returncode']==0 and r['business_passed']==180 and len(a['requests'])==60 and len(b['requests'])==120
   assert all(c['business_passed']and c['http_seconds']is not None for c in a['requests']+b['requests'])
   s=load(d/'resource-summary.json');lat=[x['http_seconds']*1000 for x in b['requests']]
   item={'round':i+1,'mode':mode,'p50_ms':percentile(lat,.5),'p95_ms':percentile(lat,.95),'p99_ms':percentile(lat,.99),'completed_rps':120/((b['end_ns']-b['start_ns'])/1e9),'error_rate':0,
    'business_cpu_one_core_percent':s['observed_jvms']['cpu_one_core_percent_mean'],'business_RSS_MiB':s['observed_jvms']['rss_bytes_mean']/2**20,'business_peak_RSS_MiB':s['observed_jvms']['rss_bytes_peak']/2**20,'deployment_cpu_one_core_percent':s['deployment']['cpu_one_core_percent_mean'],'deployment_RSS_MiB':s['deployment']['rss_bytes_mean']/2**20,'requests_with_warmup':180}
   # Store the actual same-deployment SQL side effect; a correct return alone
   # does not establish business preservation.
   db=(d/'database-after.txt').read_text();assert 'login_log_count\n180\n'in db,'Login save count differs'
   item['login_rows_saved']=180
   if mode!='original':
    o=load(d/('offline-native/summary.json'if mode=='mirrortaint'else'offline-fresh/summary.json'));process=load(d/('offline-native-process.json'if mode=='mirrortaint'else'offline-fresh-process.json'))
    assert o['correct']==o['targets']==180
    hwm=o.get('VmHWM_KiB',o.get('VmHWM_KiB_before_ablation'))/1024
    item.update(targets_correct=180,positive_correct=180,measure_events=o['measure_events'],measure_bytes=o['measure_bytes'],batch_events=o['batch_events'],batch_bytes=o['batch_bytes'],offline_core_seconds=o['core_seconds'],offline_process_wall_seconds=process['wall_seconds'],offline_process_cpu_seconds=process['cpu_seconds'],offline_VmHWM_MiB=hwm,offline_score_seconds=o['phases_seconds']['independent_score'],offline_export_seconds=o['phases_seconds']['export'],offline_decode_validate_seconds=o['phases_seconds'].get('decode_validate_bind',o['phases_seconds'].get('decode',0)+o['phases_seconds'].get('independent_capture_validation',0)))
    if mode=='mirrortaint':item['all_capture_files_bytes']=o['all_capture_bytes']
    else:
     precision=load(d/load(d/'offline-complete.json')['summary']);assert precision['without_certificate_known']==0 and precision['correct']==180
     item['without_certificate_known']=0;item['shared_or_unpaired_events']=o['shared_unattributed_events'];item['shared_or_unpaired_bytes']=o['shared_unattributed_bytes']
   rows.append(item)
 fields=sorted(set().union(*(r.keys()for r in rows)));out=home/'summary';out.mkdir(exist_ok=False)
 with(out/'rounds.csv').open('w',newline='')as f:
  w=csv.DictWriter(f,fieldnames=['round','mode']+[v for v in fields if v not in('round','mode')]);w.writeheader();w.writerows(rows)
 medians={mode:{k:statistics.median(r[k]for r in rows if r['mode']==mode and k in r)for k in fields if k not in('round','mode')and any(k in r for r in rows if r['mode']==mode)}for mode in('original','full','selective','mirrortaint')}
 pairs=[]
 for numerator,denominator in [('selective','full'),('selective','original'),('full','original'),('selective','mirrortaint'),('full','mirrortaint'),('mirrortaint','original')]:
  for key in fields:
   if key in('round','mode'):continue
   ratios=[]
   for i in range(1,6):
    a=next(r for r in rows if r['round']==i and r['mode']==numerator);b=next(r for r in rows if r['round']==i and r['mode']==denominator)
    if key in a and key in b and b[key]:ratios.append(a[key]/b[key])
   if len(ratios)==5:pairs.append({'comparison':numerator+'/'+denominator,'metric':key,'median_ratio':statistics.median(ratios),'median_percent_change':(statistics.median(ratios)-1)*100,'min_ratio':min(ratios),'max_ratio':max(ratios),'round_ratios':ratios})
 result={'algorithm':'c1a4e5ceb60a276cc3651e4cdb413aa29d7f8d5d','rounds':5,'online_deployments':20,'correct_each_observed_mode':900,'positive_each_observed_mode':900,'precision_ablation_without_certificate_known_each_TF_mode':0,'medians':medians,'paired':pairs,'MT_scope':'Fixed native MT+B0 adapter; ONE expiresIn task/deployment, additional native exported fields retained. Not cumulative per-field deployment costs.','core_definitions':'TF graph reconstruction+query; MT native tag decode. Decode/validation/binding separately reported. Total process is comparable inclusive work; core phases perform different operations.','event_attribution_limit':'Per-request root Frame/message and shared trace ancestry only; unpaired callback messages and shared startup/footer kept separately, not assigned by time or values. Batch totals include all capture records. Native diagnostic logs/class dumps separately included in all_capture_files_bytes.'}
 save(out/'results.json',result)
 # Small source-backed copies for Git; complete raw artifacts remain separate.
 (HERE/'frozen-locality-cost-rounds-20261030.csv').write_bytes((out/'rounds.csv').read_bytes());save(HERE/'frozen-locality-cost-results-20261030.json',result)
 print({m:{k:round(v,4)for k,v in s.items()if k in('p95_ms','business_cpu_one_core_percent','measure_events','offline_process_wall_seconds')}for m,s in medians.items()})

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);a=p.parse_args();run(a.home.resolve())
