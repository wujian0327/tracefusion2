#!/usr/bin/env python3
"""Fetch, verify and build pinned external baselines (Python standard library only)."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shlex
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from zipfile import ZipFile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
LOCK = json.loads((HERE / 'tools.lock.json').read_text())
DEFAULT_CACHE = ROOT / 'artifacts/external-tools'


def load(path):
    return json.loads(path.read_text())


def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def command(args, *, cwd=None, log=None, timeout=300, env=None):
    result = subprocess.run(list(map(str, args)), cwd=cwd, capture_output=True, text=True, timeout=timeout, env=env)
    if log:
        log.write_text(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError(f'{args[0]} exited {result.returncode}: ' + (result.stdout + result.stderr)[-4000:])
    return result.stdout


def download(url, dest, expected):
    """Never replace an existing destination with unchecked download bytes."""
    if dest.exists():
        require(sha(dest) == expected, f'Checksum mismatch: {dest}')
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='baseline-download-', dir=dest.parent) as temp:
        pending = Path(temp) / 'download'
        request = urllib.request.Request(url, headers={'User-Agent': 'TraceFusion-baseline-reproduction'})
        with urllib.request.urlopen(request, timeout=90) as response, pending.open('wb') as stream:
            shutil.copyfileobj(response, stream)
        require(sha(pending) == expected, f'Download checksum mismatch: {url}')
        pending.replace(dest)


def unpack_source(archive, dest):
    """Drop one GitHub archive prefix, rejecting links and paths escaping it."""
    with ZipFile(archive) as z:
        members = z.infolist()
        require(len(members) <= 20000 and sum(m.file_size for m in members) <= 512 * 1024**2, 'Source archive too large')
        prefixes = set()
        outputs = []
        for member in members:
            p = PurePosixPath(member.filename)
            require(not p.is_absolute() and '..' not in p.parts and '\\' not in member.filename, 'Unsafe archive path')
            require((member.external_attr >> 16) & 0o170000 != 0o120000, 'Archive symlink is not accepted')
            require(p.parts, 'Empty archive path')
            prefixes.add(p.parts[0])
            if len(p.parts) > 1 and not member.is_dir():
                outputs.append((member, dest.joinpath(*p.parts[1:])))
        require(len(prefixes) == 1, 'Expected one upstream archive root')
        for member, path in outputs:
            path.parent.mkdir(parents=True, exist_ok=True)
            with z.open(member) as src, path.open('wb') as stream:
                shutil.copyfileobj(src, stream)


def verify_source(tool):
    hashes = load(HERE / LOCK['tools']['phosphor']['source_hashes'])
    actual = {str(p.relative_to(tool / 'source')) for p in (tool / 'source').rglob('*.java')}
    require(actual == {p for p in hashes if p.endswith('.java')}, 'Phosphor Java source inventory differs')
    for name, expected in hashes.items():
        require(sha(tool / 'source' / name) == expected, 'Upstream source changed: ' + name)
    return hashes


def verify(name, path, built=False):
    spec = LOCK['tools'][name]
    if name == 'mirrortaint':
        require(sha(path / spec['artifact']) == spec['sha256'], 'MirrorTaint JAR differs')
    elif name == 'flowdist':
        require(command(['git', 'rev-parse', 'HEAD'], cwd=path).strip() == spec['commit'], 'FlowDist commit differs')
        command(['git', 'diff', '--exit-code', 'HEAD', '--'], cwd=path)
        for file, expected in spec['artifacts'].items():
            require(sha(path / file) == expected, 'FlowDist artifact differs: ' + file)
    else:
        verify_source(path)
        if built:
            manifest = load(path / 'manifest.json')
            require(manifest['commit'] == spec['commit'], 'Phosphor build commit differs')
            require(sha(path / spec['artifact']) == manifest['compiled_jar_sha256'], 'Phosphor built JAR differs')
            require(manifest['source_java_sha256'] == {k:v for k,v in verify_source(path).items() if k.endswith('.java')}, 'Build source manifest differs')
    return True


def fetch(name, cache, source=None):
    spec = LOCK['tools'][name]
    dest = cache / spec['cache']
    if dest.exists():
        verify(name, dest)
        print(f'{name}: verified existing {dest}')
        return dest
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=name + '-', dir=cache) as tmp:
        pending = Path(tmp) / 'tool'
        if source:
            verify(name, source)
            if name == 'flowdist':
                command(['git', 'clone', '--no-hardlinks', '--no-checkout', source, pending])
                command(['git', 'checkout', '--detach', spec['commit']], cwd=pending)
            elif name == 'mirrortaint':
                pending.mkdir();shutil.copyfile(source / spec['artifact'], pending / spec['artifact'])
            else:
                pending.mkdir();shutil.copytree(source / 'source', pending / 'source', ignore=shutil.ignore_patterns('target', '.git'))
                if (source / spec['artifact']).exists():
                    verify(name, source, built=True)
                    for file in (spec['artifact'], 'manifest.json'):
                        shutil.copyfile(source / file, pending / file)
        elif name == 'flowdist':
            pending.mkdir()
            command(['git', 'init', pending])
            command(['git', 'remote', 'add', 'origin', spec['repository']], cwd=pending)
            command(['git', 'fetch', '--depth=1', 'origin', spec['commit']], cwd=pending, timeout=600)
            command(['git', 'checkout', '--detach', 'FETCH_HEAD'], cwd=pending)
        elif name == 'mirrortaint':
            pending.mkdir();download(spec['url'], pending / spec['artifact'], spec['sha256'])
        else:
            pending.mkdir();archive = pending / 'source.zip'
            download(spec['url'], archive, spec['archive_sha256'])
            unpack_source(archive, pending / 'source')
        verify(name, pending)
        pending.rename(dest)
    print(f'{name}: prepared {dest}')
    return dest


def build_phosphor(cache, maven_repo=None):
    tool = cache / LOCK['tools']['phosphor']['cache']
    verify('phosphor', tool)
    if (tool / 'Phosphor-0.0.4.jar').exists():
        verify('phosphor', tool, built=True)
        print('Phosphor: existing built JAR verified');return
    require(shutil.which('mvn'), 'Maven is required; install Maven before building Phosphor')
    command(['docker', 'image', 'inspect', LOCK['java8_image']])
    source = tool / 'source/Phosphor'
    compiler = tool / 'java8-javac'
    repo = maven_repo or tool / 'm2'
    repo.mkdir(parents=True, exist_ok=True)
    args = ['docker', 'run', '--rm', '--network', 'none', '--user', f'{os.getuid()}:{os.getgid()}',
            '--entrypoint', '/usr/lib/jvm/java-1.8-openjdk/bin/javac', '-v', f'{tool}:{tool}:rw',
            '-v', f'{repo}:{repo}:ro', '-w', source, LOCK['java8_image']]
    compiler.write_text('#!/bin/sh\nexec ' + shlex.join(list(map(str, args))) + ' "$@"\n')
    compiler.chmod(0o755)
    args = ['mvn', '-B', '-f', source / 'pom.xml', f'-Dmaven.repo.local={repo}',
            '-Dmaven.compiler.fork=true', f'-Dmaven.compiler.executable={compiler}',
            '-DskipTests', *LOCK['maven_goals']]
    # Maven's forked-compiler @argument file must also be visible in the
    # compiler container; a host-only /tmp file would break a fresh build.
    temporary=tool/'compiler-tmp';temporary.mkdir(exist_ok=True)
    environment=dict(os.environ,MAVEN_OPTS='-Xmx512m '+shlex.quote('-Djava.io.tmpdir='+str(temporary)))
    command(args, cwd=source, log=tool / 'build.log', timeout=900, env=environment)
    hashes = verify_source(tool)
    shutil.copyfile(source / 'target/Phosphor-0.0.4.jar', tool / 'Phosphor-0.0.4.jar')
    save(tool / 'manifest.json', {'commit': LOCK['tools']['phosphor']['commit'], 'tag':'Phosphor-0.0.4',
        'source_java_sha256': {k:v for k,v in hashes.items() if k.endswith('.java')},
        'upstream_files_sha256': hashes, 'compiled_jar_sha256': sha(tool / 'Phosphor-0.0.4.jar'),
        'build_command': list(map(str,args)), 'java8_image':LOCK['java8_image'],
        'qualification':'Built from pinned upstream sources; run native and query calibration before comparison.'})
    verify('phosphor', tool, built=True)
    print('Phosphor JAR built; propagation/query qualification is a separate step')


def build_jre(cache, out):
    tool = cache / LOCK['tools']['phosphor']['cache'];verify('phosphor', tool, built=True)
    out.mkdir(parents=True, exist_ok=False)
    image = LOCK['java8_image']
    common = ['docker', 'run', '--rm', '--network', 'none', '--memory', '6g', '--cpus', '2',
              '--user', f'{os.getuid()}:{os.getgid()}', '-v', f'{tool}:/tool:ro', '-v', f'{out}:/out:rw']
    args = [*common, '--entrypoint', 'java', image, '-Xmx4g', '-jar', '/tool/Phosphor-0.0.4.jar',
            '-multiTaint', '/usr/lib/jvm/java-1.8-openjdk/jre', '/out/jre']
    text = command(args, log=out / 'instrument-jre.log', timeout=900)
    require('Done after ' in text, 'JRE instrumentation did not finish')
    java = out / 'jre/bin/java';java.chmod(java.stat().st_mode | 0o111)
    command([*common, '--entrypoint','/out/jre/bin/java',image,'-Xbootclasspath/a:/tool/Phosphor-0.0.4.jar',
             '-javaagent:/tool/Phosphor-0.0.4.jar','-version'], log=out / 'java-version.log')
    save(out / 'manifest.json', {'image':image,'phosphor_sha256':sha(tool / 'Phosphor-0.0.4.jar'),
         'files_sha256':{str(p.relative_to(out)):sha(p) for p in sorted((out/'jre').rglob('*')) if p.is_file()},
         'qualification':'JRE instrumentation and startup only; not query accuracy.'})
    print('Instrumented JRE prepared:', out / 'jre')


def smoke_phosphor(cache,jre,out):
    tool=cache/LOCK['tools']['phosphor']['cache'];verify('phosphor',tool,built=True)
    manifest=load(jre.parent/'manifest.json')
    require(manifest['phosphor_sha256']==sha(tool/'Phosphor-0.0.4.jar'),'JRE was instrumented by a different Phosphor build')
    for name,expected in manifest['files_sha256'].items():
        require(sha(jre.parent/name)==expected,'Instrumented JRE changed: '+name)
    out.mkdir(parents=True,exist_ok=False)
    v=subprocess.run(['javac','-version'],capture_output=True,text=True,check=True)
    version=(v.stdout+v.stderr).strip().split()[-1]
    target=['-source','8','-target','8'] if version.startswith('1.8.') else ['--release','8']
    command(['javac',*target,'-cp',tool/'Phosphor-0.0.4.jar','-d',out,HERE/'phosphor/PropagationProbe.java'],log=out/'compile.log')
    result=command(['docker','run','--rm','--network','none','--memory','3g','--cpus','2',
        '--user',f'{os.getuid()}:{os.getgid()}','-v',f'{tool}:/tool:ro','-v',f'{jre}:/jre:ro','-v',f'{out}:/out:rw',
        '--entrypoint','/jre/bin/java',LOCK['java8_image'],'-Xmx2g',
        '-Xbootclasspath/a:/tool/Phosphor-0.0.4.jar','-javaagent:/tool/Phosphor-0.0.4.jar',
        '-cp','/out','PropagationProbe'],log=out/'probe.log')
    require('PHOSPHOR_PROPAGATION_PASS' in result,'Native propagation smoke test failed')
    save(out/'result.json',{'passed':True,'phosphor_sha256':manifest['phosphor_sha256'],
        'probe_source_sha256':sha(HERE/'phosphor/PropagationProbe.java'),
        'scope':'One native primitive arithmetic and sequential Stream example; not Sock Shop or cross-service qualification.'})
    print(result.strip())


def prepare_dependencies():
    for name, record in load(HERE/'build-deps.lock.json').items():
        download(record['url'], ROOT/record['path'], record['sha256'])
        print('Verified:', name)


def prepare_apps():
    images=load(HERE/'images.lock.json')
    apps=load(HERE/'apps.lock.json')
    for role, spec in apps.items():
        dest=ROOT/spec['destination']
        if dest.exists():require(sha(dest)==spec['sha256'],'Existing original application differs: '+str(dest))
        else:
            info=json.loads(command(['docker','image','inspect',spec['image']]))[0]
            require(info['Id']==images[spec['image']]['image_id'],'Image ID differs: '+role)
            dest.parent.mkdir(parents=True,exist_ok=True)
            container=command(['docker','create','--network','none',spec['image']]).strip()
            try:
                with tempfile.TemporaryDirectory(prefix='baseline-app-',dir=dest.parent) as temp:
                    pending=Path(temp)/'app.jar'
                    command(['docker','cp',container+':'+spec['jar_path'],pending])
                    require(sha(pending)==spec['sha256'],'Original JAR differs: '+role)
                    pending.replace(dest)
            finally:command(['docker','rm',container])
        for alias in spec['compatibility_aliases']:
            target=ROOT/alias
            if target.exists():require(sha(target)==spec['sha256'],'Existing application alias differs: '+str(target))
            else:target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(dest,target)
        print('Original application verified:',role)
    # Existing cost drivers consume this path. Preserve an existing manifest
    # only when it describes exactly the same pinned images.
    target=ROOT/'artifacts/desktop-inputs/images-lock.json'
    if target.exists():require(load(target)==images,'Existing image lock differs')
    else:target.parent.mkdir(parents=True,exist_ok=True);save(target,images)
    target=ROOT/'artifacts/real-path-expansion-preflight-20261015/images.json'
    if target.exists():
        prior=load(target)
        for role in ('station','basic','ticketinfo'):
            require(apps[role]['image'] in prior[role]['digests'],'Existing Train Ticket image manifest differs')
    else:
        target.parent.mkdir(parents=True,exist_ok=True)
        save(target,{role:{'digests':[apps[role]['image']],'id':images[apps[role]['image']]['image_id']}
                     for role in ('station','basic','ticketinfo')})


def doctor(cache, names):
    result = {'cache':str(cache),'tools':{},'host_commands':{n:shutil.which(n) for n in ('git','python3','java','javac','javap','docker','mvn')}}
    for name in names:
        path = cache / LOCK['tools'][name]['cache']
        try:
            verify(name, path, built=name=='phosphor')
            result['tools'][name] = {'ready':True,'path':str(path),'scope':'Tool files verified, not application query qualification'}
        except (OSError, ValueError, RuntimeError, KeyError) as error:
            result['tools'][name] = {'ready':False,'path':str(path),'reason':str(error)}
    result['all_tools_ready'] = all(v['ready'] for v in result['tools'].values())
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return result['all_tools_ready']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache',type=Path,default=DEFAULT_CACHE)
    sub = parser.add_subparsers(dest='action',required=True)
    for action in ('fetch','doctor'):
        p = sub.add_parser(action);p.add_argument('--tool',choices=['all',*LOCK['tools']],default='all')
        if action=='fetch':p.add_argument('--from',dest='source',type=Path,help='Verified existing tool directory; use with a single --tool')
    sub.add_parser('deps')
    sub.add_parser('apps')
    p = sub.add_parser('build-phosphor');p.add_argument('--maven-repo',type=Path)
    p = sub.add_parser('build-jre');p.add_argument('--out',type=Path,required=True)
    p = sub.add_parser('smoke-phosphor');p.add_argument('--jre',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    args = parser.parse_args();cache=args.cache.resolve()
    if args.action in ('fetch','doctor'):
        names=list(LOCK['tools']) if args.tool=='all' else [args.tool]
        if args.action=='doctor':return 0 if doctor(cache,names) else 1
        require(not args.source or len(names)==1,'--from requires one named tool')
        for name in names:fetch(name,cache,args.source.resolve() if args.source else None)
    elif args.action=='deps':prepare_dependencies()
    elif args.action=='apps':prepare_apps()
    elif args.action=='build-phosphor':build_phosphor(cache,args.maven_repo.resolve() if args.maven_repo else None)
    elif args.action=='build-jre':build_jre(cache,args.out.resolve())
    elif args.action=='smoke-phosphor':smoke_phosphor(cache,args.jre.resolve(),args.out.resolve())
    return 0


if __name__=='__main__':
    try:sys.exit(main())
    except (OSError,ValueError,RuntimeError,subprocess.TimeoutExpired) as error:
        print('Baseline preparation failed: '+str(error),file=sys.stderr);sys.exit(1)
