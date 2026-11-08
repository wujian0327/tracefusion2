"""Read-only demand inventory. No propagation, predicted answers or oracle input.

Co-coordinate/identity witnesses are *not* certified dependencies. In particular,
later copy completion never authorizes omission of an earlier source snapshot.
"""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path

from external_transfer_oracle import require_complete_raw_capture

BOXED = {'Ljava/lang/' + t + ';' for t in
         ('Integer', 'Long', 'Boolean', 'Byte', 'Short', 'Character', 'Float', 'Double')}
BOUNDARIES = {'binding-input', 'binding-source', 'binding-opaque-touch', 'binding-opaque-result'}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def coordinate(field):
    return tuple(field.get(k) for k in ('owner', 'field', 'version'))


def available_before(observation_seq, necessary_evidence):
    # Absence of evidence is not a proof of absence; duplicates are ambiguous.
    return bool(necessary_evidence) and all(
        len(xs) == 1 and xs[0] < observation_seq for xs in necessary_evidence)


def bucket(field, descriptor, required, target):
    if field['field'] == target:
        return 'declared_target'
    if field['field'] in required:
        return 'interpreter_or_finite_contract_required'
    observed = field.get('observed', {})
    if observed.get('object', '!') is None:
        return 'null_shape_not_an_unused_numeric_payload'
    if descriptor in BOXED and 'value' in observed:
        return 'boxed_payload_candidate_missing_closed_consumer_demand'
    if field['field'].startswith('@'):
        return 'container_member_identity_or_selected_path'
    if descriptor == 'Ljava/util/Date;':
        return 'mutable_date_and_projection_contract'
    return 'reference_shape_or_unresolved_contract_input'


def inspect(plan, rows):
    require_complete_raw_capture(rows)
    properties = {p['field']: p for ps in plan['response_graph_schema'].values() for p in ps}
    policy = plan['target_observation_closure']
    required = set(policy['required_fields'])
    entries = defaultdict(list)
    calls, finishes = defaultdict(list), defaultdict(list)
    for row in rows:
        if row['kind'] == 'enter':
            entries[row['frame']].append(row)
        if row['kind'] == 'collection-call-enter':
            calls[(row.get('frame'), row.get('call_id'))].append(row)
        if row['kind'] in ('collection-call-exit', 'collection-call-throw'):
            finishes[(row.get('frame'), row.get('call_id'))].append(row)

    def root(frame):
        seen = set()
        while frame is not None:
            if frame in seen or len(entries[frame]) != 1:
                raise ValueError('Missing/ambiguous/cyclic frame parent')
            seen.add(frame)
            r = entries[frame][0]
            if r['method'] == plan['entry']:
                return frame
            frame = r.get('parent')
        return None

    scopes = {f: root(f) for f in tuple(entries)}
    records, omissions, reads = Counter(), Counter(), Counter()
    detailed = []
    sources = defaultdict(list)
    transfers, chronology, witnesses = [], [], []
    for r in rows:
        family = scopes.get(r.get('frame'))
        if family and r['kind'] == 'read':
            reads[(r['field'], r.get('site'))] += 1
        if r['kind'] == 'binding-source' and family:
            for f in r['fields']:
                sources[(family, coordinate(f))].append((r, f))
        if 'json_list_copy' in r and family:
            proof = r['json_list_copy']
            k = (r.get('frame'), r.get('call_id'))
            beginnings = calls[k]
            if proof.get('valid') and len(beginnings) == 1:
                begin = beginnings[0]
                members = proof['members']
                transfers.append({'root': family, 'begin_seq': begin['seq'],
                                  'completion_seq': r['seq'], 'call_id': r['call_id'],
                                  'input_owner': begin['receiver'].get('object'),
                                  'output_owner': r['result'].get('object'),
                                  'members': [m.get('object') for m in members],
                                  'input_epoch': begin.get('collection_epoch'),
                                  'output_epoch': proof['result_epoch'],
                                  'cache_seq': proof['cache_seq']})
        if r['kind'] not in BOUNDARIES:
            continue
        selected = r.get('target_observation', {}).get('selected', False)
        scope = 'query_selected' if family and selected else 'query_capture_all' if family else 'outside_query_family'
        for kind, values in r.get('target_observation', {}).items():
            if kind in ('scalar_fields', 'container_values'):
                for field, n in values.items():
                    omissions[(scope, kind, field)] += n
        for f in r.get('fields', []):
            field = f['field']
            descriptor = properties.get(field, {}).get('descriptor')
            reason = bucket(f, descriptor, required, plan['target'])
            records[(scope, r['kind'], field, descriptor, reason)] += 1
            # Coordinates, not field values; do not export credentials/tokens.
            detailed.append({'seq': r['seq'], 'root': family, 'scope': scope,
                             'kind': r['kind'], 'callee': r.get('callee'),
                             'owner': f['owner'], 'field': field,
                             'version': f['version'], 'path': f['path'],
                             'descriptor': descriptor, 'reason': reason})
    # Start with declared target coordinates, then inspect actual forwarding.
    # Multiple source occurrences are retained, never resolved by equal values.
    target_count = 0
    target_objects = defaultdict(set)
    for r in rows:
        family = scopes.get(r.get('frame'))
        if r['kind'] != 'binding-return' or not family:
            continue
        for f in r['fields']:
            parts, pattern = f['path'].split('/'), plan['response_binding']['path'].split('/')
            if len(parts) != len(pattern) or any(a != b and b != '*' for a, b in zip(parts, pattern)):
                continue
            target_count += 1
            target_objects[family].add(f['owner'])
            if r.get('result', {}).get('object'):
                target_objects[family].add(r['result']['object'])
            candidates = sources[(family, coordinate(f))]
            witnesses.append({'root': family, 'return_seq': r['seq'], 'target':
                              {k: f[k] for k in ('path', 'owner', 'field', 'version')},
                              'co_coordinate_sources': [
                                  {'seq': s['seq'], 'callee': s.get('callee'),
                                   'call_id': s.get('source_call_id'), 'path': v['path']}
                                  for s, v in candidates],
                              'member_copy_completions': [t['completion_seq'] for t in transfers
                                                          if t['root'] == family and f['owner'] in t['members']],
                              'certified_dependency': False})
    for t in transfers:
        earlier = [r for r in rows if r['kind'] == 'binding-source'
                   and scopes.get(r.get('frame')) == t['root'] and r['seq'] < t['begin_seq']
                   and any(f['owner'] in t['members'] for f in r['fields'])]
        for r in earlier:
            chronology.append({'root': t['root'], 'source_seq': r['seq'],
                               'copy_begin_seq': t['begin_seq'], 'cache_seq': t['cache_seq'],
                               'copy_complete_seq': t['completion_seq'],
                               'future_copy_proof_available_at_source': available_before(
                                   r['seq'], [[t['cache_seq']], [t['completion_seq']]])})
    forwarded = []
    for row in rows:
        family = scopes.get(row.get('frame'))
        if row['kind'] == 'collection-call-exit' and row.get('result', {}).get('object') in target_objects[family]:
            key = (row.get('frame'), row.get('call_id'))
            forwarded.append({'root': family, 'exit_seq': row['seq'], 'object': row['result']['object'],
                              'start_candidates': [{'seq': c['seq'], 'callee': c['callee'], 'pc': c['pc']}
                                                   for c in calls[key]],
                              'finish_candidates': [r['seq'] for r in finishes[key]],
                              'meaning': 'same physical reference only, not no-effects or ownership proof'})
    mappings = []
    for method, effect in plan.get('execution_kernel', {}).get('constructors', {}).items():
        if isinstance(effect, dict) and effect.get('kind') == 'assignments':
            mappings.append({'method': method, 'fields': effect['fields'],
                             'demands': 'Current interpreter binds every specified argument/write; no per-output demand interface.'})
    retained = [dict(zip(('scope', 'kind', 'field', 'descriptor', 'reason'), key), count=n)
                for key, n in sorted(records.items(), key=lambda p: str(p[0]))]
    old_omitted = [dict(zip(('scope', 'mechanism', 'field'), key), count=n)
                   for key, n in sorted(omissions.items())]
    return {'events': len(rows), 'roots': sum(v[0]['method'] == plan['entry'] for v in entries.values()),
            'declared_target_occurrences': target_count,
            'existing_omissions': old_omitted, 'retained': retained,
            'boundary_field_inventory': detailed, 'target_identity_witnesses': witnesses,
            'typed_member_copies': transfers, 'proof_timing': chronology,
            'object_forwarding_witnesses': forwarded, 'fixed_field_mapping_specs': mappings,
            'retained_read_sites': [{'field': k[0], 'site': k[1], 'count': n}
                                    for k, n in sorted(reads.items(), key=lambda p: str(p[0]))],
            'interpretation': 'Physical witnesses only; no origins, known status or correctness score computed. Qualification is a separate reviewed decision.'}


