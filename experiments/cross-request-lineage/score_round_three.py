#!/usr/bin/env python3
"""Independent source/version/behavior scorer. No analyzer imports."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from score_round_two import load,rows,save,msg,sources


def project(query,requests,mirror=False):
    mapping={r['traceparent']if mirror else msg(r['traceparent']):i+1 for i,r in enumerate(requests)};answer=[]
    for s in query['sources']:
        assert s.get('role'if mirror else'service')=='A'and s['direction']=='request'and s['phase']=='read','Intermediate dependency reported as external source'
        answer.append([mapping[s['message']],s['path']])
    return sorted(answer,key=str)


def score(home,predictions,out,allow_wrong=False):
    out.mkdir(parents=True,exist_ok=False);e=load(home/'expected-round-three.json');assert hashlib.sha256((home/'expected-round-three.json').read_bytes()).hexdigest()==load(home/'freeze.json')['expected_sha256']
    expected={c['id']:c for c in e['cases']};work={c['id']:c for c in load(home/'workload.json')['cases']};seeded=load(home/'expected-round-three-seeded-calibration.json');assert hashlib.sha256((home/'expected-round-three-seeded-calibration.json').read_bytes()).hexdigest()==load(home/'freeze.json')['seeded_expected_sha256'];work[seeded['id']]=seeded;scored=[];physical=[]
    for mode in ('tracefusion','mirror-online','mirror-composed'):
        for cap in sorted((home/'captures'/mode).glob('*/*')):
            unseeded=cap.name==e['calibration']['id'];calibration=unseeded or cap.name==seeded['id'];case=e['calibration']if unseeded else seeded if calibration else expected[cap.name];run=load(cap/'run.json');plain=load(home/'captures/plain'/cap.parent.name/cap.name/'run.json');p=load(predictions/mode/cap.parent.name/cap.name/'prediction.json')
            business=run['business_completed']and run['state']==plain['state']==case['state']and [r['response']for r in run['requests']]==[r['response']for r in plain['requests']]
            calls={r:[v for v in rows(cap/r/'http.jsonl')if v['path']=='/call']for r in ('A','B')}
            for role,rs in calls.items():
                assert len(rs)==len(run['requests'])and len({v['pid']for v in rs})==len({v['thread']for v in rs})==1
                assert all(v['status']==200 and not v.get('exception')for v in rs)
            assert len({v['pid']for rs in calls.values()for v in rs})==2
            for a,b in zip(calls['A'],calls['B']):
                assert a['rpc_traceparent']==b['traceparent']and a['rpc_connection']==b['connection']
                assert a['rpc_request_utf8']==b['request_utf8']and a['rpc_response_utf8']==b['response_utf8']
            if calibration:
                assert len({r['traceparent'].split('-')[1]for r in run['requests']})==1
                assert len({r['rpc_traceparent'].split('-')[2]for r in calls['A']})==2
                assert len({tuple(r['rpc_connection'])for r in calls['A']})==2
            if mode=='tracefusion'and p['state']=='analyzed':
                events=rows(cap/'B/events.jsonl');result=p['local_results']['B'];hist=result['session_history'];writes=[r for r in events if r['kind']=='write'and r.get('field')=='lineage/business/Cache$Cell.text']
                assert hist['version']==2 and hist['origin_scope']=='service-local-http-intermediate-dependency'
                assert {r['seq']for r in events if r['kind']=='write'}=={v['write_seq']for v in hist['versions']}
                for role in ('A','B'):
                    ev=rows(cap/role/'events.jsonl');assert sum(r['kind']=='session-request-cleanup'for r in ev)==len(run['requests'])
                    assert all(all(v in (0,None)for v in r['monitor'].values())for r in ev if r['kind']=='session-request-cleanup')
                assert len(p['graph']['http_exchange_links'])==len(run['requests'])*5
                relation=unseeded or len(writes)<2 or (writes[0]['owner']==writes[1]['owner'])==(case['object_relation']=='same')
                write_versions=not writes if unseeded else [r['version']for r in writes]==case['write_versions']
                physical.append({'repeat':cap.parent.name,'case':cap.name,'object_relation':relation,'write_versions':write_versions,'history_namespace':hist['namespace'],'exchange_links':len(p['graph']['http_exchange_links'])})
            for index,request in enumerate(run['requests']):
                truth=case['expected_sources'][index]if calibration else case['read_checkpoints'][index]['source'];row={'mode':mode,'repeat':cap.parent.name,'case':cap.name,'request':index+1,'calibration':calibration,'sixth_full_evidence':not calibration and case['sixth_full_evidence_control'],'expected_source':truth,'business_equal':business}
                if mode=='mirror-online':
                    sinks=[r for r in p['native']['A']if r['kind']=='sink'and r['message']==request['traceparent']];assert len(sinks)==1
                    row.update(source_status='unconnected_online',version_status='N/A',native_ids=sinks[0]['native_ids'],reason='Raw online labels do not implement paper IV-E composition')
                elif mode=='mirror-composed':
                    qs=[q for q in p.get('queries',[])if q['message']==request['traceparent']]
                    if len(qs)!=1:row.update(source_status='unknown',version_status='N/A',reason=p.get('reason','Native local relation unavailable'))
                    else:
                        q=qs[0];actual=project(q,run['requests'],True);row.update(known=q['known'],actual_source=actual,source_status=('correct'if actual==truth else'wrong')if q['known']else'unknown',version_status='N/A')
                else:
                    qs=[q for q in p.get('queries',[])if q['target']['message']==msg(request['traceparent'])]
                    if len(qs)!=1:row.update(source_status='unknown',version_status='unknown',reason=p.get('error','Distributed query absent'))
                    else:
                        q=qs[0];actual=project(q,run['requests']);row.update(known=q['known'],actual_source=actual,source_status=('correct'if actual==truth else'wrong')if q['known']else'unknown',path_edges=q['path_edges'])
                        bmessage=msg(calls['B'][index]['traceparent']);answers=[a for a in result['answers']if a['path']=='/text'and any(v['kind']=='binding-return'and v['seq']==a['seq']and v.get('message')==bmessage for v in events)];assert len(answers)==1;a=answers[0]
                        reads=[v for v in events if v['kind']=='read'and v.get('frame')==a['root_frame']and v.get('field')=='lineage/business/Cache$Cell.text']
                        slots=[v for v in events if v['kind']=='read'and v.get('frame')==a['root_frame']and v.get('field')=='lineage/business/Cache.cell'];keys=[v for v in events if v['kind']=='read'and v.get('frame')==a['root_frame']and v.get('field')=='lineage/business/Cache.key']
                        expected_slot=0 if unseeded else sum(r['op']==1 for r in work[cap.name]['requests'][:index+1]);slot_ok=bool(slots)and all(v['version']==expected_slot for v in slots+keys)
                        if reads:slot_ok&=all(v['observed']['object']==reads[0]['owner']for v in slots)
                        checkpoint=None if unseeded else case['read_checkpoints'][index];version_ok=not reads if unseeded or not checkpoint['output_reads_cache_text']else len(reads)==1 and reads[0]['version']==checkpoint['cell_text_version']
                        normal=any(r['frame']==a['root_frame']and r['completion']=='normal'for r in result['roots'])
                        row.update(version_status='unknown'if unseeded else'correct'if relation and write_versions and slot_ok and version_ok and normal else'wrong',actual_reads=reads,cache_cell_reference_reads=slots,cache_key_reads=keys,normal_completion=normal)
                        if reads:assert any(r['read_seq']==reads[0]['seq']for r in hist['reads'])
                        if cap.name in ('public-constant','miss-fallback')and index>0:
                            prior=[v for v in hist['versions']if v['coordinate'][1]=='lineage/business/Cache$Cell.text'and v['coordinate'][2]==1];assert len(prior)==1 and prior[0]['known']
                            assert sources(prior[0]['origins'],events,[{'traceparent':r['traceparent']}for r in calls['B']])==[[1,'/value']]
                            row['prior_cached_source_verified']=True
                            if cap.name=='public-constant':assert q['known']and actual==[]
                            else:assert len(writes)==1 and not reads
                scored.append(row)
    summary={m:{'source':dict(Counter(r['source_status']for r in scored if r['mode']==m)),'version':dict(Counter(r['version_status']for r in scored if r['mode']==m))}for m in ('tracefusion','mirror-online','mirror-composed')}
    save(out/'score.json',{'summary':summary,'rows':scored,'physical':physical});print(json.dumps(summary))
    assert all(r['business_equal']for r in scored),'Business behavior changed'
    if not allow_wrong:assert all(r['source_status']=='correct'and r['version_status']in ('correct','N/A')for r in scored if r['mode']in ('tracefusion','mirror-composed')and r['case']!=e['calibration']['id']),'Positive gate did not pass'


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--predictions',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--allow-wrong',action='store_true');a=p.parse_args();score(a.run.resolve(),a.predictions.resolve(),a.out.resolve(),a.allow_wrong)
