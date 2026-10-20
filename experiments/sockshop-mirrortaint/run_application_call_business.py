#!/usr/bin/env python3
"""New-Agent v2 regression on original loop entries, with unchanged independent truth."""
import argparse,traceback
from pathlib import Path
from run_planned_service import HERE,ROOT,load,save
from build_distributed_plans import build
from plan_response_binding import plan_response
import run_response_binding_revision as old
import run_execution_kernel_pilot as pilot


def run(out):
    out.mkdir(parents=True,exist_ok=False);parent=ROOT/'artifacts/call-lifecycle-revision-20261020/base-build';base=out.parent/(out.name+'-base-build')
    inputs={}
    for role in load(parent/'build.json')['inputs']:
        model=load(parent/role/'model.json');inputs[role]={'jar':str(parent/role/'original.jar'),'targets':[o+'.'+c['fields'][0]['name'] for o,c in model['classes'].items() if c['fields']]}
    build(base,inputs)
    qs=[q for q in load(HERE/'capability-comparison-62-20261020.json')['queries'] if q['role'] in ('station','route') and ('Batch' in q['entry'] or 'getRouteByStartAndTerminal' in q['entry'])]
    progress=[]
    for mode in ('full','selective'):
        for q in qs:
            dest=out/(mode+'-'+q['id']);dest.mkdir();save(dest/'query.json',q)
            p=plan_response(load(base/q['role']/'model.json'),q['entry'],q['target'],q['path'],execution_kernel=True,application_calls=True);old.query_build(dest/'build',base,q,p)
            try:
                pilot.capture(dest/'capture',dest/'build',q,mode);result=pilot.evaluate(dest/'capture',dest/'build',q)
                assert result['exact']==result['targets'] and result['fp']==result['fn']==result['unknown']==0
                progress.append({k:v for k,v in result.items() if k!='answers'});print(progress[-1],flush=True)
            except Exception as e:save(dest/'failure.json',{'error':str(e),'traceback':traceback.format_exc()});raise
            finally:save(out/'progress.json',progress)
    save(out/'results.json',{'complete':True,'queries':4,'results':progress,'scope':'Original app v2 regression, no new query families or performance','unexamined_candidates':29})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=Path);a=p.parse_args();run(a.out.resolve())
