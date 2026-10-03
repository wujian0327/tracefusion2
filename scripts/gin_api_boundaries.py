"""Request-local read provenance + an explicit, fixed Gin uint32 JSON summary.

No client response, query mode, file contents or evaluation labels enter bind.
The model is scoped to the audited fixture type, not arbitrary Go reflection.
"""
import copy
import json

import read_boundaries as reads
from hybrid_model import require
from language_adapters import get_adapter


def _bytes(event):
    require(event['read_error']==0 and 0<event['requested']<32 and event['capacity']>=event['requested'],
            'JSON slice snapshot failed or exceeds the model')
    require(event['buffer_addr']>0 and len(event['read_data'])==32,'Invalid JSON buffer')
    return bytes(event['read_data'][:event['requested']])


def _namespace(value,prefix):
    if isinstance(value,dict):
        return {k:(prefix+v if k in ('id','source','target','operation_id','external_source_id') and isinstance(v,str)
                   else _namespace(v,prefix)) for k,v in value.items()}
    if isinstance(value,list):return [_namespace(v,prefix) for v in value]
    return value


def bind(events,plans,config,runtime):
    try:
        require(config['gin_api']['model']=='gin-struct-u32-v1' and config['sink_field']=='Balance','Unsupported JSON model')
        require(0<len(events)<=100000,'Empty or oversized Gin history')
        rows=sorted(events,key=lambda e:e['observation_sequence'])
        require([e['observation_sequence'] for e in rows]==list(range(len(rows))), 'Missing or duplicate observation sequence')
        require(all(a['timestamp']<=b['timestamp'] for a,b in zip(rows,rows[1:])), 'Non-monotonic observations')
        groups=[];current=[]
        for e in rows:
            if e['kind']==3:
                require(not current and e['request_id']==len(groups)+1,'Overlapping or missing request boundary')
            require(current or e['kind']==3,'Event outside request')
            require(e['request_id']==len(groups)+1,'Event belongs to another request')
            current.append(e)
            if e['kind']==4:groups.append(current);current=[]
        require(groups and not current,'Unclosed request')
        outputs=[];computations=[];operations=[]
        for request in groups:
            rid=request[0]['request_id'];prefix='request:%d:'%rid
            require(len({e['pid_tid'] for e in request})==1,'OS-thread migration unsupported')
            get_adapter(config).context.validate(request,reads.core.model.REGS)
            framework=[e for e in request if e['kind']>=6]
            require([e['kind'] for e in framework]==[6,7,8,10,11,9],'Missing, nested or reordered Gin boundaries')
            r,m,mret,w,wret,rret=framework
            require(all(e['kind'] in (0,1,2,3) for e in request if e['observation_sequence']<r['observation_sequence']),
                    'Unsupported event before serialization')
            require(request[-8]['kind']==0 and request[-7:]==framework+[request[-1]],
                    'Computation must finish before serialization; no intervening writes supported')
            projected=[dict(e) for e in request if e['kind']<6]
            for index,e in enumerate(projected):e['observation_sequence']=index
            result=reads.bind(projected,plans,config,runtime)
            require(not result['issues'],'Read/computation inference failed: '+str(result['issues']))
            compute=[e for e in request if e['kind']==0]
            latest=compute[-1]
            final=next(v for v in result['results'] if v['call_id']==latest['call_id'])
            require(r['read_error']==m['read_error']==0,'Object snapshot failed')
            require(r['object_addr']==m['object_addr']==latest['dst_addr'] and r['object_addr']>0,
                    'JSON object is not the latest computed destination')
            require(r['object_type']==m['object_type'] and r['object_type']>0,'Marshal input type changed')
            require(r['object_value']==m['object_value']==final['value'],'Object changed after computation')
            require(mret['error_type']==wret['error_type']==rret['error_type']==0,'Serialization or response write failed')
            encoded=_bytes(mret);written=_bytes(w)
            expected=('{'+'"balance":'+str(final['value'])+'}').encode('ascii')
            require(encoded==written==expected,'Unsupported JSON representation or changed payload')
            require(mret['buffer_addr']==w['buffer_addr'] and mret['requested']==w['requested'],
                    'Response writer did not receive the Marshal slice')
            require(r['writer_addr']==w['writer_addr'] and r['writer_addr']>0,'Response writer identity mismatch')
            require(wret['returned']==len(encoded),'Partial response write')
            out=_namespace(copy.deepcopy(final),prefix)
            out.update(request_id=rid,compute_call_id=final['call_id'],call_id=rid,body=encoded.decode('ascii'),
                       json_path='$.balance',writer_addr=w['writer_addr'],buffer_addr=w['buffer_addr'],
                       sink='gin.ResponseWriter.Write',request_identity='observed serial handler invocation; not a propagated trace ID')
            graph=out['dependency_graph'];sink=next(n['id'] for n in graph['nodes'] if n.get('kind')=='sink')
            field=prefix+'json:balance';key=prefix+'json-key:balance';response=prefix+'response-write'
            graph['nodes'] += [dict(id=field,kind='json-field',path='$.balance',value=final['value']),
                               dict(id=key,kind='static-json-key',origin='output.Balance struct tag',value='balance'),
                               dict(id=response,kind='response-writer-accepted',length=len(encoded))]
            graph['edges'] += [dict(source=sink,target=field,kind='serializer-summary',model='gin-struct-u32-v1'),
                               dict(source=key,target=field,kind='field-name'),
                               dict(source=field,target=response,kind='same-slice-response-write')]
            graph['identity_scope']='request invocation + root invocation + dynamic call instance + executed instruction'
            outputs.append(out)
            computations.extend(dict(_namespace(v,prefix),request_id=rid) for v in result['results'])
            operations.extend(dict(_namespace(v,prefix),request_id=rid) for v in result['read_operations'])
        return dict(results=outputs,compute_results=computations,read_operations=operations,issues=[],boundary_issues=[],
                    oracle_used_for_inference=False,
                    scope='Serial pinned Gin requests: immutable pread -> executed computation -> fixed JSON summary -> writer acceptance; client bytes evaluated separately')
    except (ValueError,KeyError,IndexError,TypeError,StopIteration,UnicodeError) as exc:
        return dict(results=[],compute_results=[],read_operations=[],issues=[dict(error=str(exc))],
                    boundary_issues=[dict(error=str(exc))],oracle_used_for_inference=False)


