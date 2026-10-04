"""Join bounded HTTP JSON transfers; tracing selects calls, never data origins."""
from copy import deepcopy
import json
import re
from byte_provenance import snapshot
from gin_byte_boundaries import bind as bind_local,group_events
from hybrid_model import require
from lineage_graph import backward_nodes


def trace_key(text):
    m=re.fullmatch(r'00-([0-9a-f]{32})-([0-9a-f]{16})-01',text)
    require(m is not None and int(m[1],16)>0 and int(m[2],16)>0,'Missing or unsupported trace context')
    return m[1],m[2]


def text_value(event,name):return snapshot(event['values'][name])[1].decode('ascii')


def bind_service(document,plan):
    try:
        local=bind_local(document,plan)
        require(local['status']=='resolved','Local provenance failed: '+str(local.get('reason')))
        groups,_=group_events(document,plan)
        role=plan['cross_role'];require(role in ('upstream','downstream'),'Missing service role')
        for group,result in zip(groups,local['results']):
            traces=[e for e in group if e['op']=='trace']
            require([(e['op'],e['phase']) for e in traces]==[('trace','pre'),('trace','post')],'Missing or repeated incoming trace extraction')
            require(group[1:3]==traces,'Trace extraction outside request prefix')
            incoming=text_value(traces[1],'trace');trace_key(incoming)
            result['incoming_trace']=incoming
            if role=='upstream':continue
            reads=[e for e in group if e['op']=='source']
            before,after=reads[:2]
            outgoing=text_value(before,'trace');require(trace_key(outgoing)==trace_key(incoming),'Forwarding context changed')
            http=[e for e in group if e['op'] in ('http_header','http_body','decode')]
            require([(e['op'],e['phase']) for e in http]==[
                ('http_header','pre'),('http_header','post'),('http_body','pre'),('http_body','post'),('decode','pre'),('decode','post')],
                'Incomplete HTTP receive/decode boundaries')
            header,_,_,received,decode,decoded=http
            require(text_value(header,'key').lower()=='traceparent' and text_value(header,'trace')==outgoing,'Outgoing HTTP header mismatch')
            require(before['timestamp']<=http[0]['timestamp']<=http[-1]['timestamp']<=after['timestamp'],'Receive events outside remote read')
            rp,body=snapshot(received['values']['body']);dp,consumed=snapshot(decode['values']['body'])
            require(received['registers']['rdi']==0 and decoded['registers']['rax']==0,'HTTP body read or JSON decoding failed')
            require(rp==dp and body==consumed,'Decoder did not receive the observed HTTP body')
            require(received['registers']['rcx']>=len(body) and decode['registers']['rcx']>=len(body),'Invalid received slice capacity')
            value_ptr,value=snapshot(after['values']['value'])
            require(value_ptr==decode['registers']['rsi'] and decode['registers']['rdi']!=0,'Remote source differs from decoded object')
            payload=json.loads(body)
            require(isinstance(payload,dict) and set(payload)=={'result'} and isinstance(payload['result'],list) and
                    all(type(b) is int for b in payload['result']) and payload['result']==list(value),'Decoded field/value mismatch')
            result['transfer']=dict(trace=outgoing,body=body.decode(),field='$.result',source='source:1',
                received_sequence=received['sequence'],decode_sequence=decode['sequence'],return_sequence=after['sequence'],
                remote_source_pointer=value_ptr,summary='json-four-byte-array-v1')
        local['role']=role;return local
    except (ValueError,KeyError,TypeError,IndexError,UnicodeError) as exc:
        return dict(status='unknown',reason=str(exc),results=[])


def prefixed_graph(graph,service):
    graph=deepcopy(graph)
    for n in graph['nodes']:n['id']=service+'/'+n['id']
    for e in graph['edges']:
        e['source']=service+'/'+e['source'];e['target']=service+'/'+e['target']
    return graph


def stitch(upstream,downstream):
    if upstream.get('status')!='resolved' or downstream.get('status')!='resolved':
        return dict(status='unknown',reason='One service has incomplete provenance',results=[])
    index={}
    for result in upstream['results']:
        try:key=trace_key(result['incoming_trace'])
        except (ValueError,KeyError):return dict(status='unknown',reason='Invalid upstream trace context',results=[])
        index.setdefault(key,[]).append(result)
    counts={}
    for result in downstream['results']:
        try:
            key=trace_key(result['transfer']['trace']);counts[key]=counts.get(key,0)+1
        except (ValueError,KeyError):pass
    joined=[]
    for result in downstream['results']:
        rid=result['request_id']
        try:
            transfer=result['transfer'];key=trace_key(transfer['trace']);candidates=index.get(key,[])
            require(len(candidates)==1,'Missing or ambiguous upstream response for trace/span')
            require(counts[key]==1,'Multiple remote reads reuse one trace/span')
            upstream_result=candidates[0]
            require(upstream_result['body']==transfer['body'],'Upstream writer and receiver bodies differ')
            ug=prefixed_graph(upstream_result['provenance']['graph'],'upstream')
            dg=prefixed_graph(result['provenance']['graph'],'downstream')
            remote='downstream/request:%d:source:1'%rid
            # Replace the external-read definition with per-position transfer
            # dependencies. A source-only union would retain overwritten data.
            edges=[e for e in dg['edges'] if e['source']!=remote]+ug['edges']
            nodes={n['id']:n for n in ug['nodes']+dg['nodes']};links=[]
            for i in range(4):
                target=remote+'/byte:'+str(i)
                if target not in nodes:continue # fully overwritten positions
                source='upstream/request:%d:output-byte:%d'%(upstream_result['request_id'],i)
                require(source in nodes,'Upstream output position not modeled')
                edge=dict(source=source,target=target,kind='http-json-field',path='$.result[%d]'%i)
                edges.append(edge);links.append(edge)
            sink='downstream/request:%d:writer'%rid
            keep=backward_nodes(edges,[sink],{'data','same-slice-response-write','http-json-field'})
            terminal=[dict(id=n,path=nodes[n]['path']) for n in sorted(keep) if nodes[n]['kind']=='source']
            require(all(n['id']!=remote for n in terminal),'Unresolved remote source remains')
            joined.append(dict(status='resolved',downstream_request=rid,upstream_request=upstream_result['request_id'],
                trace=transfer['trace'],body=result['body'],sources=terminal,transfer_contributes=bool(links),
                graph=dict(nodes=[nodes[n] for n in sorted(keep)],edges=[e for e in edges if e['source'] in keep and e['target'] in keep]),
                evidence=dict(sender_body=upstream_result['body'],receiver_body=transfer['body'],summary=transfer['summary'])))
        except (ValueError,KeyError,TypeError,IndexError) as exc:
            joined.append(dict(status='unknown',downstream_request=rid,reason=str(exc)))
    return dict(status='resolved' if joined and all(r['status']=='resolved' for r in joined) else 'unknown',results=joined,
                oracle_used_for_inference=False,scope='One synchronous HTTP JSON response per context; fixed field model; trusted trace forwarding')
