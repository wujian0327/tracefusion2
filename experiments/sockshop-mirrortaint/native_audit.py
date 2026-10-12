#!/usr/bin/env python3
"""Load the pinned public agent and audit its bytecode; no accuracy experiment."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import zipfile

HERE = Path(__file__).resolve().parent


def constants(data):
    """Read UTF-8 constant-pool entries, without executing the JAR."""
    if data[:4] != b'\xca\xfe\xba\xbe':
        raise ValueError('Not a JVM class')
    count = struct.unpack_from('>H', data, 8)[0]
    pos, entry, strings = 10, 1, []
    sizes = {3: 4, 4: 4, 5: 8, 6: 8, 7: 2, 8: 2, 9: 4, 10: 4,
             11: 4, 12: 4, 15: 3, 16: 2, 17: 4, 18: 4, 19: 2, 20: 2}
    while entry < count:
        tag = data[pos]
        pos += 1
        if tag == 1:
            size = struct.unpack_from('>H', data, pos)[0]
            pos += 2
            strings.append(data[pos:pos + size].decode('utf-8', 'replace'))
            pos += size
        else:
            pos += sizes[tag]
            entry += int(tag in (5, 6))
        entry += 1
    return strings


def audit(agent, jdk, out):
    pinned = json.loads((HERE / 'sources.json').read_text())['mirrortaint']
    digest = hashlib.sha256(agent.read_bytes()).hexdigest()
    if digest != pinned['agent_sha256']:
        raise ValueError('Unrecognized agent SHA-256; do not silently change baseline')
    out.mkdir(parents=True, exist_ok=False)
    home, tmp = out / 'agent-home', out / 'tmp'
    home.mkdir()
    tmp.mkdir()
    libs = [str(p.parent) for name in ('libjli.so', 'libjvm.so', 'libjava.so')
            for p in jdk.rglob(name)]
    env = dict(os.environ, JAVA_HOME=str(jdk),
               LD_LIBRARY_PATH=':'.join(libs + [os.environ.get('LD_LIBRARY_PATH', '')]))
    cmd = [str(jdk / 'bin/java'), '-Xmx256m', '-Djava.io.tmpdir=' + str(tmp),
           '-Duser.home=' + str(home), '-Dtaint.env=remote',
           '-Dtaint.app=works.weave.socks', '-Dtaint.version=tf2-preflight',
           '-javaagent:' + str(agent), '-version']
    loaded = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=30)
    (out / 'agent-load.log').write_text(loaded.stdout + loaded.stderr)
    trace_constants = {}
    with zipfile.ZipFile(agent) as archive:
        manifest = archive.read('META-INF/MANIFEST.MF').decode()
        for name in archive.namelist():
            if not name.startswith('com/shadow/') or not name.endswith('.class'):
                continue
            relevant = [s for s in constants(archive.read(name)) if any(
                term.lower() in s.lower() for term in
                ('Sleuth', 'Tracer', 'getTrace', 'MDC', 'trace.id', 'hhmmss', 'resttemplate'))]
            if relevant:
                trace_constants[name] = relevant
    (out / 'manifest.txt').write_text(manifest)
    (out / 'trace-constants.json').write_text(json.dumps(trace_constants, indent=2) + '\n')
    bytecode = {}
    for label, cls in [('config', 'com.shadow.taint.agent.A.A'),
                       ('collector', 'com.shadow.taint.agent.runtime.TaintCollector')]:
        result = subprocess.run([str(jdk / 'bin/javap'), '-classpath', str(agent),
                                 '-c', '-p', cls], env=env, capture_output=True,
                                text=True, timeout=30)
        (out / (label + '-javap.txt')).write_text(result.stdout + result.stderr)
        bytecode[label] = {'returncode': result.returncode,
                           'sha256': hashlib.sha256(result.stdout.encode()).hexdigest()}
    result = {'agent_sha256': digest, 'command': cmd, 'returncode': loaded.returncode,
              'premain_invoked': 'Premain invoked' in loaded.stdout,
              'files_created': [str(p.relative_to(home)) for p in sorted(home.rglob('*')) if p.is_file()],
              'javap': bytecode, 'application_executed': False,
              'field_propagation_tested': False, 'cross_service_join_tested': False,
              'accuracy_eligible': False, 'performance_eligible': False}
    (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--agent', required=True, type=Path)
    parser.add_argument('--jdk', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    result = audit(args.agent.resolve(), args.jdk.resolve(), args.out.resolve())
    print(json.dumps(result, indent=2))
    return int(result['returncode'] != 0 or not result['premain_invoked'])


if __name__ == '__main__':
    raise SystemExit(main())
