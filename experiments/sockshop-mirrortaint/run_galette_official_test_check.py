"""Repeat the pinned upstream integration tests in a fresh output tree.

Uses the archived build image and separately installed official/modified Maven
artifacts. No upstream tests, exclusions or VM verification options are edited.
"""
import argparse
import shutil
import subprocess
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

from diagnose_galette_hosted_template import H, OLD
from run_planned_service import ROOT, HERE, save, sha


def run(out, variant, suite):
    out.mkdir(parents=True, exist_ok=False)
    source = out / 'source'
    subprocess.run(['git', 'clone', '--no-hardlinks', str(H / 'official-fixed'), str(source)], check=True,
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if variant == 'modified':
        subprocess.run(['git', '-C', str(source), 'apply', str(HERE / 'galette-hosted-template-built-20261111.patch')], check=True)
    (source / '.build-tmp').mkdir()
    cache = out / 'maven-cache'
    shutil.copytree(H / ('modified-maven-cache' if variant == 'modified' else 'maven-cache'), cache)
    agent = OLD / 'galette-original/galette-agent/target/galette-agent-1.0.0-SNAPSHOT.jar'
    cmd = ['docker', 'run', '--rm', '-e', 'JAVA_HOME=/approved-jdk',
           '-e', 'PATH=/approved-jdk/bin:/usr/share/maven/bin:/usr/bin:/bin',
           '-e', 'JAVA_TOOL_OPTIONS=-Djava.io.tmpdir=/work/.build-tmp',
           '-v', str(source) + ':/work', '-v', str(cache) + ':/root/.m2/repository',
           '-v', str(ROOT / 'artifacts/target-closure-revision-20261103/maven-settings.xml') + ':/root/.m2/settings.xml:ro',
           '-v', str(OLD / 'runtime-base/java-8-openjdk-amd64') + ':/approved-jdk:ro',
           '-v', '/etc/java-8-openjdk:/etc/java-8-openjdk:ro',
           '-v', '/etc/ssl/certs/java/cacerts:/etc/ssl/certs/java/cacerts:ro',
           '-v', str(agent) + ':/official-agent.jar:ro', '-w', '/work',
           'sha256:0f909120a5780e04d8cb0aa2f4bd04de2579ff60528719ffb09e3611423534fb',
           'mvn', '-B', '-pl', ':galette-integration-tests', '-Dgalette.agentJar=/official-agent.jar']
    if suite == 'related':
        cmd.append('-Dit.test=MethodHandleITCase,MethodReflectionITCase,ClassReflectionITCase')
    cmd.append('verify')
    save(out / 'command.json', cmd)
    with (out / 'maven.log').open('w') as f:
        result = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT)
    reports = out / 'reports'
    reports.mkdir()
    counts = Counter(suites=0, tests=0, failures=0, errors=0, skipped=0)
    for p in source.rglob('failsafe-reports/TEST-*.xml'):
        shutil.copy2(p, reports / p.name)
        xml = ET.parse(p).getroot()
        counts['suites'] += 1
        for k in ('tests', 'failures', 'errors', 'skipped'):
            counts[k] += int(xml.attrib.get(k, 0))
    counts['passed'] = counts['tests'] - counts['failures'] - counts['errors'] - counts['skipped']
    save(out / 'result.json', {'variant': variant, 'returncode': result.returncode,
                             'official_Agent_sha256': sha(agent), 'counts': dict(counts),
                             'propagation_Agent_changed': False, 'VM_verification_disabled': False})
    assert result.returncode == 0


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--variant', choices=('official', 'modified'), required=True)
    p.add_argument('--suite', choices=('related', 'full'), default='full')
    a = p.parse_args()
    run(a.out.resolve(), a.variant, a.suite)
