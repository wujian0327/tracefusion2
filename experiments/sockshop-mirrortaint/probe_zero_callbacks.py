#!/usr/bin/env python3
"""Execute actual Orders bytecode in Java 8 and reject a omitted zero-return callback."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from zipfile import ZipFile
from service_model import derive
from infer_service_sources import infer

HERE = Path(__file__).resolve().parent
IMAGE = 'weaveworksdemos/orders@sha256:b622e40e83433baf6374f15e076b53893f79958640fc6667dff597622eff03b9'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--app-jar', type=Path, required=True)
parser.add_argument('--frontend', type=Path, required=True)
parser.add_argument('--reference-model', type=Path, required=True)
parser.add_argument('--out', type=Path, required=True)
args = parser.parse_args()
out = args.out.resolve()
out.mkdir(parents=True, exist_ok=False)
classes, libs, capture = out / 'classes', out / 'libs', out / 'capture'
classes.mkdir(); libs.mkdir(); capture.mkdir(); capture.chmod(0o777)
model = json.loads(args.reference_model.read_text())
with ZipFile(args.app_jar) as archive:
    for owner, sha in model['class_sha256'].items():
        if hashlib.sha256(archive.read('BOOT-INF/classes/' + owner + '.class')).hexdigest() != sha:
            raise ValueError('Original application class differs from reference model')
    for name in archive.namelist():
        if name.startswith('BOOT-INF/classes/') and name.endswith('.class'):
            file = classes / name.removeprefix('BOOT-INF/classes/')
        elif name.startswith('BOOT-INF/lib/') and name.endswith('.jar'):
            file = libs / Path(name).name
        else:
            continue
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(archive.read(name))
source = HERE / 'ZeroCallbackDriver.java'
shutil.copyfile(source, out / source.name)
classpath = str(classes) + ':' + str(libs / '*')
compiled = subprocess.run(['javac', '--release', '8', '-cp', classpath, '-d', str(classes), str(source)],
                          capture_output=True, text=True, timeout=30)
(out / 'compile.log').write_text(compiled.stdout + compiled.stderr)
compiled.check_returncode()
commands, results = [], []
for observed in (False, True):
    command = ['docker', 'run', '--rm', '--network', 'none', '--platform', 'linux/amd64', '--entrypoint', 'java',
               '-v', str(out) + ':/probe:rw', '-v', str(args.frontend.resolve()) + ':/frontend.jar:ro', IMAGE,
               '-Xverify:all']
    if observed:
        command += ['-javaagent:/frontend.jar', '-Dtracefusion.service.output=/probe/capture']
    command += ['-cp', '/probe/classes:/probe/libs/*', 'ZeroCallbackDriver']
    result = subprocess.run(command, capture_output=True, text=True, timeout=45)
    (out / ('observed.log' if observed else 'native.log')).write_text(result.stdout + result.stderr)
    result.check_returncode()
    commands.append(command)
    results.append(next(line for line in result.stdout.splitlines() if line.startswith('TF2_ZERO_CONTROL_RESULT ')))
if results[0] != results[1]:
    raise ValueError('Frontend changed actual calculation output')
supporting = []
for owner in model['class_sha256']:
    file = capture / (owner.replace('/', '_') + '.original.class')
    if not file.exists():
        file.write_bytes((classes / (owner + '.class')).read_bytes())
        supporting.append(owner)
derived, _ = derive(capture)
assert derived == model
baseline = infer(capture, model)
rows = [json.loads(line) for line in (capture / 'events.jsonl').read_text().splitlines()]
callbacks = [e for e in rows if e['kind'] == 'enter' and e['method'] == model['mapper_method']]
returns = {e['frame']: e['result']['value'] for e in rows if e['kind'] == 'exit'}
zero = [e for e in callbacks if returns[e['frame']] == 0]
assert len(callbacks) == 2 and len(zero) == 1
damaged = out / 'omitted-zero-callback'
damaged.mkdir()
for f in capture.glob('*.original.class'):
    shutil.copyfile(f, damaged / f.name)
missing_frame = zero[0]['frame']
filtered = [copy.deepcopy(e) for e in rows if e.get('frame') != missing_frame]
for index, e in enumerate(filtered, 1):
    e['seq'] = index
(damaged / 'events.jsonl').write_text(''.join(json.dumps(e) + '\n' for e in filtered))
try:
    infer(damaged, model)
except ValueError as error:
    rejection = str(error)
else:
    raise AssertionError('Missing zero callback accepted')
assert 'callback coverage' in rejection
report = {'kind': 'original-Orders-zero-callback-control', 'passed': True, 'callback_count': len(callbacks),
          'zero_callback_count': len(zero), 'native_and_observed_output': results[0],
          'missing_zero_callback_rejected': rejection, 'omitted_callback_numeric_contribution': 0,
          'application_jar_sha256': hashlib.sha256(args.app_jar.read_bytes()).hexdigest(),
          'frontend_sha256': hashlib.sha256(args.frontend.read_bytes()).hexdigest(),
          'runtime_image': IMAGE, 'commands': commands, 'supporting_unloaded_class_proofs': supporting,
          'business_workload_run': False, 'field_accuracy_scored': False,
          'scope': 'Actual original scalar calculation only; no HTTP source labels or order queries in this supplementary probe'}
(out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({k: v for k, v in report.items() if k != 'commands'}, indent=2))
