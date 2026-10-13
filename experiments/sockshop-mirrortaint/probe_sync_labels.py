#!/usr/bin/env python3
"""Freeze and run a synchronous original-JAR label control; not Sock Shop accuracy."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import zipfile

HERE = Path(__file__).resolve().parent
DEFAULT_IMAGE = 'weaveworksdemos/orders@sha256:b622e40e83433baf6374f15e076b53893f79958640fc6667dff597622eff03b9'


def contract():
    def query(stage, field, sources, value):
        return dict(stage=stage, field=field, expected_sources=sources, expected_value=value)
    sources = [query('source-' + key, field, ['item-' + key + '/' + field], value)
               for key in ('a', 'b', 'c', 'd') for field, value in [('name', 'same-content'), ('quantity', 2), ('unitPrice', 5.0)]]
    targets = [query('copy-a', field, ['item-a/' + field], value)
               for field, value in [('name', 'same-content'), ('quantity', 2), ('unitPrice', 5.0)]]
    targets += [query('sum-a-b', 'total', ['item-a/quantity', 'item-a/unitPrice', 'item-b/quantity', 'item-b/unitPrice'], 24.99),
                query('combine-names', 'combined', ['item-a/name', 'item-b/name'], 'same-contentsame-content')]
    targets += [query('overwrite-b', field, ['item-b/' + field], value)
                for field, value in [('name', 'same-content'), ('quantity', 2), ('unitPrice', 5.0)]]
    targets += [query('accessor-copy-c', field, ['item-c/' + field], value)
                for field, value in [('name', 'same-content'), ('quantity', 2), ('unitPrice', 5.0)]]
    targets += [query('accessor-sum-c-d', 'total', ['item-c/quantity', 'item-c/unitPrice', 'item-d/quantity', 'item-d/unitPrice'], 24.99)]
    targets += [query('stream-a-b', 'total', ['item-a/quantity', 'item-a/unitPrice', 'item-b/quantity', 'item-b/unitPrice'], 24.99)]
    negatives = [query('copy-a', 'total', [], 0.0), query('copy-a', 'combined', [], None)]
    negatives += [query('stream-empty', 'total', [], 4.99)]
    return {'schema_version': 1, 'scope': 'controlled single-thread DTO fixture, manually selected public source API',
            'source_api': 'TaintTagger.tagDbQueryResult', 'source_controls': sources,
            'target_queries': targets, 'negative_controls': negatives,
            'local_constant_in_upstream_sources': False,
            'target_oracle_basis': 'predeclared fixture operations and record/field identities, not observed labels',
            'business_workload_run': False, 'rpc_join_tested': False, 'thread_adapter_installed': False}


def async_contract():
    frozen = contract()
    frozen['scope'] = 'controlled per-task heap capture, reachable-result transfer and request isolation'
    frozen['thread_adapter_installed'] = True
    frozen['source_controls'] = [dict(stage='source-' + key, field=field,
        expected_sources=['item-' + key + '/' + field], expected_value=value)
        for key in ('a', 'b', 'c', 'd', 'e', 'f')
        for field, value in [('name', 'same-content'), ('quantity', 2), ('unitPrice', 5.0)]]
    frozen['target_queries'] = []
    for stage, first, second in [('async-captured', 'a', 'b'), ('async-produced', 'c', 'd'),
                                  ('concurrent-e', 'e', 'e'), ('concurrent-f', 'f', 'f')]:
        for field, value in [('name', 'same-content'), ('quantity', 2), ('unitPrice', 5.0)]:
            frozen['target_queries'].append(dict(stage=stage, field=field,
                expected_sources=['item-' + first + '/' + field], expected_value=value))
        frozen['target_queries'].append(dict(stage=stage, field='total', expected_sources=sorted(set(
            'item-' + item + '/' + field for item in (first, second) for field in ('quantity', 'unitPrice'))), expected_value=24.99))
        frozen['target_queries'].append(dict(stage=stage, field='combined', expected_sources=sorted(set(
            'item-' + item + '/name' for item in (first, second))), expected_value='same-contentsame-content'))
    frozen['negative_controls'] = []
    frozen['lifecycle_controls'] = ['normal-worker-cleanup', 'two-caller-concurrency', 'concurrent-worker-cleanup',
        'exception-preserved', 'exception-worker-cleanup', 'cancellation-started', 'cancellation-preserved',
        'cancel-worker-cleanup', 'cross-context-get-rejected', 'parent-context-still-available', 'final-worker-cleanup']
    return frozen


def validate(log, frozen):
    records = {}
    for line in log.splitlines():
        if line.startswith('TF2_SYNC_SNAPSHOT '):
            record = json.loads(line.split(' ', 1)[1])
            if record['stage'] in records:
                raise ValueError('Duplicate snapshot stage')
            records[record['stage']] = record
    checks = {}
    for group in ('source_controls', 'target_queries', 'negative_controls'):
        checks[group] = []
        for query in frozen[group]:
            snapshot = records.get(query['stage'])
            data = snapshot['fields'].get(query['field']) if snapshot else None
            raw = data.get('tag', {}).get('A', []) if data else []
            identities = []
            for source in raw:
                match = re.match(r'^fixture\.rpc#(item-[abcdef])#result#(name|quantity|unitPrice):', source['A'])
                identities.append(match[1] + '/' + match[2] if match else 'unmapped:' + source['A'])
            actual_value = data.get('value') if data else None
            wanted = query['expected_value']
            value_ok = data is not None and (abs(actual_value - wanted) < 0.001
                if isinstance(actual_value, (int, float)) and isinstance(wanted, (int, float)) else actual_value == wanted)
            labels_ok = set(identities) == set(query['expected_sources'])
            status = 'passed' if value_ok and labels_ok and snapshot['available'] else 'failed'
            checks[group].append(dict(query, status=status, actual_sources=identities, actual_value=actual_value,
                                      value_ok=value_ok, labels_ok=labels_ok, snapshot_present=data is not None,
                                      raw_sources=raw))
    if 'lifecycle_controls' in frozen:
        observed = {}
        for line in log.splitlines():
            if line.startswith('TF2_ASYNC_CHECK '):
                name, value = line.split(' ', 1)[1].split('=', 1)
                if name in observed: raise ValueError('Duplicate lifecycle check')
                observed[name] = value == 'true'
        checks['lifecycle_controls'] = [dict(check=name, status='passed' if observed.get(name) else 'failed')
                                       for name in frozen['lifecycle_controls']]
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--agent', required=True, type=Path)
    parser.add_argument('--javac', default=shutil.which('javac'))
    parser.add_argument('--java-image', default=DEFAULT_IMAGE)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--taint-env', choices=('remote', 'local'), default='remote',
                        help='Disclosed original-JAR configuration ablation; author baseline uses remote')
    parser.add_argument('--adapter', type=Path)
    parser.add_argument('--adapter-mode', choices=('fields', 'strings', 'both', 'complete'), default='complete')
    parser.add_argument('--fixture', choices=('sync', 'async'), default='sync')
    parser.add_argument('--logging', action='store_true', help='Enable disclosed bounded logger and task-local RPC context')
    args = parser.parse_args()
    if args.logging and (not args.adapter or args.adapter_mode != 'complete'):
        raise ValueError('Logging controls require the complete adapter')
    if args.fixture == 'async' and (not args.adapter or args.adapter_mode != 'complete'):
        raise ValueError('Async controls require the complete disclosed integration adapter')
    agent = args.agent.resolve()
    pinned = json.loads((HERE / 'sources.json').read_text())['mirrortaint']['agent_sha256']
    if hashlib.sha256(agent.read_bytes()).hexdigest() != pinned:
        raise ValueError('Unrecognized agent JAR')
    if '@sha256:' not in args.java_image:
        raise ValueError('Pin the Java runtime image by registry digest')
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    home, classes = out / 'agent-home', out / 'classes'
    home.mkdir(); home.chmod(0o777); classes.mkdir()
    frozen = async_contract() if args.fixture == 'async' else contract()
    control_key = 'asynchronous_control_passed' if args.fixture == 'async' else 'synchronous_control_passed'
    (out / 'query-contract.json').write_text(json.dumps(frozen, indent=2) + '\n')
    result = {'kind': 'controlled-' + args.fixture + '-label-calibration', 'agent_sha256': pinned,
              'java_image': args.java_image, 'business_workload_run': False,
              'taint_env': args.taint_env,
              'configuration': 'author-remote' if args.taint_env == 'remote' else 'original-jar-local-env-ablation',
              'thread_adapter_installed': args.fixture == 'async', 'rpc_join_tested': False,
              'logging_adapter_installed': args.logging,
              'accuracy_eligible': False, 'performance_eligible': False, control_key: False}
    if args.adapter:
        result['configuration'] = 'original-jar-plus-integration-adapter-' + args.adapter_mode
        result['adapter_sha256'] = hashlib.sha256(args.adapter.read_bytes()).hexdigest()
        result['propagation_instrumentation_changed'] = True
    try:
        runtime_version_cmd = ['docker', 'run', '--rm', '--network', 'none', '--platform', 'linux/amd64',
                               '--entrypoint', 'java', args.java_image, '-version']
        runtime_version = subprocess.run(runtime_version_cmd, text=True, capture_output=True, timeout=30)
        result['runtime_version_command'] = runtime_version_cmd
        result['runtime_version'] = runtime_version.stdout + runtime_version.stderr
        if runtime_version.returncode:
            raise RuntimeError('Cannot verify Java runtime version')
        version = subprocess.run([args.javac, '-version'], text=True, capture_output=True, timeout=15)
        result['compiler_version'] = (version.stdout + version.stderr).strip()
        flags = ['-source', '8', '-target', '8'] if 'javac 1.8.' in result['compiler_version'] else ['--release', '8']
        sources = [HERE / 'SyncLabelOps.java', HERE / ('AsyncLabelDriver.java' if args.fixture == 'async' else 'SyncLabelDriver.java')]
        result['source_sha256'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
        for source in sources:
            shutil.copyfile(source, out / source.name)
        compile_cp = str(agent) + (':' + str(args.adapter.resolve()) if args.adapter else '')
        compile_cmd = [args.javac, *flags, '-cp', compile_cp, '-d', str(classes), *map(str, sources)]
        built = subprocess.run(compile_cmd, text=True, capture_output=True, timeout=30)
        (out / 'compile.log').write_text(built.stdout + built.stderr)
        result['compile_command'], result['compile_returncode'] = compile_cmd, built.returncode
        if built.returncode:
            raise RuntimeError('Compilation failed; see compile.log')
        cmd = ['docker', 'run', '--rm', '--network', 'none', '--platform', 'linux/amd64', '--entrypoint', 'java',
               '-v', str(agent) + ':/tf2/mirrorTaint.jar:ro', '-v', str(classes) + ':/tf2/classes:ro',
               '-v', str(home) + ':/tf2/home:rw', args.java_image, '-Xmx256m', '-javaagent:/tf2/mirrorTaint.jar',
               '-Dtaint.env=' + args.taint_env, '-Dtaint.app=works.weave.socks.calibration', '-Dtaint.version=tf2-sync',
               '-Duser.home=/tf2/home', '-cp', '/tf2/mirrorTaint.jar:/tf2/classes' + (':/tf2/integration-adapter.jar' if args.adapter else ''),
               'AsyncLabelDriver' if args.fixture == 'async' else 'syncprobe.SyncLabelDriver']
        if args.adapter:
            # Mount options precede the image; string rules must precede the original transformer,
            # while receiver repairs must follow its inserted stack hooks.
            image_index = cmd.index(args.java_image)
            cmd[image_index:image_index] = ['-v', str(args.adapter.resolve()) + ':/tf2/integration-adapter.jar:ro']
            original_index = cmd.index('-javaagent:/tf2/mirrorTaint.jar')
            if args.adapter_mode in ('strings', 'both', 'complete'):
                cmd.insert(original_index, '-javaagent:/tf2/integration-adapter.jar=strings')
            if args.adapter_mode in ('fields', 'both', 'complete'):
                cmd.insert(cmd.index('-javaagent:/tf2/mirrorTaint.jar') + 1, '-javaagent:/tf2/integration-adapter.jar=fields')
            if args.adapter_mode == 'complete':
                cmd.insert(cmd.index('-javaagent:/tf2/mirrorTaint.jar') + 1, '-javaagent:/tf2/integration-adapter.jar=sources')
                cmd.insert(cmd.index('-javaagent:/tf2/mirrorTaint.jar'), '-javaagent:/tf2/integration-adapter.jar=streams')
                cmd.insert(cmd.index('-javaagent:/tf2/mirrorTaint.jar') + 1, '-javaagent:/tf2/integration-adapter.jar=returns')
                if args.logging:
                    cmd.insert(cmd.index('-cp'), '-Dtf2.mt.logging=true')
                    cmd.insert(cmd.index('-javaagent:/tf2/mirrorTaint.jar') + 1, '-javaagent:/tf2/integration-adapter.jar=logging')
        executed = subprocess.run(cmd, text=True, capture_output=True, timeout=60)
        (out / 'runtime.log').write_text(executed.stdout + executed.stderr)
        result['run_command'], result['returncode'] = cmd, executed.returncode
        if executed.returncode:
            raise RuntimeError('Runtime failed; see runtime.log')
        result['checks'] = validate(executed.stdout, frozen)
        result['check_counts'] = {key: dict(Counter(q['status'] for q in values)) for key, values in result['checks'].items()}
        result['nonempty_error_logs'] = [str(p.relative_to(out)) for p in home.rglob('*error*.log') if p.stat().st_size]
        result['adapter_errors'] = [line for line in (executed.stdout + executed.stderr).splitlines()
                                    if 'TF2_MT_ADAPTER error' in line]
        result[control_key] = not result['nonempty_error_logs'] and all(
            q['status'] == 'passed' for group in result['checks'].values() for q in group)
        result[control_key] &= not result['adapter_errors']
        # Preserve actual inserted hooks without executing the dumped class files.
        javap = str(Path(args.javac).resolve().with_name('javap'))
        transformed = home / 'AgentLogs/ShadowTaint/tf2-sync/TaintStackFrameTransformer/works.weave.socks.calibration.SyncLabelOps.class'
        result['operations_transformed'] = transformed.exists()
        for name, target, classpath in [
            ('ops-transformed', str(transformed), []),
            ('stackframe', 'com.shadow.taint.agent.model.StackFrame', ['-classpath', str(agent)]),
            ('collector', 'com.shadow.taint.agent.runtime.TaintCollector', ['-classpath', str(agent)])]:
            inspected = subprocess.run([javap, *classpath, '-c', '-p', target], text=True, capture_output=True, timeout=30)
            (out / (name + '-javap.txt')).write_text(inspected.stdout + inspected.stderr)
            if inspected.returncode:
                raise RuntimeError('Bytecode evidence capture failed: ' + name)
        result[control_key] = result[control_key] and result['operations_transformed']
    except Exception as exc:
        result['error'] = str(exc)
    result['evidence_sha256'] = {str(p.relative_to(out)): hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in sorted(out.rglob('*')) if p.is_file() and p.suffix not in ('.class', '.jar')}
    (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    with zipfile.ZipFile(out.with_suffix('.zip'), 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(out.rglob('*')):
            if path.is_file() and path.suffix not in ('.jar', '.class'):
                archive.write(path, path.relative_to(out))
    print(json.dumps({k: v for k, v in result.items() if k not in ('checks', 'run_command', 'evidence_sha256')}, indent=2))
    return int(not result[control_key])


if __name__ == '__main__':
    raise SystemExit(main())
