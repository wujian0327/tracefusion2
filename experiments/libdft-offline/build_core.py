#!/usr/bin/env python3
"""Extract exact pinned libdft callback bodies; retain upstream BDD and tagmap code."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
REVISION = '20804d5bae5d8aed31a71761b1a1149e35a0da95'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def extract(text, name):
    match = re.search(r'^(?:static )?void PIN_FAST_ANALYSIS_CALL ' + re.escape(name)
                      + r'\([^)]*\)\s*\{', text, re.M)
    if not match:
        raise ValueError('Missing pinned callback: ' + name)
    # Tokenize comments/strings before brace matching; never rewrite function text.
    tail = text[match.end() - 1:]
    token = re.compile(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|[{}]', re.S)
    depth = 0
    for t in token.finditer(tail):
        if t.group() == '{': depth += 1
        elif t.group() == '}':
            depth -= 1
            if depth == 0:
                end = match.end() - 1 + t.end()
                return text[match.start():end], text[:match.start()].count('\n') + 1
    raise ValueError('Unclosed callback')


def build(upstream, out):
    upstream, out = Path(upstream).resolve(), Path(out).resolve()
    head = subprocess.check_output(['git', '-C', str(upstream), 'rev-parse', 'HEAD'], text=True).strip()
    if head != REVISION:
        raise ValueError('Wrong libdft revision')
    out.mkdir(parents=True, exist_ok=False)
    source = out / 'upstream'; source.mkdir()
    manifest = {}
    for p in sorted((upstream / 'src').glob('*')):
        if p.suffix not in ('.h', '.cpp'): continue
        data = p.read_bytes()
        original = subprocess.check_output(['git', '-C', str(upstream), 'show', REVISION + ':src/' + p.name])
        if data != original: raise ValueError('Changed upstream file: ' + p.name)
        (source / p.name).write_bytes(data)
        manifest['src/' + p.name] = sha(data)
    license_data = subprocess.check_output(['git', '-C', str(upstream), 'show', REVISION + ':LICENSE'])
    (out / 'UPSTREAM-LICENSE').write_bytes(license_data)
    manifest['LICENSE'] = sha(license_data)
    shim = out / 'shim'; shim.mkdir()
    shutil.copyfile(HERE / 'pin.H', shim / 'pin.H')
    functions = []
    for width in ('w', 'l', 'q'):
        for route in ('r2r', 'm2r', 'r2m', 'm2m'):
            functions.append(('ins_xfer_op.cpp', route + '_xfer_op' + width))
        for route in ('r2r', 'm2r', 'r2m'):
            functions.append(('ins_binary_op.cpp', route + '_binary_op' + width))
        functions += [('ins_clear_op.cpp', 'r_clr' + width),
                      ('ins_xfer_op.cpp', '_lea_op' + width)]
    snippets, registry, callbacks = [], [], []
    for filename, name in functions:
        code, line = extract((source / filename).read_text(), name)
        callbacks.append({'name': name, 'source': 'src/' + filename, 'line': line,
                          'sha256': sha(code.encode()), 'body_unchanged': True})
        snippets.append(code)
        # Adapter validates operand roles before calling original code.
        if name.startswith('r_clr'): roles = ['reg']
        elif name.startswith('_lea'): roles = ['reg', 'reg', 'reg']
        else: roles = {'r2r': ['reg', 'reg'], 'm2r': ['reg', 'addr'],
                       'r2m': ['addr', 'reg'], 'm2m': ['addr', 'addr']}[name[:3]]
        args = ([] if name.startswith('m2m') else ['0']) + [f'a[{i}]' for i in range(len(roles))]
        conditions = [f'a.size()=={len(roles)}'] + [f'{role}_ok(a[{i}])' for i, role in enumerate(roles)]
        registry.append(f'if (name=="{name}") {{ require({" && ".join(conditions)}, "callback operands"); '
                        + name + '(' + ','.join(args) + '); return; }')
    generated = '// Extracted unmodified callbacks. See UPSTREAM-LICENSE and extraction.json.\n'
    generated += '#include "libdft_api.h"\n#define RTAG threads_ctx[tid].vcpu.gpr\n#define MTAG(ADDR) tagmap_getb((ADDR))\n'
    generated += 'extern thread_ctx_t *threads_ctx;\n' + '\n\n'.join(snippets)
    generated += '\nvoid dispatch(const std::string& name, const std::vector<uint64_t>& a) {\n'
    generated += '\n'.join(registry) + '\nthrow std::runtime_error("unknown callback: " + name);\n}\n'
    (out / 'callbacks.inc').write_text(generated)
    shutil.copyfile(HERE / 'core.cpp', out / 'core.cpp')
    exe = out / 'libdft-replay-core'
    cmd = ['g++', '-std=c++17', '-O2', '-I' + str(shim), '-I' + str(source),
           str(out / 'core.cpp'), str(source / 'bdd_tag.cpp'), str(source / 'tag_trait.cpp'),
           str(source / 'tagmap.cpp'), '-o', str(exe)]
    p = subprocess.run(cmd, text=True, capture_output=True, timeout=120)
    report = {'revision': head, 'upstream_sha256': manifest, 'callbacks': callbacks,
              'upstream_dispatcher_reused': False, 'callback_dispatch': 'explicit bounded offline adapter',
              'bdd_and_tagmap_unchanged': True, 'command': cmd, 'returncode': p.returncode,
              'stdout': p.stdout, 'stderr': p.stderr,
              'adapter_sha256': {n: sha((HERE / n).read_bytes()) for n in ('build_core.py', 'pin.H', 'core.cpp')},
              'generated_sha256': sha(generated.encode()),
              'executable_sha256': sha(exe.read_bytes()) if p.returncode == 0 else None}
    (out / 'extraction.json').write_text(json.dumps(report, indent=2) + '\n')
    if p.returncode: raise RuntimeError(p.stderr)
    return exe, report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--libdft', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args()
    exe, report = build(a.libdft, a.output)
    print(json.dumps({'executable': str(exe), 'unchanged_callbacks': len(report['callbacks'])}))
