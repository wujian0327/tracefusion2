#!/usr/bin/env python3
"""Write a reproducible pilot comparison; preserve every per-case result."""
import argparse
import hashlib
import json
from pathlib import Path
from evaluate_five_methods import evaluate
from five_methods import METHODS


def compare(paths):
    reports = {mode:evaluate(path) for mode,path in paths.items()}
    protocols = [json.loads((p/'protocol.json').read_text()) for p in paths.values()]
    if not all(p==protocols[0] for p in protocols):
        raise ValueError('Different measurement protocols or observer builds')
    locks = [json.loads((p/'compose.lock.json').read_text()) for p in paths.values()]
    images = {s:locks[0]['services'][s]['image'] for s in locks[0]['services']}
    if any({s:l['services'][s]['image'] for s in l['services']}!=images for l in locks):
        raise ValueError('Different business images')
    table = []
    for method in METHODS:
        row = {'method':method}
        for mode,report in reports.items():
            cost = report['cost'][method]
            row[mode] = {'accuracy':report.get('accuracy',{}).get(method),
                         **{k:cost[k] for k in ('n','controller_ms','http_ms','allocated_kB','resident_kB')}}
            if mode!='plain':
                base = reports['plain']['cost'][method]
                row[mode]['runtime_overhead_percent'] = 100*(cost['controller_ms']['mean']/base['controller_ms']['mean']-1)
                row[mode]['allocation_overhead_percent'] = 100*(cost['allocated_kB']['mean']/base['allocated_kB']['mean']-1)
        table.append(row)
    for mode,path in paths.items():
        (path/'evaluation.json').write_text(json.dumps(reports[mode],indent=2)+'\n')
    return {'status':'five-method-pilot-complete','methods':table,'protocol':protocols[0],
            'images':images,'same_protocol_and_images':True,
            'totals':{mode:{'queries':sum(a['queries'] for a in r['accuracy'].values()),
                            'exact':sum(a['exact'] for a in r['accuracy'].values()),
                            'tp':sum(a['tp'] for a in r['accuracy'].values()),
                            'fp':sum(a['fp'] for a in r['accuracy'].values()),
                            'fn':sum(a['fn'] for a in r['accuracy'].values()),
                            'all_no_target_passed':r['all_no_target_passed']}
                      for mode,r in reports.items() if 'accuracy' in r},
            'offline':{mode:{k:r[k] for k in ('offline_evaluation_and_reconstruction_ms','offline_process_peak_rss_kB')}
                       for mode,r in reports.items() if 'accuracy' in r},
            'runs':{m:str(p.resolve()) for m,p in paths.items()},
            'raw_evaluation_sha256':{m:hashlib.sha256((p/'evaluation.json').read_bytes()).hexdigest() for m,p in paths.items()},
            'accuracy_eligible':False,'performance_eligible':False,
            'limitations':['One deployment per configuration, 20 serial measurements per API after 5 warmups; no confidence/ranking claim.',
                          'Selected explicit scalar field relations only: CartDAO read boundaries, Shipping input DTO, and Orders consumed HTTP responses.',
                          'Private Cart fields are evaluated at Java DTO/database call boundaries, not nonexistent HTTP response fields.',
                          'Allocated kB per invocation differs from resident kB of the entire service JVM and from retained memory.',
                          'Process-wide allocation includes background activity; RSS depends on warmup, garbage collection and retained observation objects.',
                          'TraceFusion runtime columns exclude offline reconstruction. Separate batch timing includes decoding, normalization and evaluation; not per-query latency.',
                          'MirrorTaint uses disclosed adapters plus field source-boundary configuration; original direct-run failures remain preserved.',
                          'Source commit/image build qualification, independent review, DB wire-instance oracle and repeated randomized deployments remain pending.']}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for mode in ('plain','mirrortaint','tracefusion'):p.add_argument('--'+mode,type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);args=p.parse_args()
    report=compare({m:getattr(args,m) for m in ('plain','mirrortaint','tracefusion')})
    args.out.write_text(json.dumps(report,indent=2)+'\n')
    for row in report['methods']:
        print(row['method'],*[f"{m}: {row[m]['controller_ms']['mean']:.3f} ms / {row[m]['allocated_kB']['mean']:.1f} allocated kB" for m in ('plain','mirrortaint','tracefusion')])
