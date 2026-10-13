#!/usr/bin/env python3
"""Independently check the bounded HTTP echo calibration and native baseline.

The oracle checks original controller argument/return identity and transport
metadata. It does not import the reconstruction algorithm or use its sources.
Concrete IDs bind frozen query patterns after collection: this is calibration,
not a blinded benchmark or an instance-accuracy score for FlowDist.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile


def read(path):
    return json.loads(path.read_text())


def rows(path):
    result = [json.loads(line) for line in path.read_text().splitlines()]
    if [r['seq'] for r in result] != list(range(1, len(result) + 1)) or any(r['kind'] == 'problem' for r in result):
        raise ValueError('Invalid raw observation sequence')
    return result


def audit(pilot, orders_jar, shipping_jar):
    protocol = read(pilot / 'protocol.json')
    prediction = read(pilot / 'tracefusion/http-inference.json')
    result = read(pilot / 'result.json')
    if not result['same_business_images']:
        raise ValueError('Different workload images')
    for mode in ('flowdist', 'tracefusion'):
        cases = result['runs'][mode]['cases']
        if len(cases) != 23 or not all(c['business_passed'] for c in cases):
            raise ValueError('Incomplete business workload')
        if Counter(c['phase'] for c in cases) != {'serial': 7, 'distinct': 8, 'shared': 8}:
            raise ValueError('Unexpected workload phases')
        for phase in ('distinct', 'shared'):
            intervals = [(c['start_monotonic_ns'], 1) for c in cases if c['phase'] == phase]
            intervals += [(c['end_monotonic_ns'], -1) for c in cases if c['phase'] == phase]
            active = peak = 0
            for _, delta in sorted(intervals):
                active += delta
                peak = max(peak, active)
            if peak != 8:
                raise ValueError('Concurrent requests did not all overlap')
    for role, jar, folder in (('orders', orders_jar, 'tracefusion-events'), ('shipping', shipping_jar, 'boundary-events/shipping')):
        if hashlib.sha256(jar.read_bytes()).hexdigest() != protocol['original_jars'][role]:
            raise ValueError('Original business JAR changed')
        with ZipFile(jar) as archive:
            for suffix in ('entities/Shipment', 'controllers/' + role.capitalize() + 'Controller'):
                relative = 'works/weave/socks/' + role + '/' + suffix + '.class'
                raw = archive.read('BOOT-INF/classes/' + relative)
                file = pilot / 'tracefusion' / folder / (relative.removesuffix('.class').replace('/', '_') + '.original.class')
                if raw != file.read_bytes():
                    raise ValueError('Controller or DTO differs from original business JAR')
    sender = rows(pilot / 'tracefusion/tracefusion-events/events.jsonl')
    receiver = rows(pilot / 'tracefusion/boundary-events/shipping/events.jsonl')
    sends = {r['rpc']: r for r in sender if r['kind'] == 'http-send'}
    sources = {r['frame']: r for r in receiver if r['kind'] == 'source' and r['boundary'] == 'http-request-body'}
    entries = {r['frame']: r for r in receiver if r['kind'] == 'enter' and '.postShipping(' in r['method']}
    exits = [r for r in receiver if r['kind'] == 'exit' and r['frame'] in entries]
    answers = {a['frame']: a for a in prediction['answers']}
    if len(sends) != len(sources) or len(sends) != len(exits) or len(sends) != 22:
        raise ValueError('Missing or duplicate actual Shipping invocations')
    trace_counts = Counter(s['trace_id'] for s in sends.values())
    shared_traces = [t for t, n in trace_counts.items() if n == 8]
    if len(shared_traces) != 1:
        raise ValueError('Missing eight same-trace calls')
    shared = [s for s in sends.values() if s['trace_id'] == shared_traces[0]]
    names = [next(f['observed']['value'] for f in s['request_fields'] if f['path'] == 'request#body#name') for s in shared]
    if len(set(names)) != 1:
        raise ValueError('Shared-name adversarial calls differ')
    queries = []
    counts = Counter({key: 0 for key in ('queries', 'correct', 'answered', 'unknown', 'tp', 'tn', 'fp', 'fn')})
    for returned in exits:
        frame = returned['frame']
        entered, source = entries[frame], sources[frame]
        if returned['result']['object'] != entered['args'][0]['object']:
            raise ValueError('Original echo object identity violated')
        message = source['message_id']
        if message not in sends:
            raise ValueError('Oracle transport partner missing')
        alternatives = [key for key, send in sends.items() if key != message and send['trace_id'] == entered['trace_id']]
        if not alternatives:
            alternatives = [key for key in sends if key != message]
        other_message = sorted(alternatives)[0]
        for prop in ('id', 'name'):
            target_path = 'result#' + prop
            field = next(f for f in returned['fields'] if f['path'] == target_path)
            incoming = next(f for f in source['fields'] if f['path'] == 'source#' + prop)
            if (field['owner'], field['field'], field['version'], field['observed']) != (
                incoming['owner'], incoming['field'], incoming['version'], incoming['observed']):
                raise ValueError('Receiver echo field changed after the source boundary')
            predicted = [f for f in answers.get(frame, {}).get('fields', []) if f['path'] == target_path]
            patterns = [('same-message-field', message, prop, True),
                        ('other-field', message, 'name' if prop == 'id' else 'id', False),
                        ('other-message', other_message, prop, False)]
            for pattern, query_message, query_field, expected in patterns:
                coordinate = ['orders', query_message, 'request#body#' + query_field]
                known = len(predicted) == 1 and predicted[0]['status'] == 'resolved'
                actual = coordinate in predicted[0]['sources'] if known else None
                correct = known and actual == expected
                counts['queries'] += 1
                counts['correct'] += correct
                counts['answered'] += known
                counts['unknown'] += not known
                if known:
                    counts[('tp' if expected else 'fp') if actual else ('fn' if expected else 'tn')] += 1
                queries.append({'frame': frame, 'target': target_path, 'pattern': pattern,
                                'source': coordinate, 'expected': expected, 'prediction': actual, 'correct': correct})
    native = read(pilot / 'flowdist-native-method-query-validated/result.json')
    if native['decision'] != 'candidate-flow' or native['method_path_length'] < 2:
        raise ValueError('Original FlowDist coarse candidate path not confirmed')
    inspection = read(pilot / 'flowdist-native-method-query-validated/trace-inspection-stage.json')
    if inspection['status'] != 'peer-correlation-validated':
        raise ValueError('Native query roles or process clocks not confirmed')
    invalid = read(pilot / 'flowdist-native-method-query/result.json')
    invalid_query = {'path': str(pilot / 'flowdist-native-method-query'), 'excluded': True,
                     'reason': 'Manually supplied source signature used entities.NewOrderResource; actual package is resources.NewOrderResource.',
                     'invalid_source_query': invalid['query'], 'valid_query': native['query']}
    return {'kind': 'bounded-http-instance-calibration-audit',
            'business': {'each_mode': 23, 'each_mode_shipping': 22, 'shared_trace_and_name_calls': 8, 'peak_parallel_requests': 8},
            'tracefusion': {'counts': dict(counts), 'fraction_correct': counts['correct'] / counts['queries'],
                            'field_paths': 44, 'queries': queries},
            'flowdist': {'native_method_query': native['decision'], 'candidate_methods': native['method_path_length'],
                         'field_instance_accuracy': None, 'reason': 'No field-instance predictions have been produced by the native statement query pipeline for this run.'},
            'excluded_diagnostic': invalid_query, 'accuracy_ranking_available': False,
            'performance_comparison_available': False,
            'limitations': ['This is a bounded transport/echo calibration; query patterns precede execution and concrete message IDs bind afterwards.',
                           'TraceFusion adds an explicit message header and a disclosed default String-property model.',
                           'Source begins at the outgoing Orders Shipment; customer response -> Shipment and RabbitMQ consumer are outside the reconstructed path.',
                           'FlowDist keeps original queries and aggregation; method candidates cannot be scored as field-instance answers.',
                           'Concurrency is covered by one deployment per mode; this run is not a new runtime/memory comparison.']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('pilot', 'orders', 'shipping', 'out'):
        parser.add_argument('--' + flag, type=Path, required=True)
    args = parser.parse_args()
    args.out.write_text(json.dumps(audit(args.pilot, args.orders, args.shipping), indent=2) + '\n')