def run(protocol, out):
    cfg = json.loads(protocol.read_text())
    out.mkdir(parents=True, exist_ok=False)
    summary = {}
    for task, spec in cfg['tasks'].items():
        cap, pp = Path(spec['capture']), Path(spec['plan'])
        assert sha(cap) == spec['capture_sha256'] and sha(pp) == spec['plan_sha256']
        plan = json.loads(pp.read_text())
        rows = [json.loads(line) for line in cap.open()]
        result = inspect(plan, rows)
        save(out / (task + '.json'), result)
        boxes = [r for r in result['retained'] if r['scope'] == 'query_selected'
                 and r['reason'].startswith('boxed_payload_candidate')]
        summary[task] = {'events': result['events'], 'roots': result['roots'],
                         'target_occurrences': result['declared_target_occurrences'],
                         'already_omitted_in_query': sum(r['count'] for r in result['existing_omissions']
                                                       if r['scope'] == 'query_selected'),
                         'retained_selected_fields': sum(r['count'] for r in result['retained']
                                                         if r['scope'] == 'query_selected'),
                         'boxed_payload_upper_bound_occurrences': sum(r['count'] for r in boxes),
                         'boxed_fields': boxes, 'copy_completions': len(result['typed_member_copies']),
                         'source_snapshots_preceding_copy_proof': len(result['proof_timing']),
                         'capture_sha256': sha(cap), 'plan_sha256': sha(pp)}
    save(out / 'summary.json', {'reference': cfg['reference_core'], 'tasks': summary,
                              'online_experiment': False, 'shadow_not_a_sound_slice_or_provenance_oracle': True})
    with (out / 'retained-fields.csv').open('w') as f:
        keys = ['task', 'scope', 'kind', 'field', 'descriptor', 'reason', 'count']
        writer = csv.DictWriter(f, fieldnames=keys, lineterminator='\n'); writer.writeheader()
        for task in summary:
            for row in json.loads((out / (task + '.json')).read_text())['retained']:
                writer.writerow(dict(task=task, **row))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--protocol', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args(); run(args.protocol.resolve(), args.out.resolve())
