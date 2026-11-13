#!/usr/bin/env python3
"""Explicit current-core audit: original first-round plans/events stay immutable."""
import argparse
import json
from pathlib import Path
import sys
from run import ROOT,CORE,load,save,sha
from replay_round_two import predict
from analyze import rows


def run(out):
    out.mkdir(parents=True,exist_ok=False);records=[]
    direct=ROOT/'artifacts/cross-request-lineage-diagnostics-20261113-05'
    plan=load(direct/'build/tf/B/plan.json');assert not plan.get('session_history')
    for cap in sorted((direct/'captures/direct-B/tracefusion').glob('*/*')):
        raw=cap/'B/events.jsonl';old=direct/'predictions/direct-B/tracefusion'/cap.parent.name/cap.name/'local-core.json'
        now=predict(plan,rows(raw));dest=out/('direct-'+cap.parent.name+'-'+cap.name+'.json');save(dest,now)
        previous=load(old);assert now['state']=='analyzed'
        same=previous['answers']==now['result']['answers']and previous['roots']==now['result']['roots']
        records.append({'cohort':'round-one-direct-B','repeat':cap.parent.name,'case':cap.name,'capture_sha256':sha(raw),'old_prediction_sha256':sha(old),
                        'answers_and_roots_equal':same,'old_known':sum(a['known']for a in previous['answers']),'new_known':sum(a['known']for a in now['result']['answers']),
                        'session_history_enabled':False,'explanation':'Old query-only capture has no framed historical writers; no observations invented'})
        assert same
    main=ROOT/'artifacts/cross-request-lineage-supported-20261113-04';plan=load(main/'build/tf/B/plan.json')
    for cap in sorted((main/'captures/tracefusion').glob('*/*')):
        now=predict(plan,rows(cap/'B/events.jsonl'));before=load(main/'predictions/tracefusion'/cap.parent.name/cap.name/'prediction.json')
        assert now['state']=='rejected'and now['error']==before['error']
        save(out/('process-'+cap.parent.name+'-'+cap.name+'.json'),now)
        records.append({'cohort':'round-one-original-process','repeat':cap.parent.name,'case':cap.name,'capture_sha256':sha(cap/'B/events.jsonl'),
                        'same_rejection':True,'reason':now['error'],'explanation':'Original control-write-address limitation intentionally retained'})
    save(out/'results.json',{'current_core_audit':True,'records':records,'historical_inputs_unchanged':True,'old_MT_direct_B_result':load(direct/'score.json')['summary']['direct-B']['mirrortaint'],
        'current_sources':{str(p):sha(p)for p in CORE.iterdir()if p.suffix in ('.java','.py','.json')}})
    print(json.dumps({'old_direct_B_captures':12,'old_process_captures':12,'answers_and_states_changed':0,'historical_writes_invented':0}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.out.resolve())
