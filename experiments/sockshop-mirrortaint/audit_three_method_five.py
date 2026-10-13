#!/usr/bin/env python3
"""Independent five-method protocol, raw sample and relation-score validation."""
import argparse
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
import shlex
import statistics


def load(path):return json.loads(path.read_text())


def baseline_options(text):
    return [option for option in shlex.split(text) if not any(option.startswith(prefix) for prefix in
        ('-javaagent:', '-Dflowdist.', '-Dtracefusion.', '-Dtaint.', '-Dtf2.mt.', '-Duser.home='))]


def audit(pilot, apps, total_queries, controls, out):
    out.mkdir(parents=True,exist_ok=False)
    comparison=load(pilot/'comparison.json');manifest=load(apps/'manifest.json')
    runs={mode:load(pilot/mode/'evaluation.json') for mode in ('plain','flowdist','mirrortaint','tracefusion')}
    order=['newOrder','get','delete','mergeCarts','postShipping']
    sources={}
    def pin(path):sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
    pin(pilot/'comparison.json');pin(apps/'manifest.json')
    locked=[];configs=[];rows=[];calibration=[]
    for mode,report in runs.items():
        run=pilot/mode;execution=load(run/'result.json');protocol=load(run/'protocol.json')
        if protocol!=comparison['protocol'] or execution['status']!='business-passed' or execution['frontend_errors']:
            raise ValueError('Incomplete or incompatible run: '+mode)
        business=execution['cases']
        if len(business)!=151 or len({case['case'] for case in business})!=151 or not all(case['business_passed'] for case in business):
            raise ValueError('Business denominator changed: '+mode)
        if Counter(case['phase'] for case in business)!={'accuracy':26,'warmup':25,'measurement':100}:
            raise ValueError('Wrong workload phases: '+mode)
        spec=load(run/'compose.lock.json');locked.append({k:v['image'] for k,v in spec['services'].items()});configs.append(spec)
        for role in ('orders','carts','shipping'):
            expected=manifest['apps'][role]['adapted_sha256' if mode=='flowdist' else 'original_sha256']
            if hashlib.sha256((run/(role+'.jar')).read_bytes()).hexdigest()!=expected:
                raise ValueError('Business artifact/build mismatch: '+mode+'/'+role)
            events_file=run/'cost-events'/role/'events.jsonl';pin(events_file)
            events=[json.loads(line) for line in events_file.read_text().splitlines()]
            if [e['seq'] for e in events]!=list(range(1,len(events)+1)) or any(e['kind']=='problem' for e in events):
                raise ValueError('Invalid observer: '+mode+'/'+role)
            by_seq={e['seq']:e for e in events}
            for method in order:
                service='orders' if method=='newOrder' else 'shipping' if method=='postShipping' else 'carts'
                if service!=role:continue
                cost=report['cost'][method];samples=cost['samples']
                measured=[case for case in business if case['phase']=='measurement' and case['method']==method]
                if len(samples)!=20 or {s['case'] for s in samples}!={c['case'] for c in measured}:
                    raise ValueError('Missing/extra measurement: '+mode+'/'+method)
                by_case={c['case']:c for c in measured}
                for sample in samples:
                    event=by_seq[sample['seq']]
                    if event['kind']!='exit' or event['parent']!=0 or event['trace_id']!=by_case[sample['case']]['trace_id']:
                        raise ValueError('Wrong cost invocation join')
                    for key in ('runtime_ns','process_allocated_bytes','thread_allocated_bytes','rss_kb'):
                        if event[key]!=sample[key] or event[key]<0:raise ValueError('Raw sample mismatch')
                means={label:statistics.mean(by_seq[s['seq']][key]/scale for s in samples)
                       for label,key,scale in (('controller_ms','runtime_ns',1e6),('allocated_kB','process_allocated_bytes',1024),('resident_kB','rss_kb',1))}
                for label,value in means.items():
                    if not math.isclose(value,cost[label]['mean'],abs_tol=1e-9):raise ValueError('Mean mismatch')
                rows.append({'method':method,'configuration':mode,'n':20,'controller_mean_ms':means['controller_ms'],
                             'jvm_mean_RSS_MiB':means['resident_kB']/1024,'process_allocated_KiB':means['allocated_kB']})
        pin(run/'evaluation.json');pin(run/'result.json');pin(run/'protocol.json');pin(run/'compose.lock.json')
        if mode in ('mirrortaint','tracefusion'):
            for method in order:
                actual=report['queries'][method];counts=Counter()
                for query in actual:
                    expected={tuple(c) for c in query['expected']};found={tuple(c) for c in query['actual']}
                    counts['tp']+=len(expected&found);counts['fp']+=len(found-expected);counts['fn']+=len(expected-found)
                    counts['exact']+=query['exact'];counts['unknown']+=query['unknown']
                summary=report['accuracy'][method]
                for key in ('tp','fp','fn','exact','unknown'):
                    if counts[key]!=summary[key]:raise ValueError('Relation scoring mismatch')
                denom=2*counts['tp']+counts['fp']+counts['fn']
                calibration.append({'method':method,'configuration':mode,'queries':len(actual),**dict(counts),
                    'precision':counts['tp']/(counts['tp']+counts['fp']) if counts['tp']+counts['fp'] else None,
                    'recall':counts['tp']/(counts['tp']+counts['fn']) if counts['tp']+counts['fn'] else None,
                    'f1':2*counts['tp']/denom if denom else None})
            if not report['all_no_target_passed'] or len(report['no_target'])!=2:
                raise ValueError('No-target checks failed')
    if any(lock!=locked[0] for lock in locked):raise ValueError('Image mismatch')
    for role in ('orders','carts','shipping'):
        options=[baseline_options(c['services'][role]['environment']['JAVA_OPTS']) for c in configs]
        if any(option!=options[0] for option in options):raise ValueError('Different base JVM options: '+role)
    total=load(total_queries/'comparison.json');pin(total_queries/'comparison.json')
    aggregate={}
    for mode,queries in total['queries'].items():
        counts=Counter()
        for query in queries:
            expected=query['expected_dependency'];actual=query['prediction']
            if actual is None:
                counts['unknown']+=1;counts['missed_positive_including_unknown']+=bool(expected)
            else:
                counts[('tp' if expected else 'fp') if actual else ('fn' if expected else 'tn')]+=1
                counts['correct']+=expected==actual
                counts['missed_positive_including_unknown']+=bool(expected and not actual)
        if len(queries)!=7 or counts['correct']!=total['summary'][mode]['correct']:
            raise ValueError('Total query score mismatch')
        aggregate[mode]={'queries':7,**dict(counts)}
    native=load(controls/'result.json');pin(controls/'result.json')
    if len(native['queries'])!=4 or any(not q['endpoints_covered'] for q in native['queries']):
        raise ValueError('Native reference controls require observed nonempty endpoints')
    for row in rows:
        baseline=next(r['controller_mean_ms'] for r in rows if r['method']==row['method'] and r['configuration']=='plain')
        row['overhead_percent']=100*(row['controller_mean_ms']/baseline-1)
    rows.sort(key=lambda row:(order.index(row['method']),('plain','flowdist','mirrortaint','tracefusion').index(row['configuration'])))
    with (out/'five-method-costs.csv').open('w',encoding='utf-8-sig',newline='') as file:
        writer=csv.DictWriter(file,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    keys=['method','configuration','queries','tp','fp','fn','exact','unknown','precision','recall','f1']
    with (out/'scalar-calibration.csv').open('w',encoding='utf-8-sig',newline='') as file:
        writer=csv.DictWriter(file,fieldnames=keys);writer.writeheader();writer.writerows(calibration)
    report={'kind':'five-controller-independent-validation','business_each_configuration':151,'business_total':604,
            'matched_cached_images_and_base_JVM_options':True,'raw_cost_samples_checked':400,
            'scalar_calibration':calibration,'aggregate_total_queries':aggregate,
            'native_reference_controls':native['queries'],'costs':rows,
            'readiness':'Share with caveats; bounded pilot, no formal accuracy/performance ranking',
            'accuracy_eligible':False,'performance_eligible':False,'source_sha256':sources,
            'limitations':['All means are one deployment per configuration in fixed order; negative overhead values are observed noise, not an acceleration claim.',
                           'Native reference controls, seven aggregate total queries and scalar-instance calibration have different denominators and remain separate.',
                           'Scalar-source adapters, lambda/framework models and online/offline logging scopes differ and must be disclosed.',
                           'Original controller timing excludes shutdown serialization and all static/offline work; RSS is whole-JVM resident memory.']}
    (out/'validation.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for flag in ('pilot','apps','total-queries','controls','out'):parser.add_argument('--'+flag,type=Path,required=True)
    args=parser.parse_args();report=audit(args.pilot.resolve(),args.apps.resolve(),args.total_queries.resolve(),args.controls.resolve(),args.out.resolve())
    print('Verified',report['business_total'],'business cases and',report['raw_cost_samples_checked'],'raw measured costs')
