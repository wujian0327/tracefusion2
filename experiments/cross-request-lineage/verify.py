#!/usr/bin/env python3
"""Check raw execution, actual wire pairings and saved first predictions."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


def load(p):return json.loads(p.read_text())
def rows(p):return [json.loads(l) for l in p.read_text().splitlines()]
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def msg(header):
    p=header.split('-');return p[1]+'/'+p[2]


def verify(run):
    freeze=load(run/'freeze.json');score=load(run/'score.json');checks=[]
    assert digest(run/'expected.json')==freeze['expected_sha256']
    assert digest(run/'workload.json')==freeze['workload_sha256']
    index=load(run/'files.sha256.json')
    assert all(digest(run/p)==h for p,h in index.items()),'Artifact integrity mismatch'
    for mode in ('plain','tracefusion','mirrortaint'):
        for cap in sorted((run/'captures'/mode).glob('*/*')):
            receipt=load(cap/'run.json');assert receipt['business_completed']
            ah=[r for r in rows(cap/'A/http.jsonl') if r['path']=='/call']
            bh=[r for r in rows(cap/'B/http.jsonl') if r['path']=='/call']
            assert len(ah)==len(bh)==len(receipt['requests'])
            assert len({r['pid'] for r in ah})==len({r['pid'] for r in bh})==1
            assert len({r['thread'] for r in ah})==len({r['thread'] for r in bh})==1
            assert ah[0]['pid']!=bh[0]['pid'],'Services must use separate JVMs'
            assert len({r['traceparent'].split('-')[1] for r in ah})==len(ah),'Requests reused a trace ID'
            assert not any(r.get('exception') for r in ah+bh)
            # Pair only by the actual sent/received header; compare payloads AFTER pairing.
            by_header={r['traceparent']:r for r in bh};assert len(by_header)==len(bh)
            assert len({r['rpc_traceparent'] for r in ah})==len(ah)
            assert {r['rpc_traceparent'] for r in ah}==set(by_header)
            for a in ah:
                b=by_header[a['rpc_traceparent']]
                assert a['rpc_request_utf8']==b['request_utf8']
                assert a['rpc_response_utf8']==b['response_utf8']
                assert a['rpc_status']==b['status']==a['status']==200
            if mode=='tracefusion':
                event={r:rows(cap/r/'events.jsonl') for r in ('A','B')}
                assert not any(x['kind']=='problem' for rs in event.values() for x in rs)
                assert all(sum(x['kind']=='metrics' for x in rs)==1 for rs in event.values())
                # Every raw codec snapshot must have a matching actual HTTP payload hash.
                expected={}
                for a in ah:
                    expected[('A',msg(a['traceparent']),'request','read')]=a['request_utf8']
                    expected[('A',msg(a['traceparent']),'response','write')]=a['response_utf8']
                    expected[('A',msg(a['rpc_traceparent']),'request','write')]=a['rpc_request_utf8']
                    expected[('A',msg(a['rpc_traceparent']),'response','read')]=a['rpc_response_utf8']
                for b in bh:
                    expected[('B',msg(b['traceparent']),'request','read')]=b['request_utf8']
                    expected[('B',msg(b['traceparent']),'response','write')]=b['response_utf8']
                seen=set()
                for role,rs in event.items():
                    for x in rs:
                        if x['kind']!='http-json':continue
                        key=(role,x['message'],x['direction'],x['phase']);assert key not in seen;seen.add(key)
                        raw=expected[key]
                        assert hashlib.sha256(raw.encode()).hexdigest()==x['wire_sha256']
                        payload=json.loads(raw)
                        for f in x['fields']:
                            assert f['path'].count('/')==1,'Only flat JSON is in this fixture'
                            assert payload[f['path'][1:]]==f['observed']['value']
                assert seen==set(expected)
            if mode=='mirrortaint':
                for role in ('A','B'):
                    rs=rows(cap/role/'native.jsonl');assert sum(r['kind']=='startup' for r in rs)==1,'Native heap was restarted'
                sources=[r for r in rows(cap/'A/native.jsonl') if r['kind']=='source']
                assert len({x for r in sources for x in r['native_ids']})==2*len(ah),'External field/request source IDs collided'
            checks.append({'mode':mode,'repeat':cap.parent.name,'case':cap.name,'requests':len(ah),'wire_pairs':len(bh),'persistent_jvms':True})
    scored=score['rows'];assert all(r['business_equal'] and r['shared_process_verified'] for r in scored)
    assert all(r['version_witness_matches'] for r in scored if r['mode']=='tracefusion')
    assert all(r['source_api_verified'] for r in scored if r['mode']=='mirrortaint')
    statuses={}
    for row in scored:statuses.setdefault((row['mode'],row['case']),set()).add((row['source_status'],row.get('reason')))
    assert all(len(v)==1 for v in statuses.values()),'Repeated source results differ'
    result={'verified':True,'checks':checks,'business_configurations':len(checks),'requests':sum(c['requests'] for c in checks),
            'same_result_across_repetitions':True,'cross_jvm_id_comparisons':0,'pairing':'actual sent/received traceparent; payload equality checks only after pairing'}
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=False)
    result=verify(a.run.resolve());(a.out/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='checks'}))
