"""Bounded x86-64 CFG/def-use analysis and observation-checked replay.

No function-name-to-source rules. No oracle input. This is an acyclic leaf
instruction subset, not a general disassembler, alias analyzer or C frontend.
"""
import re
from dataclasses import dataclass

REGS = ['rax', 'rbx', 'rcx', 'rdx', 'rsi', 'rdi', 'rbp', 'rsp'] + ['r%d' % i for i in range(8, 16)]
REG32 = dict(zip(['eax', 'ebx', 'ecx', 'edx', 'esi', 'edi', 'ebp', 'esp'], REGS[:8]))
REG32.update({'r%dd' % i: 'r%d' % i for i in range(8, 16)})
BRANCHES = {'je', 'jz', 'jne', 'jnz', 'jl', 'jle', 'jg', 'jge', 'ja', 'jae', 'jb', 'jbe', 'js', 'jns'}
MASK32 = (1 << 32) - 1
MASK64 = (1 << 64) - 1
CCMASK = 1 | (1 << 6) | (1 << 7) | (1 << 11)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_config(c):
    require(c['abi'] == 'linux-x86_64-sysv', 'Unsupported ABI')
    for key in ('input_fields', 'output_fields'):
        fields = c[key]
        require(0 < len(fields) <= 8 and len(set(fields)) == len(fields), 'Invalid field schema')
        require(all(re.fullmatch(r'[A-Za-z_]\w*', f) for f in fields), 'Invalid field name')
    require(c['sink_field'] in c['output_fields'], 'Unknown sink field')
    require(set(c['sensitive_fields']) <= set(c['input_fields']), 'Unknown sensitive field')
    require(0 < len(c['functions']) <= 16 and len(set(c['functions'])) == len(c['functions']), 'Invalid function scope')
    require(all(re.fullmatch(r'[A-Za-z_]\w*', f) for f in c['functions']), 'Invalid function symbol')


def operand(text):
    if text in REGS:
        return {'kind': 'reg', 'reg': text, 'width': 64}
    if text in REG32:
        return {'kind': 'reg', 'reg': REG32[text], 'width': 32}
    m = re.fullmatch(r'(?:DWORD PTR )?\[([a-z0-9]+)(?:([+-])(0x[0-9a-f]+|[0-9]+))?\]', text)
    if m and m[1] in REGS:
        return {'kind': 'mem', 'reg': m[1], 'offset': (int(m[3], 0) if m[3] else 0) * (-1 if m[2] == '-' else 1), 'width': 32}
    if re.fullmatch(r'-?(?:0x[0-9a-f]+|[0-9]+)', text):
        return {'kind': 'imm', 'value': int(text, 0), 'width': 32}
    raise ValueError('Unsupported operand: ' + text)


def decode(offset, asm, base):
    mnemonic, _, args = asm.partition(' ')
    node = {'offset': offset, 'asm': asm, 'op': mnemonic, 'args': []}
    if mnemonic in ('ret', 'endbr64', 'nop'):
        require(not args or mnemonic == 'nop', 'Unsupported return/landing pad')
    elif mnemonic in BRANCHES | {'jmp'}:
        target = re.fullmatch(r'([0-9a-f]+)(?: <[^>]+>)?', args)
        require(target is not None, 'Indirect jumps are unsupported')
        node['target'] = int(target[1], 16) - base
    elif mnemonic in ('mov', 'lea', 'xor', 'add', 'test', 'cmp'):
        fields = args.split(',')
        require(len(fields) == 2, 'Expected two operands')
        a, b = map(operand, fields)
        node['args'] = [a, b]
        if mnemonic == 'lea':
            require(a['kind'] == 'reg' and a['width'] == 64 and b['kind'] == 'mem', 'Only base+constant 64-bit LEA supported')
        elif mnemonic == 'mov':
            require(a['kind'] in ('reg', 'mem') and not (a['kind'] == b['kind'] == 'mem'), 'Invalid MOV')
            if a['width'] == 64:
                require(a['kind'] == b['kind'] == 'reg' and b['width'] == 64, '64-bit MOV only copies registers')
            else:
                require(b['width'] == 32, 'MOV operand widths differ')
        else:
            require(a['width'] == b['width'] == 32, 'Only 32-bit arithmetic/conditions supported')
            require(a['kind'] == 'reg', 'Arithmetic destination must be register')
        if mnemonic not in ('test', 'cmp'):
            require(not (a['kind'] == 'reg' and a['reg'] in ('rsp', 'rbp')), 'Stack-frame mutation is unsupported')
    else:
        raise ValueError('Unsupported instruction: ' + asm)
    return node


