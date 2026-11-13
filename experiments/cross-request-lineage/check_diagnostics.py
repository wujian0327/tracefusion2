#!/usr/bin/env python3
"""Verify secondary profiles and independently delete necessary write evidence."""
import argparse
import copy
import json
from pathlib import Path
import sys
import traceback
from run import ROOT,CORE,load,save,sha
from analyze import rows


def run(home,out):
    out.mkdir(parents=True,exist_ok=False);results=load(home/'score.json')['rows'];facts=[]
    frozen=load(home/'freeze.json')
    assert sha(home/'expected.json')==frozen['expected_sha256']
    assert all(sha(ROOT/p)==h for p,h in frozen['core_sources'].items())
    assert all(sha(home/p)==h for p,h in load(home/'files.sha256.json').items())
    assert all(r['business_equal'] for r in results)
    for cap in sorted((home/'captures').glob('*/*/*/*')):
        profile,mode,repeat,cid=cap.relative_to(home/'captures').parts
        receipt=load(cap/'run.json');assert receipt['business_completed']
        bh=[r for r in rows(cap/'B/http.jsonl') if r['path']=='/call'];assert len(bh)==len(receipt['requests'])
        assert len({r['pid'] for r in bh})==len({r['thread'] for r in bh})==1
        assert len({r['traceparent'].split('-')[1] for r in bh})==len(bh)
        assert not any(r.get('exception') for r in bh)
        if profile=='read-only-network':
            ah=[r for r in rows(cap/'A/http.jsonl') if r['path']=='/call'];assert len(ah)==len(bh)
            by_header={r['traceparent']:r for r in bh}
            assert len({r['rpc_traceparent'] for r in ah})==len(ah) and {r['rpc_traceparent'] for r in ah}==set(by_header)
            for a in ah:
                b=by_header[a['rpc_traceparent']];assert a['rpc_request_utf8']==b['request_utf8'] and a['rpc_response_utf8']==b['response_utf8']
        else:assert not (cap/'A/http.jsonl').exists(),'Direct-B must not pretend to traverse A'
        if mode=='mirrortaint':
            source_role='B' if profile=='direct-B' else 'A'
            native=rows(cap/source_role/'native.jsonl')
            assert sum(r['kind']=='startup' for r in native)==1
            sources=[r for r in native if r['kind']=='source']
            assert len(sources)==2*len(bh) and all(r['native_ids'] for r in sources)
            assert len({x for r in sources for x in r['native_ids']})==2*len(bh),'External source IDs collided'
            if profile=='read-only-network':assert sum(r['kind']=='startup' for r in rows(cap/'B/native.jsonl'))==1
        facts.append({'profile':profile,'mode':mode,'repeat':repeat,'case':cid,'persistent_b_requests':len(bh)})
    repeated={}
    for r in results:repeated.setdefault((r['profile'],r['mode'],r['case']),set()).add((r['state'],json.dumps(r['actual'],sort_keys=True)))
    assert all(len(v)==1 for v in repeated.values())
    # No hand-generated provenance: corrupt only a saved copy of the real field write.
    sys.path.insert(0,str(CORE));from infer_execution_kernel import infer_execution
    negatives=[]
    for cap in sorted((home/'captures/direct-B/tracefusion').glob('*/missing-write')):
        rs=rows(cap/'B/events.jsonl');writes=[r for r in rs if r['kind']=='write' and r.get('field')=='lineage/business/Cache$Cell.text']
        if len(writes)<2:
            # Existing observer counts unframed writes but does not emit their values.
            # Do not fabricate the write that this diagnostic was meant to remove.
            saved=load(home/'predictions/direct-B/tracefusion'/cap.parent.name/'missing-write/prediction.json')
            assert saved['known'] is False
            negatives.append({'repeat':cap.parent.name,'state':'already_missing_write_evidence','reason':'No Cell.text write values outside configured query frames; core is already unknown','rejected':None,'guard_verified':False})
            continue
        removed=writes[1];bad=copy.deepcopy([r for r in rs if r['seq']!=removed['seq']])
        for i,r in enumerate(bad,1):r['seq']=i
        dest=out/('missing-write-'+cap.parent.name);dest.mkdir()
        (dest/'derived-events.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in bad));save(dest/'deletion.json',removed)
        try:infer_execution(load(home/'build/tf/B/plan.json'),bad)
        except Exception as e:
            n={'repeat':cap.parent.name,'removed_seq':removed['seq'],'rejected':True,'reason':str(e),'exception':type(e).__name__,'traceback':traceback.format_exc()}
        else:n={'repeat':cap.parent.name,'removed_seq':removed['seq'],'rejected':False}
        negatives.append(n);save(dest/'result.json',n)
    save(out/'verification.json',{'verified':True,'configurations':len(facts),'requests':sum(r['persistent_b_requests'] for r in facts),'repeat_results_identical':True,
         'facts':facts,'missing_write_controls':negatives,'primary_first_results_replaced':False})
    assert all(n['rejected'] is not False for n in negatives),'Necessary write deletion accepted'
    print(json.dumps({'configurations':len(facts),'requests':sum(r['persistent_b_requests'] for r in facts),'negative_reasons':[n['reason'] for n in negatives]}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.run.resolve(),a.out.resolve())
