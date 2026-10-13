#!/usr/bin/env python3
"""Original service application bytecode: branch probes and static graph.

Keep framework/JDK signatures, exclude their bodies, and select all application
methods by JVM descriptor. This does not model HTTP serialization or reflection.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

import flowdist_preflight as tool
from normalize_flowdist_class_literals import run as normalize_tree
from audit_flowdist_coverage import canonical_rows


def descriptor_types(descriptor):
    primitives = dict(zip('BCDFIJSZV', ('byte','char','double','float','int','long','short','boolean','void')))
    def take(pos):
        dimension = 0
        while descriptor[pos] == '[': dimension += 1; pos += 1
        if descriptor[pos] == 'L':
            end = descriptor.index(';', pos)
            value = descriptor[pos+1:end].replace('/', '.')
            pos = end + 1
        else:
            value = primitives[descriptor[pos]]; pos += 1
        return value + '[]' * dimension, pos
    if not descriptor.startswith('('): raise ValueError('Method descriptor required')
    pos = 1; parameters = []
    while descriptor[pos] != ')':
        value, pos = take(pos); parameters.append(value)
    result, end = take(pos + 1)
    if end != len(descriptor): raise ValueError('Trailing descriptor data')
    return result, parameters


def inventory(classes, out):
    names = sorted(str(p.relative_to(classes))[:-6].replace('/', '.') for p in classes.rglob('*.class'))
    command = ['javap', '-p', '-s', '-classpath', str(classes), *names]
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    (out / 'method-inventory.log').write_text(result.stdout + result.stderr)
    if result.returncode: raise ValueError('Original class inventory failed')
    owner = None; previous = ''; methods = []
    for line in result.stdout.splitlines():
        match = re.search(r'\b(?:class|interface|enum) ([\w.$]+)', line)
        if match: owner = match[1]
        if line.strip().startswith('descriptor: ('):
            desc = line.strip().split(': ', 1)[1]
            if '(' in previous:
                name = previous.split('(', 1)[0].split()[-1]
                if name == owner: name = '<init>'
            elif previous.strip() == 'static {};': name = '<clinit>'
            else: raise ValueError('Missing method declaration')
            returns, parameters = descriptor_types(desc)
            methods.append('<' + owner + ': ' + returns + ' ' + name + '(' + ','.join(parameters) + ')>')
        if line.strip(): previous = line.strip()
    if not methods: raise ValueError('Empty original method inventory')
    return sorted(set(methods))


def run(repo, jar, branch_adapter, out, role, lambda_adapter=None):
    tool.prepare_shipping(repo, out, jar)
    work = out / 'work'
    methods = inventory(work / 'classes', out)
    for name in ('methodList.out', 'coveredMethods.txt'): (work / name).write_text('\n'.join(methods) + '\n')
    adapter = json.loads((branch_adapter.parent / 'manifest.json').read_text())
    digest = hashlib.sha256(branch_adapter.read_bytes()).hexdigest()
    if adapter['kind'] != 'flowdist-branch-probe-restoration' or digest != adapter['jar_sha256']:
        raise ValueError('Unverified branch adapter')
    shutil.copyfile(branch_adapter, work / 'branch-adapter.jar')
    dependencies = ''.join(':/work/lib/' + p.name for p in sorted((work / 'lib').glob('*.jar')))
    exclusions = ['java.*','javax.*','sun.*','com.*','org.*','ch.*','io.*','rx.*','zipkin.*','brave.*']
    restrict = ['-no-bodies-for-excluded']
    for prefix in exclusions: restrict += ['-exclude', prefix]
    manifest = json.loads((out / 'manifest.json').read_text())
    manifest.update(kind='flowdist-original-service-static-compatibility', role=role,
        application_method_count=len(methods), excluded_library_body_prefixes=exclusions,
        branch_adapter_sha256=digest, http_serialization_modeled=False, spring_reflection_modeled=False,
        original_soot_backend='bundled ASM backend; Java 8 target',
        wrap_try_catch_enabled=False,
        wrap_try_catch_reason='Author wrapper includes uninitialized constructor this; JVM VerifyError',
        accuracy_eligible=False, performance_eligible=False)
    tool.save(out / 'manifest.json', manifest)
    args = tool.static_args('OTBranchInst', 'BranchInstrumented', dependencies)
    args[3] = '/work/branch-adapter.jar:' + args[3]
    args += ['-asm-backend','-java-version','8','-slicectxinsens','-intraCD','-interCD','-exInterCD', *restrict]
    tool.execute(repo, out, 'service-branches', args, timeout=120)
    normalize_tree(work / 'BranchInstrumented', work / 'NormalizedBranches')
    shutil.copyfile(work / 'BranchInstrumented/entitystmt.out.branch', work / 'entitystmt.out.branch')
    tool.compile_static_launcher(repo, out)
    args = tool.static_args('OT3Inst', 'ServiceGraph', dependencies)
    if lambda_adapter:
        metadata=json.loads((lambda_adapter.parent/'manifest.json').read_text())
        digest=hashlib.sha256(lambda_adapter.read_bytes()).hexdigest()
        if metadata['kind']!='flowdist-invokedynamic-reference-model-extension' or metadata['jar_sha256']!=digest:
            raise ValueError('Unverified lambda reference adapter')
        shutil.copyfile(lambda_adapter,work/'lambda-adapter.jar')
        args[3]='/work/lambda-adapter.jar:'+args[3]
        manifest.update(lambda_reference_model_extended=True,lambda_adapter_sha256=digest,
                        lambda_capture_and_callback_dependencies_modeled=False)
        tool.save(out/'manifest.json',manifest)
    args[3] += ':/work/launcher'
    args[4:5] = ['FlowDistStaticLauncher', args[4]]
    args += ['-asm-backend','-java-version','8','-slicectxinsens','-intraCD','-interCD','-exInterCD', '-serializeVTG', *restrict]
    tool.execute(repo, out, 'service-refinement', args, timeout=120)
    branch_rows = (work / 'BranchInstrumented/stmtids.out').read_text().splitlines()
    graph_rows = (work / 'ServiceGraph/stmtids.out').read_text().splitlines()
    if canonical_rows(branch_rows) != canonical_rows(graph_rows): raise ValueError('Branch/graph statement indices differ')
    required = {'orders':['newOrder('], 'shipping':['postShipping('], 'carts':['get(', 'delete(', 'mergeCarts(']}[role]
    if any(not any(method in row and 'Controller:' in row for row in branch_rows) for method in required):
        raise ValueError('Controller absent from static statement map')
    counts = re.search(r'Value Transfer Graph: (\d+) nodes, (\d+) edges', (out / 'service-refinement.log').read_text())
    if not counts or not (work / 'ServiceGraph/staticVtg.dat').is_file(): raise ValueError('Graph output missing')
    tool.save(out / 'result.json', {'role': role, 'application_methods': len(methods), 'mapped_statements': len(branch_rows),
        'branches': len((work / 'entitystmt.out.branch').read_text().splitlines()), 'nodes': int(counts[1]), 'edges': int(counts[2]),
        'statement_alignment': 'per-index-local-renaming-only', 'runtime_coverage_verified': False,
        'accuracy_eligible': False, 'performance_eligible': False})


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for flag in ('repo','jar','branch-adapter','out'): p.add_argument('--' + flag, type=Path, required=True)
    p.add_argument('--role', choices=('orders','shipping','carts'), required=True)
    p.add_argument('--lambda-adapter',type=Path)
    a = p.parse_args()
    run(a.repo.resolve(), a.jar.resolve(), a.branch_adapter.resolve(), a.out.resolve(), a.role,
        a.lambda_adapter.resolve() if a.lambda_adapter else None)
