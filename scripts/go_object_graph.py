"""Finite, conditional def-use graphs for optimized Go amd64 function bodies.

This is a static candidate extractor, not a dynamic provenance evaluator. Heap
loads remain observation obligations. Calls do not imply argument-to-result
dependence. Stack spill relations require the explicitly reported frame/alias
contract; they are not certificates for arbitrary callees.
"""
from collections import deque
import re

REGS = ('AX BX CX DX DI SI R8 R9 R10 R11 R12 R13 R15 SP BP R14 X15').split()
STABLE = {'SP', 'BP', 'R14'}
MEM = re.compile(r'(-?(?:0x[0-9a-f]+|\d+))?\((\w+)\)(?:\((\w+)\*([1248])\))?')


def memory(arg):
    m = MEM.fullmatch(arg)
    if not m:
        return None
    return dict(offset=int(m[1] or '0', 0), base=m[2], index=m[3], scale=int(m[4] or 1))


def stack_key(arg):
    m = memory(arg)
    if m and m['base'] == 'SP' and m['index'] is None:
        return 'stack:' + str(m['offset'])


def analyze(rows, function):
    if not rows:
        raise ValueError('Missing function')
    addresses = {r['address']: i for i, r in enumerate(rows)}
    if len(addresses) != len(rows):
        raise ValueError('Duplicate instruction address')
    parsed = []
    for row in rows:
        op, _, arg = row['asm'].partition(' ')
        # Symbol names such as go:itab.T,I(SB) contain an unspaced comma.
        args = re.split(r',\s+', arg.strip()) if arg else []
        parsed.append((op, args))
    frames = [i for i, (op, args) in enumerate(parsed)
              if op == 'SUBQ' and len(args) == 2 and args[1] == 'SP']
    if len(frames) != 1:
        raise ValueError('Requires one fixed stack-frame prologue')
    start = frames[0] + 1
    # The compiler stack-growth stub retries entry before the body starts. It is
    # not silently treated as an ordinary call preserving all application state.
    allowed_prologue = {'LEAQ', 'CMPQ', 'JBE', 'PUSHQ', 'MOVQ', 'SUBQ'}
    if any(op not in allowed_prologue for op, _ in parsed[:start]):
        raise ValueError('Unsupported frame prologue')
    for op, args in parsed[:start]:
        if op == 'MOVQ' and args != ['SP', 'BP']:
            raise ValueError('Prologue modifies argument registers')
        if op == 'LEAQ' and args[-1] != 'R12':
            raise ValueError('Unsupported prologue scratch register')
    successors = {}
    todo = [start]
    reachable = set()
    while todo:
        i = todo.pop()
        if i in reachable:
            continue
        reachable.add(i)
        op, args = parsed[i]
        if op == 'RET':
            nxt = []
        elif op.startswith('J'):
            if len(args) != 1 or not re.fullmatch('0x[0-9a-f]+', args[0]):
                raise ValueError('Indirect/external branch: ' + rows[i]['asm'])
            target = addresses.get(int(args[0], 16))
            if target is None or target < start:
                raise ValueError('Branch leaves established frame')
            nxt = [target] + ([] if op == 'JMP' else [i + 1])
        else:
            nxt = [i + 1]
        if any(n >= len(rows) for n in nxt):
            raise ValueError('Fallthrough outside function')
        successors[i] = nxt
        todo.extend(nxt)
    supported = {'MOVQ', 'MOVL', 'MOVUPS', 'LEAQ', 'XORL', 'XORQ',
                 'ADDQ', 'SUBQ', 'CMPQ', 'CMPL', 'TESTQ', 'TESTL', 'CALL', 'POPQ', 'RET'}
    jumps = {'JMP', 'JE', 'JNE', 'JLE', 'JL', 'JGE', 'JG', 'JA', 'JAE', 'JB', 'JBE'}
    for i in reachable:
        op, args = parsed[i]
        if op not in supported | jumps and not op.startswith('NOP'):
            raise ValueError('Unsupported instruction: ' + rows[i]['asm'])
        if op == 'CALL' and (len(args) != 1 or not args[0].endswith('(SB)')):
            raise ValueError('Indirect call requires target evidence: ' + rows[i]['asm'])
        if op == 'CALL' and 'morestack' in args[0]:
            raise ValueError('Stack growth inside analyzed body')
    slots = set()
    for i in reachable:
        for arg in parsed[i][1]:
            key = stack_key(arg)
            if key:
                if memory(arg)['offset'] < 0 or memory(arg)['offset'] % 8:
                    raise ValueError('Unaligned/negative stack slot unsupported')
                slots.add(key)
        # Treat vector stores as two overlapping eight-byte stack writes.
        op, args = parsed[i]
        if op == 'MOVUPS' and len(args) == 2 and stack_key(args[1]):
            slots.add('stack:' + str(memory(args[1])['offset'] + 8))
    keys = set(REGS) | slots
    definitions = {}
    writes = {}
    for i in reachable:
        op, args = parsed[i]
        out = []
        if op == 'CALL':
            callee = args[0].removesuffix('(SB)')
            barrier = re.fullmatch(r'runtime\.gcWriteBarrier[1-8]', callee)
            out = ['R11', 'X15'] if barrier else sorted(set(REGS) - STABLE)
        elif op.startswith('MOV') or op in {'LEAQ', 'XORL', 'XORQ', 'ADDQ', 'SUBQ'}:
            if len(args) != 2:
                raise ValueError('Invalid operands')
            dst = args[1]
            if dst in REGS:
                out = [dst]
            elif stack_key(dst):
                out = [stack_key(dst)]
                if op == 'MOVUPS':
                    out.append('stack:' + str(memory(dst)['offset'] + 8))
                elif op != 'MOVQ':
                    # Partial stack writes need a byte overlap domain.
                    raise ValueError('Partial stack write unsupported')
            elif not memory(dst):
                raise ValueError('Unsupported destination: ' + dst)
        elif op == 'POPQ':
            out = [args[0]]
        writes[i] = out
        for key in out:
            definitions[i, key] = f'{rows[i]["address"]:x}:{key}'
    entry = {k: frozenset(['entry:' + k]) for k in keys}
    incoming = {start: entry}
    outgoing = {}
    pending = deque([start])
    while pending:
        i = pending.popleft()
        after = dict(incoming[i])
        for key in writes[i]:
            after[key] = frozenset([definitions[i, key]])
        if outgoing.get(i) == after:
            continue
        outgoing[i] = after
        for j in successors[i]:
            prev = incoming.get(j)
            merged = after if prev is None else {k: prev[k] | after[k] for k in keys}
            if prev != merged:
                incoming[j] = dict(merged)
                pending.append(j)

    def refs(i, arg, address=False):
        if arg.startswith('$'):
            return ['literal:' + arg]
        if arg in REGS:
            return sorted(incoming[i][arg])
        m = memory(arg)
        if m:
            key = stack_key(arg)
            if key and not address:
                return sorted(incoming[i][key])
            result = []
            for reg in (m['base'], m['index']):
                if reg in REGS:
                    result.extend(incoming[i][reg])
            return sorted(set(result))
        return []

    nodes = {('entry:' + k): dict(kind='entry' if k in REGS else 'unknown_stack',
                                location=k, inputs=[]) for k in sorted(keys)}
    nodes['entry:R12']['kind'] = 'unknown_frame_scratch'
    for i in reachable:
        for arg in parsed[i][1]:
            if arg.startswith('$'):
                nodes['literal:' + arg] = dict(kind='constant', value=int(arg[1:],0), inputs=[])
    stores, calls, returns, branches, stack_addresses = [], [], [], [], []
    for i in sorted(reachable):
        row = rows[i]
        op, args = parsed[i]
        common = dict(address=row['address'], asm=row['asm'])
        if op == 'CALL':
            callee = args[0].removesuffix('(SB)')
            calls.append(dict(**common, callee=callee,
                              arguments={r: refs(i, r) for r in REGS if r not in STABLE}))
        for key in writes[i]:
            node = dict(common, location=key, inputs=[])
            if op == 'CALL':
                node.update(kind='opaque_call_result' if key == 'AX' else 'call_clobber', callee=callee)
                if re.fullmatch(r'runtime\.gcWriteBarrier[1-8]', callee) and key == 'R11':
                    node['kind'] = 'barrier_buffer'
                elif callee in ('runtime.newobject', 'runtime.makeslice') and key == 'AX':
                    node['kind'] = 'allocation'
                # No edges from parameters to results: summaries/evidence needed.
            elif op in ('XORL', 'XORQ') and args[0] == args[1]:
                node.update(kind='constant', value=0)
            elif op.startswith('MOV'):
                src = args[0]
                mem = memory(src)
                if mem and not stack_key(src):
                    node.update(kind='heap_load', memory=mem, address_inputs=refs(i, src, True),
                                base_inputs=refs(i,mem['base']), index_inputs=refs(i,mem['index']) if mem['index'] else [])
                elif src.startswith('$'):
                    node.update(kind='constant', value=int(src[1:], 0))
                elif src in REGS or stack_key(src):
                    node.update(kind='copy' if op == 'MOVQ' else 'value_transform', inputs=refs(i, src))
                else:
                    node.update(kind='unknown', reason='Unsupported move source')
            elif op == 'LEAQ':
                mem = memory(args[0])
                node.update(kind='address', operand=args[0], inputs=refs(i, args[0], True))
                if mem:
                    node['memory'] = mem
                    if mem['base'] == 'SP':
                        stack_addresses.append(dict(common, offset=mem['offset']))
            elif op in ('ADDQ', 'SUBQ'):
                node.update(kind='value_transform', inputs=sorted(set(refs(i, args[0]) + refs(i, args[1]))))
            else:
                node.update(kind='unknown', reason='Stack epilogue')
            nodes[definitions[i, key]] = node
        if op.startswith('MOV') and len(args) == 2 and memory(args[1]) and not stack_key(args[1]):
            mem = memory(args[1])
            stores.append(dict(common, memory=mem, value_operand=args[0], value_inputs=refs(i, args[0]),
                               base_inputs=refs(i,mem['base']), index_inputs=refs(i,mem['index']) if mem['index'] else [],
                               address_inputs=refs(i, args[1], True)))
        if op == 'RET':
            returns.append(dict(common, registers={r: refs(i, r) for r in ('AX','BX','CX','DI','SI')}))
        if op in jumps and op != 'JMP':
            branches.append(dict(common, successors=[rows[j]['address'] for j in successors[i]]))
    return dict(function=function, status='conditional_static_candidates',
                frame_entry=rows[start]['address'], instructions=len(reachable),
                nodes=nodes, stores=stores, calls=calls, returns=returns, branches=branches,
                cfg={str(rows[i]['address']): [rows[j]['address'] for j in successors[i]] for i in sorted(reachable)},
                assumptions=[
                    'Fixed Go 1.25.4 amd64 ABI; body begins after the fixed frame prologue.',
                    'runtime.gcWriteBarrier1..8 preserves GPRs except R11 (runtime assembly contract).',
                    'Private spill slots are not modified through aliases or by callees; not certified here.',
                    'Heap loads are observation obligations, not reconstructed heap versions.',
                    'No dynamic instance or feasible-path identity inferred from this graph.'],
                obligations=dict(stack_addresses=stack_addresses,
                    call_memory_effects='Callee/alias validation required before using stack relations as proof',
                    loop_and_branch_binding='Runtime observations required',
                    runtime_capture_complete=False))


def terminals(graph, roots):
    """Follow only exact copies. Keep alternatives, loads and cycles explicit."""
    seen, result, pending = set(), set(), list(roots)
    while pending:
        key = pending.pop()
        if key in seen:
            continue
        seen.add(key)
        node = graph['nodes'][key]
        if node['kind'] == 'copy':
            pending.extend(node['inputs'])
        else:
            result.add(key)
    return sorted(result)
