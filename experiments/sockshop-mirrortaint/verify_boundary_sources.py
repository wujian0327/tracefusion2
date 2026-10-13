#!/usr/bin/env python3
"""Replay real four-method observations with meaningful fault controls."""
import argparse
import copy
import json
from pathlib import Path
import tempfile
from infer_boundary_sources import infer


def signature(report):
    return [(a['frame'],a['sink'],[(f['path'],f['status'],f['sources']) for f in a['fields']])
            for a in report['answers']]


def verify(capture):
    original = [json.loads(l) for l in (capture/'events.jsonl').read_bytes().splitlines()]
    baseline = infer(capture)
    checks = {}
    with tempfile.TemporaryDirectory(prefix='tf2-boundary-') as directory:
        scratch = Path(directory)
        def replay(rows):
            (scratch/'events.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
            return infer(scratch)
        (scratch/'query-contract.json').write_text('{"sources":"forged expected answer"}')
        checks['only_observations_and_poisoned_contracts_same_answers'] = signature(replay(original)) == signature(baseline)
        damaged = copy.deepcopy(original)
        for r in damaged:
            r.pop('trace_id',None)
            if r['kind']=='enter': r['trace_id']=None
        checks['trace_ids_not_used_for_inference'] = signature(replay(damaged)) == signature(baseline)
        damaged = copy.deepcopy(original)
        next(r for r in damaged if r['kind']=='write')['version'] += 1
        try:
            replay(damaged); checks['field_version_break_rejected'] = False
        except ValueError:
            checks['field_version_break_rejected'] = True
        damaged = copy.deepcopy(original)
        next(r for r in damaged if r['kind']=='enter')['parent'] = 999999
        try:
            replay(damaged); checks['wrong_frame_parent_rejected'] = False
        except ValueError:
            checks['wrong_frame_parent_rejected'] = True
        sources = [r for r in original if r['kind']=='source']
        duplicate = copy.deepcopy(original)
        index = next(i for i,r in enumerate(duplicate) if r['kind']=='source')
        duplicate.insert(index,copy.deepcopy(duplicate[index]))
        for i,r in enumerate(duplicate,1): r['seq']=i
        try:
            replay(duplicate); checks['duplicate_source_coordinate_rejected'] = False
        except ValueError:
            checks['duplicate_source_coordinate_rejected'] = True
        damaged = [copy.deepcopy(r) for r in original if r['kind']!='source']
        for i,r in enumerate(damaged,1): r['seq']=i
        missing = replay(damaged)
        checks['no_sources_never_filled_from_values_or_contracts'] = all(f['status']=='unknown' for a in missing['answers'] for f in a['fields'])
        changed = copy.deepcopy(original)
        victim = next(r for r in changed if r['kind'] in ('sink','exit') and r.get('fields'))
        field = next(f for f in victim['fields'] if f['observed'].get('value') is not None)
        field['observed']['value'] = 'deliberately changed value'
        changed_report = replay(changed)
        found = next(a for a in changed_report['answers'] if a['seq']==victim['seq'])
        checks['same_location_changed_value_not_assumed_readonly'] = next(f for f in found['fields'] if f['path']==field['path'])['status']=='unknown'
    if not all(checks.values()):
        raise AssertionError(checks)
    return checks


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    report={s:verify(args.run/'boundary-events'/s) for s in ('carts','shipping')}
    args.out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
