"""Read-only admission check of native workload/OTel/protobuf boundary evidence.

Does NOT infer field provenance or assign accuracy metrics. Matches RPCs by
SDK parentage and local message pointers, then checks values; never matches by
equal content. Typed payload snapshots are reserializations, not raw wire data.
"""
import argparse
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path

from contract import PRODUCT, CONVERT, manifest


def require(ok, why):
    if not ok:
        raise ValueError(why)


def one(rows, why):
    require(len(rows)==1, why)
    return rows[0]


def key(row):
    c = row.get('context',row)
    return c['trace_id'], c['span_id']


def value(message, path):
    data = message['fields']
    for p in path.split('.'):
        data = data[p]
    return int(data)


def inspect(catalog, checkout, truth):
    for role, rows in [('productcatalog',catalog),('checkout',checkout)]:
        require(rows and all(r['role']==role for r in rows),'process role')
        require([r['sequence'] for r in rows]==list(range(1,len(rows)+1)),'record sequence')
        require(one([r for r in rows if r['kind']=='finish'],'finish')['success'],'native failure')
        require(len({r['pid'] for r in rows})==1,'process identity')
    require(catalog[0]['pid']!=checkout[0]['pid'],'services must use different OS processes')
    spans = {}
    for row in catalog+checkout:
        if row['kind']=='span':
            require(key(row) not in spans,'duplicate span')
            require(len(row['trace_id'])==32 and int(row['trace_id'],16)>0 and
                    len(row['span_id'])==16 and int(row['span_id'],16)>0,'span ID')
            spans[key(row)] = row
    def span(k, role, kind):
        require(k in spans,'missing span')
        r = spans[k]
        require(r['role']==role and r['span_kind']==kind,'span role/kind')
        return r
    inputs = one([r for r in catalog if r['kind']=='catalog'],'catalogue snapshot')['message']['fields']['products']
    require(one([r for r in catalog if r['kind']=='catalog_end'],'final catalogue snapshot')['message']['fields']['products']==inputs,
            'immutable catalogue contract')
    catalog_records=[r for r in catalog if r['kind']=='catalog_record']
    require(sorted(r['index'] for r in catalog_records)==list(range(len(inputs))),'catalogue object coverage')
    for record in catalog_records:
        require(record['message']['fields']==inputs[record['index']],'catalogue snapshot/object binding')
    begins = [r for r in checkout if r['kind']=='case_begin']
    ends = [r for r in checkout if r['kind']=='case_end']
    require(sorted(r['case'] for r in begins)==sorted(c['name'] for c in truth['cases']),'case coverage')
    require(sorted(r['case'] for r in ends)==sorted(c['name'] for c in truth['cases']),'case completion')
    require(len({key(r) for r in begins})==len(begins),'request instance isolation')
    replies = [r for r in checkout if r['kind']=='product_reply']
    targets = [r for r in checkout if r['kind']=='target']
    handlers = [r for r in catalog if r['kind']=='handler_return']
    matched_servers = set(); used_payloads = set(); checks=[]; successes=0; failures=0
    for case in truth['cases']:
        name=case['name'];begin=one([r for r in begins if r['case']==name],'case begin')
        require(begin['ids']==case['ids'],'workload input changed')
        root=span(key(begin),'checkout',1)
        require(root['name']==name and int(root['parent_span_id'],16)==0,'workload root')
        end=one([r for r in ends if r['case']==name],'case end')
        require(key(end)==key(begin),'case completion context')
        expected_failure=any(pid not in {p['id'] for p in inputs} for pid in case['ids'])
        expected_attempts=next((i+1 for i,pid in enumerate(case['ids']) if pid not in {p['id'] for p in inputs}),len(case['ids']))
        require(end['failed']==expected_failure and end['output_items']==(0 if expected_failure else len(case['ids'])),'business outcome')
        cr=[r for r in replies if r['case']==name];ct=[r for r in targets if r['case']==name]
        require(sorted(r['ordinal'] for r in cr)==list(range(expected_attempts)),'RPC attempt coverage')
        for reply in cr:
            ordinal=reply['ordinal'];require(reply['requested_id']==case['ids'][ordinal],'requested record')
            require(key(reply)==key(begin),'checkout local request context')
            if reply['failed']:
                failures+=1
                require(ordinal==expected_attempts-1 and expected_failure,'unexpected RPC failure')
                # Even unsuccessful calls must have a matched native request payload and server span.
                requests=[r for r in checkout if r['kind']=='payload' and r['direction']=='out' and
                          r['method']==PRODUCT and r['message']['fields']['id']==reply['requested_id'] and
                          spans.get(key(r),{}).get('parent_span_id')==root['span_id'] and
                          r['context']['trace_id']==root['trace_id']]
                cp=one(requests,'failed request instance')
            else:
                successes+=1
                require(reply['message']['field_numbers']['price_usd']==5,'Product schema')
                require(reply['message']['fields']['id']==reply['requested_id'],'returned record identity')
                cp=one([r for r in checkout if r['kind']=='payload' and r['direction']=='in' and
                        r['method']==PRODUCT and r['message']['pointer']==reply['message']['pointer']], 'decoded reply object binding')
                target=one([r for r in ct if r['ordinal']==ordinal],'target coverage')
                require(target['from_pointer']==reply['price_pointer'],'original checkout field object binding')
                require(target['message']['field_numbers']['from']==1,'Convert schema')
                require(not target['context']['valid'],'original context.TODO contract changed')
                for field in ('units','nanos'):
                    annotation=one([q for q in truth['queries'] if q['case']==name and q['ordinal']==ordinal and
                                    q['target'].endswith('.'+field)],'query registration')
                    require(annotation['expected_status']=='target','target outside contract')
                    source=annotation['source'];p=inputs[source['catalog_index']]
                    require(p['id']==source['product_id'],'catalogue record identity')
                    expected=annotation['expected_value']
                    require(int(p['price_usd'][field])==expected and
                            value(reply['message'],'price_usd.'+field)==expected and
                            value(target['message'],'from.'+field)==expected,'independent input/value check')
            client=span(key(cp),'checkout',3)
            require(client['parent_trace_id']==root['trace_id'] and client['parent_span_id']==root['span_id'] and
                    client['name'].endswith('ProductCatalogService/GetProduct'),'product RPC parentage')
            server=one([r for r in spans.values() if r['role']=='productcatalog' and r['span_kind']==2 and
                        (r['parent_trace_id'],r['parent_span_id'])==key(client)],'server RPC parentage')
            require(server['parent_remote'] and server['trace_id']==client['trace_id'],'remote context propagation')
            require(key(server) not in matched_servers,'RPC server instance reused');matched_servers.add(key(server))
            handler=one([r for r in handlers if key(r)==key(server)],'handler return binding')
            require(handler['method']==PRODUCT and handler['failed']==reply['failed'],'handler status')
            request=one([r for r in catalog if r['kind']=='payload' and r['direction']=='in' and
                         r['method']==PRODUCT and key(r)==key(server)],'server request payload')
            require(request['message']['fields']['id']==reply['requested_id'],'actual server request')
            client_request=one([r for r in checkout if r['kind']=='payload' and r['direction']=='out' and
                                r['method']==PRODUCT and key(r)==key(client)],'client request payload')
            require(client_request['message']['fields']['id']==reply['requested_id'] and
                    client_request['message']['snapshot_hex']==request['message']['snapshot_hex'],'bound request snapshot mismatch')
            if reply['failed']:
                require(not [r for r in catalog+checkout if r['kind']=='payload' and r['method']==PRODUCT and
                             ((r['role']=='productcatalog' and r['direction']=='out' and key(r)==key(server)) or
                              (r['role']=='checkout' and r['direction']=='in' and key(r)==key(client)))],'response payload after failed product call')
            if not reply['failed']:
                annotation=one([q for q in truth['queries'] if q['case']==name and q['ordinal']==ordinal and
                                q['target'].endswith('.units')],'source registration')
                record=one([r for r in catalog_records if r['index']==annotation['source']['catalog_index']], 'catalogue source object')
                require(handler['message']['pointer']==record['message']['pointer'] and
                        handler['price_pointer']==record['price_pointer'],'handler catalogue field instance binding')
                outbound=one([r for r in catalog if r['kind']=='payload' and r['direction']=='out' and
                              r['method']==PRODUCT and key(r)==key(server)],'server response payload')
                require(outbound['message']['pointer']==handler['message']['pointer'],'native response object binding')
                # Equality verifies an already identity-bound RPC; it never establishes that identity.
                require(outbound['message']['snapshot_hex']==cp['message']['snapshot_hex']==reply['message']['snapshot_hex'],
                        'bound protobuf snapshot mismatch')
                for payload in (outbound,cp):
                    require(payload['payload_bytes']==len(bytes.fromhex(payload['message']['snapshot_hex'])) and
                            payload['grpc_frame_bytes']==payload['payload_bytes']+5,'uncompressed protobuf payload length')
                    identity=(payload['role'],payload['sequence']);require(identity not in used_payloads,'payload reused');used_payloads.add(identity)
                checks.append(dict(case=name,ordinal=ordinal,trace_id=client['trace_id'],client_span=client['span_id'],
                                   server_span=server['span_id'],target_fields=2))
        require(len(ct)==sum(not r['failed'] for r in cr),'extra or missing target')
    require(len(matched_servers)==len(handlers),'unmatched handler/RPC')
    require(len(targets)==successes,'unmatched target')
    require(sum(r['kind']=='payload' and r['method']==PRODUCT and r['direction']=='out' for r in checkout)==successes+failures,
            'unmatched product request payload')
    require(sum(r['kind']=='payload' and r['method']==PRODUCT and r['direction']=='in' for r in catalog)==successes+failures,
            'unmatched server request payload')
    detached=[]
    for target in targets:
        payload=one([r for r in checkout if r['kind']=='payload' and r['direction']=='out' and r['method']==CONVERT and
                     r['message']['pointer']==target['message']['pointer']],'native outgoing target request')
        currency_client=span(key(payload),'checkout',3)
        require(int(currency_client['parent_span_id'],16)==0 and int(currency_client['parent_trace_id'],16)==0,
                'currency call unexpectedly has a parent')
        require(payload['message']['snapshot_hex']==target['message']['snapshot_hex'],'native target request snapshot')
        detached.append(key(currency_client))
    require(len(set(detached))==len(targets),'currency RPC instances merged')
    parallel_names={c['name'] for c in truth['cases'] if c['concurrent']}
    intervals=[s for s in spans.values() if s['role']=='checkout' and s['span_kind']==1 and s['name'] in parallel_names]
    points=[(datetime.fromisoformat(s[t].replace('Z','+00:00')),delta)
            for s in intervals for t,delta in [('start',1),('end',-1)]]
    active=peak=0
    for _,delta in sorted(points):
        active+=delta;peak=max(active,peak)
    require(not parallel_names or peak>=2,'concurrent workload did not overlap')
    all_responses=[r for r in catalog+checkout if r['kind']=='payload' and r['method']==PRODUCT and
                   ((r['role']=='productcatalog' and r['direction']=='out') or (r['role']=='checkout' and r['direction']=='in'))]
    require(len(all_responses)==len(used_payloads),'unmatched product response payload')
    return dict(status='verified_native_boundary_preflight',native_processes=2,
                workload_instances=len(begins),distinct_input_payloads=len({tuple(c['ids']) for c in truth['cases']}),
                concurrent_workload_instances=sum(c['concurrent'] for c in truth['cases']),
                observed_peak_overlapping_workloads=peak,
                product_rpc_attempts=successes+failures,successful_product_rpcs=successes,failed_product_rpcs=failures,
                registered_queries=len(truth['queries']),confirmed_target_fields=2*successes,
                no_target_checks=sum(q['expected_status']=='no_target' for q in truth['queries']),
                native_rpcs=checks,original_convert_context_absent_at_target=len(targets),
                native_currency_detached_traces=len(detached),
                tracefusion_provenance_executed=False,external_tool_executed=False,
                accuracy_eligible=False,performance_eligible=False,selective_collection=False,
                scope='Two-process original product handler / original checkout method workload, not full deployment',
                limitations=truth['exclusions']+['Typed payload snapshots do not constitute raw wire-byte recording',
                                              'Native observer object/trace checks are admission evidence, not algorithmic provenance answers'])


