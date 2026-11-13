"""Opt-in blocking HTTP/1.1 exchange proof. No value-selected or ID-only joins.

The recorded adapter observes actual Socket/HttpExchange I/O. One fresh TCP
connection per request is a deliberate admission constraint, not a model of
keepalive, proxies, multiplexing, retries, TLS or arbitrary serializers.
"""
import hashlib
import json
from collections import defaultdict
from query_observation_planner import require
from transport_context import validate_context


def scalar_json(raw):
    def unique(items):
        result={}
        for k,v in items:
            require(k not in result,'Duplicate wire JSON property');result[k]=v
        return result
    body=json.loads(raw,object_pairs_hook=unique)
    require(isinstance(body,dict) and all(not isinstance(v,(dict,list)) for v in body.values()),'Only flat scalar DTO JSON admitted')
    return body


def validate_local(plan,rows):
    cfg=plan['http_exchange']
    require(cfg.get('version')==1 and cfg.get('scope')=='blocking-http-json-one-exchange-per-connection','Unsupported HTTP exchange plan')
    require(cfg.get('input_role') in ('external','intermediate'),'HTTP input role undeclared')
    require(rows and rows[0]['kind']=='start','HTTP capture start absent')
    namespace=(rows[0].get('capture_session'),rows[0].get('process_instance'))
    require(all(isinstance(x,str) and x for x in namespace),'HTTP capture namespace absent')
    require([r['seq']for r in rows]==list(range(1,len(rows)+1)),'HTTP exchange event sequence gap')
    require(all(r.get('http_exchange_version')==1 and (r.get('capture_session'),r.get('process_instance'))==namespace for r in rows),'HTTP exchange capture/process differs')
    footers=[r for r in rows if r['kind']=='metrics']
    require(len(footers)==1 and footers[0].get('http_exchange_event_count')==len(rows) and not footers[0].get('capture_invalid'),'HTTP exchange capture did not close')
    require(rows[0].get('plan_sha256')==hashlib.sha256((json.dumps(plan,indent=2)+'\n').encode()).hexdigest(),'HTTP frozen plan differs')
    proofs=defaultdict(list);codecs=defaultdict(list)
    for r in rows:
        if r['kind']not in ('http-exchange','http-json'):continue
        validate_context(r);key=(r['message'],r['direction'],r['phase'])
        (proofs if r['kind']=='http-exchange'else codecs)[key].append(r)
    require(set(codecs)==set(proofs),'Missing completed HTTP I/O or codec observation')
    exchanges={};field_maps=[]
    for key,codec in codecs.items():
        require(len(codec)==len(proofs[key])==1,'Duplicate HTTP I/O or codec observation')
        c=codec[0];p=proofs[key][0]
        require(p['seq']<c['seq'],'Codec observation precedes actual HTTP I/O completion')
        require(p.get('normal_complete')is True and p.get('method')=='POST'and p.get('path')=='/call','Incomplete/unsupported actual HTTP exchange')
        require(all(p.get(k)==cfg.get(k)for k in ('adapter_sha256','server_sha256')),'HTTP adapter implementation proof differs')
        fields=('message','direction','phase','carrier','connection','wire_traceparent','wire_sha256','method','path','status','span_id','parent_span_id','parent_message')
        require(all(c.get(k)==p.get(k)for k in fields),'Codec carrier/message differs from actual I/O')
        conn=p.get('connection');require(isinstance(conn,list)and len(conn)==4 and all(isinstance(x,str)and x for x in conn),'Actual TCP endpoints absent')
        require(all(x.isdecimal()and 0<int(x)<65536 for x in (conn[1],conn[3])),'Invalid TCP ports')
        require(isinstance(p.get('carrier'),str)and p['carrier'],'Actual HTTP carrier absent')
        require(p.get('wire_traceparent')=='00-'+p['trace_id']+'-'+p['request_span_id']+'-'+p['trace_flags'],'Actual HTTP wire header differs')
        require(hashlib.sha256(p['wire_utf8'].encode()).hexdigest()==p['wire_sha256'],'Actual HTTP wire body hash differs')
        body=scalar_json(p['wire_utf8']);seen=set()
        for f in c['fields']:
            owner=f['field'].rsplit('.',1)[0];props=[x for x in plan['json_schema'].get(owner,[])if x['field']==f['field']]
            require(len(props)==1,'Unknown wire DTO property');prop=props[0]
            name=prop['property'];path='/'+name.replace('~','~0').replace('/','~1')
            require(f['path']==path and name not in seen,'HTTP field mapping differs from frozen JSON schema')
            require(prop['descriptor']==f.get('descriptor') and prop['descriptor']in ('I','J','Z','D','F','S','B','C','Ljava/lang/String;'),'Unsupported wire scalar descriptor')
            require(name in body and f['observed'].get('value')==body[name],'HTTP property differs from actual serialized bytes')
            seen.add(name);field_maps.append({'message':p['message'],'direction':p['direction'],'phase':p['phase'],'proof_seq':p['seq'],'codec_seq':c['seq'],'path':path,'coordinate':[f['owner'],f['field'],f['version']]})
        require(seen==set(body),'Wire JSON field coverage differs')
        client=(key[1],key[2])in (('request','write'),('response','read'))
        exchange=(p['message'],'client'if client else'server')
        if exchange in exchanges:
            prev=exchanges[exchange];require(prev['carrier']==p['carrier']and prev['connection']==conn,'HTTP request/response uses a foreign physical carrier')
        else:exchanges[exchange]=p
        if p['direction']=='response':require(p['status']==200,'Non-normal HTTP result outside admitted exchange')
    return {'namespace':list(namespace),'field_maps':field_maps,'exchanges':list(exchanges.values())}


def bridges(plans,rows):
    """Join real endpoints, wire invocation, operation and direction BEFORE values."""
    audits={role:validate_local(plans[role],events)for role,events in rows.items()}
    require(len({tuple(x['namespace'])for x in audits.values()})==len(audits),'Two services share a capture/process namespace')
    send=defaultdict(list);receive=defaultdict(list);connections=defaultdict(set)
    for role,events in rows.items():
        for r in events:
            if r['kind']!='http-json':continue
            key=(tuple(r['connection']),r['wire_traceparent'],r['method'],r['path'],r['direction'])
            (send if r['phase']=='write'else receive)[key].append((role,r))
            side='client'if(r['direction'],r['phase'])in (('request','write'),('response','read'))else'server'
            connections[(role,tuple(r['connection']),side)].add(r['message'])
    require(all(len(messages)==1 for messages in connections.values()),'TCP connection reused for multiple messages outside admitted scope')
    links=[]
    for key,targets in receive.items():
        sources=send.get(key,[])
        if not sources:continue # unbound intermediate remains unknown in the graph
        require(len(sources)==len(targets)==1,'Ambiguous actual HTTP exchange')
        sr,s=sources[0];tr,t=targets[0];require(sr!=tr,'Remote HTTP edge stayed within one JVM')
        require(s['wire_sha256']==t['wire_sha256'],'Actual HTTP sender/receiver bytes differ')
        sf={f['path']:f for f in s['fields']};tf={f['path']:f for f in t['fields']}
        require(set(sf)==set(tf),'Remote JSON property mapping coverage differs')
        for path in sf:
            require(sf[path]['observed'].get('value')==tf[path]['observed'].get('value'),'Mapped HTTP scalar differs')
            links.append({'sender':sr,'send_seq':s['seq'],'receiver':tr,'receive_seq':t['seq'],'path':path,'connection':list(key[0]),'wire_traceparent':key[1]})
    return audits,links
