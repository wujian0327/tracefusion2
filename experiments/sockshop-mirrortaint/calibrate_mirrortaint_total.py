#!/usr/bin/env python3
"""Fresh deployment calibration before admitting MirrorTaint to cost tables."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import secrets
import threading

from run_planned_service import ROOT, load, save, sha
from host import prepare, submit
from run_sockshop_cost import spec_for, JVM
from run_distributed_paths import observed
from flowdist_full_order import CachedDeployment
import mirrortaint_instances as mt


def common_spec(mode,dest,build,bundle,cpu=1,memory='768m',observation_policy='selective'):
    if observation_policy not in ('full','selective','boundary') or mode!='tracefusion' and observation_policy!='selective':
        raise ValueError('Observation policies apply only to TraceFusion')
    spec=spec_for('original',dest,build,cpu,memory)
    if mode=='mirrortaint':mt.configure(spec,dest,bundle)
    elif mode=='tracefusion':
        for role in mt.ROLES:
            observed(spec,role,role,dest,build)
            # observed() adds a second app mount; keep one identical original.
            cfg=spec['services'][role]
            cfg['volumes']=list(dict.fromkeys(cfg['volumes']))
            cfg['entrypoint'][2]+=' --port=80'
            cfg['environment']['JAVA_OPTS']=JVM+(' -javaagent:/tf2/observer.jar -Dservice.plan=/tf2/plan.json'
                ' -Dservice.events=/tf2/capture/events.jsonl -Dservice.mode='+observation_policy)
    return spec


def run(args):
    out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    build=args.build.resolve();bundle=args.bundle.resolve();dest=out/'sockshop';dest.mkdir()
    policy=getattr(args,'observation_policy','selective')
    spec=common_spec(args.mode,dest,build,bundle,observation_policy=policy)
    save(dest/'compose.json',spec)
    dep=CachedDeployment(argparse.Namespace(project='tf2-mt-cal-'+secrets.token_hex(5),ready_timeout=240),dest,dest/'compose.json')
    result={'status':'failed','project':dep.args.project,'cases':[],'mode':args.mode}
    save(dest/'run.json',result)
    try:
        dep.start();trace=secrets.token_hex(16)
        cases=load(args.correctness/'cases.json')['sockshop']
        def setup(case,name,shared=False):
            prepared=prepare(case,name,dest/name,'http://127.0.0.1:18580','http://127.0.0.1:18581',shared=shared)
            span=secrets.token_hex(8);prepared[1].headers={'traceparent':f'00-{trace}-{span}-01','tracestate':'research=mtcal'}
            prepared[-1]['message']=trace+'/'+span;save(dest/name/'query-contract.json',prepared[-1]);return prepared
        for case in cases:
            p=setup(case,case['id']);r=submit(p,'http://127.0.0.1:18582',dest/case['id']);r['message']=p[-1]['message'];result['cases'].append(r)
            if not r['business_passed']:raise ValueError(r)
        pending=[setup(cases[0],'parallel-'+str(i),True) for i in range(8)];barrier=threading.Barrier(8)
        with ThreadPoolExecutor(max_workers=8) as pool:
            fs=[pool.submit(submit,p,'http://127.0.0.1:18582',dest/p[-1]['case'],barrier) for p in pending]
            for p,f in zip(pending,fs):
                r=f.result();r['message']=p[-1]['message'];result['cases'].append(r)
                if not r['business_passed']:raise ValueError(r)
        for role in mt.ROLES:dep.compose('stop','-t','20',role,timeout=40)
        result['status']='business-passed';save(dest/'run.json',result)
    finally:
        dep.diagnostics();clean=dep.compose('down','--volumes','--remove-orphans',timeout=120,check=False)
        result['cleanup_returncode']=clean.returncode;save(dest/'run.json',result)
    report=mt.evaluate(out,build,args.mode)
    if args.mode=='mirrortaint':mt.audit_calibration(out)
    save(out/'calibration.json',{'summary':report['summary'],'passed':report['summary']['exact']==report['summary']['queries'] and not report['summary']['unknown'],
                               'bundle_sha256':sha(bundle/'build.json'),'evaluator_sha256':sha(ROOT/'experiments/sockshop-mirrortaint/mirrortaint_instances.py'),
                               'build_sha256':sha(build/'build.json'),'cases_sha256':sha(args.correctness/'cases.json'),
                               'same_trace_distinct_spans':True,'parallel_requests':8,'contract':'Carts serialized JSON fields -> Orders.total',
                               'observation_policy':policy})
    print(report['summary'],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('out','build','bundle','correctness'):p.add_argument('--'+name,type=__import__('pathlib').Path,required=True)
    p.add_argument('--mode',choices=('mirrortaint','tracefusion'),required=True)
    run(p.parse_args())