def decode_function(name, disassembly, symbols):
    require(name in symbols, 'Missing function: ' + name)
    base, size = symbols[name]
    instructions = []
    for line in disassembly.splitlines():
        m = re.match(r'^\s*([0-9a-f]+):\s+(.+?)\s*$', line)
        if m and base <= int(m[1], 16) < base + size:
            asm = ' '.join(m[2].split()).split(' #')[0]
            instructions.append(decode(int(m[1], 16) - base, asm, base))
    require(instructions and instructions[0]['offset'] == 0, 'Missing function entry')
    require(len(instructions) <= 128, 'Function exceeds bounded analysis size')
    offsets = {n['offset'] for n in instructions}
    for i, node in enumerate(instructions):
        fall = instructions[i + 1]['offset'] if i + 1 < len(instructions) else None
        op = node['op']
        successors = [] if op == 'ret' else ([node['target']] if op == 'jmp' else
                     [fall, node['target']] if op in BRANCHES else [fall])
        require(all(s in offsets for s in successors), 'Control flow leaves supported function')
        node['successors'] = list(dict.fromkeys(successors))
    paths = []
    by_offset = {n['offset']: n for n in instructions}

    def visit(offset, path):
        require(offset not in path, 'Loops are unsupported; no silent unrolling')
        require(len(paths) < 256, 'Path enumeration limit reached')
        path = path + [offset]
        node = by_offset[offset]
        if not node['successors']:
            paths.append(path)
        for nxt in node['successors']:
            visit(nxt, path)
    visit(0, [])
    return {'function': name, 'symbol_address': base, 'symbol_size': size,
            'instructions': instructions, 'paths': paths}


@dataclass(frozen=True)
class Value:
    origins: frozenset = frozenset()
    refs: frozenset = frozenset()
    address: tuple | None = None


