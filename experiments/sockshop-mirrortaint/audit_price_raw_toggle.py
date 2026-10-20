#!/usr/bin/env python3
"""Raw-byte diagnostic independence on real five-service price captures."""
import argparse,copy,json
from pathlib import Path
from run_planned_service import load,save
from run_train_multisource import ROLES
from infer_distributed_fields import Reconstruction


def audit(root):
    results={}
    for mode in ('full','selective'):
        d=root/'price-raw-calibration'/mode;b=root/'price-raw-build';rows={r:[json.loads(l) for l in (d/r/'events.jsonl').read_text().splitlines()] for r in ROLES};count=sum(r['kind']=='http-source-fact' for rs in rows.values() for r in rs)
        assert count>0,'Raw toggle not exercised on actual RPC reads'
        stripped={r:[x for x in rs if x['kind']!='http-source-fact'] for r,rs in copy.deepcopy(rows).items()}
        for rs in stripped.values():
            for i,r in enumerate(rs,1):r['seq']=i
        g=Reconstruction(b,d,list(ROLES),decoded_rows=stripped);checked=0
        for pred in load(d/'predictions.json'):
            case=next(c for c in load(d/'run.json')['cases'] if c['case']==pred['case'])
            a=g.query(case['message'],'/data/prices/'+pred['key'],'basic',boundary=[{'service':r,'kind':'http-json','phase':'write','direction':'response'} for r in ('route','price')])
            actual=sorted((s['service'],s['message'],s['path'],s['owner'],s['field'],s['version']) for s in a['sources'])
            wanted=sorted((s['service'],s['message'],s['path'],s['owner'],s['field'],s['version']) for s in pred['answer']['sources'])
            assert a['known'] and actual==wanted;checked+=1
        faults={}
        for fault in ('missing-needed-source','ambiguous-rpc'):
            broken=copy.deepcopy(stripped)
            if fault=='missing-needed-source':
                broken['route']=[r for r in broken['route'] if not(r['kind']=='http-json' and r['direction']=='response' and r['phase']=='write')]
            else:
                rpc=next(r for r in broken['basic'] if r['kind']=='http-rpc-enter');broken['basic'].append(copy.deepcopy(rpc))
            for rs in broken.values():
                for i,r in enumerate(rs,1):r['seq']=i
            try:
                bad=Reconstruction(b,d,list(ROLES),decoded_rows=broken)
                first=next(p for p in load(d/'predictions.json') if p['expected']);c=next(c for c in load(d/'run.json')['cases'] if c['case']==first['case'])
                assert not bad.query(c['message'],'/data/prices/'+first['key'],'basic',boundary=[{'service':r,'kind':'http-json','phase':'write','direction':'response'} for r in ('route','price')])['known']
            except ValueError:pass
            faults[fault]='refused or unknown'
        off=load(root/'price-business'/mode/'evaluation.json');on=load(d/'evaluation.json')
        assert all(off[k]==on[k] for k in ('queries','exact','tp','fp','fn','unknown'))
        results[mode]={'raw_http_source_facts':count,'identical_known_answers_after_fact_removal':checked,'raw_on_off_independent_correctness':{k:on[k] for k in ('queries','exact','tp','fp','fn','unknown')},'mandatory_fault_checks':faults}
    save(root/'price-raw-toggle-audit.json',{'all_passed':True,'results':results,'primary_configuration':'source_evidence off; required HTTP/JSON fields and all computation checks remain on','scope':'Diagnostic independence, not a raw-on/raw-off performance comparison'})
    print('Price raw toggle audit passed',flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);audit(p.parse_args().root.resolve())
