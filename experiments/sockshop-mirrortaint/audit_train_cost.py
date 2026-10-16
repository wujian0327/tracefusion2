#!/usr/bin/env python3
"""Recompute cost evidence and DB-derived source oracles without reconstruction."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import random
import statistics
from run_planned_service import load,save,sha
from run_train_multisource import ROLES
from audit_cost_population import uncertainty
from transport_context import validate_protocol


def quantile(xs,p):return sorted(xs)[max(0,math.ceil(len(xs)*p)-1)]
def equal(a,b):
    if not math.isclose(a,b,rel_tol=1e-10,abs_tol=1e-10):raise ValueError('Numeric summary differs: '+str((a,b)))


def database_truth(c,db):
    body=c['body'];station={s['name']:s['_id'] for s in db['station']}
    train=next(t for t in db['train'] if t['_id']==body['trip']['trainTypeId'])
    route=next((r for r in db['route'] if r['_id']==body['trip']['routeId']),None)
    price=next((p for p in db['price'] if p['routeId']==body['trip']['routeId'] and p['trainType']==train['_id']),None)
    indices=[];fallback=False
    try:
        distance=0
        if route is not None:
            a=station.get(body['startingPlace']);b=station.get(body['endPlace']);ids=route['stations']
            i=ids.index(a) if a in ids else -1;j=ids.index(b) if b in ids else -1
            if min(i,j)<0 or max(i,j)>=len(route['distances']):raise IndexError()
            distance=route['distances'][j]-route['distances'][i];indices=[i,j]
        values={'economyClass':str(float(distance*price['basicPriceRate'])),'confortClass':str(float(distance*price['firstClassPriceRate']))}
    except (IndexError,TypeError):fallback=True;values={'economyClass':'95.0','confortClass':'120.0'}
    return {'values':values,'status':1 if body['startingPlace'] in station and body['endPlace'] in station else 0,'fallback':fallback,'indices':indices,'price':price,'route':route}


def audit_trial(root,name,mode,config):
    trial=root/name;dest=trial/'trainticket';m=load(trial/'metrics.json');run=load(dest/'run.json');warm=load(trial/'warmup.json');steady=load(trial/'steady.json')
    assert m['mode']==mode and m['status']=='passed' and run['status']=='business-passed'
    assert load(trial/'cleanup.json')['returncode']==0
    records=warm['requests']+steady['requests'];assert records==run['cases']
    assert len(warm['requests'])==round(config['warmup']*config['rate']) and len(steady['requests'])==round(config['seconds']*config['rate'])
    assert len({r['message'] for r in records})==len(records)
    db={r:json.loads(s) for r,s in load(dest/'independent-database.json').items()};truth={}
    templates=load(root/'templates.json')
    for phase in (warm,steady):
        label='warmup' if phase is warm else 'steady'
        for i,r in enumerate(phase['requests']):
            assert r['case']==f'{label}-{i:05d}' and r['body']==templates[i%len(templates)]['body']
            assert r['scheduled_ns']==phase['start_ns']+round(i/config['rate']*1e9)
            assert r['online_end_ns']>=r['online_start_ns']>=r['scheduled_ns'] and r['http_status']==200
            t=database_truth(r,db);truth[r['case']]=t
            assert r['response']['status']==t['status'] and r['response']['data']['prices']==t['values'] and r['business_passed']
        equal(phase['scheduled_end_ns']-phase['start_ns'],round((config['warmup'] if phase is warm else config['seconds'])*1e9))
    assert max(r['online_end_ns'] for r in warm['requests'])<=steady['start_ns']
    latency=[(r['online_end_ns']-r['online_start_ns'])/1e6 for r in steady['requests']]
    for p in (50,95,99):equal(quantile(latency,p/100),m['online_latency_ms']['p'+str(p)])
    equal(sum(r['online_end_ns']<=steady['scheduled_end_ns'] for r in steady['requests'])/config['seconds'],m['throughput_rps'])
    equal(len(steady['requests'])/((steady['drain_end_ns']-steady['start_ns'])/1e9),m['drained_throughput_rps'])
    equal(max((r['online_start_ns']-r['scheduled_ns'])/1e6 for r in steady['requests']),m['max_dispatch_lag_ms'])
    assert m['error_rate']==0 and m['http_status_counts']=={'200':len(steady['requests'])}
    spec=load(dest/'compose.json');actual=load(dest/'containers.json');names=[]
    for entry in actual:
        service=entry['Config']['Labels']['com.docker.compose.service'];names.append(service);expected=spec['services'][service]
        assert entry['HostConfig']['Memory']==(384 if service.endswith('-mongo') else 768)*2**20 and entry['HostConfig']['NanoCpus']==10**9
        assert entry['Config']['Image']==expected['image'] and '@sha256:' in expected['image']
        if not service.endswith('-mongo'):
            opts=next(e[len('JAVA_OPTS='):] for e in entry['Config']['Env'] if e.startswith('JAVA_OPTS='));assert opts==expected['environment']['JAVA_OPTS']
            assert opts.startswith(config['jvm']) and ('-javaagent:' in opts)==(mode!='original')
    samples=[json.loads(s) for s in (trial/'resources.jsonl').read_text().splitlines()];resources={}
    for service in names:
        selected=[s[service] for s in samples if steady['start_ns']<=s[service]['monotonic_ns']<=steady['scheduled_end_ns']];assert len(selected)>=2
        for s in selected:
            assert s['cpu_ns']==s['raw_stats']['cpu_stats']['cpu_usage']['total_usage']
            rss=s['raw_top']['Titles'].index('RSS');assert s['rss_bytes']==sum(int(p[rss])*1024 for p in s['raw_top']['Processes'])
        assert all(b['cpu_ns']>=a['cpu_ns'] for a,b in zip(selected,selected[1:]))
        cpu=100*(selected[-1]['cpu_ns']-selected[0]['cpu_ns'])/(selected[-1]['monotonic_ns']-selected[0]['monotonic_ns'])
        resources[service]=cpu;equal(cpu,m['resources'][service]['cpu_one_core_percent_mean'])
        equal(statistics.mean(s['rss_bytes'] for s in selected),m['resources'][service]['rss_bytes_mean'])
        equal(max(s['rss_bytes'] for s in selected),m['resources'][service]['rss_bytes_peak'])
    for group,members in [('observed_jvms',['ts-'+r+'-service' for r in ROLES]),('deployment',names)]:
        equal(sum(resources[s] for s in members),m['resources'][group]['cpu_one_core_percent_mean'])
        aligned=[s for s in samples if all(steady['start_ns']<=s[x]['monotonic_ns']<=steady['scheduled_end_ns'] for x in members)];assert len(aligned)>=2
        rss=[sum(s[x]['rss_bytes'] for x in members) for s in aligned]
        equal(statistics.mean(rss),m['resources'][group]['rss_bytes_mean']);equal(max(rss),m['resources'][group]['rss_bytes_peak'])
    window=load(trial/'capture-window.json');populations={};native={}
    for r in ROLES:
        path=dest/r/'events.jsonl';events=0;size=0
        if path.exists():
            lines=path.read_bytes().splitlines(keepends=True);native[r]=[json.loads(s) for s in lines];events=len(native[r]);size=path.stat().st_size
            for boundary in ('before','after'):
                n=window[boundary][r]['events'];assert window[boundary][r]['bytes']==sum(len(s) for s in lines[:n])
        assert m['total_capture'][r]=={'events':events,'bytes':size}
        for key in ('events','bytes'):assert m['steady_capture'][r][key]==window['after'][r][key]-window['before'][r][key]>=0
    if mode=='original':
        assert not native and m['offline'] is None and m['completion_to_batch_answers_seconds'] is None
    else:
        raw={};rpcs={}
        for r,rows in native.items():
            assert [x['seq'] for x in rows]==list(range(1,len(rows)+1)) and not any(x['kind']=='problem' for x in rows)
            assert rows[0]['mode']==mode and sum(x['kind']=='metrics' for x in rows)==1
            assert rows[0]['plan_sha256']==sha(Path(config['build'])/r/'plan.json')
            validate_protocol(rows)
            for x in rows:
                if x['kind']=='http-json' and x['phase']=='write' and x['direction']=='response':
                    for f in x['fields']:
                        k=(r,x['message'],f['path']);assert k not in raw;raw[k]=(x,f)
                if r=='basic' and x['kind']=='http-rpc-enter':rpcs.setdefault(x.get('parent_message'),[]).append(x)
        answers=load(dest/'answers.json');answers={(a['case'],a['key']):a['answer'] for a in answers};assert len(answers)==2*len(records)
        for label,phase in [('warmup',warm),('steady',steady)]:
            tp=0
            for c in phase['requests']:
                t=truth[c['case']];calls=rpcs[c['message']];instances={r:[x['message'] for x in calls if 'ts-'+r+'-service:' in x['uri']] for r in ('route','price')};assert all(len(v)==1 for v in instances.values())
                for key,rate in [('economyClass','basicPriceRate'),('confortClass','firstClassPriceRate')]:
                    expected=set()
                    if not t['fallback']:
                        expected.add(('price',instances['price'][0],'/data/'+rate));expected.update(('route',instances['route'][0],'/data/distances/'+str(i)) for i in t['indices'])
                    answer=answers[(c['case'],key)];assert answer['known']
                    observed={(s['service'],s['message'],s['path']) for s in answer['sources']};assert observed==expected
                    for s in answer['sources']:
                        event,f=raw[(s['service'],s['message'],s['path'])];assert s['seq']==event['seq'] and all(s[k]==f[k] for k in ('owner','field','version','observed'))
                        value=t['price'][rate] if s['service']=='price' else t['route']['distances'][int(s['path'].rsplit('/',1)[1])];assert s['observed']['value']==value
                    _,target=raw[('basic',c['message'],'/data/prices/'+key)];assert all(answer['target'][k]==target[k] for k in ('owner','field','version','observed'))
                    tp+=len(expected)
            populations[label]={'queries':len(phase['requests'])*2,'exact':len(phase['requests'])*2,'tp':tp,'fp':0,'fn':0,'unknown':0}
        off=m['offline'];assert off['populations']==populations
        native_offline=load(trial/'offline.json')
        assert all(off[k]==v for k,v in native_offline.items())
        assert off['peak_rss_bytes']>0 and 0<off['process_cpu_seconds']<=off['subprocess_wall_seconds']+.02
        assert all(v>=0 for v in off['phases'].values())
        assert sum(off['phases'].values())<=off['restore_score_export_seconds']+.001
        assert 0<off['core_seconds']<=off['restore_score_export_seconds']<=off['subprocess_wall_seconds']
        for k in ('queries','exact','tp','fp','fn','unknown'):assert off['summary'][k]==sum(p[k] for p in populations.values())
        equal(off['core_seconds'],off['phases']['validate_graph_reconstruct_seconds']+off['phases']['target_origin_restore_seconds'])
        timeline=load(trial/'result-timeline.json');assert steady['drain_end_ns']<=timeline['shutdown_started_ns']<=timeline['capture_closed_upper_bound_ns']<=off['answers_ready_ns']<=off['scored_evidence_ready_ns']
        readiness=load(trial/'answer-readiness.json');assert len(readiness)==len(steady['requests'])
        by_case={r['case']:r for r in steady['requests']}
        for r in readiness:
            assert r['response_complete_ns']==by_case[r['case']]['online_end_ns'];equal(r['completion_to_answer_seconds'],(off['answers_ready_ns']-r['response_complete_ns'])/1e9)
        for p in (50,95,99):equal(quantile([r['completion_to_answer_seconds'] for r in readiness],p/100),m['completion_to_batch_answers_seconds']['p'+str(p)])
    assert (trial/'container-console.log').stat().st_size==m['container_console_bytes']
    return {'trial':name,'mode':mode,'warmup_requests':len(warm['requests']),'steady_requests':len(steady['requests']),'query_populations':populations,'latency_sample_size':len(latency),'p99_rank':math.ceil(.99*len(latency)),**m}


def audit(root):
    config=load(root/'config.json');assert load(root/'run-status.json')['status']=='passed';rows=[]
    for path,key in [(root/'templates.json','templates_sha256'),(root/'database-fixtures.json','fixtures_sha256'),(Path(config['build'])/'build.json','build_sha256'),(Path(config['inputs']),'inputs_sha256')]:assert sha(path)==config[key]
    build=Path(config['build']);manifest=load(build/'build.json')
    assert sha(build/'distributed-observer.jar')==manifest['agent_sha256']
    for path,digest in {**manifest['sources'],**manifest['dependencies']}.items():assert sha(Path(path))==digest
    for role,record in manifest['inputs'].items():
        for name,key in [('original.jar','original_jar_sha256'),('model.json','model_sha256'),('plan.json','plan_sha256')]:assert sha(build/role/name)==record[key]
    rng=random.Random(config['seed']);expected_order=[]
    for i in range(config['rounds']):
        modes=['original','full','selective'];rng.shuffle(modes);expected_order.extend([f'round-{i+1:02d}-{j+1:02d}-{m}',m] for j,m in enumerate(modes))
    assert config['order']==expected_order
    for filename,digest in {**config['source_sha256'],**config['calibration_evidence_sha256']}.items():assert sha(Path(filename))==digest
    for name,mode in config['order']:rows.append(audit_trial(root,name,mode,config))
    pairs=[]
    def metric(r,k):
        if k.startswith('latency_'):return r['online_latency_ms'][k.removeprefix('latency_')]
        if k in ('cpu','rss_mean','rss_peak'):return r['resources']['observed_jvms'][{'cpu':'cpu_one_core_percent_mean','rss_mean':'rss_bytes_mean','rss_peak':'rss_bytes_peak'}[k]]
        if k.startswith('deployment_'):return r['resources']['deployment'][{'deployment_cpu':'cpu_one_core_percent_mean','deployment_rss_mean':'rss_bytes_mean','deployment_rss_peak':'rss_bytes_peak'}[k]]
        if k in ('capture_events','capture_bytes'):return sum(v[k.removeprefix('capture_')] for v in r['steady_capture'].values())
        if k=='console_bytes':return r['container_console_bytes']
        if k=='answer_p95':return r['completion_to_batch_answers_seconds']['p95'] if r['offline'] else None
        if k.startswith('offline_'):return r['offline'][k.removeprefix('offline_')] if r['offline'] else None
        return r[k]
    metrics=['latency_p50','latency_p95','latency_p99','throughput_rps','cpu','rss_mean','rss_peak','deployment_cpu','deployment_rss_mean','deployment_rss_peak','capture_events','capture_bytes','console_bytes','offline_core_seconds','offline_restore_score_export_seconds','offline_subprocess_wall_seconds','offline_process_cpu_seconds','offline_peak_rss_bytes','answer_p95']
    summary={mode:{key:{'median':statistics.median(v),'min':min(v),'max':max(v)} if (v:=[metric(r,key) for r in rows if r['mode']==mode and metric(r,key) is not None]) else None for key in metrics} for mode in ('original','full','selective')}
    for num,den in [('selective','full'),('selective','original'),('full','original')]:
        ratios={}
        for key in metrics:
            values=[]
            for i in range(config['rounds']):
                block={r['mode']:r for r in rows if r['trial'].startswith(f'round-{i+1:02d}-')};a,b=metric(block[num],key),metric(block[den],key)
                if a is not None and b:values.append(a/b)
            if values:ratios[key]=uncertainty(values)
        pairs.append({'comparison':num+'/'+den,'metrics':ratios})
    totals={mode:{'deployments':sum(r['mode']==mode for r in rows),'warmup_requests':sum(r['warmup_requests'] for r in rows if r['mode']==mode),'steady_requests':sum(r['steady_requests'] for r in rows if r['mode']==mode),'populations':{phase:{k:sum(r['query_populations'].get(phase,{}).get(k,0) for r in rows if r['mode']==mode) for k in ('queries','exact','tp','fp','fn','unknown')} for phase in ('warmup','steady')}} for mode in ('original','full','selective')}
    totals['original']['populations']=None
    totals['original']['provenance_status']='N/A: no observer, business responses checked'
    report={'all_passed':True,'performance_eligible':config['rounds']>=5,'rows':rows,'summary':summary,'paired':pairs,'populations':totals,'auditor_sha256':sha(Path(__file__)),'caveats':['Independent deployment is repetition unit; request latencies are not independent deployments','n=5 pair bootstrap is exploratory; min/max population-median coverage only 93.75%, unadjusted sign tests','p99 is rank119/120 in formal trial and secondary','Fixed offered rate is not saturation throughput','Sources are value operands; index/control selectors excluded by frozen query contract','Answer wait includes batch window and shutdown; raw first-availability and target creation unmeasured','Offline core includes validation, graph construction and admitted local replay; whole process includes imports/score/export','Structured capture and full-deployment console export are separate accounting scopes']}
    save(root/'independent-audit.json',report);print('Independent audit passed:',len(rows),'deployments')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);a=p.parse_args();audit(a.out.resolve())
