"""Deployment-paired primary metric; direct message/frame attribution only."""
import argparse,csv,json,math,statistics
from pathlib import Path
from run_planned_service import load,save
from run_jvm_rule_revision import H,verify

def attribution(trial,mode):
    phases={c['message']:phase for phase in ('warmup','measure')for c in load(trial/(phase+'.json'))['requests']}
    names=['events.jsonl']if mode in ('full','selective')else['native-capability.jsonl','instances.jsonl','native-library.jsonl']
    lines=[(line,json.loads(line))for name in names for line in(trial/'capture'/name).read_bytes().splitlines(keepends=True)]
    frames={r['frame']:r for _,r in lines if r['kind']=='enter'}
    owned={r['frame']:r.get('message')for _,r in lines if r['kind']=='binding-return'}
    native={r['root']:r.get('context',{}).get('message')for _,r in lines if r['kind']=='target'}
    def owner(frame):
        seen=set()
        while frame is not None and frame not in seen:
            seen.add(frame)
            if owned.get(frame)in phases:return owned[frame]
            frame=frames.get(frame,{}).get('parent')
        return None
    totals={p:{'bytes':0,'events':0}for p in ('batch','measure','warmup','unattributed')}
    for line,r in lines:
        candidates={m for m in [r.get('message'),r.get('context',{}).get('message'),native.get(r.get('root')),owner(r.get('frame')),owner(r.get('caller_frame'))]if m in phases}
        phase=phases[next(iter(candidates))]if len(candidates)==1 else'unattributed'
        for key in ('batch',phase):totals[key]['bytes']+=len(line);totals[key]['events']+=1
    return totals

def run(out):
    verify();out.mkdir(parents=True,exist_ok=False);records=[]
    for job in load(H/'formal-order-before-timing.json')['jobs']:
        trial=H/'formal'/('%02d-%s-%s'%(job['round'],job['tier'],job['mode']))
        if not(trial/'formal-job.json').exists():continue
        assert load(trial/'formal-job.json')['passed']
        cases=load(trial/'measure.json');good=[c for c in cases['requests']if c['business_passed']]
        before=load(trial/'measure-cpu-before.json')['app'];after=load(trial/'measure-cpu-after.json')['app'];cpu=(after['cpu_ns']-before['cpu_ns'])/1e9
        rss=load(trial/'resource-summary.json')['observed_jvms'];audit=load(trial/'audit/summary.json')
        normal=load(trial/'normal-offline/summary.json')if(trial/'normal-offline/summary.json').exists()else{}
        process=load(trial/'normal-offline-process.json')if(trial/'normal-offline-process.json').exists()else{}
        attributed=attribution(trial,job['mode'])if job['mode']!='original'else {p:{'bytes':0,'events':0}for p in ('batch','measure','warmup','unattributed')}
        if job['mode']!='original':assert attributed['batch']['bytes']==audit['batch_bytes']
        footer={}
        if job['mode']in ('full','selective'):
            rows=[json.loads(s)for s in(trial/'capture/events.jsonl').read_text().splitlines()];footer=rows[-1]
        latency=sorted(c['http_seconds']*1000 for c in good)
        records.append({**job,'completed':len(good),'attempted':len(cases['requests']),'completion_fraction':len(good)/len(cases['requests']),'achieved_rps':len(good)/((cases['end_ns']-cases['start_ns'])/1e9),'business_cpu_seconds':cpu,'cpu_seconds_per_request':cpu/len(good),'p95_ms':latency[math.ceil(.95*len(latency))-1],'rss_mean_MiB':rss['rss_bytes_mean']/2**20,'rss_sample_peak_MiB':rss['rss_bytes_peak']/2**20,'batch_bytes':audit.get('batch_bytes',0),'batch_events':audit.get('batch_events',0),'measure_bytes':attributed['measure']['bytes'],'unattributed_bytes':attributed['unattributed']['bytes'],'field_hook_calls':footer.get('field_hook_calls'),'boundary_payload_omissions':audit.get('actual_scalar_omissions',0),'normal_wall_seconds':normal.get('wall_seconds'),'normal_cpu_seconds':normal.get('cpu_seconds'),'normal_process_wall_seconds':process.get('wall_seconds'),'normal_process_cpu_seconds':process.get('cpu_seconds'),'normal_VmHWM_KiB':normal.get('VmHWM_KiB'),'independent_oracle_score_seconds':audit.get('independent_validation_seconds'),'trace_phases':json.dumps(normal.get('phases_seconds',{}),sort_keys=True)})
    for record in records:
        base=next(r for r in records if r['round']==record['round']and r['tier']==record['tier']and r['mode']=='original')
        record['extra_cpu_seconds_per_request']=record['cpu_seconds_per_request']-base['cpu_seconds_per_request']
    with(out/'rounds.csv').open('w',newline='')as f:
        w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
    medians=[]
    for tier in ('low','medium','high'):
        for mode in ('original','full','selective','mirrortaint'):
            selected=[r for r in records if r['tier']==tier and r['mode']==mode]
            if len(selected)!=5:continue
            names=['cpu_seconds_per_request','extra_cpu_seconds_per_request','p95_ms','rss_mean_MiB','batch_bytes','measure_bytes','field_hook_calls','boundary_payload_omissions','normal_cpu_seconds','normal_wall_seconds','normal_process_wall_seconds','normal_process_cpu_seconds','normal_VmHWM_KiB','independent_oracle_score_seconds']
            metrics={k:statistics.median(r[k]for r in selected)for k in names if all(r[k]is not None for r in selected)}
            medians.append({'tier':tier,'mode':mode,**metrics})
    increments=[]
    if len(records)==60:
      for round_ in range(1,6):
        def v(t,m):return next(r for r in records if r['round']==round_ and r['tier']==t and r['mode']==m)['extra_cpu_seconds_per_request']
        increments.append({'round':round_,'selective_high_minus_low':v('high','selective')-v('low','selective'),'MT_high_minus_low':v('high','mirrortaint')-v('low','mirrortaint'),'difference':v('high','selective')-v('low','selective')-v('high','mirrortaint')+v('low','mirrortaint')})
    pairs=[]
    if len(records)==60:
      for tier in ('low','medium','high'):
       for other in ('full','mirrortaint'):
        selected=[r for r in records if r['tier']==tier and r['mode']=='selective']
        for metric in ('p95_ms','business_cpu_seconds','batch_bytes','normal_process_wall_seconds','normal_VmHWM_KiB'):
         ratios=[r[metric]/next(v for v in records if v['round']==r['round']and v['tier']==tier and v['mode']==other)[metric]for r in selected]
         pairs.append({'tier':tier,'comparison':'selective/'+other,'metric':metric,'median_ratio':statistics.median(ratios),'min_ratio':min(ratios),'max_ratio':max(ratios)})
    save(out/'results.json',{'completed_deployments':len(records),'medians':medians,'paired_increments':increments,'paired_ratios':pairs,'slower_growth_all_five':len(increments)==5 and all(v['difference']<0 for v in increments),'scope':'Shared implementation, no new pruning mechanism. Exact message/frame/native-root attribution; no trace-prefix or time pairing. Sampled RSS. Independent scoring outside normal provenance.'})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);run(p.parse_args().out.resolve())
