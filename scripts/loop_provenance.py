#!/usr/bin/env python3
"""Loop pilot: version definitions by execution, not static instruction address.

All instructions in each configured leaf function are observed. No path
enumeration/unrolling bound is used to guess executions. A replay budget fails
closed; it never truncates a history and returns a partial success.
"""
from collections import Counter
from functools import partial
import struct

import hybrid_provenance as common
import interproc_provenance as collector
from interproc_model import Machine, STACK_WORDS, decode, symbolic_path
from hybrid_model import BRANCHES, require, validate_config
from language_adapters import get_adapter
from interproc_model import REGS

MAX_EXECUTED_STEPS = 4096


def plan_program(assembly, symbols, config):
    validate_config(config)
    plans = []
    for name in config['functions']:
        require(name in symbols, 'Unknown root')
        p = decode(name, assembly, symbols)
        for n in p['instructions']:
            require(n['op'] != 'call', 'Loop pilot supports leaf functions only')
            if n['op'] in BRANCHES | {'jmp'}:
                require(n['target'] != 0, 'A loop must not re-enter the root entry probe')
        p.update(is_root=True, paths=[], static_sources=[],
                 probe_offsets=[n['offset'] for n in p['instructions']],
                 probe_counts=dict(selected=len(p['instructions']), all_instructions=len(p['instructions'])),
                 planning='CFG with cycles; all instruction locations; no candidate path enumeration')
        plans.append(p)
    return plans


def infer(events, plans, config, runtime_bases):
    require(runtime_bases is not None, 'Executable mapping required')
    adapter = get_adapter(config)
    try:
        adapter.context.validate(events, REGS)
    except (ValueError,KeyError,IndexError) as exc:
        return dict(results=[], issues=[dict(error=str(exc))], oracle_used_for_inference=False)
    groups, results, issues = adapter.context.group(events), [], []
    functions = {p['function']: p for p in plans}
    for (tid, call), rows in sorted(groups.items()):
        try:
            require(len(rows) <= MAX_EXECUTED_STEPS, 'Executed instruction budget exceeded; no partial result')
            rows.sort(key=lambda r: r['sequence'])
            require([r['sequence'] for r in rows] == list(range(len(rows))), 'Missing or duplicate sequence')
            first = rows[0]; rid = first['root']
            require(0 <= rid < len(plans), 'Unknown root')
            root = plans[rid]; name = root['function']
            require(first['offset'] == 0, 'Missing root entry')
            require(all(r['function'] == r['root'] == rid and r['depth'] == 1 for r in rows), 'Mixed root/function/depth')
            require(all(rows[i]['timestamp'] <= rows[i+1]['timestamp'] for i in range(len(rows)-1)), 'Non-monotonic sequence')
            require(all(len(r['regs']) == 16 and len(r['inputs']) == len(config['input_fields']) and
                        len(r['outputs']) == len(config['output_fields']) and len(r['stack']) == STACK_WORDS
                        for r in rows), 'Observation shape mismatch')
            instructions = {n['offset']: n for n in root['instructions']}
            machine = Machine(first, config); path = []; visits = Counter(); backedges = 0
            for i, event in enumerate(rows):
                off = event['offset']; require(off in instructions, 'Unknown instruction offset')
                visits[off] += 1
                step = dict(function=name, offset=off, context=[name], depth=1,
                            id='%s|%x@exec%d' % (name, off, i), occurrence=visits[off])
                machine.check(event, step, runtime_bases)
                nxt = machine.step(instructions[off], runtime_bases)
                expected = None if i+1 == len(rows) else runtime_bases[name]+rows[i+1]['offset']
                require(nxt == expected, 'Executed CFG edge disagrees with events or incomplete return')
                if nxt is not None and nxt <= runtime_bases[name]+off: backedges += 1
                path.append(step)
            analyzed = symbolic_path(path, functions, config, distinguish_reads=True)
            require(analyzed is not None, 'Symbolic constant branch contradicts observed path')
            read_map = {r['id']: r for r in analyzed['source_reads']}
            require(all(s in read_map for s in analyzed['sources']), 'Sink depends on a non-read boundary')
            contributing = [read_map[s] for s in analyzed['sources']]
            edges = analyzed['edges']; keep = {analyzed['sink_node']}
            kinds = {'data', 'address', 'argument', 'return'}
            while True:
                before = len(keep)
                keep.update(e['source'] for e in edges if e['target'] in keep and e['kind'] in kinds)
                if len(keep) == before: break
            prefix = '%s:%s:' % (tid, call)
            graph = dict(nodes=[dict(id=prefix+n, local_node=n, **analyzed['nodes'].get(n, dict(kind='boundary')))
                                for n in sorted(keep)],
                         edges=[dict(source=prefix+e['source'], target=prefix+e['target'], kind=e['kind'])
                                for e in edges if e['source'] in keep and e['target'] in keep and e['kind'] in kinds],
                         identity_scope='root invocation + executed instruction ordinal; source read ordinal within root')
            results.append(dict(pid_tid=tid, call_id=call, function=name, status='resolved',
                                sources=sorted({r['field'] for r in contributing}), static_sources=[],
                                value=rows[-1]['outputs'][config['output_fields'].index(config['sink_field'])],
                                sink='output.'+config['sink_field'],
                                source_reads=analyzed['source_reads'], contributing_reads=contributing,
                                summary=dict(executed_instructions=len(rows), backward_edges=backedges,
                                             instruction_visits={str(k): v for k,v in sorted(visits.items())},
                                             total_source_reads=len(read_map), contributing_source_reads=len(contributing)),
                                dependency_graph=graph))
        except (ValueError, KeyError, IndexError, TypeError, struct.error) as exc:
            issues.append(dict(pid_tid=tid, call_id=call, error=str(exc)))
    return dict(results=results, issues=issues, oracle_used_for_inference=False,
                scope='single-thread leaf loops; immutable input memory; explicit executed read dependencies')


