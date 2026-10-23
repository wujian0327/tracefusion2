#!/usr/bin/env python3
"""Inspect raw deployments/cohorts; separate closure from common optimizations."""
import argparse,copy,csv,json,statistics
from collections import Counter
from pathlib import Path
from run_planned_service import load,save,sha
from run_execution_closure_cost import check,ARMS
from audit_lifecycle_cost import values
from audit_cost_request_records import cohort
from audit_jackson_isolation import mapper_hash
from run_sockshop_cost import Sampler,percentiles
from infer_execution_closure import validate


def median_summary(records):
    return {a:{k:{'median':statistics.median(v[k]for v in rows.values()),'min':min(v[k]for v in rows.values()),'max':max(v[k]for v in rows.values())}for k in next(iter(rows.values()))}for a,rows in records.items()}


def pairs(records,comparisons):
    result={}
    for a,b in comparisons:
        result[a+'/'+b]={}
        assert set(records[a])==set(records[b])
        for k in next(iter(records[a].values())).keys()&next(iter(records[b].values())).keys():
            if any(v[k]==0 for v in records[b].values()):continue
            ratios=[records[a][r][k]/records[b][r][k]for r in sorted(records[a])];result[a+'/'+b][k]={'ratios':ratios,'median':statistics.median(ratios),'min':min(ratios),'max':max(ratios)}
    return result


def audit(root):
    c=check(root);assert load(root/'run-status.json')['status']=='passed';memory=load(root/'offline-memory-audit.json');assert memory['all_passed']and len(memory['measurements'])==25;assert all(sha(Path(p))==h for p,h in memory['guarded_sha256'].items());planning=load(root/'static-planning/results.json');assert planning['all_passed']and len(planning['measurements'])==10
    jobs=[('cart',j['name'],j['arm'],j['mode'],root/'cart-deployments'/j['name'],root/'builds'/j['arm'])for j in c['cart_order']]
    jobs.extend(('price',name,mode,mode,root/'cost-price'/name,root/'price-build')for name,mode in load(root/'cost-price/config.json')['order'])
    records={'cart':{},'price':{}};populations={'cart':{},'price':{}};rows=[];receipts=[];projects=set()
    for kind,name,arm,mode,d,build in jobs:
        m=copy.deepcopy(load(d/'metrics.json'));assert m['status']=='passed'and m['mode']==mode;cleanup=load(d/'cleanup.json');assert cleanup['returncode']==0 and cleanup['project']not in projects;projects.add(cleanup['project']);app='trainticket'if kind=='price'else'capture';cap=d/app
        warm=load(d/'warmup.json');steady=load(d/'steady.json');assert len(warm['requests'])==60 and len(steady['requests'])==120;requests=warm['requests']+steady['requests'];assert all(r['business_passed']for r in requests);assert max(r['online_end_ns']for r in warm['requests'])<=steady['start_ns'];assert m['online_latency_ms']==percentiles([(r['online_end_ns']-r['online_start_ns'])/1e6 for r in steady['requests']])
        assert m['throughput_rps']==sum(r['online_end_ns']<=steady['scheduled_end_ns']for r in steady['requests'])/60 and m['error_rate']==0
        samples=[json.loads(v)for v in(d/'resources.jsonl').read_text().splitlines()];roles=list(load(build/'build.json')['inputs'])if kind=='price'else['carts'];observed=['ts-'+r+'-service'for r in roles]if kind=='price'else['carts'];sampler=Sampler({r:None for r in samples[0]},2,d/'unused-audit-sampler.jsonl',observed_roles=observed);sampler.rows=samples;assert sampler.summary(steady['start_ns'],steady['scheduled_end_ns'])==m['resources']
        spec=load(cap/'compose.json')
        for role in roles:
            service='carts'if role=='carts'else'ts-'+role+'-service';opts=spec['services'][service]['environment']['JAVA_OPTS'];assert opts==c['jvm']+(''if mode=='original'else' -javaagent:/tf2/observer.jar -Dservice.plan=/tf2/plan.json -Dservice.events=/tf2/capture/events.jsonl -Dservice.mode='+mode);assert spec['services'][service]['cpus']==1 and spec['services'][service]['mem_limit']=='768m'
        if mode!='original':
            data=load((cap if kind=='price'else d)/'field-results.json');s=data['summary'];assert s['queries']==s['exact']==(360 if kind=='price'else 270)and s['fp']==s['fn']==s['unknown']==0;assert m['offline']['summary']==s
            for label,expected in(('warmup',120 if kind=='price'else 90),('steady',240 if kind=='price'else 180)):
                pop=m['offline']['populations'][label];assert pop['queries']==pop['exact']==expected
            populations[kind].setdefault(arm,[]).append({'trial':name,'warmup_requests':60,'measurement_requests':120,'summary':s,'populations':m['offline']['populations']})
            paths={role:cap/role/'events.jsonl'for role in roles};closed=cohort(paths,{r['message']for r in steady['requests']});save(d/'measured-request-records.json',closed);m['file_visible_capture']=m['steady_capture'];m['steady_capture']=closed['request_records'];m['offline']['replay_vmhwm_bytes']=memory['measurements'][kind+'/'+name]['vmhwm_bytes']
            for role,path in paths.items():
                raw=[json.loads(v)for v in path.read_text().splitlines()];assert not any(v['kind']=='problem'for v in raw);proof=[r for r in raw if r['kind']=='jackson-isolation'];assert proof and all(r['business_class_sha256']==mapper_hash(build/role/'original.jar')[1]for r in proof);plan=load(build/role/'plan.json');assert raw[0]['plan_sha256']==sha(build/role/'plan.json')and plan['source_evidence']is True
                fact=validate(plan,raw)if kind=='cart'else None
                if kind=='cart':assert plan['execution_observation_closure']['enabled']==ARMS[arm][1];assert fact['elided_writes']>0 if arm=='selective'else fact['elided_writes']==0
                receipts.append({'kind':kind,'trial':name,'role':role,'events_sha256':sha(path),'closure_audit':fact})
        v=values(m);records[kind].setdefault(arm,{})[name[:8]]=v;rows.append({'kind':kind,'arm':arm,'mode':mode,'trial':name,**v})
    assert len(projects)==35
    result={'all_passed':True,'algorithm':c['algorithm_commit'],'independent_deployments':35,'shared_alias_index':True,'format_compression':False,'results':{k:{'summary':median_summary(v),'paired':pairs(v,[('selective','full'),('selective','original')]+([('selective','selective_without_closure')]if k=='cart'else[])),'trials':v,'populations':populations[k]}for k,v in records.items()},'receipts':receipts,'old_metrics_overwritten':False}
    save(root/'cost-audit.json',result)
    with(root/'deployments.csv').open('w',newline='')as f:
        fields=list(dict.fromkeys(k for row in rows for k in row));writer=csv.DictWriter(f,fieldnames=fields,lineterminator='\n');writer.writeheader();writer.writerows(rows)
    print({'cost_audit_passed':True,'deployments':35},flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',required=True,type=Path);audit(p.parse_args().root.resolve())
