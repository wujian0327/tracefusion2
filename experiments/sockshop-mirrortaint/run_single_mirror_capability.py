#!/usr/bin/env python3
"""Recalibrate one already sealed entry, preserving earlier native attempts."""
import argparse
import json
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save,sha
import run_response_binding_revision as old
from build_mirror_capability import configure
from run_mirror_read_capabilities import native_evaluate


def run(out,base,bundle,query_id):
    pool=load(HERE/'capability-comparison-62-20261020.json')['queries'];q=next(q for q in pool if q['id']==query_id);qs=[x for x in pool if x['entry']==q['entry']]
    out.mkdir(parents=True,exist_ok=False);capture=out/'capture';capture.mkdir();original=old.observed
    save(out/'protocol.json',{'queries':qs,'seed':20261020,'baseline_build_sha256':sha(bundle/'build.json'),'native_sha256':load(bundle/'build.json')['native_sha256'],'tf_changes':False,'reason':'Source-boundary immutable UUID uses native public tagManually; no target is tagged and no expected source is read by prediction. All creator ID parsing uses the fixed native source format, never value matching.'})
    def observed(spec,name,role,dest,bld):
        original(spec,name,role,dest,bld)
        if role==q['role']:configure(spec,dest,base,bundle,q)
    old.observed=observed
    try:old.capture_train(capture,base,q,20261020)
    finally:old.observed=original
    ev=native_evaluate(out,qs)
    print(json.dumps([{k:v for k,v in q.items() if k!='targets'}|{'targets':len(q['targets']),'known_correct':sum(t['state']=='known_correct' for t in q['targets']),'known_wrong':sum(t['state']=='known_wrong' for t in q['targets'])} for q in ev]),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('out','base','bundle'):p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--query-id',required=True);a=p.parse_args();run(a.out.resolve(),a.base.resolve(),a.bundle.resolve(),a.query_id)
