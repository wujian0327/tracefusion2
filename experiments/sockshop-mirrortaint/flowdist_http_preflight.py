#!/usr/bin/env python3
"""Original Orders client -> original Spring Shipping HTTP clock compatibility.

Explicit boundary method hooks, no Soot/branch instrumentation yet. RabbitMQ is
unavailable and the original controller accepts the request via its catch path.
This is not an Orders.newOrder workload, accuracy oracle or performance test.
"""
import argparse
import hashlib
import re
from pathlib import Path
import shutil
import subprocess
from zipfile import ZipFile

import flowdist_preflight as tool


def run(repo, orders, shipping, out):
    tool.verify_repository(repo)
    out.mkdir(parents=True, exist_ok=False)
    work = out / 'work'
    (work / 'classes').mkdir(parents=True)
    (work / 'lib').mkdir()
    originals = {}
    for jar in (orders, shipping):
        role = 'orders' if jar == orders else 'shipping'
        originals[str(jar)] = hashlib.sha256(jar.read_bytes()).hexdigest()
        with ZipFile(jar) as archive:
            for name in archive.namelist():
                if name.startswith('BOOT-INF/classes/'):
                    relative = name[len('BOOT-INF/classes/'):]
                    # Spring configuration comes from Shipping's original properties.
                    if not relative or name.endswith('/') or (jar == orders and not name.endswith('.class')):
                        continue
                    target = work / 'classes' / relative
                elif name.startswith('BOOT-INF/lib/') and name.endswith('.jar'):
                    target = work / 'lib' / role / Path(name).name
                else:
                    continue
                data = archive.read(name)
                if target.exists() and target.read_bytes() != data:
                    raise ValueError('Incompatible duplicate application dependency: ' + str(target))
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
    here = Path(__file__).parent
    sources = [here / 'flowdist/FlowDistHttpClock.java', here / 'FlowDistHttpConfiguration.java',
               here / 'FlowDistSockShopHttpProbe.java', here / 'flowdist/FlowDistHttpClockTest.java']
    classpath = ':'.join(map(str, [work / 'classes', repo / 'tool/FLOWDIST.jar', *sorted((work / 'lib').rglob('*.jar'))]))
    command = ['javac', '--release', '8', '-cp', classpath, '-d', str(work / 'classes'), *map(str, sources)]
    compile_result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    (out / 'compile.log').write_text(compile_result.stdout + compile_result.stderr)
    if compile_result.returncode:
        raise ValueError('HTTP adapter compilation failed')
    tool.save(out / 'manifest.json', {'kind': 'sockshop-original-client-shipping-http-compatibility',
        'upstream_commit': tool.COMMIT, 'original_jar_sha256': originals,
        'source_sha256': {str(f.relative_to(here)): hashlib.sha256(f.read_bytes()).hexdigest() for f in sources},
        'compile_command': command, 'clock_transport': 'versioned HTTP header; original OTMonitor clock and first receive rule',
        'instrumentation': 'explicit client-call and Spring HandlerMethod dispatch boundary hooks',
        'original_business_classes_modified': False, 'full_orders_controller_executed': False,
        'rabbitmq_available': False, 'accuracy_eligible': False, 'performance_eligible': False})
    for role in ('shipping', 'orders'):
        (work / 'runtime' / role / 'test1').mkdir(parents=True)
    script = '''#!/bin/sh
set -eu
COMMON='/work/classes:/flowdist/tool/*'
cd /work/runtime/shipping
java -Xmx768m -cp "/work/lib/shipping/*:$COMMON" FlowDistSockShopHttpProbe shipping > server.log 2>&1 &
server=$!
trap 'kill "$server" 2>/dev/null || true; wait "$server" 2>/dev/null || true' EXIT
ready=0
for attempt in $(seq 1 45); do
  if ! kill -0 "$server" 2>/dev/null; then cat server.log; exit 1; fi
  if sed -n '/Started FlowDistSockShopHttpProbe/p' server.log | head -n 1 | read line; then ready=1; break; fi
  sleep 1
done
if [ "$ready" != 1 ]; then cat server.log; exit 1; fi
cd /work/runtime/orders
java -Xmx512m -cp "/work/lib/orders/*:$COMMON" FlowDistSockShopHttpProbe orders > client.log 2>&1 || { cat client.log; exit 1; }
cat client.log
'''
    (work / 'run-http.sh').write_text(script)
    tool.execute(repo, out, 'http-clock-checks', ['-cp', '/work/classes:/flowdist/tool/*', 'disttaint.FlowDistHttpClockTest'])
    if 'FLOWDIST_HTTP_CLOCK_CHECKS_PASSED' not in (out / 'http-clock-checks.log').read_text():
        raise ValueError('Clock validation marker missing')
    tool.execute(repo, out, 'http-runtime', ['/work/run-http.sh'], entry='sh', timeout=90)
    log = (work / 'runtime/orders/client.log').read_text()
    if 'FLOWDIST_HTTP_BUSINESS_PASSED' not in log or 'FLOWDIST_PLAIN_HTTP_CONTROL_PASSED' not in log:
        raise ValueError('Business request/response validation missing')
    traces = work / 'traces/test1'
    traces.mkdir(parents=True)
    for role in ('shipping', 'orders'):
        files = list((work / 'runtime' / role).rglob('Remote*.em'))
        if len(files) != 1:
            raise ValueError('Expected exactly one original process trace for ' + role)
        shutil.copyfile(files[0], traces / files[0].name)
    source = '<works.weave.socks.orders.services.AsyncGetService: java.util.concurrent.Future postResource(java.net.URI,java.lang.Object,org.springframework.core.ParameterizedTypeReference)>'
    sink = '<works.weave.socks.shipping.controllers.ShippingController: works.weave.socks.shipping.entities.Shipment postShipping(works.weave.socks.shipping.entities.Shipment)>'
    inspection = tool.inspect_traces(repo, out, source, sink)
    if inspection['status'] != 'peer-correlation-validated':
        raise ValueError('Missing reciprocal HTTP process correlation')
    query = source + '; ' + sink
    result = tool.execute(repo, out, 'http-method-analysis', ['-Xmx1g', '-ea', '-cp', tool.CP,
        'disttaint.OTAnalysisAll', query, '/work/traces', '/work', '', '-prec'])
    raw = (out / 'http-method-analysis.log').read_text()
    length = re.search(r'\[The method path length\]: (\d+)', raw)
    candidates = (work / 'methodList.out').read_text().splitlines()
    if not length or source not in candidates or sink not in candidates:
        raise ValueError('Cross-process method candidate query failed')
    tool.save(out / 'result.json', {'kind': 'sockshop-http-clock-compatibility-result',
        'business_body_preserved': True, 'plain_http_control_passed': True,
        'reciprocal_process_correlation': True, 'method_query': query,
        'candidate_method_count': int(length[1]), 'original_analyzer_jar_modified': False,
        'full_orders_controller_executed': False, 'statement_instrumentation_present': False,
        'accuracy_eligible': False, 'performance_eligible': False})
    print(inspection['status'], result['status'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('repo', 'orders', 'shipping', 'out'):
        parser.add_argument('--' + flag, type=Path, required=True)
    a = parser.parse_args()
    run(a.repo.resolve(), a.orders.resolve(), a.shipping.resolve(), a.out.resolve())
