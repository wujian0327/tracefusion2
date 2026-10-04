"""Validate SDK parentage before linking observed HTTP field dependencies.

Only the bounded fixture topology is supported. SDK telemetry is trusted, and
missing/ambiguous spans cause unknown rather than a trace-ID-only fallback.
"""
from copy import deepcopy
from datetime import datetime
import json
from gin_cross_boundaries import trace_key,stitch
from hybrid_model import require

GIN='go.opentelemetry.io/contrib/instrumentation/github.com/gin-gonic/gin/otelgin'
HTTP='go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp'
DRIVER='tracefusion.load-client'


def context_key(context):
    return trace_key('00-'+context['TraceID']+'-'+context['SpanID']+'-'+context['TraceFlags'])


def read_spans(captures):
    result={}
    for service in ('upstream','downstream','driver'):
        path=(captures['downstream']/'client-spans.jsonl' if service=='driver' else captures[service]/'spans.jsonl')
        result[service]=[json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return result


def span_chains(documents):
    """Return chains keyed by the SDK driver CLIENT context, without an oracle."""
    index={};children={};roots=[]
    for service in ('upstream','downstream','driver'):
        require(bool(documents[service]),'Missing spans: '+service)
        for span in documents[service]:
            resources=[a['Value']['Value'] for a in span['Resource'] if a['Key']=='service.name']
            require(resources==[service],'Span service identity mismatch')
            key=context_key(span['SpanContext']);require(key not in index,'Duplicate span identity')
            require(not span['SpanContext']['Remote'],'Exported span must be local')
            require(datetime.fromisoformat(span['EndTime'].replace('Z','+00:00'))>=
                    datetime.fromisoformat(span['StartTime'].replace('Z','+00:00')),'Invalid span time interval')
            require(span['Status']['Code']!='Error','HTTP span reports failure')
            scope=span['InstrumentationScope']
            expected=DRIVER if service=='driver' else HTTP if span['SpanKind']==3 else GIN
            require(scope['Name']==expected,'Unexpected instrumentation scope')
            if service!='driver':require(scope['Version']=='0.63.0','Instrumentation version mismatch')
            index[key]=dict(service=service,raw=span,key=key)
            parent=span['Parent']
            if parent['SpanID']=='0'*16:
                require(parent['TraceID']=='0'*32 and service=='driver' and span['SpanKind']==1,'Unexpected root span')
                roots.append(key)
            else:
                parent_key=context_key(parent)
                require(parent_key[0]==key[0],'Parent changes trace ID')
                children.setdefault(parent_key,[]).append(key)
    require(len(roots)==1,'Expected one SDK load-test root')
    root=roots[0];clients=children.get(root,[]);require(clients,'No load-test requests')
    used={root};chains={}
    def checked(key,service,kind,remote):
        require(key in index,'Missing parent span')
        row=index[key];span=row['raw']
        require(row['service']==service and span['SpanKind']==kind,'Unexpected service/span kind')
        require(span['Parent']['Remote']==remote,'Unexpected local/remote parent')
        require(key not in used,'Span reused across requests');used.add(key)
        return key
    def child(parent,service,kind,remote):
        candidates=children.get(parent,[])
        require(len(candidates)==1,'Missing or ambiguous child span')
        return checked(candidates[0],service,kind,remote)
    for driver in clients:
        checked(driver,'driver',3,False)
        down=child(driver,'downstream',2,True)
        outgoing=child(down,'downstream',3,False)
        up=child(outgoing,'upstream',2,True)
        require(not children.get(up),'Unexpected upstream descendants')
        chains[driver]=dict(trace_id=driver[0],root_span=root[1],driver_span=driver[1],
                           downstream_server_span=down[1],downstream_client_span=outgoing[1],upstream_server_span=up[1])
    require(used==set(index),'Unmatched spans or incomplete parentage')
    return chains


def stitch_otel(upstream,downstream,documents):
    try:
        chains=span_chains(documents)
        require(upstream['status']==downstream['status']=='resolved','Incomplete local provenance')
        ups={};downs={}
        for row in upstream['results']:
            key=trace_key(row['incoming_trace']);require(key not in ups,'Ambiguous upstream request');ups[key]=row
        for row in downstream['results']:
            key=trace_key(row['incoming_trace']);require(key not in downs,'Ambiguous downstream request');downs[key]=row
        require(set(downs)==set(chains),'SDK requests differ from observed downstream scopes')
        by_request={};matched=set()
        for key,down in downs.items():
            chain=chains[key];outgoing=(key[0],chain['downstream_client_span'])
            require(trace_key(down['transfer']['trace'])==outgoing,'Observed injection differs from SDK client span')
            require(outgoing in ups,'Missing observed upstream scope for SDK span')
            matched.add(outgoing);by_request[down['request_id']]=(down['incoming_trace'],chain)
        require(matched==set(ups),'Unmatched upstream scopes')
        joined=stitch(upstream,downstream)
        require(joined['status']=='resolved','HTTP field evidence incomplete: '+str(joined.get('results')))
        for row in joined['results']:
            row['request_trace'],row['evidence']['sdk_spans']=by_request[row['downstream_request']]
        joined['scope']='One synchronous HTTP call; verified SDK parentage and observed fixed JSON field boundaries'
        joined['trace_validation']=dict(chains=len(chains),spans=1+4*len(chains),provider='OpenTelemetry Go 1.38.0')
        return joined
    except (ValueError,KeyError,TypeError,IndexError) as exc:
        return dict(status='unknown',reason=str(exc),results=[],oracle_used_for_inference=False)


def negative_span_checks(upstream,downstream,documents):
    rows=[]
    for name in ('missing_span','duplicate_span','wrong_parent','wrong_service','wrong_kind','wrong_observed_client'):
        docs=deepcopy(documents);down=deepcopy(downstream)
        if name=='missing_span':docs['upstream'].pop()
        elif name=='duplicate_span':docs['upstream'].append(deepcopy(docs['upstream'][0]))
        elif name=='wrong_parent':docs['upstream'][0]['Parent']['SpanID']=docs['upstream'][0]['SpanContext']['SpanID']
        elif name=='wrong_service':docs['downstream'][0]['Resource']=[dict(Key='service.name',Value=dict(Value='upstream'))]
        elif name=='wrong_kind':docs['upstream'][0]['SpanKind']=3
        else:down['results'][0]['transfer']['trace']=down['results'][0]['incoming_trace']
        result=stitch_otel(upstream,down,docs)
        rows.append(dict(case=name,passed=result['status']=='unknown'))
    return rows
