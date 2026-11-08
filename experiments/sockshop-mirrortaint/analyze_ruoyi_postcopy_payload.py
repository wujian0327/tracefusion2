"""Narrow, read-only post-copy association and protocol-size estimate.

Never emits a modified capture or an authentication permission. New snapshot
stage counters are NOT present in the old capture: the byte model uses minimum
one-digit placeholders, not invented evidence. No predictions/oracle are read.
"""
import argparse
from collections import Counter, defaultdict
import copy
import csv
import json
from pathlib import Path

from analyze_target_demand_shadow import BOXED, sha, save
from external_transfer_oracle import require_complete_raw_capture

COPY = 'com/alibaba/fastjson2/JSONArray.toList(Ljava/lang/Class;[Lcom/alibaba/fastjson2/JSONReader$Feature;)Ljava/util/List;'


def encoded(row):
    return json.dumps(row, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()


def unique(rows, reason):
    if len(rows) != 1:
        raise ValueError(reason + ': ' + str(len(rows)))
    return rows[0]


def member_at(field, members):
    bits = field['path'].split('/')
    if len(bits) != 3 or not bits[1].isdigit():
        return False
    index = int(bits[1])
    return index < len(members) and members[index].get('object') == field['owner']


def same_slot_and_reference(before, after):
    return all(before.get(k) == after.get(k) for k in ('path', 'owner', 'field', 'version')) and \
        before['observed'].get('object') == after['observed'].get('object')


def select_point(plan, rows, completed, calls, ends, enters, frame_ends):
    """Associate the immediate outer return, never any later same-valued row."""
    proof = completed['json_list_copy']
    start = unique(calls[(completed['frame'], completed['call_id'])], 'copy start')
    assert unique(ends[(completed['frame'], completed['call_id'])], 'copy completion') == completed
    assert start['callee'] == COPY
    assert start['collection'] == completed['collection_after'] == proof['members']
    assert start['collection_epoch'] == completed['collection_epoch']
    assert proof['result_epoch'] == 0 and completed['result_type'] == 'java.util.ArrayList'
    assert completed['result']['object'] != start['receiver']['object']
    child = unique(enters[completed['frame']], 'copy owner frame')
    child_end = unique(frame_ends[child['frame']], 'copy owner completion')
    assert child_end['kind'] == 'exit' and child_end['result'] == completed['result']
    instructions = plan['execution_kernel']['methods'][child['method']]['instructions']
    assert instructions[completed['pc'] + 1]['op'] == 176  # direct ARETURN
    assert start['seq'] < completed['seq'] < child_end['seq']
    outer_candidates = [c for values in calls.values() for c in values
                        if c['frame'] == child['parent'] and c['callee'] == child['method']
                        and c['method'] + '@' + str(c['pc']) == child['callsite']
                        and c['seq'] < child['seq']]
    # Keep all matching starts; a duplicate is not resolved by "latest".
    pairs = [(c, e) for c in outer_candidates for e in ends[(c['frame'], c['call_id'])]
             if child_end['seq'] < e['seq']]
    outer, outer_end = unique(pairs, 'enclosing call association')
    assert outer_end['kind'] == 'collection-call-exit' and outer_end['result'] == completed['result']
    snapshot = unique([r for r in rows if r['kind'] == 'binding-opaque-result'
                       and r['frame'] == outer['frame'] and r['callee'] == child['method']
                       and child_end['seq'] < r['seq'] < outer_end['seq']], 'outer result snapshot')
    assert snapshot['thread'] == child_end['thread'] == completed['thread'] == outer['thread']
    between = [r for r in rows if completed['seq'] < r['seq'] < snapshot['seq']]
    assert [r['seq'] for r in between] == [child_end['seq']], 'intervening effects/callbacks'
    before = unique([r for r in rows if r['kind'] == 'binding-opaque-result'
                     and r['frame'] == start['frame'] and r['callee'] == COPY
                     and start['seq'] < r['seq'] < completed['seq']], 'copy own snapshot')
    return snapshot, before, outer, child_end


def byte_model(snapshot, indices, completed, before, outer):
    """Costs only; proposed types/guards are not installed in the real decoder."""
    # x:1 means specifically "non-null java.lang.Long payload omitted".
    # xp ties this snapshot to copy completion, its full previous snapshot,
    # active enclosing invocation and the actual list value argument.
    permit = [completed['seq'], before['seq'], outer['call_id'], completed['result']['object']]
    tag_only = copy.deepcopy(snapshot); tag_only['xp'] = permit
    gross = 0
    for index in indices:
        observed = snapshot['fields'][index]['observed']
        assert observed.get('object') is not None and type(observed.get('value')) is int
        assert -(2**63) <= observed['value'] < 2**63
        gross += len(encoded(observed)) - len(encoded({'object': observed['object']}))
        tag_only['fields'][index]['observed'] = {'object': observed['object'], 'x': 1}
    # Even without new stage guard samples, calculate the compact tag cost.
    minimum_tag_delta = len(encoded(tag_only)) - len(encoded(snapshot))
    # A denser grouped marker sensitivity model. Positions and a type code
    # explicitly mark omitted payloads; raw slot coordinates stay unchanged.
    grouped = copy.deepcopy(snapshot); grouped['xp'] = [*permit, 1, indices]
    for index in indices:
        del grouped['fields'][index]['observed']['value']
    grouped_delta = len(encoded(grouped)) - len(encoded(snapshot))
    # Proposed conservative stage witness: epoch, size-before/after,
    # modCount-before/after. This is not claimed to be a minimal certificate.
    # No values are borrowed from later calls. Zeroes are byte lower bounds
    # for THIS schema only, never invented runtime evidence.
    tag_only['xp'] += [0, 0, 0, 0, 0]
    grouped['xp'] += [0, 0, 0, 0, 0]
    return {'snapshot_seq': snapshot['seq'], 'copy_seq': completed['seq'],
            'before_snapshot_seq': before['seq'], 'outer_call_id': outer['call_id'],
            'result_owner': completed['result']['object'], 'field_indices': indices,
            'payload_occurrences': len(indices), 'gross_value_bytes': gross,
            'tag_delta_without_new_stage_samples': minimum_tag_delta,
            'grouped_delta_without_new_stage_samples': grouped_delta,
            'tag_delta_with_minimum_stage_samples': len(encoded(tag_only)) - len(encoded(snapshot)),
            'grouped_delta_with_minimum_stage_samples': len(encoded(grouped)) - len(encoded(snapshot)),
            'stage_samples_are_missing_not_synthesized_evidence': True}


def run(protocol, out):
    spec = json.loads(protocol.read_text())['input']
    cap, plan_path = Path(spec['capture']), Path(spec['plan'])
    assert sha(cap) == spec['capture_sha256'] and sha(plan_path) == spec['plan_sha256']
    lines = cap.read_bytes().splitlines(); rows = [json.loads(line) for line in lines]
    require_complete_raw_capture(rows)
    # Establish exact compatibility with the persisted compact UTF-8 encoder.
    assert all(encoded(r) == line for r, line in zip(rows, lines))
    plan = json.loads(plan_path.read_text()); calls, ends = defaultdict(list), defaultdict(list)
    enters, frame_ends = defaultdict(list), defaultdict(list)
    for r in rows:
        if r['kind'] == 'collection-call-enter': calls[(r['frame'], r['call_id'])].append(r)
        if r['kind'] in ('collection-call-exit', 'collection-call-throw'): ends[(r['frame'], r['call_id'])].append(r)
        if r['kind'] == 'enter': enters[r['frame']].append(r)
        if r['kind'] in ('exit', 'abort'): frame_ends[r['frame']].append(r)
    def root(frame):
        seen = set()
        while frame is not None:
            if frame in seen: raise ValueError('frame cycle')
            seen.add(frame); event = unique(enters[frame], 'frame parent')
            if event['method'] == plan['entry']: return frame
            frame = event.get('parent')
        return None
    roots = {f: root(f) for f in tuple(enters)}
    properties = {p['field']: p for ps in plan['response_graph_schema'].values() for p in ps}
    required = set(plan['target_observation_closure']['required_fields'])
    candidates = [(r, i, f) for r in rows if roots.get(r.get('frame'))
                  and r.get('target_observation', {}).get('selected')
                  for i, f in enumerate(r.get('fields', []))
                  if f['field'] not in required and properties.get(f['field'], {}).get('descriptor') in BOXED
                  and f['observed'].get('object') is not None and 'value' in f['observed']]
    assert len(candidates) == 12240
    copies = [r for r in rows if r.get('json_list_copy', {}).get('valid') and roots.get(r['frame'])]
    selected, models, point_facts = {}, [], []
    for completed in copies:
        proof = completed['json_list_copy']; cfg = plan['json_list_copy']
        assert proof['version'] == cfg['version'] == 1
        assert proof['class_sha256'] == cfg['class_sha256'] and proof['runtime'] in cfg['profiles']
        init = unique([r for r in rows if r['kind'] == 'json-list-initialized'
                       and r['seq'] == proof['initialized_seq']], 'copy library initialization')
        assert init['loader'] == proof['loader'] and init['seq'] < unique(enters[roots[completed['frame']]], 'query root')['seq']
        for name, digest in cfg['class_sha256'].items():
            loaded = unique([r for r in rows if r['kind'] == 'json-list-class'
                             and r['class'] == name and r['loader'] == proof['loader']], 'copy class')
            assert loaded['class_sha256'] == digest and loaded['seq'] < completed['seq']
        hit = unique([r for r in rows if r['kind'] == 'json-list-cache'
                      and r['call_id'] == completed['call_id']], 'copy cache lookup')
        start = unique(calls[(completed['frame'], completed['call_id'])], 'copy start')
        assert hit['seq'] == proof['cache_seq'] and start['seq'] < hit['seq'] < completed['seq']
        assert hit['frame'] == start['frame'] and hit['thread'] == start['thread']
        assert hit.get('message') == start.get('message') and hit['cache_hit'] is True
        assert hit['field_based'] is False and hit['cache_type'] == 'java.util.concurrent.ConcurrentHashMap'
        assert hit['provider'] == proof['provider'] and hit['target_class'] == proof['target_class'] == start['args'][0]['object']
        snapshot, before, outer, child_end = select_point(plan, rows, completed, calls, ends, enters, frame_ends)
        members = completed['json_list_copy']['members']
        indices = []
        for r, index, field in candidates:
            if r['seq'] != snapshot['seq']: continue
            if properties[field['field']]['descriptor'] != 'Ljava/lang/Long;' or not member_at(field, members): continue
            earlier = unique([f for f in before['fields'] if f['path'] == field['path']], 'prior snapshot field')
            assert same_slot_and_reference(earlier, field), 'slot version/reference changed'
            assert type(field['observed']['value']) is int
            selected[(r['seq'], index)] = completed['seq']; indices.append(index)
        models.append(byte_model(snapshot, indices, completed, before, outer))
        point_facts.append({'copy_seq': completed['seq'], 'copy_frame': completed['frame'],
                            'copy_call_id': completed['call_id'], 'copy_owner': completed['result']['object'],
                            'outer_start_seq': outer['seq'], 'outer_call_id': outer['call_id'],
                            'child_exit_seq': child_end['seq'], 'snapshot_seq': snapshot['seq'],
                            'field_indices': indices, 'members': [m.get('object') for m in members],
                            'new_snapshot_stage_witness_present': False})
    inventory, reasons = [], Counter()
    for r, index, field in candidates:
        if (r['seq'], index) in selected: reason = 'selected_one_outer_result_site'
        elif any(roots.get(c['frame']) == roots[r['frame']] and c['seq'] < r['seq']
                 and any(m.get('object') == field['owner'] for m in c['json_list_copy']['members']) for c in copies):
            reason = 'later_same_member_but_other_snapshot_not_authorized'
        else: reason = 'before_corresponding_copy_completion_or_no_copy'
        reasons[reason] += 1
        inventory.append({'snapshot_seq': r['seq'], 'snapshot_kind': r['kind'], 'frame': r['frame'],
                          'root': roots[r['frame']], 'callee': r.get('callee'), 'field_index': index,
                          'owner': field['owner'], 'field': field['field'], 'version': field['version'],
                          'path': field['path'], 'reason': reason})
    totals = {key: sum(m[key] for m in models) for key in (
        'payload_occurrences', 'gross_value_bytes', 'tag_delta_without_new_stage_samples',
        'grouped_delta_without_new_stage_samples', 'tag_delta_with_minimum_stage_samples',
        'grouped_delta_with_minimum_stage_samples')}
    protocol_header = {'boxed_payload_encoding': {'version': 1, 'types': {'1': 'java.lang.Long'},
                        'scope': 'one-post-copy-result-snapshot', 'missing_permission': 'reject'}}
    header_bytes = len(encoded(protocol_header)) - 2 + 1  # new fields in existing start object
    summary = {'reference_core': 'bcdf059', 'capture_sha256': sha(cap), 'plan_sha256': sha(plan_path),
               'full_capture_events': len(rows), 'original_candidates': len(candidates),
               'raw_associated_one_site_candidates': len(selected), 'selected_snapshots': len(models),
               'selected_payload_still_consumed_as_value': 0,
               'consumer_review_scope': 'Only this binding-opaque-result payload; source/input, reads/writes, calls, other snapshots and output bindings unchanged.',
               'remaining_for_representation_study': len(selected), 'existing_complete_new_licenses': 0,
               'new_stage_witness_absent': True, 'partition': dict(reasons), 'byte_estimate': totals,
               'minimal_protocol_header_bytes': header_bytes,
               'tag_net_delta_without_new_stage_samples': totals['tag_delta_without_new_stage_samples'] + header_bytes,
               'grouped_net_delta_without_new_stage_samples': totals['grouped_delta_without_new_stage_samples'] + header_bytes,
               'tag_net_delta_lower_bound': totals['tag_delta_with_minimum_stage_samples'] + header_bytes,
               'grouped_net_delta_lower_bound': totals['grouped_delta_with_minimum_stage_samples'] + header_bytes,
               'stage_witness_scope': 'A proposed conservative schema, not a proof that all five numbers are necessary in every sound design. Stage-free guard/evidence reuse has not been closed.',
               'positive_delta_means_growth': True, 'new_capture_measurements': None,
               'stop': 'The reviewed stage-witness proposal grows. A denser stage-free variant has a small estimated saving but no completed safety license; no certified positive-net candidate, no Agent trial or core change.'}
    assert summary['tag_net_delta_lower_bound'] > 0 and summary['grouped_net_delta_lower_bound'] > 0
    out.mkdir(parents=True, exist_ok=False)
    save(out/'summary.json', summary); save(out/'point-associations.json', point_facts)
    save(out/'byte-estimates.json', models); save(out/'candidate-inventory.json', inventory)
    with (out/'snapshot-estimates.csv').open('w') as f:
        writer = csv.DictWriter(f, fieldnames=list(models[0]), lineterminator='\n'); writer.writeheader(); writer.writerows(models)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--protocol', required=True, type=Path)
    p.add_argument('--out', required=True, type=Path); a=p.parse_args(); run(a.protocol.resolve(), a.out.resolve())