def static_plan(function, config):
    """Path-sensitive strong updates in a closed two-region memory model.

    CFG branches are conservatively enumerated. Control/address edges support
    probe planning; reported sources are explicit DATA dependencies only.
    """
    by_offset = {n['offset']: n for n in function['instructions']}
    all_edges, candidates, path_records = set(), set(), []
    sources = ['input.' + f for f in config['input_fields']]
    instruction_ids = {o: 'i:%x' % o for o in by_offset}
    sink_index = config['output_fields'].index(config['sink_field'])
    graph_nodes = {instruction_ids[o]: {'offset': o, 'asm': n['asm']} for o, n in by_offset.items()}
    for name in sources + ['arg.select', 'arg.input', 'arg.output']:
        graph_nodes[name] = {'kind': 'boundary'}

    for path in function['paths']:
        edges = set()
        regs = {r: Value(refs=frozenset({'unknown:' + r})) for r in REGS}
        regs.update(rsi=Value(refs=frozenset({'arg.input'}), address=('input', 0)),
                    rdi=Value(refs=frozenset({'arg.output'}), address=('output', 0)),
                    rdx=Value(frozenset({'arg.select'}), frozenset({'arg.select'})))
        memory = {('input', i * 4): Value(frozenset({s}), frozenset({s})) for i, s in enumerate(sources)}
        for i, field in enumerate(config['output_fields']):
            name = 'initial:output.' + field
            memory['output', i * 4] = Value(frozenset({name}), frozenset({name}))
            graph_nodes[name] = {'kind': 'initial-output'}
        flags = Value()

        def locate(arg):
            pointer = regs[arg['reg']]
            require(pointer.address is not None, 'Unresolved memory base in static analysis')
            region, off = pointer.address
            addr = region, off + arg['offset']
            require(addr in memory, 'Memory access outside declared uint32 schema')
            return addr, pointer

        def read(arg, node_id):
            if arg['kind'] == 'imm':
                return Value()
            if arg['kind'] == 'reg':
                value = regs[arg['reg']]
                require(not any(r.startswith('unknown:') for r in value.refs), 'Read of unmodeled initial register')
                return value
            addr, pointer = locate(arg)
            edges.update((r, node_id, 'address') for r in pointer.refs)
            return memory[addr]

        for off in path:
            node, nid = by_offset[off], instruction_ids[off]
            op, args = node['op'], node['args']
            if op in ('mov', 'lea', 'xor', 'add', 'test', 'cmp'):
                a, b = args
                if op == 'lea':
                    pointer = regs[b['reg']]
                    require(pointer.address is not None, 'Unresolved LEA')
                    value = Value(refs=pointer.refs, address=(pointer.address[0], pointer.address[1] + b['offset']))
                else:
                    value = read(b, nid)
                    if op != 'mov':
                        left = read(a, nid)
                        value = Value(left.origins | value.origins, left.refs | value.refs)
                        if op == 'xor' and a == b:
                            value = Value()  # x^x clears the register and its dependence.
                edges.update((r, nid, 'data') for r in value.refs)
                new = Value(value.origins, frozenset({nid}), value.address)
                if op in ('test', 'cmp'):
                    flags = new
                elif a['kind'] == 'reg':
                    if a['width'] == 32:
                        require(new.address is None, 'Truncating pointers is unsupported')
                    regs[a['reg']] = new
                    if op in ('xor', 'add'):
                        flags = new
                else:
                    addr, pointer = locate(a)
                    require(addr[0] == 'output', 'Writes to source region are unsupported')
                    edges.update((r, nid, 'address') for r in pointer.refs)
                    memory[addr] = new  # kill the previous write for this path
            elif op in BRANCHES:
                require(flags.refs, 'Conditional jump without modeled condition')
                edges.update((r, nid, 'control') for r in flags.refs)
                for nxt in node['successors']:
                    edges.add((nid, instruction_ids[nxt], 'control'))
        final = memory['output', sink_index * 4]
        require(not any(s.startswith('initial:') for s in final.origins), 'Sink is not assigned on every candidate path')
        candidates.update(final.origins)
        sink_id = 'sink:%x' % path[-1]
        graph_nodes[sink_id] = {'kind': 'sink', 'field': config['sink_field']}
        edges.update((r, sink_id, 'data') for r in final.refs)
        path_records.append({'offsets': path, 'sources': sorted(final.origins), 'sink_node': sink_id,
                             'edges': [dict(source=a, target=b, kind=k) for a, b, k in sorted(edges)]})
        all_edges.update(edges)

    # Retain sink ancestry and every executed-path discriminator. Branch operands
    # may themselves depend on data, so close transitively over all edge kinds.
    roots = {p['sink_node'] for p in path_records}
    edges = all_edges
    roots.update(instruction_ids[o] for o, n in by_offset.items() if n['op'] in BRANCHES)
    relevant = set(roots)
    while True:
        old = len(relevant)
        relevant.update(a for a, b, _ in edges if b in relevant)
        if len(relevant) == old:
            break
    probes = {o for o in by_offset if instruction_ids[o] in relevant}
    probes.add(0)
    probes.update(o for o, n in by_offset.items() if n['op'] == 'ret')
    for node in by_offset.values():
        if node['op'] in BRANCHES:
            probes.update(node['successors'])
    for p in path_records:
        p['probe_offsets'] = [o for o in p['offsets'] if o in probes]
    function = dict(function)
    function.update(paths=path_records, static_sources=sorted(candidates), probe_offsets=sorted(probes),
                    graph={'nodes': graph_nodes, 'edges': [dict(source=a, target=b, kind=k) for a, b, k in sorted(edges)]},
                    probe_counts={'selected': len(probes), 'all_instructions': len(by_offset)},
                    dependency_scope='explicit data dependence; control/address edges used for selection, not reported as implicit taint')
    return function


def flags_for(op, left, right):
    left, right = left & MASK32, right & MASK32
    result = {'test': lambda: left & right, 'cmp': lambda: left - right,
              'xor': lambda: left ^ right, 'add': lambda: left + right}[op]() & MASK32
    carry = (left < right) if op == 'cmp' else (left + right > MASK32) if op == 'add' else False
    overflow = bool(((left ^ right) & (left ^ result) & (1 << 31)) if op == 'cmp' else
                    ((~(left ^ right) & (left ^ result) & (1 << 31)) if op == 'add' else 0))
    return int(carry) | (int(result == 0) << 6) | (((result >> 31) & 1) << 7) | (int(overflow) << 11)


