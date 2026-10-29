"""Validate recorded W3C invocation identities, independent of field values."""
from collections import defaultdict
import re
from query_observation_planner import require


def identifier(value, width):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{'+str(width)+'}', value) and int(value, 16) != 0


def validate_context(row):
    require(row.get('transport_protocol') == 'w3c-trace-context', 'Missing W3C context declaration')
    require(identifier(row.get('trace_id'), 32) and identifier(row.get('request_span_id'), 16)
            and identifier(row.get('span_id'), 16), 'Invalid W3C invocation identifier')
    require(row.get('parent_span_id') is None or identifier(row['parent_span_id'], 16), 'Invalid W3C parent span')
    require(row.get('trace_flags') in ('00', '01'), 'Invalid supported W3C flags')
    require(row['message'] == row['trace_id']+'/'+row['request_span_id'], 'W3C invocation key differs from trace/span')


def validate_protocol(rows,expected_version=1,contract=None):
    """Reject mismatched client scopes; server spans must parent the wire span.

    The local `message` field is only an internal composite key. It is never
    propagated in a custom HTTP header, nor used without validating trace/span.
    """
    require(expected_version in (1,2),'Unsupported communication protocol')
    if expected_version==2:validate_message_identity(rows,contract)
    else:require(not any(r.get('communication_version')==2 for r in rows),'V2 evidence requires an explicitly V2 plan')
    stacks = defaultdict(list)
    client_spans = set()
    server_spans = {}
    for row in rows:
        kind = row['kind']
        if kind not in ('http-rpc-enter', 'http-rpc-exit', 'http-rpc-abort', 'http-json'):
            continue
        validate_context(row)
        stack = stacks[row['thread']]
        if kind == 'http-rpc-enter':
            key = (row['trace_id'], row['span_id'])
            require(row['span_id'] == row['request_span_id'] and key not in client_spans, 'Reused or non-client RPC span')
            client_spans.add(key)
            stack.append(row)
        elif kind in ('http-rpc-exit', 'http-rpc-abort'):
            require(stack and stack[-1]['message'] == row['message'], 'Broken HTTP RPC context')
            stack.pop()
        else:
            client = (row['phase'], row['direction']) in (('read', 'response'), ('write', 'request'))
            if client:
                require(stack and all(stack[-1].get(k) == row.get(k) for k in
                        ('message', 'uri', 'trace_id', 'span_id', 'parent_span_id', 'request_span_id', 'trace_flags', 'tracestate')),
                        'JSON context does not belong to active actual RPC')
            else:
                require(row['parent_span_id'] == row['request_span_id'] or
                        (row['parent_span_id'] is None and row['span_id'] == row['request_span_id']), 'Server span has wrong wire parent')
                prior = server_spans.setdefault(row['message'], row['span_id'])
                require(prior == row['span_id'], 'Multiple server spans for one HTTP invocation')
    require(not any(stacks.values()), 'Unclosed HTTP RPC')
    return True


