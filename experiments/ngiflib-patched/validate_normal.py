#!/usr/bin/env python3
"""Validate the original patched GIF converter with ordinary generated images.

No PoC, malformed input, vulnerable binary execution, or taint-result claim.
"""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

from PIL import Image, __version__ as PILLOW_VERSION

REVISION = 'cfbedecfeca66e22b62c37b85fcad5aa825625d7'
FIX = 'be4c7dffdcf7543fe24acc7448d6014a939fd26b'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def tga_rgb(path):
    """Independent reader for the two uncompressed TGA forms emitted upstream.

    Tiny valid TGA files can be shorter than the optional 26-byte footer.
    Parse the header/payload directly instead of requiring such a footer.
    """
    data = path.read_bytes()
    assert len(data) >= 18
    width = int.from_bytes(data[12:14], 'little')
    height = int.from_bytes(data[14:16], 'little')
    assert width > 0 and height > 0 and data[17] & 0x10 == 0
    start = 18 + data[0]
    count = width * height
    if data[2] == 1:
        assert data[1] == 1 and data[7] == 24 and data[16] == 8
        first = int.from_bytes(data[3:5], 'little')
        entries = int.from_bytes(data[5:7], 'little')
        palette_end = start + entries * 3
        assert len(data) >= palette_end + count
        palette = [data[i:i+3][::-1] for i in range(start, palette_end, 3)]
        pixels = [palette[n-first] for n in data[palette_end:palette_end+count]
                  if first <= n < first + entries]
        assert len(pixels) == count
    else:
        assert data[2] == 2 and data[1] == 0 and data[16] in (24, 32)
        stride = data[16] // 8
        assert len(data) >= start + count * stride
        pixels = [data[i:i+3][::-1] for i in range(start, start+count*stride, stride)]
    rows = [b''.join(pixels[y*width:(y+1)*width]) for y in range(height)]
    if not data[17] & 0x20:
        rows.reverse()
    return (width, height), b''.join(rows)


def run(argv, cwd, records, env=None):
    p = subprocess.run(list(map(str, argv)), cwd=cwd, env=env, capture_output=True, text=True, timeout=60)
    records.append(dict(command=list(map(str, argv)), returncode=p.returncode, stdout=p.stdout, stderr=p.stderr))
    if p.returncode:
        raise RuntimeError('Command failed: ' + p.stderr[-2000:])
    return p.stdout