def evaluate(inferred, oracle, stats, plans):
    result = common.evaluate(inferred, oracle, stats, plans)
    # This pilot tests dynamic versions, not a static source precision baseline.
    result.pop('static_source_relations')
    rows = {r['call_id']: r for r in inferred['results']}
    tp = fp = fn = 0
    for truth, check in zip(oracle, result['checks']):
        row = rows.get(truth['sequence'], {})
        expected = set(truth['expected_read_instances'])
        actual = {r['id'] for r in row.get('contributing_reads', [])} if row.get('function') == truth['function'] else set()
        tp += len(expected & actual); fp += len(actual-expected); fn += len(expected-actual)
        check.update(expected_read_instances=sorted(expected), observed_read_instances=sorted(actual))
        check['passed'] = check['passed'] and expected == actual
    expected_ids = {t['sequence'] for t in oracle}
    fp += sum(len(r['contributing_reads']) for r in inferred['results'] if r['call_id'] not in expected_ids)
    result['passed'] = result['passed'] and all(c['passed'] for c in result['checks'])
    result['read_instance_relations'] = dict(tp=tp, fp=fp, fn=fn,
        precision=tp/(tp+fp) if tp+fp else None, recall=tp/(tp+fn) if tp+fn else None)
    result['scope'] = 'fixture field and executed-read identity accuracy; not database read operations or complete graph edge recall'
    return result


build = partial(common.build, planner=plan_program, source_generator=collector.bpf_source,
                extra_flags=('-fno-optimize-sibling-calls', '-fno-ipa-ra'))

if __name__ == '__main__':
    raise SystemExit(common.main(default_scenario=common.ROOT/'scenarios/loop-provenance',
        prefix='loop-provenance', build_fn=build, record_fn=collector.record, infer_fn=infer, evaluate_fn=evaluate))
