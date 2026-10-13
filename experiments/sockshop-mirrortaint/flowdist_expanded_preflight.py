#!/usr/bin/env python3
"""Diagnose candidate-scope CDG omissions using every mapped application method.

The original engine and JDK-body exclusions are retained. Expanding the method
scope disables coarse candidate pruning and changes cost; this is disclosed.
"""
import argparse
import hashlib
from pathlib import Path
import re
import shutil

import flowdist_preflight as tool
from flowdist_branch_preflight import run as branch_run
from audit_flowdist_coverage import audit


def run(repo, scope, mapped_statements, branch_adapter, socket_adapter, out):
    tool.verify_repository(repo)
    out.mkdir(parents=True, exist_ok=False)
    source = out / 'scope'
    work = source / 'work'
    work.mkdir(parents=True)
    for name in ('classes', 'data'):
        shutil.copytree(scope / 'work' / name, work / name)
    shutil.copyfile(scope / 'work/Message_PassingAPIList.txt', work / 'Message_PassingAPIList.txt')
    methods = sorted(set(row.split(' - ', 1)[0] for row in mapped_statements.read_text().splitlines()))
    for name in ('methodList.out', 'coveredMethods.txt'):
        (work / name).write_text('\n'.join(methods) + '\n')
    tool.save(source / 'manifest.json', {'kind': 'expanded-all-mapped-method-compatibility-scope',
        'methods': len(methods), 'source_map': str(mapped_statements),
        'source_map_sha256': hashlib.sha256(mapped_statements.read_bytes()).hexdigest(),
        'coarse_candidate_pruning_disabled': True, 'accuracy_eligible': False, 'performance_eligible': False})
    runtime = out / 'runtime'
    branch_run(repo, source, branch_adapter, socket_adapter, runtime)
    shutil.copyfile(runtime / 'work/methodList.out', runtime / 'coarse-query-methodList.out')
    shutil.copyfile(work / 'methodList.out', runtime / 'work/methodList.out')
    shutil.copyfile(runtime / 'work/OTBranchInstrumented/entitystmt.out.branch', runtime / 'work/entitystmt.out.branch')
    tool.compile_static_launcher(repo, runtime)
    args = tool.static_args('OT3Inst', 'ExpandedGraph')
    args[3] += ':/work/launcher'
    args[4:5] = ['FlowDistStaticLauncher', args[4]]
    args += ['-slicectxinsens', '-wrapTryCatch', '-intraCD', '-interCD', '-exInterCD',
             '-dumpFunctionList', '-serializeVTG', '-no-bodies-for-excluded',
             '-exclude', 'java.*', '-exclude', 'javax.*', '-exclude', 'sun.*', '-exclude', 'com.sun.*']
    tool.execute(repo, runtime, 'expanded-refinement', args, timeout=180)
    graph = runtime / 'work/ExpandedGraph'
    if not (graph / 'staticVtg.dat').is_file():
        raise ValueError('Original serialized graph missing')
    audit(runtime, graph, out / 'coverage-audit.json')
    log = (runtime / 'expanded-refinement.log').read_text()
    counts = re.search(r'Value Transfer Graph: (\d+) nodes, (\d+) edges', log)
    if not counts:
        raise ValueError('Graph node/edge summary missing')
    tool.save(out / 'summary.json', {'method_scope': len(methods), 'nodes': int(counts[1]), 'edges': int(counts[2]),
        'cdg_missing_diagnostics': log.count('has not been computed yet!'),
        'jdk_library_bodies_excluded': True, 'coarse_candidate_pruning_disabled': True,
        'global_graph_completeness_verified': False, 'accuracy_eligible': False, 'performance_eligible': False})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('repo', 'scope', 'mapped-statements', 'branch-adapter', 'socket-adapter', 'out'):
        parser.add_argument('--' + flag, type=Path, required=True)
    a = parser.parse_args()
    run(a.repo.resolve(), a.scope.resolve(), a.mapped_statements.resolve(),
        a.branch_adapter.resolve(), a.socket_adapter.resolve(), a.out.resolve())
