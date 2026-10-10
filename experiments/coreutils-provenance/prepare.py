#!/usr/bin/env python3
"""Pre-register source queries and check real cut/join output; NOT provenance inference."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

UPSTREAM_COMMIT = '9530a14420fc1a267e90d45e8a0d710c3668382d'  # coreutils v9.4
HERE = Path(__file__).resolve().parent


def field(file, row, column):
    return {'field': [file, row, column]}


def constant(text):
    return {'constant': text}


def line(*parts, separator='\t'):
    result = []
    for i, part in enumerate(parts):
        if i:
            result.append(constant(separator))
        result.append(part)
    return result + [constant('\n')]


def cases():
    # Expected pieces are explicit, independent of command parsing and tracing.
    same = [[['SAME', 'SAME', 'noise']]]
    multi = [[['SAME', 'SAME', 'noise'], ['SAME', 'SAME', 'noise']]]
    two = [[['SAME', 'SAME']], [['SAME', 'SAME']]]
    cut = lambda name, files, options, pieces: dict(id=name, program='cut', files=files,
                                                   options=['-d', '\t', *options], expected_pieces=pieces)
    join = lambda name, files, options, pieces: dict(id=name, program='join', files=files,
                                                     options=['-t', '\t', *options], expected_pieces=pieces)
    f = field
    a = [[['a', 'SAME'], ['b', 'SAME']], [['a', 'SAME'], ['b', 'SAME']]]
    duplicate = [[['a', 'SAME'], ['a', 'SAME']], [['a', 'SAME'], ['a', 'SAME']]]
    return [
        cut('cut_left_equal', same, ['-f', '1'], line(f(0, 0, 0))),
        cut('cut_right_equal', same, ['-f', '2'], line(f(0, 0, 1))),
        cut('cut_disjoint_fields', same, ['-f', '1,3'], line(f(0, 0, 0), f(0, 0, 2))),
        cut('cut_complement', same, ['--complement', '-f', '2'], line(f(0, 0, 0), f(0, 0, 2))),
        cut('cut_repeated_rows', multi, ['-f', '2'], line(f(0, 0, 1)) + line(f(0, 1, 1))),
        cut('cut_equal_files', two, ['-f', '2'], line(f(0, 0, 1)) + line(f(1, 0, 1))),
        cut('cut_custom_delimiter', same, ['-f', '1,2', '--output-delimiter', '|'],
            line(f(0, 0, 0), f(0, 0, 1), separator='|')),
        cut('cut_nondelimited_passthrough', [[['SAME']]], ['-f', '2'], line(f(0, 0, 0))),
        cut('cut_nondelimited_suppressed', [[['SAME']]], ['-s', '-f', '2'], []),
        cut('cut_long_first_field', [[['x'*20000, 'SAME', 'SAME']]], ['-f', '1,3'],
            line(f(0, 0, 0), f(0, 0, 2))),
        join('join_two_files_equal_payload', a, ['-o', '1.2,2.2'],
             line(f(0, 0, 1), f(1, 0, 1)) + line(f(0, 1, 1), f(1, 1, 1))),
        join('join_reverse_projection', a, ['-o', '2.2,1.2'],
             line(f(1, 0, 1), f(0, 0, 1)) + line(f(1, 1, 1), f(0, 1, 1))),
        join('join_duplicate_keys', duplicate, ['-o', '1.2,2.2'],
             sum((line(f(0, i, 1), f(1, j, 1)) for i in range(2) for j in range(2)), [])),
        join('join_unmatched_left', [[['a', 'SAME'], ['b', 'SAME']], [['a', 'SAME']]],
             ['-a', '1', '-e', '?', '-o', '1.2,2.2'],
             line(f(0, 0, 1), f(1, 0, 1)) + line(f(0, 1, 1), constant('?'))),
        join('join_select_nonkey_field', [[['a', 'SAME', 'noise']], [['a', 'SAME', 'noise']]],
             ['-o', '2.2'], line(f(1, 0, 1))),
        join('join_no_matching_keys', [[['a', 'SAME']], [['b', 'SAME']]], ['-o', '1.2,2.2'], []),
    ]


def materialize(case, folder):
    fields, paths = {}, []
    for fi, rows in enumerate(case['files']):
        content = bytearray()
        for ri, columns in enumerate(rows):
            for ci, value in enumerate(columns):
                if ci:
                    content.extend(b'\t')
                data = value.encode('ascii')
                assert b'\t' not in data and b'\n' not in data
                identity = '%d:%d:%d' % (fi, ri, ci)
                fields[identity] = dict(id=identity, file='input%d.tsv' % fi, record=ri, field=ci,
                                        offset=len(content), length=len(data))
                content.extend(data)
            content.extend(b'\n')
        path = folder / ('input%d.tsv' % fi)
        path.write_bytes(content)
        paths.append(path)
    output, queries = bytearray(), []
    for piece in case['expected_pieces']:
        if 'field' in piece:
            fi, ri, ci = piece['field']
            identity = '%d:%d:%d' % (fi, ri, ci)
            data = case['files'][fi][ri][ci].encode('ascii')
            source = fields[identity]
            assert paths[fi].read_bytes()[source['offset']:source['offset']+source['length']] == data
            origins = [identity]
        else:
            data, origins = piece['constant'].encode('ascii'), []
        queries.append(dict(output_offset=len(output), length=len(data), expected_sources=origins,
                            query_kind='data_field' if origins else 'generated_bytes'))
        output.extend(data)
    return paths, bytes(output), dict(source_fields=list(fields.values()), queries=queries,
                                     no_output_expected=not output,
                                     scope='ASCII field payloads; direct data origins; delimiters/keys/options as control or configuration')


def prepare(out):
    out.mkdir(parents=True, exist_ok=False)
    identity, results = {}, []
    for name in ('cut', 'join'):
        executable = Path(shutil.which(name) or name).resolve()
        version = subprocess.check_output([executable, '--version'], text=True).splitlines()[0]
        if version != name + ' (GNU coreutils) 9.4':
            raise ValueError('Preflight requires GNU coreutils 9.4: ' + version)
        identity[name] = dict(version=version, binary_sha256=hashlib.sha256(executable.read_bytes()).hexdigest())
    for case in cases():
        folder = out / case['id']
        folder.mkdir()
        paths, expected, oracle = materialize(case, folder)
        command = [shutil.which(case['program']), *case['options'], *map(str, paths)]
        process = subprocess.run(command, env=dict(os.environ, LC_ALL='C'), capture_output=True, timeout=20)
        (folder / 'stdout.bin').write_bytes(process.stdout)
        (folder / 'stderr.bin').write_bytes(process.stderr)
        (folder / 'expected.bin').write_bytes(expected)
        (folder / 'queries.json').write_text(json.dumps(oracle, indent=2)+'\n')
        row = dict(id=case['id'], program=case['program'], options=case['options'],
                   returncode=process.returncode, output_matched=process.returncode == 0 and process.stdout == expected,
                   output_bytes=len(expected), data_field_queries=sum(q['query_kind']=='data_field' for q in oracle['queries']),
                   generated_byte_queries=sum(q['query_kind']=='generated_bytes' for q in oracle['queries']),
                   no_output_expected=oracle['no_output_expected'], provenance_checked=False)
        results.append(row)
    summary = dict(upstream_candidate_commit=UPSTREAM_COMMIT, native_distribution_binaries=identity,
                   exact_upstream_build_verified=False, locale='C', cases=results,
                   all_native_outputs_matched=all(r['output_matched'] for r in results),
                   provenance_checked=False, bpf_executed=False, libdft_executed=False, performance_eligible=False)
    (out / 'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.output:
        result = prepare(args.output.resolve())
    else:
        with tempfile.TemporaryDirectory() as tmp:
            result = prepare(Path(tmp) / 'preflight')
    print(json.dumps(result, indent=2))
    if not result['all_native_outputs_matched']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
