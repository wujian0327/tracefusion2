#!/usr/bin/env python3
"""Offline DTO identity/version and bytecode-derived scalar reconstruction. No oracle imports."""
from collections import defaultdict
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
from service_model import derive, require


def f32(value):
    return struct.unpack('!f', struct.pack('!f', value))[0]


def evaluate(expr, fields, summed):
    op = expr['op']
    if op == 'constant':
        return f32(expr['value'])
    if op == 'field':
        value = fields[expr['field']]
        return f32(value) if expr['descriptor'] == 'F' else value
    if op == 'sum':
        return summed
    if op in ('i2f', 'd2f'):
        return f32(evaluate(expr['arg'], fields, summed))
    if op == 'f2d':
        return float(evaluate(expr['arg'], fields, summed))
    left = evaluate(expr['left'], fields, summed)
    right = evaluate(expr['right'], fields, summed)
    if op == 'fmul':
        return f32(left * right)
    if op == 'fadd':
        return f32(left + right)
    if op == 'dadd':
        return left + right
    raise ValueError('Unmodeled expression operator')


def infer(capture, model):
    derived, _ = derive(capture)
    require(derived == model, 'Model differs from independently decoded original bytecode')
    raw = (capture / 'events.jsonl').read_bytes()
    rows = [json.loads(line) for line in raw.splitlines()]
    require([row['seq'] for row in rows] == list(range(1, len(rows) + 1)), 'Observation sequence gap')
    require(rows[0]['kind'] == 'start' and not any(row['kind'] == 'problem' for row in rows), 'Failed collection')
    enters, exits, per_frame = {}, {}, defaultdict(list)
    stacks, rpcs, versions = defaultdict(list), {}, defaultdict(int)
    inventory = {}
    aliases = defaultdict(list)
    source_positions = {}
    for row in rows:
        kind = row['kind']
        thread = row['thread']
        if kind == 'enter':
            require(row['frame'] not in enters, 'Duplicate frame')
            require(row['parent'] == (stacks[thread][-1] if stacks[thread] else 0), 'Frame parent mismatch')
            enters[row['frame']] = row
            stacks[thread].append(row['frame'])
        elif kind == 'exit':
            require(stacks[thread] and stacks[thread].pop() == row['frame'], 'Unbalanced return')
            exits[row['frame']] = row
        elif kind == 'abort' and row['scope'] == 'frame':
            require(stacks[thread] and stacks[thread].pop() == row['instance'], 'Unbalanced abort')
        elif kind == 'rpc-enter':
            require(row['rpc'] not in rpcs, 'Duplicate RPC')
            rpcs[row['rpc']] = row
        elif kind == 'rpc-exit':
            require(row['rpc'] in rpcs and rpcs[row['rpc']]['thread'] == thread, 'Unpaired RPC response')
            require('response' not in rpcs[row['rpc']], 'Duplicate RPC response')
            rpcs[row['rpc']]['response'] = row
            for field in row['fields']:
                if 'value' not in field['observed'] or field['observed']['value'] is None:
                    continue
                location = (field['owner'], field['field'], field['version'])
                source = (row['rpc'], field['path'])
                require(source not in inventory, 'Duplicate source coordinate')
                inventory[source] = field
                aliases[location].append(source)
                source_positions[source] = row['seq']
        if kind in ('write', 'read'):
            location = (row['owner'], row['field'])
            if kind == 'write':
                versions[location] += 1
            require(row['version'] == versions[location], 'Field version discontinuity')
        if 'frame' in row:
            per_frame[row['frame']].append(row)
    require(not any(stacks.values()), 'Incomplete frames')
    require(all('response' in event for event in rpcs.values()), 'Incomplete RPCs')

    def resolve(field, seq):
        location = (field['owner'], field['field'], field['version'])
        sources = [s for s in aliases[location] if source_positions[s] < seq]
        if len(sources) != 1:
            return None
        observed = field.get('observed', {})
        original = inventory[sources[0]]['observed']
        if observed.get('value') != original.get('value'):
            return None
        if not field.get('primitive', True) and observed.get('object') != original.get('object'):
            return None
        return set(sources)

    calculations = {}
    for frame, entry in enters.items():
        if entry['method'] != model['calculate_method']:
            continue
        require(frame in exits, 'Calculation did not return')
        before = [r for r in per_frame[frame] if r['kind'] == 'sum-enter']
        after = [r for r in per_frame[frame] if r['kind'] == 'sum-exit']
        require(len(before) == len(after) == 1 and not before[0]['parallel'], 'Unmodeled stream reduction')
        callbacks = sorted((e for e in enters.values() if e['parent'] == frame), key=lambda e: e['seq'])
        require(isinstance(entry.get('collection_argument'), list), 'Reduction member snapshot missing')
        require([callback['args'][0]['object'] for callback in callbacks] == entry['collection_argument'],
                'Reduction callback coverage differs from actual collection membership')
        sources, returns, unknown = set(), [], []
        for callback in callbacks:
            require(callback['method'] == model['mapper_method'], 'Unmodeled callback')
            require(before[0]['seq'] < callback['seq'] < exits[callback['frame']]['seq'] < after[0]['seq'], 'Callback outside sum')
            reads = [r for r in per_frame[callback['frame']] if r['kind'] == 'read']
            require([r['field'] for r in reads] == [r['field'] for r in model['mapper_reads']], 'Callback field reads differ from bytecode')
            require(all(r['owner'] == callback['args'][0]['object'] for r in reads), 'Mapper reads another object')
            computed = evaluate(model['mapper_expression'], {r['field']: r['observed']['value'] for r in reads}, None)
            actual = exits[callback['frame']]['result']['value']
            require(computed == actual and math.isfinite(actual), 'Scalar replay contradicts actual mapper return')
            returns.append(actual)
            for read in reads:
                bound = resolve(read, read['seq'])
                if bound is None:
                    unknown.append({'callback': callback['frame'], 'field': read['field']})
                else:
                    sources.update(bound)
        require(math.fsum(returns) == after[0]['value'], 'Observed reduction differs from audited finite callback fold')
        amount = evaluate(model['calculate_expression'], {}, after[0]['value'])
        require(amount == f32(exits[frame]['result']['value']), 'Float replay contradicts actual calculation return')
        calculations[frame] = {'sources': sources, 'value': amount, 'unknown': unknown,
                               'callbacks': [c['frame'] for c in callbacks]}
    answers = []
    for frame, entry in enters.items():
        if entry['method'] != model['root_method'] or frame not in exits:
            continue
        returned = exits[frame]
        calc = [f for f, e in enters.items() if e['parent'] == frame and e['method'] == model['calculate_method']]
        constructors = [e for e in enters.values() if e['parent'] == frame and e['method'] == model['constructor_method']]
        require(len(calc) == len(constructors) == 1, 'Root does not have unique calculation/constructor')
        calculation = calculations[calc[0]]
        constructor = constructors[0]
        require(constructor['receiver'] == returned['result']['object'], 'Saved result replaced constructor object; summary unsupported')
        require(f32(constructor['args'][model['constructor_amount_arg']]['value']) == calculation['value'], 'Constructor operand differs from calculation')
        constructor_writes = [r for r in per_frame[constructor['frame']] if r['kind'] == 'write'
                              and r['owner'] == constructor['receiver'] and r['field'] == model['target_amount_field']]
        require(len(constructor_writes) == 1, 'Amount field write ambiguous')
        fields = []
        for field in returned['fields']:
            if 'value' not in field['observed'] or field['observed']['value'] is None:
                continue
            if field['owner'] == constructor['receiver'] and field['field'] == model['target_amount_field']:
                write = constructor_writes[0]
                require(field['version'] == write['version'] and f32(field['observed']['value']) == calculation['value'], 'Target amount overwritten')
                sources = calculation['sources'] if not calculation['unknown'] else None
                basis = {'kind': 'bytecode-scalar-and-sequential-stream-replay', 'calculation_frame': calc[0],
                         'callback_frames': calculation['callbacks'], 'constructor_frame': constructor['frame']}
            else:
                sources = resolve(field, returned['seq'])
                basis = {'kind': 'read-only-DTO-field-identity-and-version', 'owner': field['owner'],
                         'field': field['field'], 'version': field['version']}
            fields.append({'path': field['path'], 'observed': field['observed'],
                           'status': 'resolved' if sources is not None else 'unresolved',
                           'sources': sorted(sources) if sources is not None else [], 'basis': basis})
        answers.append({'root_frame': frame, 'target_object': returned['result']['object'], 'fields': fields})
    return {'schema': 'tracefusion-service-inference-v1', 'provenance_engine_run': True,
            'event_sha256': hashlib.sha256(raw).hexdigest(), 'model_sha256': hashlib.sha256(json.dumps(model, sort_keys=True).encode()).hexdigest(),
            'events': len(rows), 'rpc_instances': len(rpcs), 'target_orders': len(answers),
            'sources': [{'coordinate': list(key), **value} for key, value in inventory.items()],
            'answers': answers, 'accuracy_eligible': False, 'performance_eligible': False,
            'scope': model['scope'], 'oracle_consumed': False, 'mirror_taint_consumed': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    report = infer(args.capture, json.loads(args.model.read_text()))
    args.out.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ('answers', 'sources')}, indent=2))