def validate(repo, out):
    out.mkdir(parents=True, exist_ok=False)
    records = []
    summary = dict(revision=REVISION, fix_commit=FIX, inputs='ordinary Pillow-generated palette GIFs',
                   pillow_version=PILLOW_VERSION, source_modified=False, poc_executed=False,
                   vulnerable_revision_executed=False, provenance_checked=False,
                   vulnerability_reproduced=False, performance_eligible=False,
                   sanitizer_validation_complete=False,
                   cases=[])
    try:
        run(['git', '-C', repo, 'merge-base', '--is-ancestor', FIX, REVISION], out, records)
        source_dir = out / 'source'
        source_dir.mkdir()
        source_hashes = {}
        # Read the fixed git objects, independent of checkout modifications.
        for name in ('ngiflib.c', 'ngiflib.h', 'gif2tga.c'):
            data = subprocess.check_output(['git', '-C', str(repo), 'show', REVISION + ':' + name])
            (source_dir / name).write_bytes(data)
            source_hashes[name] = sha(data)
        summary['source_sha256'] = source_hashes
        summary['compiler'] = run(['gcc', '--version'], out, records).splitlines()[0]
        binaries = {}
        for mode, flags in (('native', []), ('sanitized', ['-fsanitize=address,undefined', '-fno-omit-frame-pointer'])):
            binary = out / ('gif2tga-' + mode)
            run(['gcc', '-O1', '-g', '-Wall', '-Wextra', *flags, '-o', binary,
                 source_dir / 'gif2tga.c', source_dir / 'ngiflib.c'], out, records)
            binaries[mode] = binary
        summary['binary_sha256'] = {name: sha(path.read_bytes()) for name, path in binaries.items()}
        sanitizer_blocked = False
        # Original upstream application and decoder; no logging or propagation patches.
        palette = [0, 0, 0, 255, 0, 0, 0, 255, 0, 0, 0, 255] + [0] * (768 - 12)
        for name, width, height, pattern in (
            ('single_pixel', 1, 1, lambda x, y: 1),
            ('stripes', 8, 4, lambda x, y: x % 4),
            ('checker', 31, 17, lambda x, y: (x + y) % 4),
            ('blocks', 64, 64, lambda x, y: ((x // 8) + (y // 8)) % 4),
        ):
            folder = out / name
            folder.mkdir()
            image = Image.new('P', (width, height))
            image.putpalette(palette)
            image.putdata([pattern(x, y) for y in range(height) for x in range(width)])
            path = folder / 'normal.gif'
            image.save(path, format='GIF', optimize=False, interlace=False)
            with Image.open(path) as decoded:
                reference = decoded.convert('RGB')
                assert reference.tobytes() == image.convert('RGB').tobytes()
            for mode, binary in binaries.items():
                if mode == 'sanitized' and sanitizer_blocked:
                    continue
                for indexed in (False, True):
                    target = folder / (mode + ('-indexed' if indexed else '-truecolor'))
                    target.mkdir()
                    # Short relative output base avoids unrelated pathname edge conditions.
                    argv = [binary, *(['--indexed'] if indexed else []), '--outbase', 'image', path]
                    env = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:halt_on_error=1',
                               UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1')
                    try:
                        stdout = run(argv, target, records, env)
                    except RuntimeError:
                        if mode == 'sanitized' and 'LeakSanitizer has encountered a fatal error' in records[-1]['stderr']:
                            sanitizer_blocked = True
                            summary['sanitizer_environment_failure'] = records[-1]['stderr']
                            break
                        raise
                    if 'LoadGif() returned -' in stdout:
                        raise RuntimeError('Decoder reported an error')
                    outputs = list(target.glob('*.tga'))
                    assert len(outputs) == 1, 'Expected one frame'
                    size, pixels = tga_rgb(outputs[0])
                    assert size == reference.size
                    assert pixels == reference.tobytes()
                    summary['cases'].append(dict(input=name, width=width, height=height,
                        input_sha256=sha(path.read_bytes()), build=mode, indexed=indexed, pixels_match=True,
                        output_sha256=sha(outputs[0].read_bytes())))
        summary['all_pixels_match'] = True
        summary['native_runs_passed'] = sum(c['build'] == 'native' for c in summary['cases'])
        summary['sanitized_runs_passed'] = sum(c['build'] == 'sanitized' for c in summary['cases'])
        summary['sanitizer_validation_complete'] = summary['sanitized_runs_passed'] == 8
        # A separate coverage build confirms that a normal input reaches the
        # repaired check. It is not a taint trace or a performance binary.
        coverage = out / 'coverage'
        coverage.mkdir()
        run(['gcc', '-O1', '-g', '--coverage', '-o', 'gif2tga-coverage',
             source_dir / 'gif2tga.c', source_dir / 'ngiflib.c'], coverage, records)
        run([coverage / 'gif2tga-coverage', '--outbase', 'image', out / 'stripes/normal.gif'], coverage, records)
        run(['gcov', '-b', '-j', '-o', 'gif2tga-coverage-ngiflib.gcno', source_dir / 'ngiflib.c'], coverage, records)
        with Image.open(out / 'stripes/normal.gif') as original:
            size, pixels = tga_rgb(coverage / 'image_out01.tga')
            assert size == original.size and pixels == original.convert('RGB').tobytes()
        source_lines = (source_dir / 'ngiflib.c').read_text(encoding='latin1').splitlines()
        guard_line = next(i+1 for i, line in enumerate(source_lines) if 'else if(act_code > free)' in line)
        rejection_line = next(i+1 for i in range(guard_line, guard_line+8) if 'return -1;' in source_lines[i])
        data = json.loads(gzip.decompress((coverage / 'ngiflib.gcov.json.gz').read_bytes()))
        file = next(f for f in data['files'] if Path(f['file']).name == 'ngiflib.c')
        lines = {r['line_number']: r for r in file['lines']}
        assert lines[guard_line]['count'] > 0 and lines[rejection_line]['count'] == 0
        summary['normal_path_coverage'] = dict(input='stripes', guard_line=guard_line,
            guard_evaluations=lines[guard_line]['count'], rejection_line=rejection_line,
            rejection_executions=lines[rejection_line]['count'], pixels_match=True,
            provenance_checked=False, performance_eligible=False)
    except Exception as exc:
        summary['failure'] = str(exc)
        raise
    finally:
        (out / 'commands.json').write_text(json.dumps(records, indent=2)+'\n')
        (out / 'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True, help='Upstream ngiflib git checkout containing pinned objects')
    p.add_argument('--output', type=Path)
    args = p.parse_args()
    if args.output:
        result = validate(args.source.resolve(), args.output.resolve())
    else:
        with tempfile.TemporaryDirectory() as temp:
            result = validate(args.source.resolve(), Path(temp) / 'validation')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
