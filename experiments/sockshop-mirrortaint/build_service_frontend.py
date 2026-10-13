#!/usr/bin/env python3
"""Build the independent Java 8 DTO/stream observation frontend, pinned ASM 9.7.1."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import urllib.request
from zipfile import ZipFile, ZIP_DEFLATED

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DEPS = {'asm': '8cadd43ac5eb6d09de05faecca38b917a040bb9139c7edeb4cc81c740b713281',
        'asm-tree': '9929881f59eb6b840e86d54570c77b59ce721d104e6dfd7a40978991c2d3b41f'}
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--out', type=Path, required=True)
args = parser.parse_args()
out = args.out.resolve()
out.mkdir(parents=True, exist_ok=False)
cache = ROOT / 'artifacts/java-collection-deps'
cache.mkdir(exist_ok=True)
jars = []
for name, sha in DEPS.items():
    jar = cache / (name + '-9.7.1.jar')
    if not jar.exists():
        with urllib.request.urlopen('https://repo.maven.apache.org/maven2/org/ow2/asm/' + name + '/9.7.1/' + jar.name, timeout=30) as response:
            data = response.read(2000000)
        if hashlib.sha256(data).hexdigest() != sha:
            raise ValueError('Dependency hash mismatch')
        jar.write_bytes(data)
    if hashlib.sha256(jar.read_bytes()).hexdigest() != sha:
        raise ValueError('Dependency hash mismatch')
    jars.append(jar)
classes = out / 'classes'
classes.mkdir()
sources = sorted((HERE / 'tracefusion').glob('*.java'))
command = ['javac', '--release', '8', '-cp', ':'.join(map(str, jars)), '-d', str(classes), *map(str, sources)]
compiled = subprocess.run(command, capture_output=True, text=True, timeout=30)
(out / 'compile.log').write_text(compiled.stdout + compiled.stderr)
if compiled.returncode:
    raise RuntimeError('Frontend compilation failed')
agent = out / 'tracefusion-service-agent.jar'
with ZipFile(agent, 'w', ZIP_DEFLATED) as archive:
    archive.writestr('META-INF/MANIFEST.MF', 'Manifest-Version: 1.0\nPremain-Class: tracefusion.service.ServiceAgent\n\n')
    for f in classes.rglob('*.class'):
        archive.write(f, f.relative_to(classes))
    for jar in jars:
        with ZipFile(jar) as dependency:
            for name in dependency.namelist():
                if name.startswith('org/objectweb/asm/') and name.endswith('.class'):
                    archive.writestr(name, dependency.read(name))
for f in sources:
    shutil.copyfile(f, out / f.name)
(out / 'result.json').write_text(json.dumps({'kind': 'tracefusion-service-frontend-build',
    'agent_sha256': hashlib.sha256(agent.read_bytes()).hexdigest(), 'dependencies': DEPS,
    'source_sha256': {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in sources},
    'compile_command': command}, indent=2) + '\n')
print(agent)
