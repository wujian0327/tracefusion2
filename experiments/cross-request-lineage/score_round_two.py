#!/usr/bin/env python3
"""Independent truth/scoring side. No inference code is imported."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


def load(p):return json.loads(p.read_text())
def rows(p):return [json.loads(l)for l in p.read_text().splitlines()]
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def msg(parent):return '/'.join(parent.split('-')[1:3])


def sources(origins,events,requests):
    mapping={msg(r['traceparent']):i+1 for i,r in enumerate(requests)};by_seq={r['seq']:r for r in events};answer=[]
    for origin in origins:
        assert len(origin)==3 and origin[0]=='http','A method/cache boundary became a source'
        _,seq,path=origin;row=by_seq[seq]
        assert row['kind']=='http-json'and row['direction']=='request'and row['phase']=='read','Source is not external HTTP'
        assert any(f['path']==path for f in row['fields'])
        answer.append([mapping[row['message']],path])
    return sorted(answer,key=str)


def score(home,predictions,out):
    out.mkdir(parents=True,exist_ok=False);freeze=load(home/'freeze.json');expected_path=home/'expected-round-two.json'
    assert hashlib.sha256(expected_path.read_bytes()).hexdigest()==freeze['expected_sha256']
    expected={c['id']:c for c in load(expected_path)['cases']};scored=[];physical=[]
    workload={c['id']:c for c in load(home/'workload.json')['cases']}
    for mode in ('tracefusion','mirrortaint'):
        for cap in sorted((home/'captures'/mode).glob('*/*')):
            e=expected[cap.name];run=load(cap/'run.json');plain=load(home/'captures/plain'/cap.parent.name/cap.name/'run.json')
            business=run['business_completed']and plain['business_completed']and run['state']==plain['state']==e['state']and [r['response']for r in run['requests']]==[r['response']for r in plain['requests']]
            audit=rows(cap/'B/http.jsonl');calls=[r for r in audit if r['path']=='/call']
            assert len(calls)==len(run['requests'])and len({r['pid']for r in calls})==len({r['thread']for r in calls})==1
            assert len({r['traceparent'].split('-')[1]for r in calls})==len(calls)
            assert all(r['status']==200 and not r.get('exception')for r in calls)
            prediction=load(predictions/mode/cap.parent.name/cap.name/'prediction.json')
            if mode=='tracefusion':
                events=rows(cap/'B/events.jsonl');by_seq={r['seq']:r for r in events};result=prediction.get('result',{})
                hist=result.get('session_history',{});writes=[r for r in events if r['kind']=='write'and r.get('field')=='lineage/business/Cache$Cell.text']
                relation=len(writes)<2 or (writes[0]['owner']==writes[1]['owner'])==(e['object_relation']=='same')
                write_versions=[r['version']for r in writes]==e['write_versions']
                namespace=hist.get('namespace');assert namespace==[events[0]['capture_session'],events[0]['process_instance']]
                all_writes=[r for r in events if r['kind']=='write']
                assert {r['seq']for r in all_writes}=={v['write_seq']for v in hist['versions']},'Captured write not represented in history'
                for b in hist['bindings']:
                    s=by_seq[b['source_seq']];assert b['namespace']==namespace and b['source_path']in [f['path']for f in s['fields']]
                canonical={}
                for b in hist['bindings']:
                    key=(b['source_seq'],b['source_path']);canonical.setdefault(tuple(b['coordinate']),set()).add(key)
                assert all(len(v)==1 for v in canonical.values()),'Repeated observation reset source identity'
                assert all(all(v in (0,None)for v in r['monitor'].values())for r in events if r['kind']=='session-request-cleanup'), 'Same-worker monitor state leaked'
                # Real wire bytes authenticate the external field observations independently.
                wire={msg(r['traceparent']):r for r in calls}
                for r in events:
                    if r['kind']!='http-json':continue
                    raw=wire[r['message']]['request_utf8'if r['phase']=='read'else'response_utf8']
                    assert hashlib.sha256(raw.encode()).hexdigest()==r['wire_sha256']
                    body=json.loads(raw)
                    assert all(body[f['path'][1:]]==f['observed']['value']for f in r['fields'])
                physical.append({'case':cap.name,'repeat':cap.parent.name,'object_relation':relation,'write_versions':write_versions,'writes':writes,'namespace':namespace})
            else:
                native=prediction['events'];labels={t:[i+1,s['path']]for i,r in enumerate(run['requests'])for s in native if s['kind']=='source'and s['message']==r['traceparent']for t in s['native_ids']}
                assert sum(r['kind']=='startup'for r in native)==1
                assert len(labels)==2*len(run['requests']),'Native source granularity differs'
            for checkpoint in e['read_checkpoints']:
                index=checkpoint['request']-1;message=msg(run['requests'][index]['traceparent']);r={'mode':mode,'repeat':cap.parent.name,'case':cap.name,'request':index+1,'sixth_full_evidence':e['sixth_full_evidence_control'],'expected_source':checkpoint['source'],'business_equal':business}
                if mode=='tracefusion':
                    returns=[v for v in events if v['kind']=='binding-return'and v.get('message')==message and v.get('fields')]
                    assert len(returns)==1;ret=returns[0];answers=[a for a in result.get('answers',[])if a['seq']==ret['seq']and a['path']=='/text']
                    if len(answers)!=1:r.update(source_status='unknown',version_status='unknown',reason=prediction.get('error','No query result'))
                    else:
                        a=answers[0];actual=sources(a['origins'],events,run['requests']);r.update(known=a['known'],actual_source=actual,source_status=('correct'if actual==checkpoint['source']else'wrong')if a['known']else'unknown',target=a)
                        reads=[v for v in events if v['kind']=='read'and v.get('frame')==a['root_frame']and v.get('field')=='lineage/business/Cache$Cell.text']
                        slot_reads=[v for v in events if v['kind']=='read'and v.get('frame')==a['root_frame']and v.get('field')=='lineage/business/Cache.cell']
                        key_reads=[v for v in events if v['kind']=='read'and v.get('frame')==a['root_frame']and v.get('field')=='lineage/business/Cache.key']
                        # Existing frozen business semantics: op=1 replaces key/cell.
                        slot_version=sum(v['op']==1 for v in workload[cap.name]['requests'][:index+1])
                        slot_ok=bool(slot_reads)and all(v['version']==slot_version for v in slot_reads+key_reads)
                        if reads:slot_ok&=all(v['observed']['object']==reads[0]['owner']for v in slot_reads)
                        expected_v=checkpoint['cell_text_version'];read_version=(len(reads)==1 and reads[0]['version']==expected_v)if checkpoint['output_reads_cache_text']else not reads
                        rooted=[v for v in result['roots']if v['frame']==a['root_frame']];normal=len(rooted)==1 and rooted[0]['completion']=='normal'
                        r.update(version_status='correct'if read_version and slot_ok and write_versions and relation and normal else'wrong',normal_completion=normal,actual_reads=reads,
                                 cache_cell_reference_reads=slot_reads,cache_key_reads=key_reads,expected_cache_reference_version=slot_version)
                        if reads:
                            assert any(h['read_seq']==reads[0]['seq']and h['write_seq']in {v['seq']for v in writes}for h in hist['reads']),'Read has no exact history write witness'
                        cache=[v for v in hist['versions']if v['coordinate'][1]=='lineage/business/Cache$Cell.text'and v['coordinate'][2]==checkpoint['cache_text_version']]
                        if cap.name=='public-constant'and index>0:
                            prior=[v for v in hist['versions']if v['coordinate'][1]=='lineage/business/Cache$Cell.text'and v['coordinate'][2]==1]
                            r['constant_precondition_verified']=len(prior)==1 and prior[0]['known']and sources(prior[0]['origins'],events,run['requests'])==[[1,'/value']]
                            assert r['constant_precondition_verified']and a['known']and actual==[]
                        if cap.name=='miss-fallback'and index>0:
                            r['miss_cache_unchanged']=len(writes)==1 and len(cache)==1 and cache[0]['known']and sources(cache[0]['origins'],events,run['requests'])==[[1,'/value']]
                            assert r['miss_cache_unchanged']
                else:
                    sink=[v for v in native if v['kind']=='sink'and v['message']==run['requests'][index]['traceparent']]
                    assert len(sink)==1;actual=sorted([labels.get(v,['unmapped',v])for v in sink[0]['native_ids']],key=str)
                    r.update(source_status='correct'if actual==checkpoint['source']else'wrong',actual_source=actual,version_status='N/A',offline_missing_evidence='N/A')
                scored.append(r)
    summary={m:{'source':dict(Counter(r['source_status']for r in scored if r['mode']==m)), 'version':dict(Counter(r['version_status']for r in scored if r['mode']==m))}for m in ('tracefusion','mirrortaint')}
    final={m:[r for r in scored if r['mode']==m and r['request']==len(expected[r['case']]['read_checkpoints'])]for m in ('tracefusion','mirrortaint')}
    save(out/'score.json',{'summary':summary,'rows':scored,'final_queries':final,'physical':physical})
    print(json.dumps(summary))
    assert all(r['business_equal']and r['source_status']=='correct'and r['version_status']in ('correct','N/A')for r in scored),'Positive gate did not pass'


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--predictions',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();score(a.run.resolve(),a.predictions.resolve(),a.out.resolve())
