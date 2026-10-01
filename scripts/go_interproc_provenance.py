#!/usr/bin/env python3
"""Bounded Go ABIInternal calls; observe stack guards, reject runtime slow paths."""
from functools import partial
import re

import go_provenance as go
import interproc_model as core
from language_adapters import GO_CALLS, get_adapter, require


def decode_go(name, assembly, symbols):
    require(re.fullmatch(GO_CALLS.function_pattern, name), 'Only application Go functions are supported; runtime/external calls rejected')
    base, size = symbols[name]
    rows = []
    for line in assembly.splitlines():
        match = re.match(r'^\s*([0-9a-f]+):\s+(.+?)\s*$', line)
        if match and base <= int(match[1],16) < base+size:
            rows.append((int(match[1],16), ' '.join(match[2].split()).split(' #')[0]))
    require(rows, 'Empty Go function')
    specials = {}
    guard_index = 0
    # Two small-frame prologues: CMP SP, guard, or LEA R12,[SP-N]; CMP R12,guard.
    if re.fullmatch(r'lea r12,\[rsp-0x[0-9a-f]+\]', rows[0][1]):
        guard_index = 1
    if guard_index < len(rows):
        match = re.fullmatch(r'cmp (rsp|r12),QWORD PTR \[r14\+0x10\]', rows[guard_index][1])
        if match:
            require(match[1] == ('r12' if guard_index else 'rsp'), 'Unsupported Go stack-check register')
            require(len(rows) > guard_index+1, 'Missing stack-check branch')
            jump = re.fullmatch(r'jbe ([0-9a-f]+)(?: <[^>]+>)?', rows[guard_index+1][1])
            require(jump is not None, 'Unsupported Go stack-check branch')
            slow = int(jump[1],16)
            slow_rows = [(addr,asm) for addr,asm in rows if addr >= slow]
            require(slow_rows and slow_rows[0][0] == slow and slow > rows[guard_index+1][0], 'Invalid Go stack-check slow-path target')
            targets = {address for symbol,(address,_) in symbols.items() if symbol == 'runtime.morestack_noctxt.abi0'}
            calls = [re.fullmatch(r'call ([0-9a-f]+)(?: <[^>]+>)?', asm) for _,asm in slow_rows]
            require(any(c and int(c[1],16) in targets for c in calls), 'Unrecognized Go stack slow path')
            specials[rows[guard_index][0]-base] = dict(op='guard_cmp', compare_register=match[1], guard_offset=16)
            specials[slow-base] = dict(op='unsupported_runtime', reason='stack-growth or preemption path; never modeled as a successful return')
    # Go uses the two-byte XCHG AX,AX encoding as a NOP. Other XCHG is rejected.
    for addr, asm in rows:
        if asm == 'xchg ax,ax': specials.setdefault(addr-base, dict(op='nop'))
    plan = core.decode(name,assembly,symbols,special_instructions=specials)
    if any(n['op'] == 'guard_cmp' for n in plan['instructions']):
        plan['runtime_policy'] = 'observed stack check; slow-path entry is a rejection probe'
    return plan


def plan_program(assembly, symbols, config):
    require(get_adapter(config) == GO_CALLS, 'Go cross-function planner requires the calls adapter')
    return core.plan_program(assembly,symbols,config,decoder=decode_go)


def evaluate(inferred, oracle, stats, plans):
    result = go.common.evaluate(inferred,oracle,stats,plans)
    result['scope'] = 'Go fixed-field acyclic direct-call fixture; guard fast path only; no general runtime or database coverage'
    return result


build = partial(go.build, planner=plan_program)

if __name__ == '__main__':
    raise SystemExit(go.common.main(default_scenario=go.common.ROOT/'scenarios/go-interproc-provenance',
        prefix='go-interproc-provenance', build_fn=build, record_fn=go.collector.record,
        infer_fn=core.infer, evaluate_fn=evaluate, required_tools=('go','objdump')))
