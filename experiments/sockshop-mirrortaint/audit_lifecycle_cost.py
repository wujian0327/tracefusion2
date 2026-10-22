#!/usr/bin/env python3
"""Raw population/measurement audit and separate per-query deployment comparisons."""
import argparse,copy,csv,json,statistics,subprocess,sys
from pathlib import Path
from run_planned_service import load,save,sha
from run_bound_query_cost import query
import run_response_binding_revision as old
from run_sockshop_cost import percentiles,Sampler


def values(m):
    r=m['resources']['observed_jvms'];off=m['offline']
    result={'p50_ms':m['online_latency_ms']['p50'],'p95_ms':m['online_latency_ms']['p95'],'p99_ms':m['online_latency_ms']['p99'],'throughput_rps':m['throughput_rps'],'error_rate':m['error_rate'],'online_cpu_percent':r['cpu_one_core_percent_mean'],'online_rss_mean_bytes':r['rss_bytes_mean'],'online_rss_peak_bytes':r['rss_bytes_peak'],'capture_events':sum(x['events'] for x in m['steady_capture'].values()),'capture_bytes':sum(x['bytes'] for x in m['steady_capture'].values()),'whole_capture_events':sum(x['events'] for x in m['total_capture'].values()),'whole_capture_bytes':sum(x['bytes'] for x in m['total_capture'].values()),'console_bytes':m['container_console_bytes']}
    deployment=m['resources']['deployment'];result.update(deployment_cpu_percent=deployment['cpu_one_core_percent_mean'],deployment_rss_mean_bytes=deployment['rss_bytes_mean'],deployment_rss_peak_bytes=deployment['rss_bytes_peak'])
    if 'file_visible_capture' in m:
        result.update(file_visible_capture_events=sum(v['events'] for v in m['file_visible_capture'].values()),file_visible_capture_bytes=sum(v['bytes'] for v in m['file_visible_capture'].values()))
    if off:
        result.update(offline_core_seconds=off['core_seconds'],offline_child_wall_seconds=off['subprocess_wall_seconds'],offline_child_cpu_seconds=off['process_cpu_seconds'],offline_child_peak_rss_bytes=off.get('replay_vmhwm_bytes',off['peak_rss_bytes']),offline_launch_rusage_peak_rss_bytes=off['peak_rss_bytes'],answer_wait_p50_seconds=m['completion_to_batch_answers_seconds']['p50'],answer_wait_p95_seconds=m['completion_to_batch_answers_seconds']['p95'])
        for k,v in off['phases'].items():result['offline_'+k]=v
    return result


