#!/usr/bin/env python3
"""Independent evidence audit: raw DB facts and HTTP source instances, no inference.

Reads the engine's predictions only after independently deriving the expected
business output and exact raw source event/field coordinates.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from run_planned_service import load,save,sha,ROOT
from transport_context import validate_protocol


def audit(out,build):
    frozen=load(out/'freeze.json');manifest=load(build/'build.json');results={};semantic={}
    if sha(build/'build.json')!=frozen['build_sha256']:raise ValueError('Build changed')
    for file,key in [(out/'cases.json','cases_sha256'),(out/'database-fixtures.json','fixtures_sha256')]:
        if sha(file)!=frozen[key]:raise ValueError('Frozen inputs changed')
    for file,digest in manifest['sources'].items():
        snapshot=out/'sources'/Path(file).relative_to(ROOT)
        if sha(snapshot)!=digest:raise ValueError('Frozen source snapshot differs')
        if sha(Path(file))!=digest:raise ValueError('Audit must run with the frozen source version: '+file)
    driver=Path(__file__).with_name('run_train_multisource.py')
    if sha(driver)!=frozen['driver_sha256']:raise ValueError('Frozen driver changed')
    for mode in ('selective','full'):
        dest=out/mode;run=load(dest/'run.json');pred=load(dest/'predictions.json');rows={}
        if run['status']!='business-passed' or run['cleanup_returncode']:raise ValueError('Incomplete deployment/cleanup')
        for role in manifest['inputs']:
            path=dest/role/'events.jsonl';rs=[json.loads(s) for s in path.read_text().splitlines()];rows[role]=rs
            if [r['seq'] for r in rs]!=list(range(1,len(rs)+1)) or any(r['kind']=='problem' for r in rs) or rs[0]['mode']!=mode:raise ValueError('Incomplete/corrupt capture')
            if sum(r['kind']=='metrics' for r in rs)!=1 or rs[0]['plan_sha256']!=sha(build/role/'plan.json'):raise ValueError('Unclosed/wrong plan capture')
            validate_protocol(rs)
        db={r:json.loads(s) for r,s in load(dest/'independent-database.json').items()}
        raw={}
        for role,rs in rows.items():
            for r in rs:
                if r['kind']=='http-json' and r['phase']=='write' and r['direction']=='response':
                    for f in r['fields']:
                        k=(role,r['message'],f['path'])
                        if k in raw:raise ValueError('Duplicated source/target JSON pointer instance')
                        raw[k]=(r,f)
        by_case={(p['case'],p['key']):p for p in pred};tp=0;exact=0;unavailable=[];canonical=[]
        messages=[c['message'] for c in run['cases']]
        if len(messages)!=len(set(messages)) or len({m.split('/')[0] for m in messages})!=1:raise ValueError('Same-trace distinct request instance control missing')
        entry=load(build/'basic/plan.json')['entry'];root_frames={r['frame'] for r in rows['basic'] if r['kind']=='enter' and r['method']==entry}
        active=set();max_active=0
        for r in rows['basic']:
            if r['frame'] not in root_frames:continue
            if r['kind']=='enter':active.add(r['frame']);max_active=max(max_active,len(active))
            if r['kind'] in ('exit','abort'):active.remove(r['frame'])
        if active or max_active<2:raise ValueError('Overlapping root execution or cleanup control missing')
        for c in run['cases']:
            body=c['body'];station={s['name']:s['_id'] for s in db['station']};train=next((v for v in db['train'] if v['_id']==body['trip']['trainTypeId']),None)
            if train is None:
                if c['target_available'] or c['response'].get('status')!=500:raise ValueError('Absent upstream train incorrectly treated as target answer')
                if any((c['case'],key) in by_case for key in ('economyClass','confortClass')):raise ValueError('Absent target scored')
                unavailable.append(c['case']);continue
            route=next((v for v in db['route'] if v['_id']==body['trip']['routeId']),None)
            price=next((v for v in db['price'] if v['routeId']==body['trip']['routeId'] and v['trainType']==train['_id']),None)
            indexes=[];fallback=False
            try:
                distance=0
                if route is not None:
                    start=station.get(body['startingPlace']);end=station.get(body['endPlace'])
                    # Java indexOf returns -1; unlike Python, negative get is
                    # an error and must enter the original catch handler.
                    i=route['stations'].index(start) if start in route['stations'] else -1
                    j=route['stations'].index(end) if end in route['stations'] else -1
                    if min(i,j)<0 or max(i,j)>=len(route['distances']):raise IndexError()
                    distance=route['distances'][j]-route['distances'][i];indexes=[i,j]
                values={'economyClass':str(float(distance*price['basicPriceRate'])),'confortClass':str(float(distance*price['firstClassPriceRate']))}
            except (IndexError,TypeError):fallback=True;values={'economyClass':'95.0','confortClass':'120.0'}
            if c['response']['data']['prices']!=values or c['response']['status']!=(1 if body['startingPlace'] in station and body['endPlace'] in station else 0):raise ValueError('Database-derived business oracle differs')
            calls=[r for r in rows['basic'] if r['kind']=='http-rpc-enter' and r.get('parent_message')==c['message']]
            actual_request={role:[r for r in calls if 'ts-'+role+'-service:' in r['uri']] for role in ('route','price')}
            if any(len(v)!=1 for v in actual_request.values()):raise ValueError('Source invocation ambiguous')
            for key,rate in [('economyClass','basicPriceRate'),('confortClass','firstClassPriceRate')]:
                expected=set()
                if not fallback:
                    expected.add(('price',actual_request['price'][0]['message'],'/data/'+rate))
                    for index in indexes:expected.add(('route',actual_request['route'][0]['message'],'/data/distances/'+str(index)))
                p=by_case[(c['case'],key)];answer=p['answer'];actual={(s['service'],s['message'],s['path']) for s in answer['sources']}
                if not answer['known'] or actual!=expected:raise ValueError('Independent exact source-instance oracle differs')
                for s in answer['sources']:
                    event,f=raw[(s['service'],s['message'],s['path'])]
                    if any(s[k]!=f[k] for k in ('owner','field','version','observed')) or s['seq']!=event['seq']:raise ValueError('Predicted source is not its raw observed field instance')
                    expected_value=price[rate] if s['service']=='price' else route['distances'][int(s['path'].rsplit('/',1)[1])]
                    if s['observed']['value']!=expected_value:raise ValueError('Raw source disagrees with independent database')
                _,target=raw[('basic',c['message'],'/data/prices/'+key)]
                if any(answer['target'][k]!=target[k] for k in ('owner','field','version','observed')):raise ValueError('Target field identity differs')
                tp+=len(expected);exact+=1;canonical.append((c['case'],key,sorted((s['service'],s['path']) for s in answer['sources'])))
        if exact!=len(pred) or len(run['cases'])!=20:raise ValueError('Population differs')
        semantic[mode]=sorted(canonical)
        stats={r:{'events':len(rs),'bytes':(dest/r/'events.jsonl').stat().st_size,'kinds':dict(Counter(x['kind'] for x in rs))} for r,rs in rows.items()}
        results[mode]={'requests':20,'exact':exact,'tp':tp,'fp':0,'fn':0,'unknown':0,'unavailable_requests':unavailable,'max_overlapping_roots':max_active,'distinct_root_frames':len(root_frames),'one_shared_trace':True,'roles':stats,'events':sum(s['events'] for s in stats.values()),'bytes':sum(s['bytes'] for s in stats.values())}
    if semantic['full']!=semantic['selective']:raise ValueError('Policy answers differ')
    result={'all_passed':True,'results':results,'same_logical_answers':True,'auditor_sha256':sha(Path(__file__)),'source_oracle':'Raw independent database readbacks plus root-parent RPC span and raw server JSON field coordinates; does not invoke planner/reconstructor','not_formal_performance_measurement':True}
    save(out/'independent-audit.json',result);print(json.dumps(result,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);p.add_argument('--build',type=Path,required=True);a=p.parse_args();audit(a.out.resolve(),a.build.resolve())
