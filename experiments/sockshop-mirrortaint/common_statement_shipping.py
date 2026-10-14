#!/usr/bin/env python3
"""Four-tool Shipping statement projection on the same four HTTP inputs.

One aggregate positive statement pair, not four instance queries or a general
accuracy benchmark. Native FlowDist graph traversal is retained unchanged.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import secrets
import shlex
import shutil
import subprocess
import time
import urllib.error
import urllib.request

import flowdist_preflight as tool
from audit_flowdist_coverage import canonical_rows, coverage
from evaluate_five_methods import boundary_claims
from phosphor_shipping import CASES, IMAGE, evaluate as evaluate_phosphor

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PILOT = ROOT / 'artifacts/sockshop-three-five-v3-20261013'
GRAPH = ROOT / 'artifacts/flowdist-shipping-data-20261014'
DRIVER = ROOT / 'artifacts/flowdist-all-query-launcher-v2-20261014'
PHOSPHOR = ROOT / 'artifacts/phosphor-shipping-20261014'


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze(out):
    out.mkdir(parents=True, exist_ok=False)
    rows = (GRAPH / 'work/ServiceGraph/stmtids.out').read_text().splitlines()
    method = '<works.weave.socks.shipping.controllers.ShippingController: works.weave.socks.shipping.entities.Shipment postShipping(works.weave.socks.shipping.entities.Shipment)>'
    def one(fragment):
        hits = [(i, row) for i, row in enumerate(rows) if row.startswith(method + ' - ')
                and (row.split(' - ', 1)[1].startswith(fragment) if fragment.startswith('return ')
                     else fragment in row.split(' - ', 1)[1])]
        if len(hits) != 1:
            raise ValueError('Ambiguous statement endpoint: ' + fragment)
        return {'id': hits[0][0], 'text': hits[0][1]}
    original = PILOT / 'tracefusion/shipping.jar'
    disassembly = subprocess.check_output(['javap', '-c', str(
        ROOT / 'artifacts/sockshop-five-methods-original-20261013/shipping/BOOT-INF/classes/works/weave/socks/shipping/controllers/ShippingController.class')], text=True)
    body = disassembly.split(' postShipping(', 1)[1].split('public java.util.Map', 1)[0]
    if not re.search(r'\d+: aload_1\s+\d+: areturn', body):
        raise ValueError('Independent original return-alias oracle not verified')
    (out / 'original-shipping.javap').write_text(disassembly)
    contract = {'kind': 'common-aggregate-statement-shipping-calibration', 'cases': CASES,
        'source': one('@parameter0:'), 'sink': one('return r1'),
        'expected_pairs': [['postShipping.parameter0', 'postShipping.return']],
        'source_profile': 'Selected id/name contents of the incoming Shipment at parameter0',
        'target_profile': 'Selected id/name contents of the returned Shipment',
        'projection': 'Map every declared entry-field source to the parameter statement; map every return-field target to the return statement; deduplicate over the complete four-call workload.',
        'oracle': 'Original controller directly returns its unmodified Shipment parameter, independently checked from original bytecode; expected answers never enter tracking engines.',
        'freeze_status': 'Calibration: historical endpoint observations exist; contract written before fresh MT/TF/FlowDist predictions.',
        'request_instance_accuracy': False, 'negative_queries': 0,
        'original_shipping_sha256': digest(original),
        'statement_map_sha256': digest(GRAPH / 'work/ServiceGraph/stmtids.out'),
        'phosphor_cases_sha256': digest(PHOSPHOR / 'http-cases.json'),
        'accuracy_eligible': False, 'performance_eligible': False}
    save(out / 'contract.json', contract)
    return contract


def collect(mode, out, contract, port):
    run = out / mode
    run.mkdir()
    old = PILOT / mode
    spec = json.loads((old / 'compose.lock.json').read_text())['services']['shipping']
    volumes, copied = [], {}
    for mount in spec['volumes']:
        source, target, permission = mount.split(':')
        source = Path(source)
        dest = run / source.relative_to(old)
        if source.is_dir():
            dest.mkdir(parents=True, exist_ok=True)
            dest.chmod(0o777)
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, dest)
            copied[str(dest)] = digest(dest)
        volumes += ['-v', str(dest) + ':' + target + ':' + permission]
    app = run / 'shipping.jar'
    if mode != 'flowdist' and digest(app) != contract['original_shipping_sha256']:
        raise ValueError('Original business JAR differs')
    if mode == 'flowdist':
        manifest = json.loads((ROOT / 'artifacts/flowdist-five-fullmethods-parameters-v4-20261013/manifest.json').read_text())
        if digest(app) != manifest['apps']['shipping']['adapted_sha256'] or contract['original_shipping_sha256'] != manifest['apps']['shipping']['original_sha256']:
            raise ValueError('Unqualified FlowDist business adaptation')
        runtime = run / 'runtime/shipping'
        (runtime / 'test1').mkdir()
        (runtime / 'test1').chmod(0o777)
        for name in ('stmtids.out', 'entitystmt.out.branch'):
            shutil.copyfile(old / 'runtime/shipping' / name, runtime / name)
    options = [o for o in shlex.split(spec['environment']['JAVA_OPTS']) if not o.startswith(('-Xms', '-Xmx'))]
    command = ['java', '-Xms128m', '-Xmx2g', *options, '-Dspring.rabbitmq.host=127.0.0.1',
               '-jar', '/tf2/app.jar', '--port=8080']
    name = 'tf2-statement-shipping-' + secrets.token_hex(5)
    docker = ['docker', 'run', '-d', '--name', name, '--label', 'tracefusion.experiment=common-statement-shipping',
              '--network', 'bridge', '-p', f'127.0.0.1:{port}:8080', '--memory', '3g', '--cpus', '2',
              '--user', '1000:1000', *volumes, '-w', '/tf2/output', '--entrypoint', 'java', IMAGE, *command[1:]]
    save(run / 'configuration.json', {'command': docker, 'input_artifact_sha256': copied,
         'original_business_sha256': contract['original_shipping_sha256'], 'cases': CASES,
         'rabbitmq': 'not deployed; original controller accepts queue connection exceptions',
         'costs_comparable': False})
    status = {'configuration': mode, 'stage': 'startup', 'status': 'unavailable', 'business': []}
    subprocess.run(docker, check=True, capture_output=True)
    try:
        deadline = time.monotonic() + 300
        base = 'http://127.0.0.1:' + str(port)
        while True:
            try:
                with urllib.request.urlopen(base + '/shipping', timeout=3) as response:
                    if response.status == 200:
                        break
            except (OSError, urllib.error.URLError):
                if time.monotonic() >= deadline:
                    raise TimeoutError('Shipping startup timed out')
                time.sleep(1)
        status['stage'] = 'business'
        for case in CASES:
            req = urllib.request.Request(base + '/shipping', data=json.dumps(case['body']).encode(),
                                         headers={'Content-Type': 'application/json'}, method='POST')
            with urllib.request.urlopen(req, timeout=45) as response:
                observed = json.load(response)
                if response.status != 201 or observed != case['body']:
                    raise ValueError('Business result differs')
                status['business'].append({'case': case['case'], 'status': response.status, 'body': observed})
            save(run / 'status.json', status)
        status.update(stage='analysis', status='business-passed')
    except Exception as error:
        status['error'] = str(error)
        raise
    finally:
        subprocess.run(['docker', 'stop', '--timeout', '30', name], check=True, capture_output=True, timeout=45)
        (run / 'service.log').write_bytes(subprocess.check_output(['docker', 'logs', name], stderr=subprocess.STDOUT))
        subprocess.run(['docker', 'rm', name], check=True, capture_output=True)
        save(run / 'status.json', status)
    if any(marker in (run / 'service.log').read_text() for marker in ('TF2_BOUNDARY error=', 'TF2_MT_ADAPTER error')):
        raise ValueError('Frontend error in ' + mode)
    print(mode, '4/4 common HTTP inputs passed', flush=True)


def native_query(repo, out, contract):
    tool.verify_repository(repo)
    manifest = json.loads((DRIVER / 'manifest.json').read_text())
    if manifest['engine_class_overridden'] or manifest['upstream_engine_sha256'] != tool.TOOL_HASHES['FLOWDIST.jar']:
        raise ValueError('Unqualified native driver')
    for name, expected in manifest['class_sha256'].items():
        if digest(DRIVER / 'launcher' / name) != expected:
            raise ValueError('Native driver class changed: ' + name)
    for name, expected in manifest['source_sha256'].items():
        if digest(Path(name)) != expected:
            raise ValueError('Native decoding/model source changed: ' + name)
    runtime = out / 'flowdist/runtime/shipping'
    graph = GRAPH / 'work/ServiceGraph'
    rows = (graph / 'stmtids.out').read_text().splitlines()
    if digest(graph / 'stmtids.out') != contract['statement_map_sha256'] or canonical_rows(rows) != canonical_rows((runtime / 'stmtids.out').read_text().splitlines()):
        raise ValueError('Graph/runtime statement alignment changed')
    mapping = [set(map(int, row.split())) for row in (runtime / 'entitystmt.out.branch').read_text().splitlines()]
    _, covered = coverage(runtime / 'stmtCoverage1.out', mapping, len(rows))
    if any(contract[endpoint]['id'] not in covered for endpoint in ('source', 'sink')):
        raise ValueError('Unobserved statement endpoint')
    target = out / 'native-query'
    work = target / 'work'
    work.mkdir(parents=True)
    shutil.copytree(graph, work / 'graph')
    shutil.copytree(DRIVER / 'launcher', work / 'launcher')
    if (work / 'launcher/disttaint/DynTransferGraph.class').exists():
        raise ValueError('Author engine override forbidden')
    for name in ('methodList.out', 'coveredMethods.txt'):
        shutil.copyfile(GRAPH / 'work' / name, work / name)
    shutil.copyfile(GRAPH / 'work/methodList.out', work / 'methodsInPair.out')
    (work / 'traces').mkdir()
    for trace in runtime.glob('Local*.em'):
        shutil.copyfile(trace, work / 'traces' / trace.name)
    (work / 'query.txt').write_text(contract['source']['text'] + '; ' + contract['sink']['text'] + '\n')
    (work / 'graph/stmtCoverageOT1.out').write_text(' '.join(map(str, sorted(covered))) + '\n')
    (work / 'graph/stmtCoverage1.out').unlink(missing_ok=True)
    tool.execute(repo, target, 'statement-query', ['-Xmx1g', '-ea', '-cp', '/work/launcher:' + tool.CP,
        'FlowDistFieldDecision', '/work/query.txt', '/work/traces', '/work/graph', '--all-query-matching'])
    text = (target / 'statement-query.log').read_text()
    flags = json.loads(re.search(r'FLOWDIST_ORIGINAL_FLAGS=(\{[^\n]+\})', text)[1])
    if flags['source_nodes'] <= 0 or flags['sink_nodes'] <= 0 or flags['exercised_nodes'] <= 0 or flags['exercised_edges'] <= 0:
        raise ValueError('Native query did not exercise nonempty endpoints/graph')
    prediction = True if flags['is_local'] else False if flags['no_dependency'] else None
    return prediction, flags


def evaluate(repo, out):
    contract = json.loads((out / 'contract.json').read_text())
    for mode in ('tracefusion', 'mirrortaint', 'flowdist'):
        run = out / mode
        status = json.loads((run / 'status.json').read_text())
        config = json.loads((run / 'configuration.json').read_text())
        if status['status'] != 'business-passed' or len(status['business']) != len(contract['cases']):
            raise ValueError('Incomplete common business execution: ' + mode)
        if config['cases'] != contract['cases'] or config['original_business_sha256'] != contract['original_shipping_sha256']:
            raise ValueError('Different frozen workload/business contract: ' + mode)
        for case, response in zip(contract['cases'], status['business']):
            if response != {'case': case['case'], 'status': 201, 'body': case['body']}:
                raise ValueError('Common workload result differs: ' + mode)
        for name, expected in config['input_artifact_sha256'].items():
            if digest(Path(name)) != expected:
                raise ValueError('Runtime input artifact changed: ' + name)
    phos = evaluate_phosphor(PHOSPHOR)
    if json.loads((PHOSPHOR / 'http-cases.json').read_text()) != contract['cases'] or digest(PHOSPHOR / 'shipping.jar') != contract['original_shipping_sha256']:
        raise ValueError('Phosphor used a different workload/business input')
    results = []
    for mode in ('tracefusion', 'mirrortaint'):
        run = out / mode
        claims = boundary_claims(run, 'shipping', mode)
        fields = [f for targets in claims.values() for target in targets for f in target['fields'].values()]
        if len(claims) != 4 or len(fields) != 8:
            raise ValueError('Incomplete field-to-statement projection')
        unresolved = sum(not f['known'] for f in fields)
        sources = [c for f in fields for c in f['sources']]
        if any(len(c) != 3 or c[0] not in claims or c[2] not in ('id', 'name') for c in sources):
            raise ValueError('Unmapped source claim; do not hide it in statement projection')
        prediction = True if sources else None if unresolved else False
        results.append({'configuration': mode, 'prediction': prediction, 'projected_field_targets': len(fields),
                        'unresolved_field_targets': unresolved, 'basis': 'Actual engine-produced field sources projected to the frozen statement pair'})
    prediction, flags = native_query(repo, out, contract)
    results.append({'configuration': 'flowdist', 'prediction': prediction, 'native_flags': flags,
                    'basis': 'Unchanged author all-query graph builder and statement search; full-event decoder, no static fallback'})
    source_tokens = {'shipping:' + str(invocation) + ':' + field
                     for invocation in range(1, len(contract['cases']) + 1) for field in ('id', 'name')}
    observed_tokens = {token for query in phos['queries'] for token in query['actual']}
    if observed_tokens - source_tokens:
        raise ValueError('Unmapped Phosphor source label; cannot project it to the declared statement')
    results.append({'configuration': 'phosphor', 'prediction': bool(observed_tokens),
                    'projected_field_targets': phos['http_queries'], 'unresolved_field_targets': 0,
                    'basis': 'Pinned previous identical four-case HTTP capture; actual native labels projected to parameter/return statements'})
    for row in results:
        p = row['prediction']
        row.update(queries=1, tp=int(p is True), fp=0, fn=int(p is not True), unknown=int(p is None),
                   precision=1.0 if p is True else None, recall=float(p is True), f1=1.0 if p is True else 0.0)
    report = {'kind': contract['kind'], 'results': results, 'contract': contract,
              'field_instance_accuracy': False, 'accuracy_eligible': False, 'performance_eligible': False,
              'limitations': ['One aggregate positive pair from four common business inputs; no precision/false-positive discrimination.',
                  'Four calls and eight field answers collapse to one statement pair; no per-request, field-version or cross-JVM claims.',
                  'Source/target profile is selected parameter/return contents; unrelated fields and source profiles are outside this calibration.',
                  'Phosphor reuses its verified identical workload capture; MT/TF/FlowDist collected fresh. This is calibration, not blinded evaluation.',
                  'RabbitMQ is absent for every configuration; original controller accepts queue exceptions. No cost comparison.',
                  'Adapters are disclosed; FlowDist original all-query builder uses another author-provided matching mode.']}
    save(out / 'comparison.json', report)
    names = {'tracefusion': 'TraceFusion', 'mirrortaint': 'MirrorTaint + disclosed adapters',
             'flowdist': 'FlowDist + disclosed adapters', 'phosphor': 'Phosphor 0.0.3 + source/observation adapter'}
    lines = ['# Common statement-level Shipping calibration', '',
             'Four identical HTTP inputs; one aggregate positive parameter-to-return statement pair.', '',
             '| Configuration | Queries | TP | FP | FN | Unknown | Precision | Recall | F1 |',
             '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for row in results:
        values = [f"{row[k]:.1%}" if row[k] is not None else 'N/A' for k in ('precision', 'recall', 'f1')]
        lines.append('| ' + names[row['configuration']] + ' | ' + ' | '.join(str(row[k]) for k in
                     ('queries', 'tp', 'fp', 'fn', 'unknown')) + ' | ' + ' | '.join(values) + ' |')
    lines += ['', *['- ' + limitation for limitation in report['limitations']], '']
    (out / 'comparison.md').write_text('\n'.join(lines))
    with (out / 'main-table.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        keys = ('configuration', 'queries', 'tp', 'fp', 'fn', 'unknown', 'precision', 'recall', 'f1')
        writer = csv.DictWriter(stream, fieldnames=keys, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(results)
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('stage', choices=('freeze', 'collect', 'evaluate'))
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--mode', choices=('tracefusion', 'mirrortaint', 'flowdist'))
    p.add_argument('--port', type=int, default=18583)
    p.add_argument('--repo', type=Path, default=ROOT / 'artifacts/external-tools/flowdist')
    a = p.parse_args()
    out = a.out.resolve()
    if a.stage == 'freeze':
        freeze(out)
    elif a.stage == 'collect':
        if not a.mode:
            p.error('--mode is required to collect')
        collect(a.mode, out, json.loads((out / 'contract.json').read_text()), a.port)
    else:
        report = evaluate(a.repo.resolve(), out)
        print(json.dumps([{k: row[k] for k in ('configuration', 'queries', 'tp', 'fp', 'fn', 'unknown')} for row in report['results']], indent=2))
