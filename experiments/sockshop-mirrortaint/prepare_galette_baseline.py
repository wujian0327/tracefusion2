"""Reproducible official build/JDK instrumentation, separate from business costs.

Requires the pinned official clone. Each stage writes a fresh output directory;
the original tool sources and application JARs are never patched.
"""
import argparse, os, subprocess, time, resource
from pathlib import Path
from run_planned_service import ROOT, load, save, sha
from seal_galette_static_baselines import H


def command(cmd, out, cwd=None):
    save(out/'command.json', cmd)
    start = time.perf_counter(); before = resource.getrusage(resource.RUSAGE_CHILDREN)
    with (out/'command.log').open('w') as log:
        p = subprocess.run(cmd, cwd=cwd, stdout=log, stderr=subprocess.STDOUT)
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    save(out/'process.json', {'returncode': p.returncode, 'wall_seconds': time.perf_counter()-start,
                             'client_process_cpu_seconds': after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime,
                             'client_cpu_is_not_container_build_CPU': True})
    if p.returncode:
        raise RuntimeError('Failure preserved: '+str(out))


def run(home, stage, out):
    out.mkdir(parents=True, exist_ok=False)
    source = home/'galette-original'
    pin = load(home/'protocol-before-calibration.json')['galette_commit']
    assert subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip() == pin
    assert not subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain'], text=True)
    if stage == 'build':
        image = load(home/'build-image.json')[0]['Id']
        (source/'.build-tmp').mkdir(exist_ok=True)
        cmd = ['docker', 'run', '--rm', '-e', 'JAVA_TOOL_OPTIONS=-Djava.io.tmpdir=/work/.build-tmp',
               '-v', str(source)+':/work', '-v', str(home/'maven-cache')+':/root/.m2/repository',
               '-v', str(ROOT/'artifacts/target-closure-revision-20261103/maven-settings.xml')+':/root/.m2/settings.xml:ro',
               '-w', '/work', image, 'mvn', '-B', '-DskipTests', 'install']
        command(cmd, out)
        subprocess.run(['docker', 'run', '--rm', '-v', str(source)+':/work', image,
                        'chown', '-R', str(os.getuid())+':'+str(os.getgid()), '/work'], check=True)
    elif stage == 'instrument':
        base = home/'runtime-base/java-8-openjdk-amd64'
        instrument = source/'galette-instrument/target/galette-instrument-1.0.0-SNAPSHOT.jar'
        save(out/'input-hashes.json', {'instrument_jar': sha(instrument), 'base_java': sha(base/'bin/java'),
                                     'base_rt_jar': sha(base/'jre/lib/rt.jar')})
        command(['/usr/bin/time', '-v', str(base/'bin/java'), '-Xmx2g', '-XX:ActiveProcessorCount=2',
                 '-Dgalette.instrument.verbose=true', '-jar', str(instrument), str(base), str(out/'jdk')], out)
    else:
        raise ValueError(stage)


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--home', type=Path, default=H)
    p.add_argument('--stage', choices=('build', 'instrument'), required=True); p.add_argument('--out', type=Path, required=True)
    a = p.parse_args(); run(a.home.resolve(), a.stage, a.out.resolve())