def audit(root, calibration_files=None, request_records=None):
    if not (root/'offline-memory-audit.json').exists():
        subprocess.run([sys.executable,str(Path(__file__).with_name('measure_offline_memory.py')),'run','--root',str(root)],check=True)
    memory=load(root/'offline-memory-audit.json');assert memory['all_passed'] and memory['replay_count']==30
    frozen=load(root/'algorithm-freeze.json')
    for f,h in frozen['core_sources'].items():assert sha(Path(__file__).resolve().parents[2]/f)==h,('Core changed',f)
    for gate in (calibration_files or ('bound-calibration-audit.json', 'price-raw-toggle-audit.json')):
        assert load(root/gate)['all_passed'], gate
    results={};projects=set();csvrows=[]
    mapping=load(root/'formal-run-map.json') if (root/'formal-run-map.json').exists() else {k:'cost-'+k for k in ('cart','train','price')}
    for kind in ('cart','train','price'):
        home=root/mapping[kind];cfg=load(home/'config.json');assert load(home/'run-status.json')['status']=='passed'
        assert cfg['rounds']==5 and len(cfg['order'])==15
        summaries={};records={};populations={};specs=[]
        for name,mode in cfg['order']:
            d=home/name;m=load(d/'metrics.json');assert m['mode']==mode and m['status']=='passed'
            clean=load(d/'cleanup.json');assert clean['returncode']==0 and clean['project'] not in projects;projects.add(clean['project'])
            dest=d/('trainticket' if kind=='price' else 'capture');cases=load(dest/'run.json')['cases'];warm=load(d/'warmup.json');steady=load(d/'steady.json')
            assert len(warm['requests'])==round(cfg['warmup']*cfg['rate'])==60
            assert len(steady['requests'])==round(cfg['seconds']*cfg['rate'])==120
            assert all(r['business_passed'] for r in cases) and len(cases)==180
            assert len({r['message'] for r in cases})==len(cases)
            assert max(r['online_end_ns'] for r in warm['requests'])<=steady['start_ns']
            assert {r['case'] for r in cases}=={r['case'] for r in warm['requests']+steady['requests']}
            measured=steady['requests'];assert m['online_latency_ms']==percentiles([(r['online_end_ns']-r['online_start_ns'])/1e6 for r in measured])
            assert m['throughput_rps']==sum(r['online_end_ns']<=steady['scheduled_end_ns'] for r in measured)/cfg['seconds'] and m['error_rate']==0
            samples=[json.loads(l) for l in (d/'resources.jsonl').read_text().splitlines()]
            observed=['ts-'+r+'-service' for r in ('station','train','route','price','basic')] if kind=='price' else ['carts' if kind=='cart' else 'ts-train-service']
            sampler=Sampler({r:None for r in samples[0]},cfg['sample_interval'],d/'unused-audit-sampler.jsonl',observed_roles=observed)
            sampler.rows=samples
            assert sampler.summary(steady['start_ns'],steady['scheduled_end_ns'])==m['resources'],'Raw resource aggregation differs'
            spec=json.dumps(load(dest/'compose.json'),sort_keys=True).replace(str(dest),'$CAPTURE').replace('-Dservice.mode='+mode,'-Dservice.mode=$POLICY')
            if mode!='original':specs.append(spec)
            if mode!='original':
                score=load(dest/'field-results.json' if kind=='price' else d/'field-results.json');s=score['summary'];assert s['exact']==s['queries'] and s['unknown']==s['fp']==s['fn']==0
                expected=sum(2 if kind=='price' else len(old.leaves(c['response'],query(kind)['path'])) for c in cases);assert s['queries']==expected
                assert len(score['queries'])==expected and all(r['known'] and r['exact'] for r in score['queries'])
                assert m['offline']['summary']==s
                for label in ('warmup','steady'):
                    selected=[r for r in score['queries'] if r['case'].startswith(label+'-')]
                    pop=m['offline']['populations'][label];assert pop['queries']==pop['exact']==len(selected)
                    for k in ('tp','fp','fn'):assert pop[k]==sum(r[k] for r in selected)
                populations.setdefault(mode,[]).append({'trial':name,'warmup_requests':60,'steady_requests':120,'targets':s['queries'],'warmup_targets':m['offline']['populations']['warmup']['queries'],'steady_targets':m['offline']['populations']['steady']['queries'],**s})
                window=load(d/'capture-window.json')
                for role,measure in m['steady_capture'].items():
                    lines=(dest/role/'events.jsonl').read_bytes().splitlines(keepends=True)
                    before=window['before'][role] if kind=='price' else window['before'];after=window['after'][role] if kind=='price' else window['after'];cohort=lines[before['events']:after['events']]
                    assert measure['events']==len(cohort) and measure['bytes']==sum(map(len,cohort))
                    assert all(json.loads(l)['kind']!='problem' for l in lines)
            if mode!='original':m['offline']['replay_vmhwm_bytes']=memory['measurements'][kind+'/'+name]['vmhwm_bytes']
            if request_records is not None and mode!='original':
                m=copy.deepcopy(m)
                m['file_visible_capture']=m['steady_capture']
                m['steady_capture']=request_records[kind+'/'+name]['request_records']
            raw=values(m);records.setdefault(mode,{})[name[:8]]=raw
            csvrows.append({'kind':kind,'trial':name,'mode':mode,**raw})
        assert all(s==specs[0] for s in specs),'Full/selective deployment difference'
        for mode,rs in records.items():
            summaries[mode]={k:{'median':statistics.median([r[k] for r in rs.values()]),'min':min(r[k] for r in rs.values()),'max':max(r[k] for r in rs.values())} for k in next(iter(rs.values()))}
        paired={}
        for lhs,rhs in (('selective','full'),('selective','original')):
            paired[lhs+'/'+rhs]={}
            for k in summaries[lhs].keys()&summaries[rhs].keys():
                if any(records[rhs][r][k]==0 for r in records[rhs]):continue
                ratios=[records[lhs][r][k]/records[rhs][r][k] for r in sorted(records[lhs])]
                paired[lhs+'/'+rhs][k]={'ratios':ratios,'median':statistics.median(ratios),'min':min(ratios),'max':max(ratios)}
        results[kind]={'summary':summaries,'paired':paired,'populations':populations,'trials':records}
    save(root/'cost-audit.json',{'all_passed':True,'performance_eligible':True,'independent_deployments':len(projects),'algorithm_commit':frozen['algorithm_commit'],'queries_reported_separately':True,'results':results})
    fields=list(dict.fromkeys(k for r in csvrows for k in r))
    with (root/'cost-deployments.csv').open('w') as f:
        w=csv.DictWriter(f,fields);w.writeheader();w.writerows(csvrows)
    print('Cost population/measurement audit passed:',len(projects),'deployments',flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);audit(p.parse_args().root.resolve())