def branch_taken(op, flags):
    cf, zf, sf, of = bool(flags & 1), bool(flags & 64), bool(flags & 128), bool(flags & 2048)
    return {'je': zf, 'jz': zf, 'jne': not zf, 'jnz': not zf, 'jl': sf != of,
            'jle': zf or sf != of, 'jg': not zf and sf == of, 'jge': sf == of,
            'ja': not cf and not zf, 'jae': not cf, 'jb': cf, 'jbe': cf or zf,
            'js': sf, 'jns': not sf}[op]


class Machine:
    """Validate modeled execution against registers/memory at observed points."""
    def __init__(self, event, config):
        self.regs = dict(zip(REGS, event['regs']))
        self.flags = event['flags'] & CCMASK
        self.src, self.dst = event['src_addr'], event['dst_addr']
        require(self.src % 4 == self.dst % 4 == 0, 'Unaligned boundary regions are unsupported')
        require(not (self.src < self.dst + 4 * len(event['outputs']) and
                     self.dst < self.src + 4 * len(event['inputs'])), 'Input/output regions overlap')
        self.memory = {self.src + 4 * i: value for i, value in enumerate(event['inputs'])}
        self.memory.update({self.dst + 4 * i: value for i, value in enumerate(event['outputs'])})
        self.config = config

    def read(self, arg):
        if arg['kind'] == 'imm':
            return arg['value'] & MASK32
        if arg['kind'] == 'reg':
            return self.regs[arg['reg']] & (MASK32 if arg['width'] == 32 else MASK64)
        addr = (self.regs[arg['reg']] + arg['offset']) & MASK64
        require(addr in self.memory, 'Dynamic memory address outside declared regions')
        return self.memory[addr]

    def write(self, arg, value):
        if arg['kind'] == 'reg':
            self.regs[arg['reg']] = value & (MASK32 if arg['width'] == 32 else MASK64)
        else:
            addr = (self.regs[arg['reg']] + arg['offset']) & MASK64
            require(addr in {self.dst + i * 4 for i in range(len(self.config['output_fields']))}, 'Unmodeled destination')
            self.memory[addr] = value & MASK32

    def check(self, event, offset, base):
        require(event['source_error'] == event['destination_error'] == 0, 'User memory read failed')
        require(event['src_addr'] == self.src and event['dst_addr'] == self.dst, 'Boundary pointers changed')
        require(event['ip'] == base + offset, 'Instruction address contradicts plan')
        require(event['regs'] == [self.regs[r] for r in REGS], 'Register state contradicts decoded execution')
        require((event['flags'] & CCMASK) == self.flags, 'Condition flags contradict decoded execution')
        require(event['inputs'] == [self.memory[self.src + i * 4] for i in range(len(self.config['input_fields']))], 'Input memory changed')
        require(event['outputs'] == [self.memory[self.dst + i * 4] for i in range(len(self.config['output_fields']))], 'Output memory contradicts decoded execution')

    def step(self, node):
        op, args = node['op'], node['args']
        if op in BRANCHES:
            return node['target'] if branch_taken(op, self.flags) else node['successors'][0]
        if op == 'jmp':
            return node['target']
        if op == 'ret':
            return None
        if op in ('mov', 'lea', 'xor', 'add', 'test', 'cmp'):
            a, b = args
            if op == 'lea':
                result = self.regs[b['reg']] + b['offset']
            elif op == 'mov':
                result = self.read(b)
            else:
                left, right = self.read(a), self.read(b)
                self.flags = flags_for(op, left, right)
                result = (left ^ right) if op == 'xor' else left + right
            if op not in ('test', 'cmp'):
                self.write(a, result)
        return node['successors'][0]


