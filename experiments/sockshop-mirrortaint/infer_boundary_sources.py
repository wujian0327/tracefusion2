#!/usr/bin/env python3
"""Offline readonly scalar aliases from actual source/sink object-field versions.

Reads observations only. Neither workload contracts nor MirrorTaint tags are inputs.
Unsupported assignments remain unknown rather than being inferred by equal values.
"""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path


def infer(capture):
    raw = (capture / 'events.jsonl').read_bytes()
    rows = [json.loads(line) for line in raw.splitlines()]
    if [r['seq'] for r in rows] != list(range(1, len(rows) + 1)):
        raise ValueError('Observation sequence gap')
    if any(r['kind'] == 'problem' for r in rows):
        raise ValueError('Collection failed')
    stacks, roots, entries, versions = defaultdict(list), {}, {}, defaultdict(int)
    aliases, inventory, answers = defaultdict(list), {}, []
    completed = set()
    source_instances = set()
    for row in rows:
        kind, thread = row['kind'], row['thread']
        if kind == 'enter':
            parent = stacks[thread][-1] if stacks[thread] else 0
            if row['parent'] != parent or row['frame'] in entries:
                raise ValueError('Invalid call context')
            entries[row['frame']] = row
            roots[row['frame']] = roots[parent] if parent else row['frame']
            stacks[thread].append(row['frame'])
        if kind in ('read', 'write'):
            key = (row['owner'], row['field'])
            if kind == 'write':
                versions[key] += 1
            if row['version'] != versions[key]:
                raise ValueError('Field version discontinuity')
        if kind == 'source':
            if row['instance'] in source_instances:
                raise ValueError('Duplicate source instance')
            source_instances.add(row['instance'])
            root = roots[row['frame']]
            for field in row['fields']:
                if field['observed'].get('value') is None:
                    continue
                coordinate = (row['instance'], field['path'])
                if coordinate in inventory:
                    raise ValueError('Duplicate source')
                inventory[coordinate] = field
                aliases[(root, field['owner'], field['field'], field['version'])].append(coordinate)
        if kind in ('exit', 'sink') and row.get('fields'):
            root = roots[row['frame']]
            fields = []
            for field in row['fields']:
                if field['observed'].get('value') is None:
                    continue
                key = (root, field['owner'], field['field'], field['version'])
                sources = aliases[key]
                # Multiple source instances for a single location are ambiguous.
                source = inventory[sources[0]] if len(sources) == 1 else None
                intact = (source is not None and source['observed'].get('value') == field['observed'].get('value')
                          and (field['primitive'] or source['observed']['object'] == field['observed']['object']))
                fields.append(dict(field, status='resolved' if intact else 'unknown',
                                   sources=[list(sources[0])] if intact else None))
            answers.append({'frame': row['frame'], 'root': root, 'seq': row['seq'],
                            'trace_id': entries[root]['trace_id'], 'method': entries[root]['method'],
                            'sink': row.get('boundary', 'return'), 'fields': fields})
        if kind == 'exit':
            if not stacks[thread] or stacks[thread].pop() != row['frame']:
                raise ValueError('Unbalanced return')
            completed.add(row['frame'])
        if kind == 'abort':
            if not stacks[thread] or stacks[thread].pop() != row['instance']:
                raise ValueError('Unbalanced abort')
    if any(stacks.values()):
        raise ValueError('Incomplete calls')
    answers = [a for a in answers if a['root'] in completed]
    return {'event_sha256': hashlib.sha256(raw).hexdigest(), 'answers': answers,
            'source_inventory': [{'coordinate': list(c), 'field': f} for c,f in inventory.items()],
            'contracts_consumed': False, 'MirrorTaint_consumed': False,
            'engine': 'TraceFusion readonly object-field-version alias reconstruction',
            'scope': 'actual CartDAO query results and Shipping request DTO; scalar identity aliases only'}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--capture', type=Path, required=True); p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    args.out.write_text(json.dumps(infer(args.capture), indent=2) + '\n')
