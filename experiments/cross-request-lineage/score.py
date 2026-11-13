#!/usr/bin/env python3
"""Independent scorer. Never imported by the collectors or analyzers."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


def load(p):return json.loads(p.read_text())
def rows(p):return [json.loads(l) for l in p.read_text().splitlines()]
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def message(parent):
    p=parent.split('-');return p[1]+'/'+p[2]


def actual_sources(answer,run):
    known={message(r['traceparent']):i+1 for i,r in enumerate(run['requests'])}
    return sorted([[known.get(s.get('message'),'foreign'),s.get('path')] for s in answer.get('sources',[])],key=str)


def score(run):
    oracle=load(run/'expected.json');assert hashlib.sha256((run/'expected.json').read_bytes()).hexdigest()==load(run/'freeze.json')['expected_sha256']
    results=[]
    for mode in ('tracefusion','mirrortaint'):
        for cap in sorted((run/'captures'/mode).glob('*/*')):
            case=next(c for c in oracle['cases'] if c['id']==cap.name)
            receipt=load(cap/'run.json');plain=load(run/'captures/plain'/cap.parent.name/cap.name/'run.json')
            predicted=load(run/'predictions'/mode/cap.parent.name/cap.name/'prediction.json')
            business=receipt.get('business_completed',False) and plain.get('business_completed',False)
            if business:
                business=([r['response'] for r in receipt['requests']]==[r['response'] for r in plain['requests']]
                          and receipt['state']==plain['state']==case['state'] and receipt['requests'][-1]['response']=={'text':case['response']})
            item={'mode':mode,'repeat':cap.parent.name,'case':cap.name,'business_equal':business,'expected':case,'source_status':'unknown'}
            b_http=rows(cap/'B/http.jsonl') if (cap/'B/http.jsonl').exists() else []
            live=[r for r in b_http if r['path']=='/call']
            item['shared_process_verified']=len(live)==len(case.get('requests',receipt['requests'])) and len({r['pid'] for r in live})==1 and len({r['thread'] for r in live})==1
            if not business:item.update(source_status='cannot_run',reason=receipt.get('error','business mismatch'))
            elif mode=='tracefusion':
                rs=rows(cap/'B/events.jsonl');writes=[r for r in rs if r['kind']=='write' and r.get('field')=='lineage/business/Cache$Cell.text']
                item['observed_writes']=[{k:r[k] for k in ('seq','owner','field','version','frame')} for r in writes]
                item['version_witness_matches']=([r['version'] for r in writes]==case['field_versions'] and
                    (len(writes)<2 or (writes[0]['owner']==writes[1]['owner'])==(case['object_relation']=='same')))
                b_requests=[r for r in b_http if r['path']=='/call'];sink_msg=message(b_requests[-1]['traceparent'])
                if predicted['status']=='analysis_error':item.update(reason=predicted['error'],classification='analysis_rejection')
                else:
                    q=next(q for q in predicted['queries'] if q['role']=='B' and q['message']==sink_msg);a=q['answer']
                    actual=actual_sources(a,receipt);item.update(actual=actual,known=a['known'],target=a['target'],local_diagnostic=a['unrestricted_leaf_diagnostic'])
                    if a['known']:item['source_status']='correct' if actual==case['source'] else 'wrong'
                    local=a['unrestricted_leaf_diagnostic']
                    item['reason']=('core returned unresolved dependency/effect' if not local['known'] else 'core stopped at B request boundary; no complete external-source path') if not a['known'] else 'complete core path'
                    item['classification']='propagation_or_query_gap' if not local['known'] else 'query_boundary_gap'
                neg=run/'predictions'/mode/cap.parent.name/cap.name/'drop-second-field-write/prediction.json'
                if neg.exists():
                    n=load(neg);item['missing_write_control']={'state':n['status'],'reason':n.get('error'),'rejected':n['status']=='analysis_error' or not any(q['answer']['known'] for q in n.get('queries',[]))}
                    item['missing_write_control']['guard_verified']=predicted['status']=='analyzed' and n.get('error')!=predicted.get('error')
                    if predicted['status']=='analysis_error':item['missing_write_control']['limitation']='Original capture already rejected; deletion guard is not independently verified'
            else:
                native=predicted['native'];a_sources=[r for r in native['A'] if r['kind']=='source']
                item['source_api_verified']=len(a_sources)==2*len(receipt['requests']) and all(r['native_ids'] for r in a_sources)
                sinks=[r for r in native['B'] if r['kind']=='sink'];ids=sinks[-1]['native_ids'] if sinks else None
                source_ids={s:(i+1,r['path']) for i,req in enumerate(receipt['requests']) for r in a_sources if r['message']==req['traceparent'] for s in r['native_ids']}
                actual=sorted([list(source_ids.get(i,('unmapped-native-id',i))) for i in (ids or [])],key=str)
                item.update(native_ids=ids,actual=actual,strict_version_query='unavailable',missing_write_control='online native API has no write-evidence input')
                if ids is None or not item['source_api_verified']:item.update(source_status='configuration_error',reason='missing sink export or source API did not install labels')
                else:
                    item['source_status']='correct' if actual==case['source'] else 'wrong'
                    item['reason']='native tag set is empty after HTTP; no manual transport propagation allowed' if not ids else 'native exported labels'
                    item['classification']='transport_configuration_or_unsupported_protocol' if not ids else 'native_result'
            results.append(item)
    summary={mode:dict(Counter(r['source_status'] for r in results if r['mode']==mode)) for mode in ('tracefusion','mirrortaint')}
    report={'summary':summary,'rows':results,'core_changed':False,'no_innovation_claim':True}
    save(run/'score.json',report)
    text=['# 跨请求共享状态字段溯源：第一轮', '', '固定来源：A 外部 HTTP 输入字段 /value、/fallback。表内为最后请求的 B HTTP /text；A 最终代理响应及完整路径另存 predictions。', '',
          '| 轮次 | 案例 | 工具 | 预期来源 | 实际状态／来源 | 首次错误或 unknown 原因 |', '|---|---|---|---|---|---|']
    for r in results:text.append('| '+ ' | '.join([r['repeat'],r['case'],r['mode'],str(r['expected']['source']),r['source_status']+' '+str(r.get('actual','')),r.get('reason','').replace('|','/')])+' |')
    text+=['','业务、进程身份、字段版本见 score.json；运行命令见 captures/*/*/*/run.json。原始证据不覆盖，缺写证据存派生目录。', '', '汇总：`'+json.dumps(summary,ensure_ascii=False)+'`。本轮不计性能，不据此宣布创新成立。']
    (run/'REPORT.md').write_text('\n'.join(text)+'\n')
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);score(p.parse_args().run.resolve())
