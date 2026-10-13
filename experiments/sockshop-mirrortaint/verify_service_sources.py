#!/usr/bin/env python3
"""Independent inference/audit negative controls and diagnostic-metadata isolation checks."""
import argparse
import copy
import json
from pathlib import Path
import shutil
import tempfile
from infer_service_sources import infer
from audit_service_sources import audit

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--run', type=Path, required=True)
parser.add_argument('--out', type=Path, required=True)
args = parser.parse_args()
capture = args.run / 'tracefusion-events'
model = json.loads((args.run / 'service-model.json').read_text())
baseline = infer(capture, model)
assert audit(args.run)['calibration_passed']
rows = [json.loads(line) for line in (capture / 'events.jsonl').read_text().splitlines()]
checks = {}
with tempfile.TemporaryDirectory(prefix='tf2-service-verify-') as directory:
    scratch = Path(directory)
    isolated = scratch / 'isolated-input'
    isolated.mkdir()
    for file in capture.glob('*.original.class'):
        shutil.copyfile(file, isolated / file.name)

    def replay(events):
        (isolated / 'events.jsonl').write_text(''.join(json.dumps(e) + '\n' for e in events))
        return infer(isolated, model)

    stripped = [{k: v for k, v in e.items() if k not in ('trace_id', 'span_id')} for e in rows]
    stripped_result = replay(stripped)
    checks['trace_and_span_removed_same_answers'] = stripped_result['answers'] == baseline['answers'] and stripped_result['sources'] == baseline['sources']
    (isolated / 'query-contract.json').write_text('{"poisoned_expected_answers": "this must never be read"}')
    (isolated / 'wire.json').write_text('not valid JSON')
    poisoned = replay(stripped)
    checks['no_oracle_or_wire_needed_and_poison_ignored'] = poisoned['answers'] == baseline['answers']

    def rejected(events, name):
        try:
            replay(events)
        except ValueError:
            checks[name] = True
        else:
            checks[name] = False

    damaged = copy.deepcopy(rows)
    next(e for e in damaged if e['kind'] == 'write')['version'] += 1
    rejected(damaged, 'field_version_discontinuity_rejected')
    damaged = copy.deepcopy(rows)
    next(e for e in damaged if e['kind'] == 'enter' and e['method'] == model['mapper_method'])['parent'] = 0
    rejected(damaged, 'wrong_callback_context_rejected')
    damaged = copy.deepcopy(rows)
    damaged.pop(next(i for i, e in enumerate(damaged) if e['kind'] == 'read' and e.get('frame') in {
        e['frame'] for e in rows if e['kind'] == 'enter' and e['method'] == model['mapper_method']}))
    for index, event in enumerate(damaged, 1):
        event['seq'] = index
    rejected(damaged, 'missing_callback_operand_read_rejected')
    damaged = copy.deepcopy(rows)
    damaged.append(copy.deepcopy(next(e for e in rows if e['kind'] == 'rpc-exit')))
    for index, event in enumerate(damaged, 1):
        event['seq'] = index
    rejected(damaged, 'duplicate_RPC_response_rejected')

    evaluated = scratch / 'evaluation'
    shutil.copytree(args.run, evaluated)
    inference_file = evaluated / 'inference.json'
    damaged_inference = copy.deepcopy(baseline)
    first, second = damaged_inference['answers'][:2]
    wrong = next(f for f in second['fields'] if f['path'] == 'arg#card#ccv')
    next(f for f in first['fields'] if f['path'] == 'arg#card#ccv')['sources'] = wrong['sources']
    inference_file.write_text(json.dumps(damaged_inference))
    checks['same_value_foreign_request_source_rejected'] = not audit(evaluated)['calibration_passed']
    inference_file.write_text(json.dumps(baseline))
    stats_file = evaluated / 'wire/carts/capture-result.json'
    stats_original = stats_file.read_text()
    stats = json.loads(stats_original)
    stats['socket_drops'] = 1
    stats_file.write_text(json.dumps(stats))
    checks['wire_capture_loss_rejected'] = not audit(evaluated)['calibration_passed']
    stats_file.write_text(stats_original)
    manifest_file = evaluated / 'result.json'
    manifest = json.loads(manifest_file.read_text())
    manifest['cases'].pop()
    manifest_file.write_text(json.dumps(manifest))
    checks['missing_registered_case_rejected'] = not audit(evaluated)['calibration_passed']
assert all(checks.values()), checks
report = {'run': str(args.run.resolve()), 'baseline_passed': True, 'checks': checks,
          'all_checks_passed': True, 'original_evidence_modified': False,
          'scope': 'Actual service inference replay and evaluation on temporary copies; supplementary real zero-return callback test is recorded separately'}
args.out.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
