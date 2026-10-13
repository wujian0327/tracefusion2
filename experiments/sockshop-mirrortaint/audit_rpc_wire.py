#!/usr/bin/env python3
"""Validate actual HTTP peer instances and field contracts using independent wire bodies."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
import audit_adapted


def values(tree, key):
    found = []
    if isinstance(tree, dict):
        for name, value in tree.items():
            if name == key:
                found.extend(value if isinstance(value, list) else [value])
            else:
                found.extend(values(value, key))
    elif isinstance(tree, list):
        for child in tree:
            found.extend(values(child, key))
    return found


def one(tree, key):
    found = values(tree, key)
    if len(found) != 1:
        raise ValueError(f'Expected unique {key}, found {len(found)}')
    return found[0]


def headers(http):
    parsed = defaultdict(list)
    for line in values(http, 'http.request.line'):
        name, _, value = line.partition(':')
        parsed[name.lower()].append(value.strip())
    return {name: value[0] for name, value in parsed.items() if len(value) == 1}


def audit(run):
    calibration = audit_adapted.audit(run)
    result = json.loads((run / 'result.json').read_text())
    metadata = json.loads((run / 'capture-metadata.json').read_text())
    events = [json.loads(line) for line in next(run.glob('agent-logs/orders/**/adapted-events.jsonl')).read_text().splitlines()]
    agent_requests = [e for e in events if e['phase'] == 'rpc-request']
    agent_responses = {e['rpc_request_event']: e for e in events if e['phase'] == 'rpc-response'}
    agent_index = defaultdict(list)
    for e in agent_requests:
        agent_index[(e['trace_id'], e['span_id'], e['fields']['arg1#method']['value'],
                     e['fields']['arg1#url']['value'])].append(e)
    source_index = defaultdict(list)
    coordinate_index = {}
    invocations = []
    issues = []
    hashes = {}
    stats = {}
    for service in ('carts', 'user', 'payment', 'shipping'):
        folder = run / 'wire' / service
        stats[service] = json.loads((folder / 'capture-result.json').read_text())
        for name in ('http.pcap', 'http.json', 'capture-result.json'):
            f = folder / name
            hashes[str(f.relative_to(run))] = hashlib.sha256(f.read_bytes()).hexdigest()
        packets = json.loads((folder / 'http.json').read_text())
        wire_requests = {}
        wire_responses = defaultdict(list)
        for packet in packets:
            layers = packet['_source']['layers']
            http = layers['http']
            frame = one(layers['frame'], 'frame.number')
            stream = one(layers['tcp'], 'tcp.stream')
            if values(http, 'http.request'):
                wire_requests[(stream, frame)] = layers
            if values(http, 'http.response'):
                wire_responses[(stream, one(http, 'http.request_in'))].append(layers)
        for (stream, frame), layers in wire_requests.items():
            http = layers['http']
            h = headers(http)
            uri = one(http, 'http.request.full_uri')
            method = one(http, 'http.request.method')
            invocation = {'service': service, 'tcp_stream': stream, 'request_frame': frame,
                          'trace_id': h.get('x-b3-traceid'), 'wire_span_id': h.get('x-b3-spanid'),
                          'parent_span_id': h.get('x-b3-parentspanid'), 'method': method, 'uri': uri}
            invocations.append(invocation)
            if (one(layers['ip'], 'ip.src') != metadata['containers']['orders']['ip']
                    or one(layers['ip'], 'ip.dst') != metadata['containers'][service]['ip']
                    or urlsplit(uri).hostname != service):
                issues.append({'invocation': invocation, 'reason': 'endpoint-identity-mismatch'})
                continue
            # Sleuth creates an HTTP client child span after the original agent's
            # pre-call hook. Join via the actual wire parent, never trace alone.
            key = (h.get('x-b3-traceid'), h.get('x-b3-parentspanid'), method, uri)
            candidates = agent_index.get(key, [])
            responses = wire_responses.get((stream, frame), [])
            if not h.get('x-b3-spanid') or len(candidates) != 1 or len(responses) != 1:
                issues.append({'invocation': invocation, 'reason': 'missing-or-ambiguous-instance',
                               'agent_matches': len(candidates), 'response_matches': len(responses)})
                continue
            request = candidates[0]
            response = responses[0]
            response_frame = one(response['frame'], 'frame.number')
            if one(http, 'http.response_in') != response_frame:
                issues.append({'invocation': invocation, 'reason': 'response-back-reference-mismatch'})
                continue
            if (one(response['ip'], 'ip.src') != metadata['containers'][service]['ip']
                    or one(response['ip'], 'ip.dst') != metadata['containers']['orders']['ip']):
                issues.append({'invocation': invocation, 'reason': 'response-endpoint-mismatch'})
                continue
            consumed = agent_responses.get(request['event_id'])
            if consumed is None:
                issues.append({'invocation': invocation, 'reason': 'missing-consumed-response'})
                continue
            code = one(response['http'], 'http.response.code')
            status = consumed['fields'].get('result#statusCode', {}).get('value')
            if str(status) != code:
                issues.append({'invocation': invocation, 'reason': 'response-status-mismatch'})
                continue
            invocation.update(response_frame=response_frame, http_status=code,
                              agent_request_event=request['event_id'], agent_response_event=consumed['event_id'])
            body_data = values(response['http'], 'http.file_data')
            if not body_data:
                # Empty DELETE response is still a valid invocation, not a source body.
                continue
            if len(body_data) != 1:
                issues.append({'invocation': invocation, 'reason': 'ambiguous-response-body'})
                continue
            payload = json.loads(bytes.fromhex(body_data[0].replace(':', '')).decode('utf-8'))
            invocation['body_sha256'] = hashlib.sha256(bytes.fromhex(body_data[0].replace(':', ''))).hexdigest()
            if service not in ('carts', 'user') or method != 'GET':
                continue
            objects = list(enumerate(payload)) if isinstance(payload, list) else [(None, payload)]
            for index, obj in objects:
                if not isinstance(obj, dict) or not obj.get('id'):
                    issues.append({'invocation': invocation, 'reason': 'missing-wire-record-identity'})
                    continue
                for field, value in obj.items():
                    if isinstance(value, (dict, list)):
                        continue
                    consumer_path = (f'result#body[{index}]#{field}' if index is not None
                                     else 'result#body#content#' + field)
                    json_path = (f'$[{index}].{field}' if index is not None else '$.' + field)
                    coordinate = (service, stream, frame, response_frame, json_path, obj['id'])
                    source_index[(invocation['trace_id'], service, urlsplit(uri).path, obj['id'], field)].append(coordinate)
                    coordinate_index[(consumed['event_id'], consumer_path)] = (coordinate, value)
    joined = [i for i in invocations if 'agent_request_event' in i]
    joined_ids = [i['agent_request_event'] for i in joined]
    wire_span_keys = [(i['trace_id'], i['wire_span_id']) for i in invocations]
    if len(joined_ids) != len(set(joined_ids)):
        issues.append({'reason': 'multiple-wire-invocations-for-one-agent-request'})
    if set(joined_ids) != {e['event_id'] for e in agent_requests}:
        issues.append({'reason': 'agent-request-coverage-gap'})
    if len(wire_span_keys) != len(set(wire_span_keys)):
        issues.append({'reason': 'duplicate-wire-span-identity'})
    checks = []
    event_by_id = {e['event_id']: e for e in events}
    for case in calibration['cases']:
        contract = json.loads((run / case['case'] / 'query-contract.json').read_text())
        for observed, query in zip(case['queries'], contract['queries']):
            expected, actual = set(), set()
            unknown = []
            for source in query['sources']:
                key = (case['trace_id'], source['service'], source['route'], source['record_id'], source['field'])
                coordinates = source_index.get(key, [])
                if len(coordinates) != 1:
                    unknown.append({'expected': source, 'matches': len(coordinates)})
                else:
                    expected.add(coordinates[0])
            for coord in observed['actual']:
                decoded = coordinate_index.get(tuple(coord))
                if decoded is None:
                    unknown.append({'reported': coord, 'reason': 'unmapped-wire-source'})
                else:
                    coordinate, wire_value = decoded
                    consumer_value = event_by_id[coord[0]]['fields'][coord[1]].get('value')
                    if wire_value != consumer_value:
                        unknown.append({'reported': coord, 'reason': 'wire-consumer-payload-mismatch'})
                    actual.add(coordinate)
            status = ('unresolved' if observed['status'] == 'unresolved' or unknown
                      else 'agreement' if actual == expected else 'mismatch')
            checks.append({'case': case['case'], 'target': query['target'], 'status': status,
                           'expected_wire_sources': sorted(expected), 'reported_wire_sources': sorted(actual), 'unknown': unknown})
    passed = (calibration['calibration_passed'] and not issues and not result['capture_errors']
              and all(s['socket_drops'] == 0 and s['saved_packets'] > 0 for s in stats.values())
              and all(q['status'] == 'agreement' for q in checks))
    handler_checks = []
    observer_errors = [line for line in (run / 'compose.log').read_text(errors='replace').splitlines()
                       if 'TF2_HTTP_OBSERVER error' in line]
    server_evidence_available = all((run / 'server' / name / 'server-events.jsonl').exists()
                                    for name in ('carts', 'shipping'))
    if server_evidence_available:
        for service in ('carts', 'shipping'):
            server_log = run / 'server' / service / 'server-events.jsonl'
            hashes[str(server_log.relative_to(run))] = hashlib.sha256(server_log.read_bytes()).hexdigest()
            server_events = [json.loads(line) for line in server_log.read_text().splitlines()]
            controller_events = [json.loads(line) for line in next(run.glob('agent-logs/' + service + '/**/adapted-events.jsonl')).read_text().splitlines()]
            for invocation in (i for i in joined if i['service'] == service):
                entries = [e for e in server_events if e['phase'] == 'enter'
                           and e['X-B3-TraceId'] == invocation['trace_id']
                           and e['X-B3-SpanId'] == invocation['wire_span_id']
                           and e['X-B3-ParentSpanId'] == invocation['parent_span_id']
                           and e['method'] == invocation['method'] and e['uri'] == urlsplit(invocation['uri']).path]
                check = {'service': service, 'agent_request_event': invocation['agent_request_event'], 'status': 'unresolved'}
                handler_checks.append(check)
                if len(entries) != 1:
                    check['reason'] = 'ambiguous-or-missing-servlet-entry'
                    continue
                entry = entries[0]
                own = [e for e in server_events if e['invocation_id'] == entry['invocation_id']]
                exits = [e for e in own if e['phase'] == 'exit']
                dispatches = [e for e in own if e['phase'] == 'handler']
                if (len(exits) != 1 or len(dispatches) != 1
                        or str(exits[0]['http_status']) != invocation['http_status']):
                    check['reason'] = 'incomplete-or-ambiguous-dispatch'
                    continue
                dispatch = dispatches[0]
                if any(e['thread_id'] != entry['thread_id'] or e['trace_id'] != invocation['trace_id'] for e in own):
                    check['reason'] = 'servlet-context-changed'
                    continue
                sinks = [e for e in controller_events if e['phase'] == 'sink'
                         and e['owner'] == dispatch['controller_owner'] and e['method'] == dispatch['controller_method']
                         and e['trace_id'] == invocation['trace_id'] and e['thread_id'] == entry['thread_id']
                         and e['span_id'] == dispatch['dispatch_span_id']]
                # This checks execution identity and complete return logging, not
                # callee taint propagation. An inactive heap must remain visible.
                if len(sinks) != 1 or not sinks[0]['capture_complete']:
                    check['reason'] = 'ambiguous-or-missing-controller-return'
                    continue
                check.update(status='agreement', server_invocation_id=entry['invocation_id'],
                             server_span_id=entry['server_span_id'], controller_span_id=sinks[0]['span_id'],
                             controller_owner=dispatch['controller_owner'], controller_method=dispatch['controller_method'],
                             controller_return_event=sinks[0]['event_id'], callee_taint_heap_active=sinks[0]['available'])
    handler_passed = bool(passed and server_evidence_available and not observer_errors and handler_checks
                          and all(c['status'] == 'agreement' for c in handler_checks))
    return {'schema_version': 1, 'run': str(run.resolve()), 'wire_calibration_passed': passed,
            'cross_service_http_peer_join_validated': passed,
            'java_application_handler_join_validated': handler_passed,
            'java_handler_checks': len(handler_checks), 'java_handler_status': dict(Counter(c['status'] for c in handler_checks)),
            'java_handler_taint_heap_status': dict(Counter(str(c.get('callee_taint_heap_active')) for c in handler_checks)),
            'server_observer_errors': observer_errors,
            'scoped_orders_http_join_validated': handler_passed, 'full_cross_service_join_validated': False,
            'accuracy_eligible': False, 'performance_eligible': False,
            'business_cases_passed': sum(c['business_passed'] for c in result['cases']),
            'agent_rpc_requests': len(agent_requests), 'wire_http_invocations': len(invocations),
            'joined_rpc_instances': len(joined), 'service_invocations': dict(Counter(i['service'] for i in invocations)),
            'field_queries': len(checks), 'wire_query_status': dict(Counter(q['status'] for q in checks)),
            'capture_statistics': stats, 'issues': issues, 'raw_sha256': hashes,
            'limitations': ['Peer HTTP invocation identity is observed in the callee network namespace; it is not a Go/internal handler execution span.',
                            'Raw HTTP response bodies independently resolve frozen-contract sources. Companion labels are only decoded to actual wire coordinates.',
                            'B3 wire child/parent, method and URI must uniquely identify the pre-call hook. Repeated indistinguishable calls remain ambiguous.',
                            'No time or content equality is used to join RPCs; payload values are compared only after structural identity joins.',
                            'Java servlet invocation UUID links actual wire headers to observed MVC dispatch. Controller return requires unique method/trace/thread evidence; repeated ambiguous invocations remain unresolved.',
                            'Handler identity and complete return logging do not require or prove callee taint propagation; inactive Carts heaps and null source tags remain disclosed.',
                            'Scope excludes asynchronous RabbitMQ delivery, database write history and formal source/image and second-human oracle review.'],
            'invocations': invocations, 'queries': checks, 'handler_checks': handler_checks}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.run)
    args.out.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ('invocations', 'queries', 'handler_checks', 'raw_sha256')}, indent=2))
    required = report['wire_calibration_passed'] and (not (args.run / 'server').exists()
               or report['java_application_handler_join_validated'])
    raise SystemExit(0 if required else 1)
