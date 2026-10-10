"""Boundary/ABI configuration only: no selector, interpreter, or fixture oracle.

These are the same manually declared source/sink contracts as the payment
experiment, independently checked against the supplied ELF and its DWARF.
"""
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from go_byte_adapter import assembly_rows
from go_string_adapter import file_offset

BASE = 'github.com/GoogleCloudPlatform/microservices-demo/src/checkoutservice'
PLACE = BASE + '.(*checkoutService).PlaceOrder'
PREP = BASE + '.(*checkoutService).prepareOrderItemsAndShippingQuoteFromCart'
PAY = BASE + '.(*checkoutService).chargeCard'


def diagnostic_instructions(binary, command, out):
    """All instructions in named functions, independent of query/taint results."""
    data = binary.read_bytes()
    result = []
    for name in (PLACE, BASE + '/money.MultiplySlow', BASE + '/money.Sum',
                 BASE + '/money.IsValid', 'runtime.asyncPreempt.abi0'):
        asm = command(['tool', 'objdump', '-s', '^' + re.escape(name) + '$', str(binary)])
        rows = assembly_rows(asm)
        check(rows, 'Missing diagnostic function: ' + name)
        for row in rows:
            offset = file_offset(data, row['address'])
            code = bytes.fromhex(row['code'])
            check(data[offset:offset + len(code)] == code, 'Diagnostic ELF bytes differ')
            result.append(dict(function=name, **row))
    (out / 'diagnostic-instructions.json').write_text(json.dumps(result, indent=2) + '\n')
    config = out / 'diagnostic-pcs.txt'
    config.write_text(''.join('%x\n' % row['address'] for row in result))
    return config


def check(condition, message):
    if not condition:
        raise ValueError(message)


def plan_binary(binary, command, reader, out):
    data = binary.read_bytes()
    check(data[:6] == b'\x7fELF\x02\x01', 'Require little-endian ELF64')
    check(int.from_bytes(data[16:18], 'little') == 2, 'Initial adapter requires ET_EXEC, not PIE')
    check(int.from_bytes(data[18:20], 'little') == 62, 'Require amd64')
    asm = command(['tool', 'objdump', '-s', '^' + re.escape(PLACE) + '$', str(binary)])
    (out / 'external-PlaceOrder.asm').write_text(asm)
    rows = assembly_rows(asm)
    for row in rows:
        offset = file_offset(data, row['address'])
        code = bytes.fromhex(row['code'])
        check(data[offset:offset + len(code)] == code, 'ELF instruction mismatch')
    prep = [i for i, r in enumerate(rows) if r['asm'] == 'CALL ' + PREP + '(SB)']
    pay = [i for i, r in enumerate(rows) if r['asm'] == 'CALL ' + PAY + '(SB)']
    check(len(prep) == len(pay) == 1 and prep[0] < pay[0], 'Ambiguous source/sink boundary')
    start = prep[0] + 1
    spills = []
    for reg, row in zip(('AX', 'BX', 'CX', 'DI', 'SI', 'R8', 'R9'), rows[start:start + 7]):
        match = re.fullmatch(r'MOVQ ' + reg + r', (0x[0-9a-f]+)\(SP\)', row['asm'])
        check(match is not None, 'Preparation return aggregate ABI changed')
        spills.append(int(match[1], 0))
    check(len(spills) == 7 and spills == list(range(spills[0], spills[0] + 56, 8)), 'Return aggregate spill changed')
    expected = {
        BASE + '/genproto.Money': {'Units': (56, 8), 'Nanos': (64, 4)},
        BASE + '/genproto.OrderItem': {'Item': (40, 8), 'Cost': (48, 8)},
        BASE + '/genproto.CartItem': {'Quantity': (56, 4)},
        BASE + '.orderPrep': {'orderItems': (0, 24), 'cartItems': (24, 24), 'shippingCostLocalized': (48, 8)},
    }
    layout = json.loads(command(['run', str(reader), str(binary), *expected]))
    for name, fields in expected.items():
        actual = {f['name']: (f['offset'], f['size']) for f in layout[name]['fields']}
        check(all(actual.get(k) == v for k, v in fields.items()), 'DWARF layout changed: ' + name)
    sites = [dict(kind='source', **rows[start]), dict(kind='sink', **rows[pay[0]])]
    sites += [dict(kind='end', **r) for r in rows if r['asm'] == 'RET']
    check(len(sites) > 2, 'Missing PlaceOrder return')
    return dict(adapter='external-payment-boundaries-v1', binary_sha256=hashlib.sha256(data).hexdigest(),
                sites=sites, layouts=layout, source_limit=32,
                abi={'source_items': 'AX', 'source_count': 'BX', 'source_shipping': 'R9',
                     'source_error_type': 'R10', 'sink_money': 'DI', 'goroutine': 'R14'},
                scope='Preparation-return price/shipping numeric fields to chargeCard amount; direct data dependencies',
                note='Manual ABI contract, ELF/DWARF verified; no production branch selection or inferred origins consumed')
