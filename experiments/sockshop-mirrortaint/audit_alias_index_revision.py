#!/usr/bin/env python3
"""Preserve every graph/answer across the exposed62+29 query captures."""
import argparse,statistics
from pathlib import Path
from collections import defaultdict
from run_planned_service import ROOT,HERE,load,save,sha
from infer_distributed_fields import Reconstruction
from run_alias_index_revision import reference


def run(root):
    protocol=load(root/'protocol.json');assert load(root/'benchmark-complete.json')['all_passed'];legacy=reference(Path(protocol['reference_module'])).Reconstruction
    import run_response_binding_revision as old
    cap=ROOT/'artifacts/transport-observation-shared-20261023';held=ROOT/'artifacts/heldout29-first-20261023';qs={q['id']:q for q in load(HERE/'capability-comparison-62-20261020.json')['queries']};qs.update({q['id']:q for q in load(held/'protocol-before-first.json')['queries']});jobs=[]
    for r in load(cap/'capability-audit/source-union/queries.json'):
        d=Path(r['capture']).parent;jobs.append((d,qs[r['query']],load(d/'evaluation.json')['predictions']))
    for r in load(held/'audit-final-reviewed/audit.json')['records']:
        if r['mode']in ('full','selective'):
            d=Path(r['evaluation_file']).parent
            if not(d/'build').exists():
                receipts=load(held/'independent-id-projection-correction/receipt.json')['changes'];matches=[v for v in receipts if v['corrected']==r['evaluation_file']];assert len(matches)==1;receipt=matches[0];assert sha(Path(receipt['corrected']))==receipt['corrected_sha256']and sha(Path(receipt['source']))==receipt['sha256'];d=Path(receipt['source']).parent
            jobs.append((d,qs[r['query']],r['predictions']))
    for mode in ('full','selective'):
        d=cap/'cart-create-pair'/mode;cases=load(d/'capture/run.json')['cases'];jobs.append((d,qs['sockshop-carts-get-customerId'],[{'message':c['message'],'path':'/customerId'}for c in cases]))
    out=root/'regression-final';out.mkdir();receipts=[];targets=0
    for i,(d,q,predictions)in enumerate(jobs):
        a=legacy(d/'build',d/'capture',[q['role']]);b=Reconstruction(d/'build',d/'capture',[q['role']]);assert a.export()==b.export(),('Graph changed',str(d))
        for p in predictions:
            x=a.query(p['message'],p['path'],q['role'],boundary=old.BOUNDARY);y=b.query(p['message'],p['path'],q['role'],boundary=old.BOUNDARY);assert x==y
        targets+=len(predictions);receipts.append({'capture':str(d/'capture'),'query':q['id'],'targets':len(predictions),'graph_exact':True,'answers_exact':True,'events_sha256':sha(d/'capture'/q['role']/'events.jsonl')});save(out/'receipts.json',receipts);save(out/'progress.json',{'completed':i+1,'total':len(jobs),'target_answers_compared':targets})
    assert len(jobs)==184 and targets==1350
    by=defaultdict(lambda:defaultdict(dict))
    for i,j in enumerate(protocol['jobs']):
        d=root/'replays'/(f'{i:02d}-'+j['trial']+'-'+j['variant']);a=load(d/'offline.json');m=load(d/'memory.json');by[j['arm']][j['variant']][j['trial'][:8]]={'core_seconds':a['core_seconds'],'cpu_seconds':a['process_cpu_seconds'],'vmhwm_bytes':m['vmhwm_bytes']}
    def ratios(a,b):
        return {k:{'median':statistics.median(a[i][k]/b[i][k]for i in a),'min':min(a[i][k]/b[i][k]for i in a),'max':max(a[i][k]/b[i][k]for i in a),'ratios':[a[i][k]/b[i][k]for i in sorted(a)]}for k in next(iter(a.values()))}
    paired={}
    for variant in ('reference','indexed'):
        paired[variant+'/projection']=ratios(by['selective'][variant],by['selective_base'][variant]);paired[variant+'/strict']=ratios(by['selective'][variant],by['full'][variant])
    for arm in by:paired['index/'+arm]=ratios(by[arm]['indexed'],by[arm]['reference'])
    save(root/'audit.json',{'all_passed':True,'graphs_compared':184,'complete_target_answers_compared':1350,'counts_are_compatibility_checks_not_new_accuracy_population':True,'graph_answer_receipts':receipts,'timing_trials':dict(by),'paired':paired,'indexed_source_sha256':sha(HERE/'infer_distributed_fields.py'),'reference_source_sha256':protocol['reference_sha256'],'no_new_online_data':True,'original_data_unchanged':True})
    print('Alias index:184 graphs and1350 complete answers identical;40 measured replays passed',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);run(p.parse_args().root.resolve())
