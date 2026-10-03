"""Demultiplex observed pinned scopes before shared field/JSON provenance.

Global sequence is atomic uniqueness, not timestamp order across CPUs. Every
request also has a contiguous local observation sequence. No oracle enters bind.
"""
import json

import gin_api_boundaries as shared
from hybrid_model import require


def groups(rows):
    active={};contexts={};gs={};closed={}
    for event in rows:
        rid=event['request_id'];tid=event['pid_tid'];g=event['regs'][14]
        require(isinstance(rid,int) and rid>0,'Invalid request ID')
        if event['kind']==3:
            require(rid not in active and rid not in closed,'Repeated request generation')
            require(tid not in contexts and g not in gs and g>0,'Overlapping pinned execution context')
            active[rid]=[];contexts[tid]=rid;gs[g]=rid
        require(rid in active,'Event outside request lifetime')
        require(contexts.get(tid)==rid and gs.get(g)==rid,'Thread/G migration or cross-request event')
        request=active[rid]
        require(event['request_sequence']==len(request),'Missing or repeated request-local observation')
        if request:require(event['timestamp']>=request[-1]['timestamp'],'Non-monotonic request observations')
        request.append(event)
        if event['kind']==4:
            closed[rid]=active.pop(rid);del contexts[tid];del gs[g]
    require(not active and closed,'Unclosed or empty request set')
    require(set(closed)==set(range(1,len(closed)+1)),'Missing request generation')
    return [closed[k] for k in sorted(closed)]


def bind(events,plans,config,runtime, *, group_requests=None, context_policy=None):
    result=shared.bind(events,plans,config,runtime,group_requests=group_requests or groups,context_policy=context_policy)
    if result['issues']:return result
    try:
        require(config['gin_api']['serial_requests'] is False,'Concurrent scope adapter not configured')
        rows=sorted(events,key=lambda e:e['observation_sequence'])
        peak=active=0;switches=0;previous=None
        by_id={}
        for e in rows:
            by_id.setdefault(e['request_id'],[]).append(e)
            if previous is not None and previous!=e['request_id']:switches+=1
            previous=e['request_id']
            if e['kind']==3:active+=1;peak=max(peak,active)
            elif e['kind']==4:active-=1
        ownership=[]
        for out in result['results']:
            request=by_id[out['request_id']];compute=[e for e in request if e['kind']==0]
            require(len({e['src_addr'] for e in compute})==len({e['dst_addr'] for e in compute})==1,
                    'Concurrent fixture requires one private input/output object per request')
            src=compute[0]['src_addr'];dst=compute[0]['dst_addr']
            first=request[0]['observation_sequence'];last=request[-1]['observation_sequence']
            # Shared mutable memory is outside this pilot. Equal byte values do
            # not make overlapping live request objects safe to merge.
            for start,end in ((src,src+12),(dst,dst+8)):
                require(start>0 and end<1<<64,'Invalid private object range')
                for a,b,enter,leave,rid in ownership:
                    require(not (max(first,enter)<min(last,leave) and max(start,a)<min(end,b)),
                            'Overlapping private request objects')
                ownership.append((start,end,first,last,out['request_id']))
            out.update(input_addr=src,request_identity='observed invocation generation; private object mapping used only by evaluation',
                       scope_interval=dict(entry=first,exit=last),
                       phase_observations=dict(read_entries=[e['observation_sequence'] for e in request if e['kind']==1],
                           read_exits=[e['observation_sequence'] for e in request if e['kind']==2],
                           compute_start=compute[0]['observation_sequence'],compute_end=compute[-1]['observation_sequence'],
                           render_entry=next(e['observation_sequence'] for e in request if e['kind']==6)))
        result.update(concurrency=dict(max_active_scopes=peak,request_switches=switches),
                      scope='Concurrent pinned Gin requests: private pread state -> shared instruction provenance -> fixed JSON summary; no thread migration or shared mutable memory support')
        return result
    except (ValueError,KeyError,IndexError,TypeError,StopIteration) as exc:
        return dict(results=[],compute_results=[],read_operations=[],issues=[dict(error=str(exc))],boundary_issues=[dict(error=str(exc))],oracle_used_for_inference=False)


