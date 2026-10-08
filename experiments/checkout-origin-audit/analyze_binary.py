#!/usr/bin/env python3
"""Extract conservative object graphs with explicit unknown stack effects."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from go_byte_adapter import assembly_rows
from go_object_graph import analyze, terminals
from go_string_adapter import file_offset
from go_provenance import parse_nm


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--binary', type=Path, required=True)
    p.add_argument('--go', default=os.environ.get('TRACEFUSION_GO') or shutil.which('go'))
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if not args.go:
        p.error('Go 1.25.4 required')
    env = dict(os.environ, GOTOOLCHAIN='local', GOFLAGS='', GOWORK='off', GOTELEMETRY='off')
    def command(argv):
        return subprocess.check_output(argv, env=env, text=True)
    if command([args.go,'env','GOVERSION']).strip() != 'go1.25.4':
        raise ValueError('Use Go 1.25.4')
    binary = args.binary.resolve()
    data = binary.read_bytes()
    build_info = command([args.go,'version','-m',str(binary)])
    if ': go1.25.4' not in build_info.splitlines()[0]:
        raise ValueError('Target was not built by pinned Go 1.25.4')
    type_prefix = 'github.com/GoogleCloudPlatform/microservices-demo/src/checkoutservice/genproto.'
    layouts = json.loads(command([args.go,'run',str(HERE/'inspect_layout.go'),str(binary)] +
        [type_prefix+t for t in ('OrderItem','CartItem','Product','Money','CurrencyConversionRequest')]))
    symbols = parse_nm(command([args.go,'tool','nm','-size',str(binary)]))
    graphs = {}
    for name in ('prepOrderItems','convertCurrency'):
        symbol = 'main.(*checkoutService).' + name
        asm = command([args.go,'tool','objdump','-s','^'+re.escape(symbol)+'$',str(binary)])
        rows = assembly_rows(asm)
        if not rows:
            raise ValueError('Missing symbol: ' + symbol)
        first, size = symbols[symbol]
        if rows[0]['address'] != first or rows[-1]['address']+len(bytes.fromhex(rows[-1]['code'])) != first+size:
            raise ValueError('Disassembly does not cover full symbol: ' + symbol)
        for i, row in enumerate(rows):
            code = bytes.fromhex(row['code'])
            off = file_offset(data,row['address'])
            if data[off:off+len(code)] != code:
                raise ValueError('ELF/disassembly mismatch')
            if i and rows[i-1]['address']+len(bytes.fromhex(rows[i-1]['code'])) != row['address']:
                raise ValueError('Gap in disassembly')
        graph = analyze(rows,symbol)
        graph['binary_verified_instructions'] = len(rows)
        for store in graph['stores']:
            store['value_terminals'] = terminals(graph,store['value_inputs'])
            store['address_terminals'] = terminals(graph,store['address_inputs'])
        graphs[name] = graph
    result = dict(schema=2,binary_sha256=hashlib.sha256(data).hexdigest(),build_info=build_info,
                  status='conservative_static_candidates',layouts=layouts,graphs=graphs,
                  source_files_read=False,answers_or_runtime_truth_read=False,
                  allocation_type_binding_complete=False,
                  stack_alias_contract_verified=False,
                  bpf_capture_executed=False,dynamic_provenance_complete=False)
    if binary.read_bytes() != data:
        raise ValueError('Target ELF changed during analysis')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x') as f:
        json.dump(result,f,ensure_ascii=False,indent=2); f.write('\n')
    print(json.dumps(dict(output=str(args.output),status=result['status'],
        functions={k:dict(instructions=v['instructions'],stores=len(v['stores'])) for k,v in graphs.items()})))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as exc:
        print(json.dumps(dict(status='unsupported_or_failed',error=str(exc))),file=sys.stderr)
        sys.exit(1)
