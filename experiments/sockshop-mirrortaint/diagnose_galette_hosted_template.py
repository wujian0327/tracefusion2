"""Reproduce official artifacts and inspect the caller-sensitive template."""
import argparse, subprocess, json
from pathlib import Path
from zipfile import ZipFile
from run_planned_service import ROOT, HERE, load, save, sha

H = ROOT/'artifacts/galette-compatibility-selection-20261111'
OLD = ROOT/'artifacts/galette-static-baselines-20261111'


def command(cmd, out):
    out.mkdir(parents=True, exist_ok=False)
    cmd = list(map(str, cmd))
    save(out/'command.json', cmd)
    p = subprocess.run(list(map(str, cmd)), capture_output=True, text=True)
    (out/'stdout.log').write_text(p.stdout); (out/'stderr.log').write_text(p.stderr)
    save(out/'result.json', {'returncode': p.returncode})
    return p


def run(out):
    out.mkdir(parents=True, exist_ok=False)
    protocol = load(H/'protocol-before-revisions.json')
    for path, digest in protocol['core_sources'].items(): assert sha(Path(path)) == digest
    base = OLD/'runtime-base/java-8-openjdk-amd64'
    inst = OLD/'jdk8-galette'
    agent = OLD/'galette-original/galette-agent/target/galette-agent-1.0.0-SNAPSHOT.jar'
    for path, fact in protocol['tool_receipt']['files'].items(): assert sha(Path(path)) == fact['sha256']
    classes = out/'classes'; classes.mkdir()
    compile = command([base/'bin/javac', '-cp', agent, '-d', classes,
        HERE/'GaletteCallerSensitiveProbe.java', HERE/'GaletteTemplateAnalysis.java'], out/'compile')
    assert compile.returncode == 0
    original = command([base/'bin/java', '-verbose:class', '-cp', classes,
                        'GaletteCallerSensitiveProbe'], out/'original')
    galette = command([inst/'bin/java', '-verbose:class', '-Xbootclasspath/a:'+str(agent),
                       '-javaagent:'+str(agent), '-cp', classes, 'GaletteCallerSensitiveProbe'], out/'galette')
    assert original.returncode == 0 and galette.returncode != 0 and 'VerifyError' in galette.stderr
    names = ['java/lang/invoke/MethodHandleImpl$BindCaller$T.class',
             'java/lang/invoke/MethodHandleImpl$BindCaller.class']
    for label, jdk in [('original', base), ('instrumented', inst)]:
        for name in names:
            dest = out/'bytecode'/label/name
            dest.parent.mkdir(parents=True, exist_ok=True)
            with ZipFile(jdk/'jre/lib/rt.jar') as z: dest.write_bytes(z.read(name))
            dis = command([base/'bin/javap', '-p', '-c', '-v', dest], out/('javap-'+label+'-'+Path(name).stem))
            assert dis.returncode == 0
    raw = out/'bytecode/original'/names[0]
    transformed = out/'context-transforms'; transformed.mkdir()
    result = command([base/'bin/java', '-cp', str(classes)+':'+str(agent),
                      'GaletteTemplateAnalysis', raw, transformed], out/'transform')
    assert result.returncode == 0
    for path in transformed.glob('*.class'):
        command([base/'bin/javap', '-p', '-c', '-v', path], out/('javap-'+path.stem))
    save(out/'receipt.json', {'original_succeeded': True, 'official_failed': True,
        'original_commands_and_loaded_class_origins_retained': True,
        'TF_core_unchanged': True, 'files': {str(p): sha(p) for p in [agent, base/'bin/java', inst/'bin/java', base/'jre/lib/rt.jar', inst/'jre/lib/rt.jar', HERE/'GaletteCallerSensitiveProbe.java']},
        'bytecode_files': {str(p.relative_to(out)): sha(p) for p in out.rglob('*.class')},
        'already_instrumented_hosted_transform_returns_null': 'true' in result.stdout})


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--out', type=Path, required=True)
    run(p.parse_args().out.resolve())
