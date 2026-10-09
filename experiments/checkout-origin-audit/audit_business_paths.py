#!/usr/bin/env python3
"""Read-only source audit + normal production build; no fixtures or BPF capture."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from go_byte_adapter import assembly_rows
from go_string_adapter import file_offset
from hybrid_model import require

COMMIT = '474d0f2eb73d97525234995a40d7781b7923a07d'
PACKAGE = 'github.com/GoogleCloudPlatform/microservices-demo/src/checkoutservice'
FUNCTIONS = [
    'main.(*checkoutService).PlaceOrder',
    'main.(*checkoutService).prepareOrderItemsAndShippingQuoteFromCart',
    'main.(*checkoutService).prepOrderItems',
    'main.(*checkoutService).convertCurrency',
    PACKAGE + '/money.Sum',
    PACKAGE + '/money.MultiplySlow',
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkout', type=Path, required=True)
    parser.add_argument('--go', default=os.environ.get('TRACEFUSION_GO') or shutil.which('go'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(args.go, 'Supply --go or put Go 1.25.4 on PATH')
    checkout, out = args.checkout.resolve(), args.output.resolve()
    module = checkout / 'src/checkoutservice'
    out.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ, GOOS='linux', GOARCH='amd64', CGO_ENABLED='0',
               GOTOOLCHAIN='local', GOTELEMETRY='off', GOFLAGS='', GOEXPERIMENT='', GOAMD64='v1', GO111MODULE='on')

    def command(argv, cwd=module):
        p = subprocess.run(list(map(str, argv)), cwd=cwd, env=env,
                           text=True, capture_output=True, timeout=600)
        with (out / 'commands.jsonl').open('a') as f:
            f.write(json.dumps(dict(command=list(map(str, argv)), returncode=p.returncode,
                                   stdout=p.stdout, stderr=p.stderr)) + '\n')
        if p.returncode:
            raise RuntimeError(f'Command failed: {argv}\n{p.stdout}\n{p.stderr}')
        return p.stdout

    require(command(['git', 'rev-parse', 'HEAD'], checkout).strip() == COMMIT, 'Wrong upstream commit')
    require(not command(['git', 'status', '--porcelain', '--untracked-files=no'], checkout).strip(), 'Tracked source changes')
    require(not command(['git', 'ls-files', '--others', '--exclude-standard', '--', '*.go']).strip(), 'Extra Go source in module')
    require(command([args.go, 'env', 'GOVERSION']).strip() == 'go1.25.4', 'Use Go 1.25.4')
    hashes = {p: hashlib.sha256((module / p).read_bytes()).hexdigest() for p in ('main.go', 'money/money.go')}
    binary = out / 'checkout'
    command([args.go, 'build', '-mod=readonly', '-buildvcs=false', '-o', binary, '.'])
    data = binary.read_bytes()
    records = []
    for symbol in FUNCTIONS:
        asm = command([args.go, 'tool', 'objdump', '-s', '^' + re.escape(symbol) + '$', binary])
        rows = assembly_rows(asm)
        require(rows, 'Missing production symbol: ' + symbol)
        for row in rows:
            offset = file_offset(data, row['address'])
            code = bytes.fromhex(row['code'])
            require(data[offset:offset + len(code)] == code, 'ELF instruction mismatch')
        name = symbol.rsplit('/', 1)[-1].replace('main.(*checkoutService).', '')
        (out / (name + '.asm')).write_text(asm)
        records.append(dict(function=symbol, instructions=len(rows),
                            opcodes=sorted({r['asm'].split(' ', 1)[0] for r in rows}),
                            calls=sorted({r['asm'][5:] for r in rows if r['asm'].startswith('CALL ')})))
    require(hashes == {p: hashlib.sha256((module / p).read_bytes()).hexdigest() for p in hashes}, 'Source changed')
    report = dict(upstream_commit=COMMIT, go='go1.25.4', source_sha256=hashes,
                  binary_sha256=hashlib.sha256(data).hexdigest(), functions=records,
                  fixture_added=False, bpf_executed=False, production_source_unchanged=True,
                  scope='Original optimized production binary inventory, not a field-provenance proof or a deployed service run')
    (out / 'business-paths.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