def rejection_checks(catalog, checkout, truth):
    results=[]
    for name in ('missing_server_span','duplicate_payload','wrong_remote_parent','same_value_wrong_object',
                 'same_value_wrong_catalog_record','missing_target'):
        a,b=deepcopy(catalog),deepcopy(checkout)
        if name=='missing_server_span':
            a.remove(next(r for r in a if r['kind']=='span'))
        elif name=='duplicate_payload':
            b.append(deepcopy(next(r for r in b if r['kind']=='payload')))
        elif name=='wrong_remote_parent':
            next(r for r in a if r['kind']=='span')['parent_span_id']='f'*16
        elif name=='same_value_wrong_object':
            xs=[r for r in b if r['kind']=='target' and r['case']=='equal-distinct']
            require(len(xs)==2,'same-value rejection fixture')
            xs[0]['from_pointer']=xs[1]['from_pointer']
        elif name=='same_value_wrong_catalog_record':
            first=next(r for r in a if r['kind']=='catalog_record' and r['message']['fields']['id']=='66VCHSJNUP')
            other=next(r for r in a if r['kind']=='catalog_record' and r['message']['fields']['id']=='0PUK6V6EV0')
            require(first['message']['fields']['price_usd']==other['message']['fields']['price_usd'],'equal-price original catalogue')
            row=next(r for r in a if r['kind']=='handler_return' and not r['failed'] and
                     r['message']['fields']['id']=='66VCHSJNUP')
            row['message']['pointer']=other['message']['pointer'];row['price_pointer']=other['price_pointer']
        else:
            b.remove(next(r for r in b if r['kind']=='target'))
        # Keep the framing sequence valid so substantive checks reject the mutation.
        for rows in (a,b):
            for i,r in enumerate(rows,1):r['sequence']=i
        try:inspect(a,b,truth)
        except (ValueError,KeyError) as e:results.append(dict(case=name,rejected=True,reason=str(e)))
        else:raise ValueError('Accepted damaged evidence: '+name)
    return results


def read(path):
    return [json.loads(s) for s in path.read_text().splitlines() if s.strip()]


def verify_directory(directory):
    source_manifest=json.loads((directory/'source-manifest.json').read_text())
    for name,digest in source_manifest.items():
        copied=directory/'source'/Path(name).relative_to('src') if name.startswith('src/') else directory/'source'/'demo.proto'
        require(hashlib.sha256(copied.read_bytes()).hexdigest()==digest,'copied upstream source digest: '+name)
    truth=json.loads((directory/'contract.json').read_text())
    require(truth==manifest(directory/'source/productcatalogservice/products.json'),'contract differs from frozen source/workload')
    catalog,checkout=read(directory/'catalog.jsonl'),read(directory/'checkout.jsonl')
    report=inspect(catalog,checkout,truth)
    report['rejection_checks']=rejection_checks(catalog,checkout,truth)
    report['evidence_sha256']={name:hashlib.sha256((directory/name).read_bytes()).hexdigest()
                               for name in ('catalog.jsonl','checkout.jsonl','contract.json','source-manifest.json')}
    report['verifier_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);a=p.parse_args()
    print(json.dumps(verify_directory(a.directory),indent=2))
