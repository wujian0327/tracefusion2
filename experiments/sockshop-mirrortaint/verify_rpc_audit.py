#!/usr/bin/env python3
"""Replay negative audit controls on copies of real evidence, leaving originals intact."""
import argparse
import copy
import json
from pathlib import Path
import shutil
import tempfile
import audit_rpc_wire

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--run', type=Path, required=True)
parser.add_argument('--out', type=Path, required=True)
args = parser.parse_args()
checks = {}
with tempfile.TemporaryDirectory(prefix='tf2-rpc-audit-') as folder:
    root = Path(folder) / 'run'
    shutil.copytree(args.run, root)
    report = audit_rpc_wire.audit(root)
    assert report['wire_calibration_passed'] and report['java_application_handler_join_validated']
    wire = root / 'wire/carts/http.json'
    original = json.loads(wire.read_text())
    damaged = copy.deepcopy(original)
    request = next(p['_source']['layers']['http'] for p in damaged
                   if 'http.request' in p['_source']['layers']['http'])
    request['http.request.line'] = ['X-B3-ParentSpanId: ffffffffffffffff\r\n' if h.startswith('X-B3-ParentSpanId:') else h
                                    for h in request['http.request.line']]
    wire.write_text(json.dumps(damaged))
    checks['wrong_wire_parent'] = not audit_rpc_wire.audit(root)['wire_calibration_passed']
    damaged = copy.deepcopy(original)
    response = next(p['_source']['layers']['http'] for p in damaged
                    if 'http.response' in p['_source']['layers']['http'])
    body = json.loads(bytes.fromhex(response['http.file_data'].replace(':', '')).decode())
    body[0]['quantity'] += 1
    response['http.file_data'] = json.dumps(body).encode().hex(':')
    wire.write_text(json.dumps(damaged))
    checks['wire_consumer_payload_disagreement'] = not audit_rpc_wire.audit(root)['wire_calibration_passed']
    wire.write_text(json.dumps([p for p in original if p is not next(p for p in original
                                if 'http.response' in p['_source']['layers']['http'])]))
    checks['missing_wire_response'] = not audit_rpc_wire.audit(root)['wire_calibration_passed']
    wire.write_text(json.dumps(original))
    server = root / 'server/carts/server-events.jsonl'
    original_server = server.read_text()
    dispatch = next(json.loads(line) for line in original_server.splitlines() if json.loads(line)['phase'] == 'handler'
                    and json.loads(line)['X-B3-TraceId'] is not None)
    server.write_text(original_server + json.dumps(dispatch) + '\n')
    checks['duplicate_controller_dispatch'] = not audit_rpc_wire.audit(root)['java_application_handler_join_validated']
    server.write_text(original_server)
    stats = root / 'wire/carts/capture-result.json'
    value = json.loads(stats.read_text())
    value['socket_drops'] = 1
    stats.write_text(json.dumps(value))
    checks['capture_drops'] = not audit_rpc_wire.audit(root)['wire_calibration_passed']
assert all(checks.values()), checks
args.out.write_text(json.dumps({'run': str(args.run.resolve()), 'baseline_passed': True,
                               'negative_controls': checks, 'original_evidence_modified': False}, indent=2) + '\n')
print(json.dumps(checks, indent=2))
