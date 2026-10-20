#!/usr/bin/env python3
"""Reject missing or contradictory proof on an actual original Cart capture."""
import argparse,copy,json
from pathlib import Path
from run_planned_service import load,save
from infer_distributed_fields import Reconstruction


def run(dest):
    capture=dest/'capture';build=dest/'build';q=load(dest/'query.json');case=next(c for c in load(capture/'run.json')['cases'] if c['response'])
    roles=load(capture/'run.json')['roles'];raw={r:[json.loads(x) for x in (capture/r/'events.jsonl').read_text().splitlines()] for r in roles}
    frame=next(r['frame'] for r in raw['carts'] if r['kind']=='binding-return' and r.get('message')==case['message']);path='/0/quantity'
    baseline=Reconstruction(build,capture,roles);assert baseline.query(case['message'],path,'carts',boundary=[{'kind':'binding-source'}])['known']
    result={}
    for fault in ('missing-runtime','missing-call-end','missing-call-summary','missing-source','wrong-source-owner','wrong-source-version','wrong-root-constructor-proof','wrong-selected-identity','duplicate-source'):
        bad=copy.deepcopy(raw);rows=bad['carts']
        kind={'missing-runtime':'binding-call-runtime','missing-call-end':'binding-call-exit','missing-call-summary':'binding-call-summary','missing-source':'binding-source'}.get(fault)
        if kind:
            at=next(i for i,r in enumerate(rows) if r['kind']==kind and (kind=='binding-call-runtime' or r.get('frame')==frame));rows.pop(at)
        elif fault.startswith('wrong-source-'):
            r=next(r for r in rows if r['kind']=='binding-source' and r['frame']==frame)
            for f in r['fields']:
                if fault=='wrong-source-owner':f['owner']='same-valued-other-owner'
                else:f['version']+=1
        elif fault=='wrong-root-constructor-proof':next(r for r in rows if r['kind']=='binding-call-summary' and r['frame']==frame)['root_effects_verified']=False
        elif fault=='wrong-selected-identity':next(r for r in rows if r['kind']=='binding-call-exit' and r['mode']=='stream-first' and r['frame']==frame)['detail']['selected_object']='same-valued-other-instance'
        else:
            at=next(i for i,r in enumerate(rows) if r['kind']=='binding-source' and r['frame']==frame);rows.insert(at+1,copy.deepcopy(rows[at]))
        for seq,r in enumerate(rows,1):r['seq']=seq
        try:
            g=Reconstruction(build,capture,roles,decoded_rows=bad);a=g.query(case['message'],path,'carts',boundary=[{'kind':'binding-source'}]);assert not a['known'],fault
            result[fault]='unknown'
        except ValueError as e:result[fault]='evidence-invalid: '+str(e)
    save(dest/'fault-audit.json',{'all_passed':True,'controls':result,'actual_original_business_capture':True});print(result,flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--query',type=Path,required=True);a=p.parse_args();run(a.query.resolve())
