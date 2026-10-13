#!/usr/bin/env python3
"""Evaluate independent TraceFusion answers against frozen contracts and callee wire bodies."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
from audit_rpc_wire import headers, one, values


def audit(run):
    result = json.loads((run / 'result.json').read_text())
    if result['mode'] != 'tracefusion' or result['status'] != 'business-preflight-passed':
        raise ValueError('Requires completed independent frontend business run')
    inferred = json.loads((run / 'inference.json').read_text())
    raw = (run / 'tracefusion-events/events.jsonl').read_bytes()
    if hashlib.sha256(raw).hexdigest() != inferred['event_sha256']:
        raise ValueError('Inference does not match raw observation snapshot')
    events = [json.loads(line) for line in raw.splitlines()]
    entries = {e['frame']: e for e in events if e['kind'] == 'enter'}
    requests = {e['rpc']: e for e in events if e['kind'] == 'rpc-enter'}
    responses = {e['rpc']: e for e in events if e['kind'] == 'rpc-exit'}
    metadata = json.loads((run / 'capture-metadata.json').read_text())
    request_index = defaultdict(list)
    for e in requests.values():
        request_index[(e['trace_id'], e['span_id'], e['method'], e['uri'])].append(e)
    source_index = defaultdict(list)
    decoded_sources = {}
    joins, issues, hashes, stats = [], [], {}, {}
    manifest = json.loads((run / 'cases.json').read_text())
    expected_cases = [c['id'] for c in manifest['cases']] + ['parallel-' + str(i) for i in range(manifest['concurrent']['count'])]
    recorded_cases = [c['case'] for c in result['cases']]
    if len(recorded_cases) != len(set(recorded_cases)) or set(recorded_cases) != set(expected_cases):
        issues.append({'reason': 'workload-case-registry-coverage-gap-or-duplicate'})
    span_ids = set()
    for service in ('carts', 'user', 'payment', 'shipping'):
        folder = run / 'wire' / service
        stats[service] = json.loads((folder / 'capture-result.json').read_text())
        for name in ('http.pcap', 'http.json', 'capture-result.json'):
            file = folder / name
            hashes[str(file.relative_to(run))] = hashlib.sha256(file.read_bytes()).hexdigest()
        packets = json.loads((folder / 'http.json').read_text())
        wire_requests, wire_responses = {}, defaultdict(list)
        for packet in packets:
            layers = packet['_source']['layers']
            http = layers['http']
            key = (one(layers['tcp'], 'tcp.stream'), one(layers['frame'], 'frame.number'))
            if values(http, 'http.request'):
                wire_requests[key] = layers
            if values(http, 'http.response'):
                wire_responses[(key[0], one(http, 'http.request_in'))].append(layers)
        for (stream, frame), layers in wire_requests.items():
            http = layers['http']
            h = headers(http)
            uri = one(http, 'http.request.full_uri')
            method = one(http, 'http.request.method')
            key = (h.get('x-b3-traceid'), h.get('x-b3-parentspanid'), method, uri)
            candidates, returned = request_index.get(key, []), wire_responses.get((stream, frame), [])
            invocation = {'service': service, 'stream': stream, 'request_frame': frame, 'uri': uri,
                          'trace_id': key[0], 'wire_span_id': h.get('x-b3-spanid')}
            if len(candidates) != 1 or len(returned) != 1 or not h.get('x-b3-spanid'):
                issues.append({'invocation': invocation, 'reason': 'ambiguous-or-missing-RPC'})
                continue
            request, returned = candidates[0], returned[0]
            response_frame = one(returned['frame'], 'frame.number')
            endpoints_valid = (one(layers['ip'], 'ip.src') == metadata['containers']['orders']['ip']
                               and one(layers['ip'], 'ip.dst') == metadata['containers'][service]['ip']
                               and one(returned['ip'], 'ip.src') == metadata['containers'][service]['ip']
                               and one(returned['ip'], 'ip.dst') == metadata['containers']['orders']['ip'])
            if not endpoints_valid or one(http, 'http.response_in') != response_frame or urlsplit(uri).hostname != service:
                issues.append({'invocation': invocation, 'reason': 'connection-identity-mismatch'})
                continue
            if str(responses[request['rpc']]['status']) != one(returned['http'], 'http.response.code'):
                issues.append({'invocation': invocation, 'reason': 'response-status-mismatch'})
                continue
            span_key = (key[0], h['x-b3-spanid'])
            if span_key in span_ids:
                issues.append({'invocation': invocation, 'reason': 'duplicate-wire-span'})
            span_ids.add(span_key)
            invocation.update(rpc=request['rpc'], response_frame=response_frame)
            joins.append(invocation)
            if service not in ('carts', 'user') or method != 'GET':
                continue
            body = json.loads(bytes.fromhex(one(returned['http'], 'http.file_data').replace(':', '')).decode())
            invocation['body_size'] = len(body) if isinstance(body, list) else None
            records = list(enumerate(body)) if isinstance(body, list) else [(None, body)]
            for index, record in records:
                if not isinstance(record, dict) or not record.get('id'):
                    issues.append({'invocation': invocation, 'reason': 'missing-wire-record-id'})
                    continue
                for field, value in record.items():
                    if isinstance(value, (dict, list)):
                        continue
                    path = f'result#body[{index}]#{field}' if index is not None else 'result#body#content#' + field
                    json_path = f'$[{index}].{field}' if index is not None else '$.' + field
                    coordinate = (service, stream, frame, response_frame, json_path, record['id'])
                    source_index[(key[0], service, urlsplit(uri).path, record['id'], field)].append(coordinate)
                    decoded_sources[(request['rpc'], path)] = (coordinate, value)
    joined_ids = [j['rpc'] for j in joins]
    if len(joined_ids) != len(set(joined_ids)) or set(joined_ids) != set(requests):
        issues.append({'reason': 'RPC-coverage-gap-or-duplicate'})
    inventory = {tuple(s['coordinate']): s for s in inferred['sources']}
    checks, no_targets = [], []
    for business in result['cases']:
        contract = json.loads((run / business['case'] / 'query-contract.json').read_text())
        trace = contract['trace_id_requested']
        answers = [a for a in inferred['answers'] if entries[a['root_frame']]['trace_id'] == trace]
        if not contract['expected_target']:
            no_targets.append({'case': business['case'], 'checks': len(contract['queries']), 'passed': not answers})
            continue
        answer = answers[0] if len(answers) == 1 else None
        fields = {f['path']: f for f in answer['fields']} if answer else {}
        target_valid = fields.get('arg#id', {}).get('observed', {}).get('value') == business['order_id']
        for query in contract['queries']:
            path = 'arg#' + query['target'].replace('.', '#')
            match = re.fullmatch(r'items\[itemId=(.*)\]\.(.*)', query['target'])
            if match:
                indices = [m[1] for p, f in fields.items() if (m := re.fullmatch(r'arg#items\[(\d+)\]#itemId', p))
                           and f['observed'].get('value') == match[1]]
                path = f'arg#items[{indices[0]}]#{match[2]}' if len(indices) == 1 else '<ambiguous-item>'
            expected, actual, unknown = set(), set(), []
            for source in query['sources']:
                coordinates = source_index.get((trace, source['service'], source['route'], source['record_id'], source['field']), [])
                if len(coordinates) != 1:
                    unknown.append({'expected': source, 'matches': len(coordinates)})
                else:
                    expected.add(coordinates[0])
            field = fields.get(path)
            if field:
                for source in field['sources']:
                    key = tuple(source)
                    decoded, observed = decoded_sources.get(key), inventory.get(key)
                    if decoded is None or observed is None or observed['observed'].get('value') != decoded[1]:
                        unknown.append({'reported': source, 'reason': 'wire-source-unresolved-or-payload-different'})
                    else:
                        actual.add(decoded[0])
            status = ('unresolved' if not target_valid or not field or field['status'] != 'resolved' or unknown
                      else 'agreement' if expected == actual else 'mismatch')
            checks.append({'case': business['case'], 'target': query['target'], 'profile': query['profile'], 'status': status,
                           'expected': sorted(expected), 'actual': sorted(actual), 'unknown': unknown})
    passed = (not issues and not result.get('frontend_errors') and not result.get('capture_errors')
              and all(s['socket_drops'] == 0 and s['saved_packets'] > 0 for s in stats.values())
              and all(c['status'] == 'agreement' for c in checks) and all(c['passed'] for c in no_targets))
    return {'schema': 'tracefusion-service-calibration-v1', 'run': str(run.resolve()),
            'calibration_passed': passed, 'provenance_engine_run': True, 'mirror_taint_loaded': False,
            'business_cases_passed': sum(c['business_passed'] for c in result['cases']), 'target_queries': len(checks),
            'query_status': dict(Counter(c['status'] for c in checks)), 'profiles': dict(Counter(c['profile'] for c in checks)),
            'no_target_checks': sum(c['checks'] for c in no_targets), 'no_target_results': no_targets,
            'observed_rpc_instances': len(requests), 'joined_wire_instances': len(joins),
            'expected_workload_cases': len(expected_cases), 'recorded_workload_cases': len(recorded_cases),
            'source_join_basis': 'Exact container endpoints, TCP request/response back-references and B3 parent/child plus method/URI; engine relations use object/field/version only',
            'engine_input_basis': 'Raw DTO/stream observations and summaries derived from actual class bytes; no expected answer, MirrorTaint output or wire payload supplied to engine',
            'capture_statistics': stats, 'issues': issues, 'raw_sha256': hashes,
            'accuracy_eligible': False, 'performance_eligible': False,
            'limitations': ['Bounded read-only DTO aliases and audited sequential stream/float/constructor path, not general Java support.',
                            'Wire reference is independent of source-label inference; human review and full source/image correspondence remain outstanding.',
                            'Callee internal database propagation, asynchronous RabbitMQ delivery and arbitrary repeated calls are outside scope.'],
            'rpc_joins': joins, 'queries': checks}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.run)
    args.out.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ('rpc_joins', 'queries', 'raw_sha256')}, indent=2))
    raise SystemExit(0 if report['calibration_passed'] else 1)
