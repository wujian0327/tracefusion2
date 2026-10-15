#!/usr/bin/env python3
"""Build the disclosed companion adapter against the fixed public agent; no core extraction."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from zipfile import ZipFile
from experiment_environment import java8_target

HERE = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--agent', required=True, type=Path)
parser.add_argument('--out', required=True, type=Path)
args = parser.parse_args()
agent = args.agent.resolve()
expected = json.loads((HERE / 'sources.json').read_text())['mirrortaint']['agent_sha256']
if hashlib.sha256(agent.read_bytes()).hexdigest() != expected:
    raise ValueError('Unrecognized original agent JAR')
out = args.out.resolve()
out.mkdir(parents=True, exist_ok=False)
sources = [HERE / 'MirrorTaintIntegrationAdapter.java', HERE / 'MirrorTaintThreadAdapter.java', HERE / 'MirrorTaintLogAdapter.java',
           HERE / 'MirrorTaintStreamAdapter.java']
cmd = [shutil.which('javac'), *java8_target()[1], '-cp', str(agent), '-d', str(out), *map(str, sources)]
completed = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
(out / 'compile.log').write_text(completed.stdout + completed.stderr)
if completed.returncode:
    raise RuntimeError('Adapter compilation failed')
jar = out / 'integration-adapter.jar'
with ZipFile(jar, 'w') as archive:
    archive.writestr('META-INF/MANIFEST.MF', 'Manifest-Version: 1.0\nPremain-Class: MirrorTaintIntegrationAdapter\n\n')
    for path in out.glob('MirrorTaint*Adapter*.class'):
        archive.write(path, path.name)
result = {'kind': 'integration-adapter-build', 'original_agent_sha256': expected,
          'source_sha256': {source.name: hashlib.sha256(source.read_bytes()).hexdigest() for source in sources},
          'adapter_sha256': hashlib.sha256(jar.read_bytes()).hexdigest(), 'compile_command': cmd}
for source in sources:
    shutil.copyfile(source, out / source.name)
(out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
