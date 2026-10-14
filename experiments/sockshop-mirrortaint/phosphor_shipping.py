#!/usr/bin/env python3
"""Prepare Java8 Phosphor and qualify original Shipping; never a cost benchmark."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path(__file__).resolve().parent
IMAGE = 'weaveworksdemos/orders@sha256:b622e40e83433baf6374f15e076b53893f79958640fc6667dff597622eff03b9'
TOOL_SHA = '12d9613d93baaa3dc64e7727bcfba006147e06b244af80b6b5fd33e1af1fd837'
LABEL = 'phosphor-shipping-20261014'
CASES = [
    {'case': 'distinct-fields', 'body': {'id': 'repeat-id', 'name': 'first-name'}},
    {'case': 'same-value-fields', 'body': {'id': 'same-value', 'name': 'same-value'}},
    {'case': 'repeat-same-values', 'body': {'id': 'same-value', 'name': 'same-value'}},
    {'case': 'same-record-new-name', 'body': {'id': 'repeat-id', 'name': 'second-name'}}]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def run(command, log=None):
    if log:
        with log.open('wb') as stream:
            subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, check=True)
    else:
        subprocess.run(command, check=True)


def mounts(work, tool):
    return ['-v', str(tool) + ':/phosphor:ro', '-v', str(work) + ':/out']


def verify_tool(tool):
    if sha(tool / 'Phosphor-0.0.3.jar') != TOOL_SHA:
        raise ValueError('Not the pinned official Phosphor 0.0.3 artifact')


def freeze_prepared(work, tool):
    verify_tool(tool)
    files = [SOURCE / name for name in ('PhosphorShippingAgent.java', 'PhosphorShippingProbe.java')]
    files += [tool / 'Phosphor-0.0.3.jar', work / 'shipping.jar', work / 'shipping-adapter.jar']
    files += list((work / 'probe-classes').glob('*.class'))
    files += [work / 'jre/lib/rt.jar', work / 'jre/bin/java', work / 'runtime-smoke.log',
              work / 'instrument-jre.log', work / 'shipping-probe.log']
    if 'Done after ' not in (work / 'instrument-jre.log').read_text():
        raise ValueError('Incomplete JRE instrumentation')
    save(work / 'prepared.json', {'image': IMAGE, 'phosphor_version': '0.0.3',
         'profile': 'multiTaint, explicit data flow; object-wide String source tags',
         'rabbitmq': 'not deployed; original controller accepts its queue exception',
         'source_and_artifact_sha256': {str(p): sha(p) for p in files}})


def prepare(work, tool, shipping):
    verify_tool(tool)
    work.mkdir(parents=True, exist_ok=False)
    (work / 'jre').mkdir()
    (work / 'shipping.jar').write_bytes(shipping.read_bytes())
    with zipfile.ZipFile(shipping) as app:
        for name in app.namelist():
            if name.startswith(('BOOT-INF/classes/', 'BOOT-INF/lib/')) and not name.endswith('/'):
                target = work / 'shipping' / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(app.read(name))
    common = ['docker', 'run', '--rm', '--network', 'none', '--user', '1000:1000'] + mounts(work, tool)
    run(common + ['--memory', '6g', '--cpus', '4', '--entrypoint', 'java', IMAGE,
                  '-Xmx4g', '-jar', '/phosphor/Phosphor-0.0.3.jar', '-multiTaint',
                  '/usr/lib/jvm/java-1.8-openjdk/jre', '/out/jre'], work / 'instrument-jre.log')
    (work / 'jre/bin/java').chmod((work / 'jre/bin/java').stat().st_mode | 0o100)
    cp = str(tool / 'Phosphor-0.0.3.jar')
    run(['javac', '--release', '8', '-cp', cp, '-d', str(work / 'adapter-classes'),
         str(SOURCE / 'PhosphorShippingAgent.java')], work / 'compile-adapter.log')
    run(['javac', '--release', '8', '-cp', cp + ':' + str(work / 'shipping/BOOT-INF/classes') + ':'
         + str(work / 'shipping/BOOT-INF/lib/*'), '-d', str(work / 'probe-classes'),
         str(SOURCE / 'PhosphorShippingProbe.java')], work / 'compile-probe.log')
    with zipfile.ZipFile(work / 'shipping-adapter.jar', 'w', zipfile.ZIP_DEFLATED) as agent:
        agent.writestr('META-INF/MANIFEST.MF', 'Manifest-Version: 1.0\nPremain-Class: PhosphorShippingAgent\n\n')
        for file in (work / 'adapter-classes').rglob('*.class'):
            agent.write(file, str(file.relative_to(work / 'adapter-classes')))
    java = common + ['--memory', '3g', '--cpus', '2', '--entrypoint', '/out/jre/bin/java', IMAGE,
                     '-Xmx2g', '-Xbootclasspath/a:/phosphor/Phosphor-0.0.3.jar',
                     '-javaagent:/phosphor/Phosphor-0.0.3.jar']
    run(java + ['-version'], work / 'runtime-smoke.log')
    run(java + ['-cp', '/out/probe-classes:/out/shipping/BOOT-INF/classes:/out/shipping/BOOT-INF/lib/*',
                'PhosphorShippingProbe'], work / 'shipping-probe.log')
    freeze_prepared(work, tool)


def evaluate(work):
    prepared = json.loads((work / 'prepared.json').read_text())
    for name, expected in prepared['source_and_artifact_sha256'].items():
        if sha(Path(name)) != expected:
            raise ValueError('Prepared artifact changed: ' + name)
    probe = (work / 'shipping-probe.log').read_text()
    if len([l for l in probe.splitlines() if l.startswith('PROBE_PASS ')]) != 12 or 'PROBE_COMPLETE checks=12' not in probe:
        raise ValueError('Native propagation probes did not complete')
    text = (work / 'http-fields.log').read_text()
    if any(error in text + probe for error in (
            'java.lang.VerifyError', 'java.lang.NoSuchMethodError', 'AnalyzerException',
            'Calling uninstrumented Phosphor stubs')):
        raise ValueError('Phosphor instrumentation/runtime compatibility error')
    if 'PHOSPHOR_ADAPTER_ERROR' in text or 'PHOSPHOR_ADAPTER controller-instrumented' not in text:
        raise ValueError('Adapter failure or controller not observed')
    rows = [json.loads(l.split('PHOSPHOR_BOUNDARY ', 1)[1]) for l in text.splitlines() if l.startswith('PHOSPHOR_BOUNDARY ')]
    cases = json.loads((work / 'http-cases.json').read_text())
    responses = json.loads((work / 'http-results.json').read_text())
    if cases != CASES or len(responses) != len(cases) or len(rows) != 4 * len(cases):
        raise ValueError('Incomplete HTTP workload or boundary capture')
    counts, queries = Counter(tp=0, fp=0, fn=0, exact=0), []
    for invocation, (case, response) in enumerate(zip(cases, responses), 1):
        if response['case'] != case['case'] or response['status'] != 201 or response['body'] != case['body']:
            raise ValueError('HTTP business failure')
        for field in ('id', 'name'):
            observed = [r for r in rows if r['invocation'] == invocation and r['field'] == field]
            if Counter(r['phase'] for r in observed) != {'source': 1, 'sink': 1}:
                raise ValueError('Missing or duplicate field source/target')
            source = next(r for r in observed if r['phase'] == 'source')
            sink = next(r for r in observed if r['phase'] == 'sink')
            label = 'shipping:' + str(invocation) + ':' + field
            if source['configured_source_label'] != label or source['value'] != case['body'][field] or sink['value'] != case['body'][field]:
                raise ValueError('Source declaration or business field mismatch')
            if set(source['tags']) != {label}:
                raise ValueError('Source adapter failed to set the declared native label')
            # The expected label is the independently declared entry field;
            # values only validate business output and never join provenance.
            expected, actual = {label}, set(sink['tags'])
            score = {'tp': len(expected & actual), 'fp': len(actual - expected),
                     'fn': len(expected - actual), 'exact': actual == expected}
            counts.update(score)
            queries.append({'case': case['case'], 'invocation': invocation, 'field': field,
                            'expected': sorted(expected), 'actual': sorted(actual), **score})
    tp, fp, fn = (counts[k] for k in ('tp', 'fp', 'fn'))
    result = {'kind': 'phosphor-shipping-qualification', 'configuration': prepared,
              'status': 'bounded-http-calibration-complete', 'business_calls': len(cases),
              'direct_probe_checks_passed': 12,
              'shared_reference_field_labels_independent': 'field_labels_independent=true' in probe,
              'http_queries': len(queries), 'counts': dict(counts),
              'precision': tp / (tp + fp) if tp + fp else None,
              'recall': tp / (tp + fn) if tp + fn else None,
              'f1': 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
              'queries': queries, 'main_table_eligible': False, 'performance_eligible': False,
              'limitations': [
                  'This version/profile tags String objects; shared references cannot preserve independent field source tags.',
                  'HTTP target is the controller return Shipment; serialized response tags are not examined.',
                  'No RabbitMQ transport, second JVM, Carts, Orders, parallel workload or cost qualification.',
                  'Direct probes test controlled setters and object reuse; HTTP calls create fresh request DTOs.',
                  'This eight-query qualification is separate from the existing 166-query two-baseline suite.'],
              'evidence_sha256': {str(work / n): sha(work / n) for n in (
                  'prepared.json', 'http-cases.json', 'http-results.json', 'http-fields.log')}}
    save(work / 'qualification.json', result)
    return result


def exercise(work, tool, port, existing=None):
    verify_tool(tool)
    if (work / 'http-results.json').exists():
        raise ValueError('HTTP evidence already exists; use a new work directory')
    save(work / 'http-cases.json', CASES)  # Frozen before the first business call.
    name = existing or ('tf2-phosphor-shipping-' + uuid.uuid4().hex[:10])
    if existing:
        spec = json.loads(subprocess.check_output(['docker', 'inspect', name]))[0]
        if spec['Config']['Labels'].get('tracefusion.experiment') != LABEL:
            raise ValueError('Existing container is not owned by this experiment')
        if spec['Config']['Image'] != IMAGE or '-javaagent:/out/shipping-adapter.jar' not in spec['Config']['Cmd']:
            raise ValueError('Unexpected existing container configuration')
        if not any(m['Source'] == str(work) and m['Destination'] == '/out' for m in spec['Mounts']):
            raise ValueError('Different experiment evidence directory')
    else:
        run(['docker', 'run', '-d', '--name', name, '--label', 'tracefusion.experiment=' + LABEL,
             '--network', 'bridge', '-p', f'127.0.0.1:{port}:8080', '--memory', '3g', '--cpus', '2',
             '--user', '1000:1000'] + mounts(work, tool) + [
             '--entrypoint', '/out/jre/bin/java', IMAGE, '-Xms128m', '-Xmx2g',
             '-Xbootclasspath/a:/phosphor/Phosphor-0.0.3.jar', '-javaagent:/out/shipping-adapter.jar',
             '-javaagent:/phosphor/Phosphor-0.0.3.jar=cacheDir=/out/phosphor-cache',
             '-Dspring.zipkin.enabled=false', '-Dspring.rabbitmq.host=127.0.0.1', '-jar', '/out/shipping.jar'])
    responses = []
    save(work / 'compatibility.json', {'stage': 'startup', 'status': 'running', 'field_metrics': None})
    try:
        save(work / 'http-container.json', json.loads(subprocess.check_output(['docker', 'inspect', name])))
        base = 'http://127.0.0.1:' + str(port)
        deadline = time.monotonic() + 300
        while True:
            try:
                with urllib.request.urlopen(base + '/shipping', timeout=3) as response:
                    if response.status == 200:
                        break
            except (OSError, urllib.error.URLError):
                if time.monotonic() >= deadline:
                    raise TimeoutError('Shipping startup did not complete in 300 seconds')
                time.sleep(1)
        save(work / 'compatibility.json', {'stage': 'business', 'status': 'running', 'field_metrics': None})
        for case in CASES:
            request = urllib.request.Request(base + '/shipping', data=json.dumps(case['body']).encode(),
                                            headers={'Content-Type': 'application/json'}, method='POST')
            with urllib.request.urlopen(request, timeout=45) as response:
                responses.append({'case': case['case'], 'status': response.status, 'body': json.load(response)})
            save(work / 'http-results.json', responses)
    finally:
        (work / 'http-fields.log').write_bytes(subprocess.check_output(['docker', 'logs', name], stderr=subprocess.STDOUT))
        run(['docker', 'stop', '--timeout', '10', name])
        run(['docker', 'rm', name])
    save(work / 'compatibility.json', {'stage': 'analysis', 'status': 'running', 'field_metrics': None})
    result = evaluate(work)
    save(work / 'compatibility.json', {'stage': 'analysis', 'status': result['status'],
         'business_passed': len(responses), 'field_metrics': result['counts'], 'main_table_eligible': False})
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=('prepare', 'http', 'evaluate'))
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--tool', type=Path, default=ROOT / 'artifacts/external-tools/phosphor-0.0.3')
    parser.add_argument('--shipping', type=Path, default=ROOT / 'artifacts/sockshop-five-methods-original-20261013/shipping.jar')
    parser.add_argument('--port', type=int, default=18583)
    parser.add_argument('--existing-container')
    args = parser.parse_args()
    work, tool = args.work.resolve(), args.tool.resolve()
    if args.stage == 'prepare':
        prepare(work, tool, args.shipping.resolve())
        print('Prepared pinned Java8 runtime and direct Shipping probes')
    else:
        try:
            result = exercise(work, tool, args.port, args.existing_container) if args.stage == 'http' else evaluate(work)
        except Exception as error:
            if args.stage == 'http' and (work / 'compatibility.json').exists():
                status = json.loads((work / 'compatibility.json').read_text())
                status.update(status='unavailable', error=str(error), field_metrics=None)
                save(work / 'compatibility.json', status)
            raise
        print(json.dumps({k: result[k] for k in ('status', 'http_queries', 'counts', 'f1', 'shared_reference_field_labels_independent', 'main_table_eligible')}))
