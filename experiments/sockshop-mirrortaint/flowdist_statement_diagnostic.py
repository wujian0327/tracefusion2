#!/usr/bin/env python3
"""Run the original statement analyzer with audited, measured coverage.

Merged and isolated process runs expose process-boundary limitations. The input
graph may be incomplete; these runs never qualify accuracy or performance.
"""
import argparse
import hashlib
import re
from pathlib import Path
import shutil

import flowdist_preflight as tool
from audit_flowdist_coverage import audit, coverage


def run(repo, runtime, graph, query, out):
    tool.verify_repository(repo)
    out.mkdir(parents=True, exist_ok=False)
    checked = audit(runtime, graph, out / 'coverage-audit.json')
    branch = runtime / 'work/OTBranchInstrumented'
    mapping = [set(map(int, row.split())) for row in (branch / 'entitystmt.out.branch').read_text().splitlines()]
    results = {}
    for name, roles in (('merged', ('server', 'client')), ('server-only', ('server',)), ('client-only', ('client',))):
        target = out / name
        work = target / 'work'
        work.mkdir(parents=True)
        shutil.copytree(graph, work / 'graph')
        shutil.copyfile(runtime / 'work/methodList.out', work / 'methodList.out')
        # Use the current runtime's method candidate set, rather than stale traces.
        shutil.copyfile(runtime / 'work/methodList.out', work / 'methodsInPair.out')
        (work / 'query.txt').write_text(query + '\n')
        traces = work / 'traces'
        traces.mkdir()
        measured = set()
        inputs = {}
        for role in roles:
            source = runtime / 'work/runtime' / role
            _, statements = coverage(source / 'stmtCoverage1.out', mapping, checked['statement_count'])
            measured.update(statements)
            for trace in source.rglob('*.em'):
                destination = traces / trace.name
                if destination.exists():
                    raise ValueError('Trace filename collision: ' + trace.name)
                shutil.copyfile(trace, destination)
                inputs[trace.name] = {'role': role, 'sha256': hashlib.sha256(trace.read_bytes()).hexdigest()}
        if len(list(traces.glob('Local*.em'))) != len(roles) or len(list(traces.glob('Remote*.em'))) != len(roles):
            raise ValueError('Missing discoverable process traces')
        # The original reader prefers OT1 over 1. Replace both in this fresh copy
        # so its static instrumentation output cannot masquerade as runtime data.
        (work / 'graph/stmtCoverageOT1.out').write_text(' '.join(map(str, sorted(measured))) + '\n')
        (work / 'graph/stmtCoverage1.out').unlink(missing_ok=True)
        args = ['-Xmx1g', '-ea', '-cp', tool.CP, 'disttaint.OT3AnalysisAll',
                '/work/query.txt', '/work/traces', '/work/graph', '-method',
                '-stmtcov', '-postprune', '-debug', '']
        stage = tool.execute(repo, target, 'statement-analysis', args)
        log = (target / 'statement-analysis.log').read_text()
        results[name] = {'status': stage['status'], 'covered_statements': len(measured),
                         'trace_inputs': inputs,
                         'path_lengths': re.findall(r'\[The statement path length\]: ([^\n]+)', log),
                         'path_types': re.findall(r'\[The statement path type[^\n]+', log),
                         'unexecuted_endpoint': 'not in the executed statement list!' in log,
                         'log_sha256': hashlib.sha256(log.encode()).hexdigest()}
    tool.save(out / 'summary.json', {'kind': 'flowdist-measured-statement-process-diagnostic',
        'query': query, 'input_graph': str(graph), 'runtime': str(runtime), 'results': results,
        'graph_completeness_verified': False, 'accuracy_eligible': False, 'performance_eligible': False})
    print(results)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for flag in ('repo', 'runtime', 'graph', 'out'):
        p.add_argument('--' + flag, type=Path, required=True)
    p.add_argument('--query', required=True)
    a = p.parse_args()
    run(a.repo.resolve(), a.runtime.resolve(), a.graph.resolve(), a.query, a.out.resolve())