def validate_message_identity(rows,contract):
    """Actual attempt and message object lineage; sequence numbers are not IDs."""
    require(contract and contract.get('version')==2,'V2 contract declaration missing')
    checked={}
    for r in rows:
        if r['kind']in ('communication-class','communication-framework'):
            require(contract['class_sha256'].get(r.get('class'))==r.get('class_sha256'),'Communication implementation proof differs')
            checked[r['class']]=r['class_sha256']
    stacks=defaultdict(list);calls={};ids=set();observations=set();servers={}
    related={'http-client-attempt','http-request-derived','http-client-send','http-client-receive','http-client-failure','http-response-derived'}
    roles={('request','read'):'server-receive-request',('request','write'):'client-send-request',('response','read'):'client-receive-response',('response','write'):'server-send-response'}
    def current(r):
        stack=stacks[r['thread']];require(stack and stack[-1]['id']==r.get('rpc_call_id'),'Communication event has no matching actual RPC attempt')
        c=stack[-1];require(all(c['start'].get(k)==r.get(k)for k in ('message','trace_id','request_span_id','span_id','parent_message','uri')),'Communication attempt context differs');return c
    def role(r,wanted):
        require(r.get('communication_role')==wanted and r.get('message_instance'),'Missing/wrong communication role or physical message instance')
        direction='request'if wanted.endswith('request')else'response'
        require(r.get('communication_message')==r['message']+'|'+direction,'Communication message key differs from actual exchange/direction')
    for r in rows:
        kind=r['kind']
        if kind in ('http-rpc-enter','http-rpc-exit','http-rpc-abort','http-json')or kind in related:
            require(r.get('communication_version')==2,'V2 capture lacks required communication coordinates; never infer them from a root context')
        if kind=='http-rpc-enter':
            key=r.get('rpc_call_id');require(isinstance(key,str)and key and key not in ids,'Duplicate/missing actual RPC call identity');ids.add(key)
            c={'id':key,'start':r,'requests':set(),'responses':{},'sent':None,'received':None,'attempt':False,'network_finished':False}
            calls[key]=c;stacks[r['thread']].append(c)
        elif kind in related:
            c=current(r)
            if kind=='http-client-attempt':
                require(not c['attempt']and r.get('request_object')and r.get('original_request'),'Missing/duplicate concrete client attempt');c['attempt']=True;c['requests'].add(r['request_object'])
            elif kind=='http-request-derived':
                require(r.get('parent_request')in c['requests']and r.get('request_object')not in c['requests'],'Foreign/repeated request derivation');c['requests'].add(r['request_object'])
            elif kind=='http-client-send':
                require(r.get('client_class')in ('feign/Client$Default','feign/okhttp/OkHttpClient')and r['client_class']in checked,'Actual client implementation proof missing')
                role(r,'client-send-request');require(c['sent']is None and r.get('request_object')in c['requests'] and r['message_instance']==r['request_object'],'Duplicate/foreign actual client send')
                require(r.get('wire_traceparent')=='00-'+r['trace_id']+'-'+r['request_span_id']+'-'+r['trace_flags'],'Actual sent header differs from attempt')
                c['sent']=r['request_object']
            elif kind=='http-client-receive':
                role(r,'client-receive-response');require(c['sent']and not c['network_finished']and r.get('request_object')==c['sent']and r.get('response_object')==r['message_instance'],'Response belongs to another request or completed twice')
                c['received']=r['response_object'];c['responses'][r['response_object']]=r['response_object'];c['network_finished']=True
            elif kind=='http-client-failure':
                require(c['sent']and not c['network_finished']and r.get('request_object')==c['sent']and r.get('exception_object'),'Client exception lacks its actual request/completion');c['network_finished']=True
            elif kind=='http-response-derived':
                parent=r.get('parent_response');require(parent in c['responses']and r.get('response_object')not in c['responses']and r.get('request_object')in c['requests'],'Foreign/repeated response derivation')
                require(c['responses'][parent]==r.get('network_response_object')and r.get('body_object')==r.get('parent_body_object'),'Response/body identity chain differs')
                c['responses'][r['response_object']]=c['responses'][parent]
        elif kind=='http-json':
            wanted=roles.get((r.get('direction'),r.get('phase')));require(wanted is not None,'Invalid codec role');role(r,wanted)
            # A second observation of one message/role is still a duplicate,
            # regardless of a new event sequence number or carrier wrapper.
            identity=(r['message'],r['direction'],r['phase']);require(identity not in observations,'Duplicate codec observation of the same actual message');observations.add(identity)
            require(r.get('carrier_object'),'Codec carrier identity missing')
            carrier=r['carrier_object']
            for link in r.get('carrier_chain',[]):
                require(link['wrapper']==carrier and checked.get(link['class'])==link['class_sha256'],'Broken/unverified codec carrier chain');carrier=link['delegate']
            require(carrier==r.get('codec_adapter_object'),'Codec adapter is not the actual carrier/delegate')
            if wanted.startswith('client-'):
                c=current(r)
                if wanted=='client-receive-response':require(r.get('response_object')in c['responses']and c['responses'][r['response_object']]==r.get('network_response_object')==r['message_instance']and r.get('request_object')in c['requests'],'Codec response is not part of this completed client message')
                else:require(r.get('request_object')==r['message_instance']in c['requests'],'Codec request is not part of the actual client message')
            else:
                prior=servers.setdefault((r['message'],wanted),r['message_instance']);require(prior==r['message_instance'],'Server codec changed physical message identity')
        elif kind in ('http-rpc-exit','http-rpc-abort'):
            c=current(r)
            if c['start'].get('client_kind')=='feign-synchronous-attempt':
                require(all(k in checked for k in ('feign/SynchronousMethodHandler','feign/Response','feign/Response$Builder')),'Necessary client framework witness missing')
                require(c['attempt'],'Feign attempt has no actual request')
                if kind=='http-rpc-exit':require(c['sent']and c['received']and c['network_finished'],'Normal attempt lacks actual request/response completion')
                elif c['sent']:require(c['network_finished'],'Aborted attempt lacks client completion')
            stacks[r['thread']].pop()
    require(not any(stacks.values()),'Unclosed actual communication attempt')
    return True
