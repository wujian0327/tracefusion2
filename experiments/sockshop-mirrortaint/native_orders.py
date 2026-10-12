#!/usr/bin/env python3
"""Original Orders startup + invalid-request compatibility, without Mongo/mock services."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import time
import urllib.error
import urllib.request

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--jar', required=True, type=Path)
    parser.add_argument('--agent', type=Path)
    parser.add_argument('--jdk', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    jar, jdk, out = args.jar.resolve(), args.jdk.resolve(), args.out.resolve()
    if args.agent:
        args.agent = args.agent.resolve()
        expected = json.loads((HERE / 'sources.json').read_text())['mirrortaint']['agent_sha256']
        if hashlib.sha256(args.agent.read_bytes()).hexdigest() != expected:
            raise ValueError('Unrecognized agent')
    out.mkdir(parents=True, exist_ok=False)
    home, tmp = out / 'agent-home', out / 'tmp'
    home.mkdir()
    tmp.mkdir()
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        port = s.getsockname()[1]
    libs = [str(p.parent) for name in ('libjli.so', 'libjvm.so', 'libjava.so') for p in jdk.rglob(name)]
    env = dict(os.environ, JAVA_HOME=str(jdk), LD_LIBRARY_PATH=':'.join(libs))
    cmd = [str(jdk / 'bin/java'), '-Xmx512m', '-Djava.io.tmpdir=' + str(tmp),
           '-Duser.home=' + str(home), '-Djava.security.egd=file:/dev/urandom']
    if args.agent:
        cmd += ['-Dtaint.env=remote', '-Dtaint.app=works.weave.socks',
                '-Dtaint.version=tf2-native-orders', '-javaagent:' + str(args.agent)]
    cmd += ['-jar', str(jar), '--server.address=127.0.0.1', '--server.port=' + str(port),
            '--spring.zipkin.enabled=false', '--http.timeout=1',
            '--spring.data.mongodb.uri=mongodb://127.0.0.1:27017/data?connectTimeoutMS=500&serverSelectionTimeoutMS=500']
    result = {'command': cmd, 'orders_jar_sha256': hashlib.sha256(jar.read_bytes()).hexdigest(),
              'mode': 'mirrortaint' if args.agent else 'plain',
              'status': 'failed', 'dependencies_available': False, 'positive_order_tested': False,
              'field_propagation_tested': False, 'cross_service_join_tested': False,
              'accuracy_eligible': False, 'performance_eligible': False}
    process = None
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with (out / 'service.log').open('w') as log:
            process = subprocess.Popen(cmd, env=env, stdout=log, stderr=subprocess.STDOUT)
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError('Original service exited during startup: ' + str(process.returncode))
                req = urllib.request.Request('http://127.0.0.1:' + str(port) + '/orders',
                    data=b'{}', method='POST', headers={'Content-Type': 'application/json',
                    'X-B3-TraceId': '0123456789abcdef', 'X-B3-SpanId': '1234567890abcdef', 'X-B3-Sampled': '1'})
                try:
                    with opener.open(req, timeout=5) as response:
                        status, body = response.status, response.read().decode()
                except urllib.error.HTTPError as exc:
                    status, body = exc.code, exc.read().decode()
                except (urllib.error.URLError, TimeoutError):
                    time.sleep(0.5)
                    continue
                result['http'] = {'request': {}, 'status': status, 'body': body,
                                  'trace_id_requested': '0123456789abcdef'}
                if status != 406 or 'Invalid order request' not in body:
                    raise RuntimeError('Unexpected response from original invalid-order branch')
                result['status'] = 'invalid-order-compatibility-passed'
                break
            else:
                raise RuntimeError('Original service startup timeout')
    except Exception as exc:
        result['error'] = str(exc)
    finally:
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        result['process_returncode'] = process.returncode if process else None
        result['agent_files'] = [{'path': str(p.relative_to(home)), 'bytes': p.stat().st_size}
                                 for p in sorted(home.rglob('*')) if p.is_file()]
        result['agent_error_logs_nonempty'] = [str(p.relative_to(home))
            for p in home.rglob('*error*.log') if p.is_file() and p.stat().st_size]
        (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    return int(result['status'] != 'invalid-order-compatibility-passed')


if __name__ == '__main__':
    raise SystemExit(main())
