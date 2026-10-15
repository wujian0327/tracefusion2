#!/usr/bin/env python3
"""Bounded security application of readonly field observations.

Static instruction operands + runtime branch choices reconstruct reference copies;
no online taint propagation and no fixture/oracle input. Unknown calls fail closed.
HTTP joins use independent message IDs and property names, never values/request IDs.
"""
from collections import defaultdict
import copy
import hashlib
import json
import re


def read_events(path):
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    if [r['seq'] for r in rows] != list(range(1, len(rows) + 1)):
        raise ValueError('Event sequence gap')
    if any(r['kind'] in ('problem', 'abort') for r in rows):
        raise ValueError('Incomplete or failed observation')
    if len({r['process'] for r in rows}) != 1:
        raise ValueError('Mixed process capture')
    versions = defaultdict(int)
    for row in rows:
        if row['kind'] in ('read', 'write'):
            key = (row['owner'], row['field'])
            if row['kind'] == 'write':
                versions[key] += 1
            if row['version'] != versions[key]:
                raise ValueError('Field version discontinuity')
    return rows


def token(origins=(), known=True, **extra):
    return dict(origins=list(origins), known=known, evidence=[], **extra)


def unknown(reason):
    return token(known=False, reason=reason)


def wire_binding(send, enter):
    if send['message'] != enter['message'] or send['wire'] != enter['wire']:
        raise ValueError('Message body mismatch')
    for row in (send, enter):
        if hashlib.sha256(row['wire'].encode()).hexdigest() != row['wire_sha256']:
            raise ValueError('Wire checksum mismatch')
    body = json.loads(send['wire'])
    if set(body) != {'secret', 'publicValue', 'businessId'} or any(not isinstance(v, str) for v in body.values()):
        raise ValueError('Unsupported wire schema')
    sources = {f['property']: f for f in send['fields']}
    targets = {f['property']: f for f in enter['fields']}
    if set(sources) != set(body) or set(targets) != set(body):
        raise ValueError('Incomplete DTO capture')
    bindings = {}
    for prop, value in body.items():
        source, target = sources[prop], targets[prop]
        # Identity/property join above; values only validate the chosen edge.
        if source['observed']['value'] != value or target['observed']['value'] != value:
            raise ValueError('Selected property value changed')
        coord = [send['process'], send['message'], source['owner'], source['field'], source['version']]
        bindings[(target['owner'], target['field'], target['version'])] = token(
            [coord], ref=target['observed']['object'], actual=value,
            property=prop, source_seq=send['seq'], receiver_seq=enter['seq'])
    return bindings


def argument_count(desc):
    return len(re.findall(r'\[*L[^;]+;|\[*[ZBCSIJFD]', desc[1:desc.index(')')]))


def replay(model, enter, rows, bindings):
    """Only the admitted reference-copy/control subset is executed offline."""
    instructions = model['instructions']
    by_site = {r['site']: r for r in instructions}
    observed = [r for r in rows if r['kind'] in ('read', 'write', 'branch', 'sink-argument')]
    cursor = 0
    locals_ = {0: token(ref=enter['record'])}
    stack, writes, allocations = [], {}, {}
    answer = None

    def consume(kind, site):
        nonlocal cursor
        if cursor >= len(observed):
            raise ValueError('Missing runtime observation')
        row = observed[cursor]
        if row['kind'] != kind or row['site'] != site:
            raise ValueError('Static/runtime instruction mismatch')
        cursor += 1
        return row

    def owner_matches(t, owner):
        if 'allocation' in t:
            key = t['allocation']
            if key not in allocations:
                allocations[key] = owner
            return allocations[key] == owner
        return t.get('ref') == owner

    pc = 0
    for _ in range(10000):
        n = by_site[pc]
        op, site = n['op'], n['site']
        if op == 25:  # ALOAD
            stack.append(copy.deepcopy(locals_.get(n['var'], unknown('unmodelled-input-argument'))))
        elif op == 58:  # ASTORE
            locals_[n['var']] = stack.pop()
        elif op == 18:  # LDC string constant
            stack.append(token(actual=n['constant']))
        elif op == 1:
            stack.append(token(actual=None))
        elif op == 187:  # NEW; bind allocation identity at its first observed field access
            stack.append(token(allocation=(enter['frame'], site)))
        elif op == 89:
            stack.append(copy.deepcopy(stack[-1]))
        elif op == 87:
            stack.pop()
        elif op in (180, 181):
            value = stack.pop() if op == 181 else None
            owner = stack.pop()
            row = consume('write' if op == 181 else 'read', site)
            declared = n['owner'] + '.' + n['name']
            if row['field'] != declared:
                raise ValueError('Declared field mismatch')
            key = (row['owner'], row['field'], row['version'])
            matches = owner_matches(owner, row['owner'])
            if op == 181:
                stored = copy.deepcopy(value) if matches else unknown('unresolved-write-owner')
                stored['evidence'].append(row['seq'])
                writes[key] = stored
            else:
                resolved = copy.deepcopy(writes.get(key, bindings.get(key, unknown('unobserved-reaching-write')))) if matches else unknown('unresolved-read-owner')
                if resolved['known'] and 'actual' in resolved and resolved['actual'] != row['observed']['value']:
                    raise ValueError('Reconstructed field value differs')
                resolved['evidence'].append(row['seq'])
                resolved['actual'] = row['observed']['value']
                resolved['ref'] = row['observed']['object']
                stack.append(resolved)
        elif op in (182, 183, 184, 185):
            args = [stack.pop() for _ in range(argument_count(n['desc']))][::-1]
            if op != 184:
                stack.pop()
            if n['owner'] == 'SecurityLeakLab$Sink' and n['name'] == 'write':
                row = consume('sink-argument', site)
                answer = copy.deepcopy(args[0]);answer['sink_seq'] = row['seq']
                answer['sink_site'] = site;answer['observed'] = row['observed']
                if answer['known'] and 'actual' in answer and answer['actual'] != row['observed']['value']:
                    raise ValueError('Actual sink argument differs')
                if answer['known'] and answer.get('ref') is not None and answer['ref'] != row['observed']['object']:
                    raise ValueError('Actual sink argument identity differs')
            elif n['desc'].split(')')[1] != 'V':
                stack.append(unknown('unsupported-call:' + n['owner'] + '.' + n['name'] + n['desc']))
            elif not (op == 183 and n['owner'] == 'SecurityLeakLab$Box'
                      and n['name'] == '<init>' and n['desc'] == '()V'):
                raise ValueError('Unsupported side-effecting void call')
        elif 153 <= op <= 166 or op in (198, 199):
            stack.pop()
            if 159 <= op <= 166:
                stack.pop()
            row = consume('branch', site)
            pc = n['target'] if row['taken'] else pc + 1
            continue
        elif op == 167:
            pc = n['target'];continue
        elif op == 177:
            if cursor != len(observed) or answer is None:
                raise ValueError('Unconsumed observations or missing sink')
            return answer
        else:
            raise ValueError('Unsupported instruction ' + str(op))
        pc += 1
    raise ValueError('Instruction bound exceeded')


