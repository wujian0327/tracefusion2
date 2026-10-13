#!/usr/bin/env python3
"""Add disclosed Spring clock/hooks configuration to copies of original Boot JARs.

Verify every original business class and nested dependency remains byte-identical.
Only add configuration and the unmodified author runtime JAR; never edit inputs.
"""
import argparse
import hashlib
from pathlib import Path
import subprocess
from zipfile import ZipFile, ZIP_DEFLATED, ZIP_STORED

import flowdist_preflight as tool


def build(repo, orders, shipping, out):
    tool.verify_repository(repo)
    out.mkdir(parents=True, exist_ok=False)
    here = Path(__file__).parent
    evidence = {}
    for role, original in (('orders', orders), ('shipping', shipping)):
        folder = out / role
        folder.mkdir()
        libs = folder / 'lib'
        libs.mkdir()
        with ZipFile(original) as archive:
            for name in archive.namelist():
                if name.startswith('BOOT-INF/lib/') and name.endswith('.jar'):
                    (libs / Path(name).name).write_bytes(archive.read(name))
        sources = folder / 'sources'
        sources.mkdir()
        text = (here / 'FlowDistHttpConfiguration.java').read_text()
        # Handler dispatch monitoring in the earlier probe is replaced by real
        # Spring method advice; never emit duplicate postShipping enter events.
        start = text.index('    @Override public void addInterceptors')
        end = text.index('    @Bean public FilterRegistrationBean', start)
        text = text[:start] + text[end:]
        config = sources / 'FlowDistHttpConfiguration.java'
        config.write_text('package disttaint.http;\n' + text)
        app_config = sources / 'FlowDistServiceConfiguration.java'
        app_config.write_text('package works.weave.socks.' + role + '.config;\n'
            '@org.springframework.context.annotation.Configuration\n'
            'public class FlowDistServiceConfiguration extends disttaint.http.FlowDistHttpConfiguration {\n'
            ' public FlowDistServiceConfiguration() { disttaint.http.FlowDistSpringHooks.initialize(); }\n'
            ' @org.springframework.context.annotation.Bean public static disttaint.http.FlowDistSpringHooks flowDistSpringHooks() {\n'
            '  return new disttaint.http.FlowDistSpringHooks();\n }\n}\n')
        java = [config, app_config, here / 'flowdist/FlowDistHttpClock.java', here / 'flowdist/FlowDistSpringHooks.java']
        classes = folder / 'classes'
        classes.mkdir()
        command = ['javac', '--release', '8', '-cp', ':'.join(map(str, [repo / 'tool/FLOWDIST.jar', *sorted(libs.glob('*.jar'))])),
            '-d', str(classes), *map(str, java)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        (folder / 'compile.log').write_text(result.stdout + result.stderr)
        if result.returncode:
            raise ValueError('Spring adapter compilation failed: ' + role)
        output = out / (role + '-flowdist.jar')
        additions = {}
        with ZipFile(original) as source, ZipFile(output, 'w', ZIP_DEFLATED) as target:
            for item in source.infolist():
                target.writestr(item, source.read(item.filename))
            for file in sorted(classes.rglob('*.class')):
                name = 'BOOT-INF/classes/' + str(file.relative_to(classes))
                if name in source.namelist(): raise ValueError('Refusing to replace business class')
                data = file.read_bytes()
                target.writestr(name, data, compress_type=ZIP_STORED)
                additions[name] = hashlib.sha256(data).hexdigest()
            # FLOWDIST.jar contains OTMonitor and its original stream classes.
            for runtime in ('FLOWDIST.jar', 'DUA1.jar'):
                name = 'BOOT-INF/lib/flowdist-original-' + runtime
                data = (repo / 'tool' / runtime).read_bytes()
                target.writestr(name, data, compress_type=ZIP_STORED)
                additions[name] = hashlib.sha256(data).hexdigest()
        with ZipFile(original) as source, ZipFile(output) as target:
            if any(source.read(name) != target.read(name) for name in source.namelist()):
                raise ValueError('Original JAR entry changed')
            if any(item.compress_type != ZIP_STORED for item in target.infolist()
                   if item.filename.startswith('BOOT-INF/lib/') and item.filename.endswith('.jar')):
                raise ValueError('Spring Boot nested JAR must be stored without compression')
        evidence[role] = {'original_sha256': hashlib.sha256(original.read_bytes()).hexdigest(),
            'adapted_sha256': hashlib.sha256(output.read_bytes()).hexdigest(), 'added_entries': additions,
            'original_entries_preserved': True, 'compile_command': command}
    tool.save(out / 'manifest.json', {'kind': 'sockshop-spring-flowdist-boundary-runtime', 'upstream_commit': tool.COMMIT,
        'source_sha256': {str(f.relative_to(here)): hashlib.sha256(f.read_bytes()).hexdigest() for f in
            (here / 'FlowDistHttpConfiguration.java', here / 'flowdist/FlowDistHttpClock.java', here / 'flowdist/FlowDistSpringHooks.java')},
        'apps': evidence, 'method_instrumentation': 'Spring advice for newOrder/postResource/postShipping; entry only',
        'static_statement_instrumentation': False, 'original_business_classes_modified': False,
        'accuracy_eligible': False, 'performance_eligible': False})


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for flag in ('repo', 'orders', 'shipping', 'out'): p.add_argument('--' + flag, type=Path, required=True)
    a = p.parse_args()
    build(a.repo.resolve(), a.orders.resolve(), a.shipping.resolve(), a.out.resolve())