def evaluate(inferred,oracle,stats,plans):
    by_id={r['request_id']:r for r in inferred['results']};checks=[];tp=fp=fn=0
    for truth in oracle:
        mode=truth['mode'];rid=truth['request_id'];actual=by_id.get(rid,{})
        left=424242;right=424242;off=0
        if mode=='zero':left=right=0;off=8
        elif mode=='max':left=right=0xffffffff;off=12
        value={'left':(left^0x55)+3,'right':right,'merge':((left^0x55)+3+right)&0xffffffff,
               'overwrite':42,'same':right,'zero':right,'max':right}[mode]
        fields={'left':{'input.left'},'merge':{'input.left','input.right'},'overwrite':set()}.get(mode,{'input.right'})
        expected={(1 if f=='input.left' else 2,'a.bin' if f=='input.left' else 'b.bin',off,4) for f in fields}
        observed={(s['io_id'],s['file_name'],s['file_offset'],s['length']) for s in actual.get('external_sources',[])}
        tp+=len(expected&observed);fp+=len(observed-expected);fn+=len(expected-observed)
        expected_body=json.dumps({'balance':value},separators=(',',':'))
        passed=(actual.get('status')=='resolved' and actual.get('value')==value and
                actual.get('body')==truth['body']==expected_body and set(actual.get('sources',[]))==fields and
                expected==observed and truth['status']==200 and truth['content_type']=='application/json; charset=utf-8')
        checks.append(dict(request_id=rid,mode=mode,passed=passed,expected_value=value,observed_value=actual.get('value'),
                           expected_sources=sorted(expected),observed_sources=sorted(observed),client_body=truth['body']))
    clean=bool(stats.get('received_events')) and all(stats.get(k)==0 for k in ('lost_events','submit_errors','state_errors','process_returncode'))
    clean=clean and stats.get('attempted_events')==stats.get('received_events')
    expected_count=14;expected_ids=set(range(1,expected_count+1))
    passed=(clean and not inferred['issues'] and len(oracle)==len(by_id)==len(inferred['results'])==expected_count
            and {r['request_id'] for r in oracle}==expected_ids==set(by_id) and all(c['passed'] for c in checks)
            and len(inferred['read_operations'])==2*expected_count and len(inferred['compute_results'])==18)
    return dict(passed=passed,capture_clean=clean,checks=checks,requests=len(by_id),expected_requests=expected_count,
                compute_calls=len(inferred['compute_results']),read_operations=len(inferred['read_operations']),
                external_source_relations=dict(tp=tp,fp=fp,fn=fn,precision=tp/(tp+fp) if tp+fp else None,recall=tp/(tp+fn) if tp+fn else None),
                scope='Fixture request/field/read-source accuracy and client body agreement; no kernel socket lineage or general JSON support')