def evaluate(inferred,oracle,stats,plans, *, require_phase_barriers=True):
    checks=[];tp=fp=fn=0;by_input={r['input_addr']:r for r in inferred['results']}
    modes=['left','right','merge','overwrite','same','zero','max']*4
    shape=(len(oracle)==28 and {r['ticket'] for r in oracle}==set(range(1,29))
           and len({r['input_addr'] for r in oracle})==28 and len(by_input)==len(inferred['results'])==28)
    mapped={}
    for truth in oracle:
        ticket=truth['ticket'];mode=truth['mode'];actual=by_input.get(truth['input_addr'],{})
        mapped[ticket]=actual
        value=0 if mode=='zero' else (0xffffffff if mode=='max' else 424242)
        expected_value={'left':(value^0x55)+3,'merge':((value^0x55)+3+value)&0xffffffff,'overwrite':42}.get(mode,value)
        fields={'left':{'input.left'},'merge':{'input.left','input.right'},'overwrite':set()}.get(mode,{'input.right'})
        offset=(ticket-1)*16+(8 if mode=='zero' else 12 if mode=='max' else 0)
        expected={(1 if f=='input.left' else 2,'a.bin' if f=='input.left' else 'b.bin',offset,4) for f in fields}
        observed={(s['io_id'],s['file_name'],s['file_offset'],s['length']) for s in actual.get('external_sources',[])}
        tp+=len(expected&observed);fp+=len(observed-expected);fn+=len(expected-observed)
        body=json.dumps({'balance':expected_value},separators=(',',':'))
        passed=(1<=ticket<=28 and modes[ticket-1]==mode and actual.get('status')=='resolved' and
                expected==observed and set(actual.get('sources',[]))==fields and actual.get('value')==expected_value and
                actual.get('body')==truth['body']==body and truth['status']==200 and truth['content_type']=='application/json; charset=utf-8')
        checks.append(dict(ticket=ticket,observed_request_id=actual.get('request_id'),mode=mode,passed=passed,
                           expected_value=expected_value,observed_value=actual.get('value'),expected_sources=sorted(expected),observed_sources=sorted(observed)))
    batches=[]
    for first in range(1,29,4):
        batch=[mapped.get(t,{}) for t in range(first,first+4)];passed=False
        try:
            phases=[r['phase_observations'] for r in batch]
            passed=(all(len(p['read_entries'])==len(p['read_exits'])==2 for p in phases) and
                max(r['scope_interval']['entry'] for r in batch)<min(r['scope_interval']['exit'] for r in batch) and
                max(p['read_exits'][0] for p in phases)<min(p['read_entries'][1] for p in phases) and
                max(p['read_exits'][1] for p in phases)<min(p['compute_start'] for p in phases) and
                max(p['compute_end'] for p in phases)<min(p['render_entry'] for p in phases))
        except (KeyError,IndexError):pass
        batches.append(dict(tickets=list(range(first,first+4)),overlap_and_phase_order_verified=passed))
    clean=bool(stats.get('received_events')) and all(stats.get(k)==0 for k in ('lost_events','submit_errors','state_errors','process_returncode'))
    clean=clean and stats.get('attempted_events')==stats.get('received_events')
    passed=(shape and clean and not inferred['issues'] and all(c['passed'] for c in checks) and
            len(inferred['compute_results'])==36 and len(inferred['read_operations'])==56)
    if require_phase_barriers:
        passed=(passed and all(b['overlap_and_phase_order_verified'] for b in batches) and
                inferred.get('concurrency',{}).get('max_active_scopes')==4)
    return dict(passed=passed,capture_clean=clean,requests=len(inferred['results']),expected_requests=28,
                compute_calls=len(inferred['compute_results']),read_operations=len(inferred['read_operations']),
                checks=checks,batches=batches,concurrency=inferred.get('concurrency',{}),
                external_source_relations=dict(tp=tp,fp=fp,fn=fn,precision=tp/(tp+fp) if tp+fp else None,recall=tp/(tp+fn) if tp+fn else None),
                scope='Four overlapping pinned requests per batch; request-instance/file-offset origin checks; no migration or general concurrent program claim')