def infer(events, plans, config, runtime_bases=None):
    """Only observations and program/model metadata; never reads an oracle.

    Addresses optionally checked against the actual /proc executable mapping.
    Unknown/missing paths become issues rather than invented provenance edges.
    """
    if len({e['pid_tid'] for e in events}) > 1:
        return {'results': [], 'issues': [{'error': 'Multiple execution contexts are outside this pilot scope'}],
                'oracle_used_for_inference': False}
    groups = {}
    for e in events:
        groups.setdefault((e['pid_tid'], e['call_id']), []).append(e)
    accepted, issues = [], []
    for (tid, call), rows in sorted(groups.items(), key=lambda item: item[1][0]['timestamp']):
        try:
            rows.sort(key=lambda e: e['sequence'])
            first = rows[0]
            fid = first['function']
            require(0 <= fid < len(plans), 'Unknown function')
            p = plans[fid]
            require(first['offset'] == 0, 'Missing entry event')
            require([r['sequence'] for r in rows] == list(range(len(rows))), 'Missing or duplicate event sequence')
            require(all(r['function'] == fid for r in rows), 'Mixed functions in one invocation')
            require(all(rows[i]['timestamp'] <= rows[i+1]['timestamp'] for i in range(len(rows)-1)), 'Non-monotonic events')
            require(all(len(r['regs']) == len(REGS) and len(r['inputs']) == len(config['input_fields']) and
                        len(r['outputs']) == len(config['output_fields']) for r in rows), 'Wrong observation shape')
            base = first['ip']
            if runtime_bases is not None:
                require(base == runtime_bases[p['function']], 'Entry IP does not match executable mapping')
            schedules = [q for q in p['paths'] if q['probe_offsets'] == [r['offset'] for r in rows]]
            require(bool(schedules), 'Observed path missing, duplicated, or outside CFG')
            survivors = []
            for path in schedules:
                machine = Machine(first, config)
                observed = iter(rows)
                row = next(observed, None)
                by_offset = {n['offset']: n for n in p['instructions']}
                try:
                    for index, off in enumerate(path['offsets']):
                        if row is not None and off == row['offset']:
                            machine.check(row, off, base)
                            row = next(observed, None)
                        nxt = machine.step(by_offset[off])
                        require(nxt == (path['offsets'][index+1] if index+1 < len(path['offsets']) else None), 'Branch evidence excludes this path')
                    require(row is None, 'Unconsumed observations')
                    survivors.append(path)
                except ValueError:
                    continue
            require(bool(survivors), 'Observed values/addresses contradict every candidate path')
            origins = sorted({s for q in survivors for s in q['sources']})
            # Retain final-sink ancestry from the surviving PATH-SPECIFIC edges.
            # Filtering only the union graph by executed instruction addresses
            # would incorrectly merge aliases at a common load after a join.
            dynamic_edges = {(e['source'], e['target'], e['kind']) for q in survivors for e in q['edges']}
            kept = {q['sink_node'] for q in survivors}
            while True:
                before = len(kept)
                kept.update(a for a, b, kind in dynamic_edges if b in kept and kind in ('data', 'address'))
                if len(kept) == before:
                    break
            prefix = '%s:%s:' % (tid, call)
            nodes = []
            for name in sorted(kept):
                metadata = dict(p['graph']['nodes'].get(name, {'kind': 'boundary'}))
                if 'offset' in metadata:
                    metadata['evidence'] = 'observed-and-modeled' if metadata['offset'] in p['probe_offsets'] else 'modeled'
                nodes.append(dict(id=prefix + name, static_node=name, **metadata))
            dynamic_graph = {'nodes': nodes,
                'edges': [dict(source=prefix+a, target=prefix+b, kind=k) for a, b, k in sorted(dynamic_edges)
                          if a in kept and b in kept and k in ('data', 'address')],
                'identity_scope': 'invocation-local instruction definitions and boundary fields; no cross-call heap history'}
            result = {'pid_tid': tid, 'call_id': call, 'function': p['function'],
                      'status': 'resolved' if len(survivors) == 1 else 'ambiguous',
                      'sources': origins, 'static_sources': p['static_sources'],
                      'candidate_paths': len(survivors), 'observed_offsets': [r['offset'] for r in rows],
                      'value': rows[-1]['outputs'][config['output_fields'].index(config['sink_field'])],
                      'sink': 'output.' + config['sink_field'], 'dependency_graph': dynamic_graph,
                      'basis': 'observed path and machine-state checks plus bounded instruction model'}
            accepted.append(result)
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            issues.append({'pid_tid': tid, 'call_id': call, 'error': str(exc)})
    return {'results': accepted, 'issues': issues, 'oracle_used_for_inference': False,
            'scope': 'acyclic native leaf functions; explicit data dependencies; modeled gaps checked at probes'}
