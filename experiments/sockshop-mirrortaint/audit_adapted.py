#!/usr/bin/env python3
"""Check adapter calibration against frozen contracts; never claim formal accuracy."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit


def tokens(observation):
    return {source['A'] for source in (observation.get('tag') or {}).get('A', [])}


def audit(run):
    result = json.loads((run / 'result.json').read_text())
    if result['status'] != 'business-preflight-passed' or not result.get('integration_adapter_sha256'):
        raise ValueError('Requires completed, disclosed adapted run')
    log = next(run.glob('agent-logs/orders/**/adapted-events.jsonl'))
    events = [json.loads(line) for line in log.read_text().splitlines() if line.strip()]
    by_id = {e['event_id']: e for e in events}
    if len(by_id) != len(events):
        raise ValueError('Duplicate event identities')
    pairs = []
    label_index = defaultdict(set)
    source_index = defaultdict(list)
    for e in events:
        if e['phase'] != 'rpc-response':
            continue
        request = by_id.get(e['rpc_request_event'])
        if not request or request['phase'] != 'rpc-request':
            raise ValueError('Unpaired response')
        if any(e[k] != request[k] for k in ('trace_id', 'span_id', 'thread_id', 'method')):
            raise ValueError('RPC pair context mismatch')
        pairs.append(e['rpc_request_event'])
        url = urlsplit(request['fields']['arg1#url']['value'])
        for path, observation in e['fields'].items():
            # The label index decodes tool identifiers only. Expected relations use
            # the frozen contract plus actual response record identities below.
            coordinate = (e['event_id'], path)
            for token in tokens(observation):
                label_index[token].add(coordinate)
            match = re.fullmatch(r'result#body\[(\d+)\]#([^#]+)', path)
            if match:
                record_path = f'result#body[{match[1]}]#id'
                field = match[2]
            elif path.startswith('result#body#content#'):
                record_path = 'result#body#content#id'
                field = path.removeprefix('result#body#content#')
            else:
                continue
            identity = e['fields'].get(record_path, {}).get('value')
            if identity is None and path.startswith('result#body#content#'):
                # HAL DTOs omit their id; require the actual response's unique
                # self link to agree with the request URI before taking its id.
                self_links = [urlsplit(e['fields'].get(k.removesuffix('#rel') + '#href', {}).get('value', ''))
                              for k, v in e['fields'].items()
                              if k.startswith('result#body#links[') and k.endswith('#rel')
                              and v.get('value') == 'self']
                if len(self_links) == 1 and (self_links[0].hostname, self_links[0].path) == (url.hostname, url.path):
                    identity = self_links[0].path.rsplit('/', 1)[-1]
            key = (e['trace_id'], url.hostname, url.path, identity, field)
            source_index[key].append(coordinate)
    if len(pairs) != len(set(pairs)):
        raise ValueError('Multiple responses for one request')
    requests = {e['event_id'] for e in events if e['phase'] == 'rpc-request'}
    paired_requests_complete = requests == set(pairs)
    diagnostic_log = run / 'compose.log'
    adapter_errors = [line for line in diagnostic_log.read_text(errors='replace').splitlines()
                      if 'TF2_MT_ADAPTER error' in line] if diagnostic_log.exists() else []
    runtime_errors = [str(p.relative_to(run)) for p in (run / 'agent-logs').rglob('*error*.log')
                      if p.stat().st_size]

    cases = []
    for business in result['cases']:
        folder = run / business['case']
        contract_path = folder / 'query-contract.json'
        contract = json.loads(contract_path.read_text())
        fixture = json.loads((folder / 'fixture.json').read_text())
        trace = contract['trace_id_requested']
        targets = [e for e in events if e['phase'] == 'sink' and e['method'] == 'newOrder'
                   and e['fields'].get('arg#customerId', {}).get('value') == fixture['customer_id']]
        case = {'case': business['case'], 'trace_id': trace,
                'contract_sha256': hashlib.sha256(contract_path.read_bytes()).hexdigest(), 'queries': []}
        if not contract['expected_target']:
            case.update(no_target_checks=len(contract['queries']), no_target_passed=not targets)
            cases.append(case)
            continue
        target = targets[0] if len(targets) == 1 else None
        target_valid = bool(target and target['trace_id'] == trace
                            and target['fields']['arg#id']['value'] == business['order_id']
                            and target['capture_complete'] and target['available'])
        case['target_identity_valid'] = target_valid
        for query in contract['queries']:
            field = 'arg#' + query['target'].replace('.', '#')
            match = re.fullmatch(r'items\[itemId=(.*)\]\.(.*)', query['target'])
            if match and target:
                indices = [m[1] for k, v in target['fields'].items()
                           if (m := re.fullmatch(r'arg#items\[(\d+)\]#itemId', k))
                           and v.get('value') == match[1]]
                field = f'arg#items[{indices[0]}]#{match[2]}' if len(indices) == 1 else '<ambiguous-item>'
            expected = set()
            unresolved = []
            for source in query['sources']:
                key = (trace, source['service'], source['route'], source['record_id'], source['field'])
                coordinates = source_index.get(key, [])
                if len(coordinates) != 1:
                    unresolved.append({'source': source, 'matches': len(coordinates)})
                else:
                    expected.add(coordinates[0])
            actual = set()
            unknown = []
            observation = target['fields'].get(field) if target else None
            if observation is not None:
                for token in tokens(observation):
                    coordinates = label_index.get(token, set())
                    if len(coordinates) != 1:
                        unknown.append({'label': token, 'matches': len(coordinates)})
                    else:
                        actual.update(coordinates)
            status = ('unresolved' if not target_valid or observation is None
                      or observation.get('tag') is None or unresolved or unknown
                      else 'agreement' if actual == expected else 'mismatch')
            case['queries'].append({'target': query['target'], 'field': field,
                                    'profile': query['profile'], 'status': status,
                                    'expected': sorted(expected), 'actual': sorted(actual),
                                    'unresolved_expected': unresolved, 'unknown_labels': unknown})
        cases.append(case)
    queries = [q for c in cases for q in c['queries']]
    all_complete = all(e['capture_complete'] and e['available'] for e in events)
    empty = next(c for c in cases if c['case'] == 'empty_cart')
    empty_responses = [e for e in events if e['phase'] == 'rpc-response'
                       and e['trace_id'] == empty['trace_id']
                       and e['fields'].get('result#body') == {'container': 'collection', 'size': 0}]
    parallel = [c for c in cases if c['case'].startswith('parallel-')]
    passed = (all_complete and paired_requests_complete and diagnostic_log.exists()
              and not adapter_errors and not runtime_errors and len(empty_responses) == 1
              and all(q['status'] == 'agreement' for q in queries)
              and all(c.get('no_target_passed', True) for c in cases)
              and len({c['trace_id'] for c in parallel}) == len(parallel))
    return {'schema_version': 1, 'run': str(run.resolve()),
            'configuration': 'Original MirrorTaint JAR plus instrumentation/library/source/thread/logging adapters',
            'integration_adapter_sha256': result['integration_adapter_sha256'],
            'log_sha256': hashlib.sha256(log.read_bytes()).hexdigest(),
            'event_phases': dict(Counter(e['phase'] for e in events)),
            'unique_event_ids': len(by_id), 'rpc_pairs': len(pairs), 'all_events_complete_and_active': all_complete,
            'all_requests_paired': paired_requests_complete, 'adapter_errors': adapter_errors,
            'runtime_error_logs': runtime_errors,
            'target_queries': len(queries), 'query_status': dict(Counter(q['status'] for q in queries)),
            'profiles': dict(Counter(q['profile'] for q in queries)),
            'no_target_checks': sum(c.get('no_target_checks', 0) for c in cases),
            'empty_cart_response_confirmed': len(empty_responses) == 1,
            'parallel_unique_traces': len({c['trace_id'] for c in parallel}),
            'calibration_passed': passed, 'accuracy_eligible': False, 'performance_eligible': False,
            'cross_service_join_validated': False,
            'limitations': ['Calibration agreement is not a formal accuracy score or an original-tool result.',
                            'Response values and identities are observed at the Orders RPC consumer, using the companion logger.',
                            'Record identities use actual response id or unique HAL self URI agreeing with request URI; tool labels use exact token identity, never content/time equality joins.',
                            'Caller-to-callee server invocation join, independent oracle review, image/source verification and our engine remain outstanding.',
                            'Thread support covers the pinned Spring Future/void submit paths; stream support is sequential DoubleStream.sum.'],
            'cases': cases}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.run)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'cases'}, indent=2))
    raise SystemExit(0 if report['calibration_passed'] else 1)
