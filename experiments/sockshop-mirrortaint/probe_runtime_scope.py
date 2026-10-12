#!/usr/bin/env python3
"""Diagnose original public-JAR ThreadLocal scope; not the Sock Shop workload."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--agent', required=True, type=Path)
    parser.add_argument('--jdk', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    agent, jdk, out = args.agent.resolve(), args.jdk.resolve(), args.out.resolve()
    digest = hashlib.sha256(agent.read_bytes()).hexdigest()
    expected = json.loads((HERE / 'sources.json').read_text())['mirrortaint']['agent_sha256']
    if digest != expected:
        raise ValueError('Unrecognized agent JAR')
    out.mkdir(parents=True, exist_ok=False)
    tmp = out / 'tmp'
    tmp.mkdir()
    source = HERE / 'RuntimeScopeProbe.java'
    env = dict(os.environ, JAVA_HOME=str(jdk), LD_LIBRARY_PATH=':'.join(
        str(p.parent) for name in ('libjli.so', 'libjvm.so', 'libjava.so') for p in jdk.rglob(name)))
    compile_cmd = [str(jdk / 'bin/javac'), '-J-Xmx128m', '-J-Djava.io.tmpdir=' + str(tmp),
                   '-classpath', str(agent), '-d', str(out), str(source)]
    compiled = subprocess.run(compile_cmd, env=env, text=True, capture_output=True, timeout=30)
    (out / 'compile.log').write_text(compiled.stdout + compiled.stderr)
    if compiled.returncode:
        raise RuntimeError('Scope probe compilation failed')
    cmd = [str(jdk / 'bin/java'), '-Xmx128m', '-Djava.io.tmpdir=' + str(tmp),
           '-classpath', str(agent) + os.pathsep + str(out), 'RuntimeScopeProbe']
    executed = subprocess.run(cmd, env=env, text=True, capture_output=True, timeout=30)
    (out / 'runtime.log').write_text(executed.stdout + executed.stderr)
    result = {'kind': 'controlled-runtime-scope-diagnostic', 'agent_sha256': digest,
              'probe_source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
              'compile_command': compile_cmd, 'run_command': cmd, 'returncode': executed.returncode,
              'business_workload_run': False, 'adapter_installed': False,
              'cross_service_join_tested': False, 'accuracy_eligible': False,
              'performance_eligible': False}
    if executed.returncode == 0:
        result['observed'] = json.loads(executed.stdout.strip())
    (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    return int(executed.returncode != 0)


if __name__ == '__main__':
    raise SystemExit(main())
