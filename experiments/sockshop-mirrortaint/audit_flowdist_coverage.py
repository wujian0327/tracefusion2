#!/usr/bin/env python3
"""Validate measured branch coverage and index-preserving statement alignment."""
import argparse
import hashlib
import json
from pathlib import Path
import re

LOCAL = re.compile(r'(?<![\w.$])(\$?[ribdlszfc]\d+)\b')
QUOTED = re.compile(r'("(?:\\.|[^"\\])*")')


def canonical_rows(rows):
    methods = {}
    result = []
    for row in rows:
        method, body = row.split(' - ', 1)
        names = methods.setdefault(method, {})
        def replace(match):
            name = match.group(1)
            prefix = re.sub(r'\d+$', '', name)
            if name not in names:
                names[name] = prefix + '_' + str(sum(v.startswith(prefix + '_') for v in names.values()))
            return names[name]
        pieces = QUOTED.split(body)
        result.append(method + ' - ' + ''.join(
            text if i % 2 else LOCAL.sub(replace, text) for i, text in enumerate(pieces)))
    return result


def coverage(path, mapping, size):
    raw = path.read_text()
    statements = set(map(int, re.search(r'Statements covered \(based on branch coverage\):([^\n]*)', raw)[1].split()))
    branches = set(map(int, re.search(r'Branches covered:([^\n]*)', raw)[1].split()))
    if not branches or not statements:
        raise ValueError('No measured coverage: ' + str(path))
    if not all(0 <= b < len(mapping) for b in branches):
        raise ValueError('Invalid branch index')
    expected = set().union(*(mapping[b] for b in branches))
    if expected != statements or not all(0 <= s < size for s in statements):
        raise ValueError('Statement coverage differs from measured branch mapping')
    branch_total = tuple(map(int, re.search(r'Total branches covered: (\d+)/(\d+)', raw).groups()))
    stmt_total = tuple(map(int, re.search(r'Total statements covered: (\d+)/(\d+)', raw).groups()))
    # The author reporter uses maximum mapped statement ID + 1 as denominator.
    mapped_size = max(set().union(*mapping)) + 1
    if branch_total != (len(branches), len(mapping)) or stmt_total != (len(statements), mapped_size):
        raise ValueError('Incorrect coverage totals')
    return branches, statements


def audit(runtime, graph, out):
    branch = runtime / 'work/OTBranchInstrumented'
    ids = branch / 'stmtids.out'
    graph_ids = graph / 'stmtids.out'
    rows, reference = ids.read_text().splitlines(), graph_ids.read_text().splitlines()
    if canonical_rows(rows) != canonical_rows(reference):
        raise ValueError('Statement indices do not structurally align')
    mapping = [set(map(int, row.split())) for row in (branch / 'entitystmt.out.branch').read_text().splitlines()]
    roles = {}
    union = set()
    measured_branches = []
    for role in ('server', 'client'):
        report = runtime / 'work/runtime' / role / 'stmtCoverage1.out'
        branches, statements = coverage(report, mapping, len(rows))
        union.update(statements)
        measured_branches.append(branches)
        roles[role] = {'branches_hit': len(branches), 'statements_hit': len(statements),
                       'report_sha256': hashlib.sha256(report.read_bytes()).hexdigest()}
    if measured_branches[0] == measured_branches[1]:
        raise ValueError('Identical process coverage requires investigation')
    result = {'kind': 'flowdist-measured-coverage-audit', 'runtime': str(runtime), 'graph': str(graph),
              'statement_count': len(rows), 'branch_count': len(mapping), 'roles': roles,
              'statement_union': sorted(union), 'index_alignment': 'per-index-local-renaming-only',
              'runtime_statement_sha256': hashlib.sha256(ids.read_bytes()).hexdigest(),
              'graph_statement_sha256': hashlib.sha256(graph_ids.read_bytes()).hexdigest(),
              'accuracy_eligible': False, 'performance_eligible': False}
    with out.open('x') as handle:
        json.dump(result, handle, indent=2)
        handle.write('\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('runtime', 'graph', 'out'):
        parser.add_argument('--' + flag, type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.runtime.resolve(), args.graph.resolve(), args.out.resolve())
    print(json.dumps({k: v for k, v in result.items() if k != 'statement_union'}, indent=2))
