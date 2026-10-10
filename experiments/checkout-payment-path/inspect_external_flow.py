#!/usr/bin/env python3
"""Offline inspection of an external --trace-flow archive; never executes it.

Finds loss of register tags across recorded branches/returns that do not write
those registers. Such a gap can include unrecorded signal/runtime activity;
this report does not attribute the loss to the branch instruction itself.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
from zipfile import ZipFile


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def elf_bytes(data, address, size):
    require(data[:6] == b'\x7fELF\x02\x01', 'Require ELF64 little endian')
    phoff = struct.unpack_from('<Q', data, 32)[0]
    entsize, count = struct.unpack_from('<HH', data, 54)
    for i in range(count):
        off = phoff + i * entsize
        kind, _, fileoff, va, _, filesz = struct.unpack_from('<IIQQQQ', data, off)
        if kind == 1 and va <= address and address + size <= va + filesz:
            start = fileoff + address - va
            return data[start:start + size]
    raise ValueError('Instruction outside ELF file-backed load segment')


def inspect_contexts(flow, labels):
    """Pair recorded signal callbacks; value equality is diagnostic, not provenance."""
    finish = flow[-1]
    if not finish.get('context_diagnostics'):
        require(not any(r['kind'] in ('context_change', 'context_resume') for r in flow),
                'Context records without enabled marker')
        return dict(enabled=False, signal_pairs=[], events=[])
    events, resumes, stacks, pairs = {}, {}, {}, []
    unpaired_returns = 0
    for r in flow:
        if r['kind'] == 'context_change':
            require(r['id'] == len(events) + 1, 'Invalid context event sequence')
            events[r['id']] = r
            stack = stacks.setdefault(r['tid'], [])
            if r['reason'] == 'signal':
                stack.append(r)
            elif r['reason'] == 'sigreturn' and stack:
                entry = stack.pop()
                require(entry['from'] is not None and r['to'] is not None, 'Missing signal context')
                changes = []
                for reg in entry['shadow_at_callback']:
                    old = labels(entry['shadow_at_callback'][reg])
                    now = labels(r['shadow_at_callback'][reg])
                    if not old and not now and reg not in ('R10', 'R11'):
                        continue
                    values_recorded = reg in entry['from']['registers'] and reg in r['to']['registers']
                    changes.append(dict(register=reg, entry_labels=sorted(old), return_labels=sorted(now),
                        interrupted_value_restored=(entry['from']['registers'][reg] == r['to']['registers'][reg])
                            if values_recorded else None,
                        labels_lost=sorted(old - now)))
                pairs.append(dict(signal_event=entry['id'], return_event=r['id'],
                                  signal_number=entry['info'], registers=changes))
            elif r['reason'] == 'sigreturn':
                unpaired_returns += 1
        elif r['kind'] == 'context_resume':
            require(r['id'] in events and r['id'] not in resumes, 'Invalid context resume sequence')
            require(r['tid'] == events[r['id']]['tid'], 'Context resume changed thread')
            require(r['actual'] is not None, 'Missing resumed context')
            resumes[r['id']] = r
    require(finish['context_events'] == len(events) and finish['context_resumes'] == len(resumes),
            'Context count mismatch')
    require(set(events) == set(resumes), 'Context event lacks first-instruction observation')
    report = []
    for key, event in events.items():
        resumed = resumes[key]
        report.append(dict(id=key, reason=event['reason'], after_step=event['step'],
            resume_after_step=resumed['step'],
            next_instruction_matches_to=(event['to'] == resumed['actual']),
            registers={reg: dict(callback_labels=sorted(labels(event['shadow_at_callback'][reg])),
                                resumed_labels=sorted(labels(resumed['shadow_before_instruction'][reg])))
                       for reg in event['shadow_at_callback']
                       if reg in ('R10', 'R11') or labels(event['shadow_at_callback'][reg])
                       or labels(resumed['shadow_before_instruction'][reg])}))
    return dict(enabled=True, event_count=len(events), events=report, signal_pairs=pairs,
                unpaired_signal_entries=sum(len(v) for v in stacks.values()),
                unpaired_signal_returns=unpaired_returns,
                caveat='Callback shadow state is sampled once. Signal pairing assumes normal nested returns; '
                       'it does not model modified ucontext, longjmp, or prove a unique cause.')


def inspect(archive, case='one', allow_failed_run=False):
    with ZipFile(archive) as z:
        summaries = [n for n in z.namelist() if n.count('/') == 1 and n.endswith('/summary.json')]
        require(len(summaries) == 1, 'Ambiguous archive root')
        root = summaries[0].rsplit('/', 1)[0] + '/'
        def doc(name): return json.loads(z.read(root + name))
        def records(name): return [json.loads(l) for l in z.read(root + name).decode().splitlines() if l]
        summary = doc('summary.json')
        binary = z.read(root + 'checkout-identity')
        require(hashlib.sha256(binary).hexdigest() == summary['binary_sha256'], 'ELF hash mismatch')
        ins = {r['address']: r for r in doc('diagnostic-instructions.json')}
        for pc, row in ins.items():
            code = bytes.fromhex(row['code'])
            require(elf_bytes(binary, pc, len(code)) == code, 'Diagnostic instruction bytes mismatch')
        flow = records(case + '/libdft_payment/flow.jsonl')
        origins = records(case + '/libdft_payment/origins.jsonl')
        require(flow and flow[-1]['kind'] == 'flow_finish' and flow[-1]['exit_code'] == 0, 'Incomplete flow log')
        require(origins[-1]['kind'] == 'finish' and origins[-1]['exit_code'] == 0, 'Invalid origin log completion')
        failed = origins[-1]['bad']
        require(allow_failed_run or not failed, 'Invalid origin log completion')
        dictionary = {}
        for r in flow:
            if r['kind'] != 'tag_dictionary':
                continue
            require(r['tag'] not in dictionary, 'Duplicate tag dictionary entry')
            labels = set()
            for begin, end in r['segments']:
                require(0 <= begin <= end <= 67, 'Out-of-range source segment')
                labels.update(range(begin, end))
            dictionary[r['tag']] = labels
        def labels(tags):
            require(all(t in dictionary for t in tags), 'Missing tag dictionary entry')
            return set().union(*(dictionary[t] for t in tags))
        source_pairs = [r for r in origins if r['kind'] == 'source_field_pair']
        source_reads = [r for r in flow if r['kind'] == 'source_tag_readback']
        require(len(source_pairs) == len(source_reads) and source_reads, 'Missing source readback')
        require([r['index'] for r in source_reads] == list(range(len(source_reads))), 'Invalid source order')
        for r in source_reads:
            for field, width, label in [('Units', 8, 1 + 2*r['index']), ('Nanos', 4, 2 + 2*r['index'])]:
                require(len(r[field]) == width and all(labels([t]) == {label} for t in r[field]), 'Source was not correctly tagged')
        steps = [r for r in flow if r['kind'] == 'before_instruction']
        require([r['step'] for r in steps] == list(range(1, len(steps) + 1)), 'Noncontiguous step sequence')
        require(flow[-1]['steps'] == len(steps), 'Step count mismatch')
        contexts = inspect_contexts(flow, labels)
        gaps = []
        for a, b in zip(steps, steps[1:]):
            previous = ins[a['pc']]
            code = bytes.fromhex(previous['code'])
            # Exact machine encodings: near conditional branch or near RET.
            branch = len(code) == 6 and code[:1] == b'\x0f' and 0x80 <= code[1] <= 0x8f
            ret = code == b'\xc3'
            if not (branch or ret) or a['tid'] != b['tid']:
                continue
            for reg in ('R10', 'R11'):
                before, after = a['registers'][reg], b['registers'][reg]
                old, new = labels(before['tags']), labels(after['tags'])
                if old and not new and before['value'] == after['value']:
                    gaps.append(dict(before_step=a['step'], after_step=b['step'], register=reg,
                        before_function=previous['function'], before_instruction=previous['asm'],
                        after_function=ins[b['pc']]['function'], after_instruction=ins[b['pc']]['asm'],
                        lost_source_labels=sorted(old), value_unchanged=True,
                        interpretation='Unexplained by this recorded branch/return; unrecorded context activity remains possible'))
        sink = [r for r in origins if r['kind'] == 'sink']
        require(len(sink) == 1 or (allow_failed_run and failed and not sink), 'Expected a single diagnostic sink')
        return dict(source_readback_verified=True, source_fields=2*len(source_reads),
                    controlled_diagnostic=summary.get('controlled_diagnostic', False),
                    thread_control=summary.get('thread_control', 'default'),
                    adapter_rejected_run=failed, instruction_trace_may_be_partial=failed,
                    adapter_errors=[r['reason'] for r in origins if r['kind'] == 'error'],
                    diagnostic_instruction_count=len(ins), executed_diagnostic_steps=len(steps),
                    register_tag_loss_gaps=gaps,
                    raw_sink_labels={k:sink[0][k] for k in ('Units','Nanos')} if sink else None,
                    uncovered_opcode_kinds=origins[-1]['unhandled_opcode_kinds'],
                    wrapper_status=doc(case + '/libdft_payment/observation.json')['status'],
                    context_diagnostics=contexts,
                    performance_eligible=False,
                    limitation='Recorded gaps alone do not establish the context-loss mechanism. '
                               'Context callbacks, when enabled, add temporal evidence but do not validate propagation semantics.')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('archive', type=Path)
    p.add_argument('--case', default='one')
    p.add_argument('--allow-failed-run', action='store_true',
                   help='Inspect completed but adapter-rejected runs as partial diagnostics only')
    args = p.parse_args()
    print(json.dumps(inspect(args.archive, args.case, args.allow_failed_run), ensure_ascii=False, indent=2))
