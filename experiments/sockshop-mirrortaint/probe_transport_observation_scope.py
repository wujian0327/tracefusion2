#!/usr/bin/env python3
"""Feasibility only: omit unused server-response request-serialization proofs.

No collector or frozen capture is changed; this is not an online experiment,
nor does it establish instruction/call-site slicing or a performance benefit.
"""
import argparse,json,traceback
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save,sha
from infer_distributed_fields import Reconstruction
from infer_response_binding import matches
import run_response_binding_revision as old


def probe(root,out):
    out.mkdir(parents=True,exist_ok=False);results=[];summary={'captures':0,'targets':0,'equal_answers':0,'differences':0,'skipped_no_binding':0,'failures':0}
    for f in sorted(root.glob('all62-*/*/evaluation.json'))+sorted((root/'cart-create-pair').glob('*/evaluation.json')):
        d=f.parent;build=d/'build';cap=d/'capture';ev=load(f)
        if not build.exists() or not cap.exists():
            results.append({'capture':str(d),'skipped':'Nonstandard supplemental layout; not counted as full431 acceptance'});continue
        role=next(k for k in load(build/'build.json')['inputs']if (cap/k/'events.jsonl').exists())
        plan=load(build/role/'plan.json');pattern=plan.get('response_binding',{}).get('path');summary['captures']+=1
        r={'capture':str(d),'query':ev.get('query'),'mode':ev.get('mode'),'pattern':pattern,'source_sha256':sha(cap/role/'events.jsonl')}
        if not pattern:summary['skipped_no_binding']+=1;r['unchanged']='No response binding: conservative retain all output fields';results.append(r);continue
        try:
            rows=[json.loads(line)for line in (cap/role/'events.jsonl').read_text().splitlines()];returns={v.get('message')for v in rows if v['kind']=='binding-return'};projected=[];removed=0;before=after=0
            for row in rows:
                n=row
                if row['kind']=='http-json'and row['direction']=='response'and row['phase']=='write'and row['message']in returns:
                    n=dict(row); removed+=int('request_serialization' in n);n.pop('request_serialization',None)
                before+=len(json.dumps(row,separators=(',',':')).encode());after+=len(json.dumps(n,separators=(',',':')).encode());projected.append(n)
            a=Reconstruction(build,cap,[role],decoded_rows={role:rows});b=Reconstruction(build,cap,[role],decoded_rows={role:projected});checks=[]
            for c in load(cap/'run.json')['cases']:
                leaves=old.leaves(c['response'],pattern)if 200<=c['http_status']<300 else []
                for path,value in leaves:
                    x=a.query(c['message'],path,role,boundary=old.BOUNDARY);y=b.query(c['message'],path,role,boundary=old.BOUNDARY);same=x==y;summary['targets']+=1;summary['equal_answers']+=same;summary['differences']+=not same;checks.append({'case':c['case'],'path':path,'same_full_answer_including_physical_sources':same,'known':x['known']})
            r.update(removed_response_request_proofs=removed,compact_json_comparison_before=before,compact_json_comparison_after=after,raw_bytes_claim=False,checks=checks)
        except Exception as e:summary['failures']+=1;r.update(failure=str(e),traceback=traceback.format_exc())
        results.append(r);save(out/'probe.json',{'complete':False,'summary':summary,'results':results});print({k:v for k,v in r.items()if k in ('query','mode','failure','removed_response_request_proofs')},flush=True)
    save(out/'probe.json',{'complete':True,'scope':'In-memory derived omission of request-only proofs on bound server responses, all runtime/identity/effect evidence retained. No collector changed, no online cost claim. Compact JSON byte estimates exclude original spacing and must not be called measured log savings.','summary':summary,'results':results})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();probe(a.root.resolve(),a.out.resolve())
