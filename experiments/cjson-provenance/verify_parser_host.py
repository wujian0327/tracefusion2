#!/usr/bin/env python3
"""Reverify native cJSON evidence using trusted code; never execute uploaded code."""
import argparse
from collections import Counter
import json
from pathlib import Path

from elftools.elf.elffile import ELFFile
from parser_core import build, replay, require, decode
from parser_host import records, check_completion, convert
from parser_local import NAMES
from parser_ours import infer
from preflight import HERE, ROOT, FLAGS, prepare, validate, CASES, oracle, sha, save


def read(p):
    return json.loads(p.read_text())


def verify_elf(host, manifest):
    binary = host / 'cjson-workload'
    with binary.open('rb') as f:
        elf = ELFFile(f)
        require(elf['e_machine'] == 'EM_X86_64' and elf.little_endian, 'ELF architecture')
        symbols = {s.name: [s['st_value'], s['st_size']]
                   for s in elf.get_section_by_name('.symtab').iter_symbols() if s.name in NAMES}
        require(set(symbols) == set(NAMES), 'ELF symbols')
        segments = [dict(address=s['p_vaddr'], size=s['p_memsz'], flags=s['p_flags'], data=s.data().hex())
                    for s in elf.iter_segments() if s['p_type'] == 'PT_LOAD']
        wanted = {'cJSON': (64, {'valuestring': 32}),
                  'parse_buffer': (56, {'content': 0, 'length': 8, 'offset': 16, 'depth': 24, 'hooks': 32}),
                  'internal_hooks': (24, {'allocate': 0})}
        seen = set()
        for cu in elf.get_dwarf_info().iter_CUs():
            for die in cu.iter_DIEs():
                name = die.attributes.get('DW_AT_name')
                if die.tag != 'DW_TAG_typedef' or not name or name.value.decode() not in wanted:
                    continue
                name = name.value.decode(); typ = die.get_DIE_from_attribute('DW_AT_type')
                size, members = wanted[name]
                actual = {c.attributes['DW_AT_name'].value.decode():
                          c.attributes['DW_AT_data_member_location'].value
                          for c in typ.iter_children() if c.tag == 'DW_TAG_member'}
                require(typ.attributes['DW_AT_byte_size'].value == size and
                        all(actual.get(k) == v for k, v in members.items()), 'DWARF ABI: ' + name)
                seen.add(name)
        require(seen == set(wanted), 'missing DWARF ABI')
    plan = dict(symbols=symbols, segments=segments, binary_sha256=sha(binary),
                upstream_sha256=manifest, private_layout=[64,32,56,0,8,16,24,32,0,24],
                elf_dwarf_layout_checked=True, compiler_flags=FLAGS)
    require(plan == read(host / 'plan.json'), 'ELF plan differs')
    return plan


def check_run(directory, native, root):
    require((directory / 'stdout.jsonl').read_text() == native, 'business output')
    commands = records(directory / 'commands.jsonl')
    require(len(commands) == 1 and commands[0]['returncode'] == 0 and
            commands[0]['stdout'] == native, 'capture command result')
    args = commands[0]['command']
    require(Path(args[0]).name == 'pin' and args[args.index('-root')+1] == str(root), 'capture command')
    rows = records(directory / 'observations.jsonl')
    check_completion(rows, root)
    return rows


