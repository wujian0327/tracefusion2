#!/usr/bin/env python3
"""Build independent Spring HTTP boundary observer against pinned bundled libraries."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from zipfile import ZipFile

HERE = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--agent', type=Path, required=True)
parser.add_argument('--out', type=Path, required=True)
parser.add_argument('--deployment', type=Path, help='Prepare companion compose override for this existing adapted deployment')
args = parser.parse_args()
expected = json.loads((HERE / 'sources.json').read_text())['mirrortaint']['agent_sha256']
if hashlib.sha256(args.agent.read_bytes()).hexdigest() != expected:
    raise ValueError('Unknown dependency JAR')
out = args.out.resolve()
out.mkdir(parents=True, exist_ok=False)
source = HERE / 'HttpServerBoundaryObserver.java'
command = ['javac', '--release', '8', '-cp', str(args.agent.resolve()), '-d', str(out), str(source)]
compiled = subprocess.run(command, capture_output=True, text=True, timeout=30)
(out / 'compile.log').write_text(compiled.stdout + compiled.stderr)
if compiled.returncode:
    raise RuntimeError('Observer compilation failed')
jar = out / 'http-observer.jar'
with ZipFile(jar, 'w') as archive:
    archive.writestr('META-INF/MANIFEST.MF', 'Manifest-Version: 1.0\nPremain-Class: HttpServerBoundaryObserver\n\n')
    for f in out.glob('HttpServerBoundaryObserver*.class'):
        archive.write(f, f.name)
shutil.copyfile(source, out / source.name)
(out / 'result.json').write_text(json.dumps({'original_agent_sha256': expected,
    'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(), 'observer_sha256': hashlib.sha256(jar.read_bytes()).hexdigest(),
    'compile_command': command}, indent=2) + '\n')
if args.deployment:
    spec = json.loads((args.deployment / 'compose.lock.json').read_text())
    override = {'services': {}}
    for name in ('carts', 'shipping'):
        logs = out / 'server-logs' / name
        logs.mkdir(parents=True)
        logs.chmod(0o777)
        override['services'][name] = {'volumes': [str(jar) + ':/tf2/http-observer.jar:ro',
            str(logs) + ':/tf2/server-observation:rw'], 'environment': {'JAVA_OPTS':
            spec['services'][name]['environment']['JAVA_OPTS'] +
            ' -javaagent:/tf2/http-observer.jar -Dtf2.http.observer.log=/tf2/server-observation/server-events.jsonl'}}
    (out / 'compose.observer.json').write_text(json.dumps(override, indent=2) + '\n')
print(jar)