def infer(source_path, target_path):
    sender, receiver = read_events(source_path), read_events(target_path)
    sends = {}
    for row in sender:
        if row['kind'] == 'http-send':
            if row['message'] in sends:
                raise ValueError('Duplicate HTTP send identity')
            sends[row['message']] = row
    models = [r for r in receiver if r['kind'] == 'model']
    if len(models) != 1:
        raise ValueError('Exactly one observed Flow bytecode model required')
    grouped = defaultdict(list)
    for row in receiver:
        if row.get('frame'):
            grouped[row['frame']].append(row)
    answers, messages = [], set()
    for frame, rows in grouped.items():
        if rows[0]['kind'] != 'enter' or rows[-1]['kind'] != 'exit':
            raise ValueError('Incomplete flow frame')
        entry = rows[0];message = entry['message']
        if message in messages:
            raise ValueError('Duplicate HTTP receive identity')
        messages.add(message)
        send = sends.get(message)
        if send is None:
            answer = unknown('missing-http-message');answer['sink_seq'] = None
        else:
            bindings = wire_binding(send, entry)
            answer = replay(models[0], entry, rows, bindings)
        actual = [r for r in rows if r['kind'] == 'log-argument']
        if len(actual) != 1:
            raise ValueError('Actual logger argument was not observed exactly once')
        if answer.get('observed') and actual[0]['observed'] != answer['observed']:
            raise ValueError('Wrapper/logger argument mismatch')
        lookups = [r for r in rows if r['kind'] == 'jndi-lookup']
        origins = answer['origins']
        sensitive = any(c[3] == 'SecurityLeakLab$Record.secret' for c in origins)
        untrusted = any(c[3] in ('SecurityLeakLab$Record.secret', 'SecurityLeakLab$Record.publicValue') for c in origins)
        # Explicit, bounded library summary: a sole literal ${jndi:key} message
        # supplies key to JndiLookup. Match the actually observed argument only
        # after the source-attributed logger/frame association; never select origins by text.
        expression = re.fullmatch(r'\$\{jndi:([^{}]+)\}', actual[0]['observed']['value'])
        lookup_relation = bool(lookups)
        if lookups and (expression is None or len(lookups) != 1 or lookups[0]['key'] != expression[1]):
            lookup_relation = None
        answers.append(dict(answer, frame=frame, request_id=entry['request_id'],
                            message=message, logger_seq=actual[0]['seq'], logger_value=actual[0]['observed']['value'],
                            jndi_lookups=[{'seq':r['seq'],'key':r['key']} for r in lookups],
                            disclosure=sensitive if answer['known'] else None,
                            unsafe_lookup=(bool(untrusted and lookup_relation) if lookup_relation is not None else None) if answer['known'] else None))
    return {'engine':'TraceFusion bounded readonly security field-flow extension',
            'answers':answers,'message_count':len(messages),'source_count':len(sends),
            'oracle_consumed':False,'case_modes_consumed':False,
            'matching_uses_values':False,'matching_uses_request_ids':False,
            'online_labels_propagated':False,
            'limitations':['Only admitted acyclic reference-copy bytecode and actually observed branch choices.',
                           'Unknown helper calls remain unknown; no value-based origin recovery.',
                           'Single HTTP hop, default three-String DTO schema, no custom serialization.',
                           'Data dependence only; no implicit/control-flow taint.',
                           'JNDI rule uses an explicit sole-literal ${jndi:key} summary, validated against the actual same-frame native lookup argument; it does not reconstruct every internal Log4j statement.',
                           'DTOs are thread-owned and immutable outside the observed Flow writes; the audited fresh Box constructor has no field writes.',
                           'A sensitive-to-log alert presumes the configured log destination is forbidden for that field; it is not a universal vulnerability judgement.']}