def verify(host, cjson, libdft, out):
    out.mkdir(parents=True, exist_ok=False)
    sources = {}
    names = ('cases.py', 'driver.c', 'preflight.py', 'parser_core.py', 'parser_local.py',
             'parser_ours.py', 'parser_capture.cpp', 'parser_host.py', 'requirements.txt')
    for name in names:
        p = HERE / name
        require(p.read_bytes() == (host / 'adapter-source' / name).read_bytes(), 'adapter: ' + name)
        sources[name] = sha(p)
    support = [ROOT / 'scripts' / n for n in
               ('c_bit_machine.py','interproc_model.py','hybrid_model.py','language_adapters.py')]
    support += [HERE.parent / 'libdft-offline' / n for n in ('build_core.py','core.cpp','pin.H','replay.py')]
    support += [HERE.parent / 'checkout-payment-path/external_compare.py']
    support_hashes = {}
    for p in support:
        require(p.read_bytes() == (host / 'support-source' / p.name).read_bytes(), 'support: ' + p.name)
        support_hashes[p.name] = sha(p)
    require(support_hashes == read(host / 'support-source-sha256.json'), 'support manifest')
    source, manifest = prepare(cjson, out)
    for p in source.iterdir():
        require(p.read_bytes() == (host / 'source' / p.name).read_bytes(), 'workload source: ' + p.name)
    plan = verify_elf(host, manifest)
    exe, extraction = build(libdft, out / 'rebuilt-core')
    claimed = read(host / 'validation.json')
    archived = read(host / 'offline-core/extraction.json')
    require(archived == claimed['extraction'] and archived['returncode'] == 0, 'extraction report')
    for k in ('revision','upstream_sha256','callbacks','adapter_sha256','generated_sha256','parser_builder_sha256'):
        require(extraction[k] == archived[k], 'extraction: ' + k)
    for rel, digest in extraction['upstream_sha256'].items():
        for p in (host / 'libdft-build' / rel,
                  host / 'offline-core' / ('UPSTREAM-LICENSE' if rel == 'LICENSE' else 'upstream/' + Path(rel).name)):
            require(sha(p) == digest, 'upstream source: ' + str(p))
    for name in ('callbacks.inc','core.cpp','shim/pin.H'):
        require((host / 'offline-core' / name).read_bytes() ==
                (out / 'rebuilt-core' / name).read_bytes(), 'generated core: ' + name)
    require(sha(host / 'offline-core/libdft-replay-core') == archived['executable_sha256'], 'core digest')
    require((host / 'libdft-build/tools/cjson_parser_capture.cpp').read_bytes() ==
            (HERE / 'parser_capture.cpp').read_bytes(), 'native capture source')
    tools = read(host / 'tool-build.json')
    require(tools['compiled'] and not tools['propagation_code_modified'], 'tool build status')
    for name, item in tools['tools'].items():
        require(sha(host / 'libdft-build/tools/obj-intel64' / (name + '.so')) == item['sha256'], 'tool digest')
    native = (host / 'native.jsonl').read_text()
    validate(records(host / 'native.jsonl'))
    commands = records(host / 'commands.jsonl')
    require(all(c['returncode'] == 0 for c in commands), 'host command failure')
    null = [c for c in commands if Path(c['command'][0]).name == 'pin' and
            any(str(x).endswith('/nullpin.so') for x in c['command'])]
    require(len(null) == 1 and null[0]['stdout'] == native, 'nullpin output')
    index = check_run(host / 'index', native, 0)
    fields = {(r['case'],r['query']): r for r in index if r['kind'] == 'field'}
    roots = [r for r in index if r['kind'] == 'parser_end']
    results, callbacks, mnemonics = [], Counter(), Counter()
    raw_count, byte_count, different_bytes, different_queries = len(index), 0, 0, 0
    final_allocation_checks = 0
    for ci, case in enumerate(CASES, 1):
        expected = oracle(case)
        for qi, truth in enumerate(expected['queries']):
            field = fields[ci, qi]
            q = dict(case=case['name'], path=truth['path'], status='unknown')
            results.append(q)
            if truth['status'] == 'no_sink':
                require(field['item'] == field['address'] == 0, 'unexpected target')
                q['status'] = 'native_no_sink'; continue
            require(field['address'] and field['data'] == truth['value_hex'], 'target value')
            if truth['format_field_origin'] == 'replacement':
                q.update(status='not_in_parser_scope', reason='post-parse replacement'); continue
            matches = [r for r in roots if r['case'] == ci and r['item'] == field['item'] and
                       r['address'] == field['address'] and r['success']]
            require(len(matches) == 1, 'ambiguous decoder binding')
            span = expected['input_string_spans'][truth['path']]
            require(matches[0]['offset'] == span['begin']-1, 'token binding')
            q['root'] = matches[0]['root']
            directory = host / f'case-{ci:02d}-query-{qi:02d}'
            rows = check_run(directory, native, q['root']); raw_count += len(rows)
            trace, states, sink = convert(rows, plan, q['root'])
            require(json.loads(json.dumps(trace)) == read(directory / 'trace.json'), 'saved trace')
            require(trace['source']['offset'] == span['begin']-1 and trace['source']['data'] ==
                    (case['text'].encode()+b'\0').hex(), 'repeated source binding')
            actual_fields = [r for r in rows if r['kind'] == 'field' and r['case'] == ci and r['query'] == qi]
            require(len(actual_fields) == 1 and actual_fields[0]['item'] == sink['item'] and
                    actual_fields[0]['address'] == sink['address'], 'repeated object binding')
            lib = replay(exe, trace); ours = infer(plan, trace)
            require(lib == read(directory / 'libdft-offline.json'), 'saved libdft replay')
            require(ours == read(directory / 'ours.json'), 'saved own replay')
            require(lib['allocation_labels'] == sink['allocation_tags'], 'final native/core tags')
            for i, state in enumerate(states):
                require([x['bytes'] for x in lib['intermediate_tags_before'][i*17:(i+1)*17]] ==
                        state['tag_bytes'] + [state['allocation_tags']], 'intermediate native/core tags')
            require(sink['data'] == truth['value_hex'], 'independent output value')
            lib_bytes = [[x-1 for x in b] for b in lib['byte_labels']]
            offsets = sorted({x for b in lib_bytes for x in b})
            empty = case.get('semantics') == 'control_diagnostic' or truth['empty_content']
            diagnostics = {name: all(span['begin'] <= x < span['end'] for x in xs) and
                           bool(xs) == (not empty) for name, xs in
                           [('ours',ours['source_offsets']),('libdft',offsets)]}
            q.update(status='native_calibrated', steps=len(states),
                     intermediate_byte_checks=len(states)*(128+trace['source']['allocation_size']),
                     ours_source_offsets=ours['source_offsets'], libdft_source_offsets=offsets,
                     field_presence_diagnostics=diagnostics)
            require(len(lib_bytes) == len(ours['byte_source_offsets']), 'output label width')
            diffs = sum(set(a) != set(b) for a,b in zip(lib_bytes,ours['byte_source_offsets']))
            different_bytes += diffs; different_queries += bool(diffs); byte_count += len(lib_bytes)
            final_allocation_checks += trace['source']['allocation_size']
            mnemonics.update(decode(r).mnemonic for r in trace['instructions'])
            for step in lib['dispatch']:
                callbacks.update(c.split()[1] if c.startswith('call ') else c.split()[0] for c in step['callbacks'])
    require(results == claimed['queries'], 'host summary differs')
    require(claimed['status'] == 'native_parser_calibrated' and claimed['native_core_calibration']
            and claimed['performance_eligible'] is False, 'host completion status')
    calibrated = [q for q in results if q['status'] == 'native_calibrated']
    report = dict(status='verified_bounded_native_parser_calibration', query_requests=len(results),
                  calibrated_queries=len(calibrated),
                  no_sink_queries=sum(q['status']=='native_no_sink' for q in results),
                  out_of_scope_queries=sum(q['status']=='not_in_parser_scope' for q in results),
                  instruction_records=sum(q['steps'] for q in calibrated), raw_jsonl_records=raw_count,
                  intermediate_byte_checks=sum(q['intermediate_byte_checks'] for q in calibrated),
                  final_allocation_byte_checks=final_allocation_checks,
                  field_presence_diagnostics_passed={n:sum(q['field_presence_diagnostics'][n] for q in calibrated)
                                                     for n in ('ours','libdft')},
                  output_content_bytes=byte_count, cross_engine_different_byte_sets=different_bytes,
                  cross_engine_queries_with_different_byte_sets=different_queries,
                  aggregate_source_sets_equal=sum(q['ours_source_offsets']==q['libdft_source_offsets'] for q in calibrated),
                  extracted_callbacks=len(extraction['callbacks']), exercised_callbacks=dict(callbacks),
                  mnemonic_counts=dict(mnemonics), queries=results, binary_sha256=plan['binary_sha256'],
                  cjson_source_sha256=manifest, libdft_revision=extraction['revision'],
                  libdft_source_files_verified=len(extraction['upstream_sha256']),
                  implementation_sha256=sources, support_source_sha256=support_hashes,
                  verifier_sha256=sha(Path(__file__)),
                  generated_core_sha256=extraction['generated_sha256'],
                  host_reported_environment=claimed['environment'], performance_eligible=False,
                  independent_per_byte_accuracy=None,
                  limitations=['Post-allocation string decoding only; replacement and serialization excluded',
                               'Field presence is not an independent per-byte dependency oracle',
                               'Observed native states calibrate exercised forms, not all 46 callbacks',
                               'Diagnostic full traces do not establish sparse collection or performance gains'])
    save(out / 'verification.json', report)
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--host', type=Path, required=True)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--libdft', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    result = verify(a.host.resolve(), a.source.resolve(), a.libdft.resolve(), a.output.resolve())
    print(json.dumps({k:result[k] for k in ('status','calibrated_queries','instruction_records',
                                          'intermediate_byte_checks','cross_engine_different_byte_sets')}))
