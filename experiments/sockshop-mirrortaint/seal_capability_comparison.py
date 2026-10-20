#!/usr/bin/env python3
"""Seal the already exposed 62 families, without trying any remaining candidate."""
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    out = HERE / 'capability-comparison-62-20261020.json'
    if out.exists():
        raise SystemExit('Immutable seal already exists')
    paths = [ROOT/'artifacts/query-coverage-first-20261019/pool.json',
             HERE/'response-binding-heldout-20261019.json',
             HERE/'sockshop-model-heldout-20261020.json']
    pool = json.loads(paths[0].read_text())
    groups = [[q for q in pool['candidates'] if q['id'] in pool['selected_ids']]]
    groups += [json.loads(p.read_text())['queries'] for p in paths[1:]]
    queries = []
    for name, group in zip(('development20', 'binding22', 'model20'), groups):
        queries += [{**q, 'exposure_group': name} for q in group]
    assert len(queries) == len({q['id'] for q in queries}) == 62
    assert sum(q['application'] == 'sockshop' for q in queries) == 30
    freeze = ROOT/'artifacts/call-lifecycle-revision-20261020/algorithm-freeze.json'
    record = {
        'schema_version': 1, 'purpose': 'Capability inclusion, not performance',
        'tf_algorithm_commit': '2b3b9297e8382162865075d22459480980a45bbc',
        'seal_parent_commit': subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT, text=True).strip(),
        'source_files_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in [*paths, freeze]},
        'counts': {'sockshop': 30, 'trainticket': 32, 'selected': 62, 'remaining_unexamined': 29},
        'selection': 'Union of all three previously tested sets; no replacement, exclusion or support-based selection.',
        'task': 'Original JAR; declared entry / response JSON path / original source boundary; concrete invocation, object, field/element and observed version; data origins exclude selector/control origins.',
        'inputs': {
            'seed': 20261020,
            'ordinary': 'Six existing fixture structures: multi-record, equal-value, single, empty, more, repeated. Shared across tools with identical prepared database/request fixtures.',
            'basic_ticketinfo': 'Existing eight real travel templates including normal, fallback and upstream failure; same fixtures/body for both tools.',
            'cart_first_creation': 'Additional paired absent-cart first GET / second GET, same customerId family; include as an explicit challenge, not a new query.',
            'previously_refused': 'Execute original business entry despite TF planning refusal; fill itemId/start/terminal/batch bodies from actual fixture coordinates, not predicted provenance.',
            'empty': 'Actual client JSON enumerates targets; explicit null is a target, empty wildcard has no element; N/A is counted per request.'},
        'baseline': {
            'first': 'MirrorTaint + disclosed adapter, original pinned propagation JAR',
            'native_sha256': 'e4c679206993b45c6727a4ace1d4dcff6df0ded2b80b56b27b8c86741be63fe7',
            'adapter_allowed': 'Configure/tag the declared boundaries using native APIs; export native tags and raw identities/versions/messages. Bind native IDs to observed source instances. No TF reconstruction, expected origins or business propagation formula in prediction.',
            'calibration': 'Same-value distinct objects, repeated reads, overwritten versions, missing/ambiguous necessary evidence, constants and exception isolation.',
            'other_tools': 'Phosphor and FlowDist follow after MirrorTaint task calibration; no capability claim from historical different-task results.'},
        'truth': 'Independent original-bytecode review and raw database/messages/object/call witnesses. Never use TF graph traversal or baseline labels to decide expected origins. Report oracle unavailable separately.',
        'states': ['planning_refused', 'known_correct', 'known_wrong', 'unknown', 'evidence_invalid', 'N/A', 'execution_failed', 'not_yet_run', 'oracle_unavailable'],
        'acceptance': 'For EVERY concrete target independently correct for baseline, TF selective must also be independently correct with no added false origins. Report the actual matched-instance set and all counterexamples; an empty/unrun baseline set cannot establish capability preservation.',
        'versioning': 'Keep first results and all failures immutable. Any algorithm/model repair is a separately frozen version/regression; do not overwrite first gap table. Existing cost tables remain specific to their frozen versions.',
        'queries': queries}
    out.write_text(json.dumps(record, ensure_ascii=False, indent=2)+'\n')
    print(out, hashlib.sha256(out.read_bytes()).hexdigest())


if __name__ == '__main__':
    main()
