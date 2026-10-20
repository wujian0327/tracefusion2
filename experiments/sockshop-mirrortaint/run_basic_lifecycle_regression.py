#!/usr/bin/env python3
"""Replay the two formerly invalid Basic batches with interleaved normal calls."""
import argparse,json
from pathlib import Path
import run_response_binding_revision as old
from run_planned_service import ROOT,load,save
from plan_response_binding import plan_response


def run(out,base):
    out.mkdir();raw=load(ROOT/'experiments/sockshop-mirrortaint/sockshop-model-heldout-20261020.json')
    def queries(x):
        if isinstance(x,dict):
            if 'id' in x and 'entry' in x:yield x
            else:
                for v in x.values():yield from queries(v)
        elif isinstance(x,list):
            for v in x:yield from queries(v)
    selected=[q for q in queries(raw) if q['id'] in ('trainticket-basic-queryForTravel-data-trainType-id','trainticket-basic-queryForTravel-data-trainType-averageSpeed')]
    assert len(selected)==2
    results=[]
    for q in selected:
        d=out/q['id'];d.mkdir();p=plan_response(load(base/'basic/model.json'),q['entry'],q['target'],q['path'],read_forward_contracts=True);p['source_evidence']=True
        b=d/'build';old.query_build(b,base,q,p);cap=d/'capture';cap.mkdir()
        old.capture_train(cap,b,q,201020,mixed_lifecycle=True)
        r=old.evaluate(cap,b,q);assert r['evidence_invalid']==0 and r['oracle_unavailable']==0,r
        assert r['target_instances']==15 and r['N/A_requests']==1,r
        rows=[json.loads(l) for l in (cap/'basic/events.jsonl').read_text().splitlines()]
        summaries=[r for r in rows if r['kind']=='binding-call-summary'];throws=[r for r in rows if r['kind']=='binding-call-throw']
        assert len(summaries)==16 and all(r['unpaired']==0 for r in summaries) and sum(r['completion']=='exceptional' for r in summaries)==1
        assert any(r['case']=='following-normal-7' and r['status']!='evidence-invalid' for r in r['predictions'])
        results.append({**{k:v for k,v in r.items() if k!='predictions'},'root_summaries':len(summaries),'exceptional_invocations':len(throws),'aborted_roots':1})
        save(out/'results.json',{'all_passed':True,'old_first_results_unchanged':'Two failed batches / 14 invalid targets at c3e6739','mixed_development_regressions':results})
        print(results[-1],flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);p.add_argument('--base',type=Path,required=True);a=p.parse_args();run(a.out.resolve(),a.base.resolve())
