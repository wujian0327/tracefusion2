"""Bounded direct-call provenance; explicit contexts and native stack semantics.

This is an experimental ELF instruction model, not a general C/JVM analyzer.
Reject recursion, loops, unknown calls, partial stack accesses and unmodeled
memory. Root ABI is (output*, input*, int); helpers are discovered automatically.
"""
import re
import struct
from dataclasses import dataclass

from hybrid_model import REGS, REG32, BRANCHES, MASK32, MASK64, CCMASK, require, branch_taken, validate_config

STACK_BYTES = 256
STACK_WORDS = STACK_BYTES // 8 + 1
MAX_DEPTH = 8
ARG_REGS = ('rdi', 'rsi', 'rdx', 'rcx', 'r8', 'r9')
SAVED_REGS = ('rbx', 'rbp', 'r12', 'r13', 'r14', 'r15')


def operand(text):
    if text in REGS or text in REG32:
        return dict(kind='reg', reg=REG32.get(text, text), width=32 if text in REG32 else 64)
    m = re.fullmatch(r'(?:(DWORD|QWORD) PTR )?\[([a-z0-9]+)(?:\+([a-z0-9]+)\*([1248]))?(?:([+-])(0x[0-9a-f]+|[0-9]+))?\]', text)
    if m and m[2] in REGS and (not m[3] or m[3] in REGS):
        return dict(kind='mem', reg=m[2], index=m[3], scale=int(m[4] or 1),
                    offset=int(m[6], 0) * (-1 if m[5] == '-' else 1) if m[6] else 0,
                    width=64 if m[1] == 'QWORD' else 32)
    if re.fullmatch(r'-?(?:0x[0-9a-f]+|[0-9]+)', text):
        return dict(kind='imm', value=int(text, 0))
    raise ValueError('Unsupported operand: ' + text)


def decode(name, assembly, symbols):
    base, size = symbols[name]
    instructions = []
    for line in assembly.splitlines():
        match = re.match(r'^\s*([0-9a-f]+):\s+(.+?)\s*$', line)
        if not match or not base <= int(match[1], 16) < base + size:
            continue
        asm = ' '.join(match[2].split()).split(' #')[0]
        op, _, args = asm.partition(' ')
        node = dict(function=name, offset=int(match[1], 16)-base, asm=asm, op=op, args=[])
        if op in BRANCHES | {'jmp', 'call'}:
            target = re.fullmatch(r'([0-9a-f]+)(?: <[^>]+>)?', args)
            require(target is not None, 'Indirect calls/jumps are unsupported')
            node['target_address'] = int(target[1], 16)
        elif op in ('push', 'pop'):
            arg = operand(args)
            require(arg['kind'] == 'reg' and arg['width'] == 64 and arg['reg'] != 'rsp', 'Only 64-bit register push/pop supported')
            node['args'] = [arg]
        elif op in ('mov', 'lea', 'xor', 'add', 'sub', 'test', 'cmp'):
            parts = args.split(','); require(len(parts) == 2, 'Expected two operands')
            a, b = map(operand, parts)
            require(a['kind'] in ('reg', 'mem'), 'Invalid destination')
            width = a['width']
            if b['kind'] == 'imm': b['width'] = width
            if op == 'lea':
                require(a['kind'] == 'reg' and b['kind'] == 'mem', 'Invalid LEA')
            else:
                require(width == b['width'], 'Mismatching widths')
                if op != 'mov': require(a['kind'] == 'reg', 'Memory arithmetic unsupported')
                if width == 64 and op not in ('mov',):
                    require(op in ('add', 'sub') and a['reg'] == 'rsp' and b['kind'] == 'imm', '64-bit arithmetic only adjusts RSP')
            if a['kind'] == b['kind'] == 'mem': raise ValueError('Memory-to-memory operation unsupported')
            if a.get('reg') == 'rsp' and a['kind'] == 'reg':
                require(op in ('add', 'sub') and b['kind'] == 'imm', 'Unsupported stack pointer write')
            node['args'] = [a, b]
        else:
            require(op in ('ret', 'endbr64', 'nop') and (not args or op == 'nop'), 'Unsupported instruction: ' + asm)
        instructions.append(node)
    require(instructions and instructions[0]['offset'] == 0 and len(instructions) <= 128, 'Invalid or oversized function')
    offsets = {n['offset'] for n in instructions}
    for i, n in enumerate(instructions):
        nxt = instructions[i+1]['offset'] if i+1 < len(instructions) else None
        n['next'] = nxt
        if n['op'] in BRANCHES | {'jmp'}:
            n['target'] = n['target_address'] - base
            require(n['target'] in offsets, 'Jump leaves function; tail calls unsupported')
        if n['op'] not in ('ret', 'jmp'):
            require(nxt is not None, 'Fallthrough leaves function')
    return dict(function=name, symbol_address=base, symbol_size=size, instructions=instructions)


def enumerate_paths(root, functions):
    paths = []
    maps = {name: {n['offset']: n for n in p['instructions']} for name, p in functions.items()}

    def walk(name, off, context, returns, seen, path):
        key = (context, name, off)
        require(key not in seen, 'Loops are unsupported')
        require(len(path) < 512 and len(paths) < 128, 'Bounded path budget exceeded')
        n = maps[name][off]
        sid = '/'.join(context) + '|' + name + ':%x' % off
        step = dict(function=name, offset=off, context=list(context), depth=len(returns)+1, id=sid)
        path = path + [step]; seen = seen | {key}
        if n['op'] == 'call':
            require(len(returns)+1 < MAX_DEPTH, 'Call depth exceeds limit')
            ctx = context + (name + ':%x' % off,)
            walk(n['callee'], 0, ctx, returns + [(name, n['next'], context)], seen, path)
        elif n['op'] == 'ret':
            if not returns: paths.append(path)
            else:
                caller, resume, ctx = returns[-1]
                walk(caller, resume, ctx, returns[:-1], seen, path)
        elif n['op'] == 'jmp':
            walk(name, n['target'], context, returns, seen, path)
        elif n['op'] in BRANCHES:
            for nxt in dict.fromkeys([n['next'], n['target']]): walk(name, nxt, context, returns, seen, path)
        else:
            walk(name, n['next'], context, returns, seen, path)
    walk(root, 0, (root,), [], set(), [])
    return paths


def flags_for(op, left, right, width):
    mask, sign = (1 << width)-1, 1 << (width-1)
    left, right = left & mask, right & mask
    sub = op in ('sub', 'cmp')
    result = ((left-right) if sub else (left+right) if op == 'add' else (left^right) if op == 'xor' else (left&right)) & mask
    carry = left < right if sub else left+right > mask if op == 'add' else False
    overflow = bool(((left^right) & (left^result) & sign) if sub else ((~(left^right) & (left^result) & sign) if op == 'add' else 0))
    return int(carry) | (int(result == 0)<<6) | (int(bool(result & sign))<<7) | (int(overflow)<<11)


@dataclass(frozen=True)
class Sym:
    origins: frozenset = frozenset()
    refs: frozenset = frozenset()
    address: tuple | None = None
    number: int | None = None


def symbolic_path(path, functions, config):
    """Context-qualified definitions; exact stores kill earlier field versions."""
    edges, nodes = set(), {}
    regs = {r: Sym(frozenset({'unmodeled:' + r}), frozenset({'initial:' + r})) for r in REGS}
    regs.update(rdi=Sym(refs=frozenset({'arg.output'}), address=('output', 0)),
                rsi=Sym(refs=frozenset({'arg.input'}), address=('input', 0)),
                rsp=Sym(refs=frozenset({'arg.stack'}), address=('stack', 0)),
                rdx=Sym(frozenset({'arg.select'}), frozenset({'arg.select'})))
    memory = {}
    for region in ('input', 'output'):
        for i, field in enumerate(config[region + '_fields']):
            label = ('input.' if region == 'input' else 'initial:output.') + field
            memory[region, i*4, 4] = Sym(frozenset({label}), frozenset({label}))
            nodes[label] = dict(kind='boundary', field=label)
    flags, returns = Sym(), []
    maps = {name: {n['offset']: n for n in p['instructions']} for name, p in functions.items()}

    def dependencies(values, nid, kind='data'):
        for value in values:
            edges.update((r, nid, kind) for r in value.refs)

    def address(arg):
        base = regs[arg['reg']]
        require(base.address is not None, 'Unresolved memory base')
        extra = 0
        if arg.get('index'):
            index = regs[arg['index']]
            require(index.number is not None and not index.origins, 'Dynamic indexed addresses unsupported')
            extra = index.number * arg['scale']
        return base.address[0], base.address[1] + arg['offset'] + extra

    def check_region(region, off, width):
        if region == 'stack':
            require(-STACK_BYTES <= off and off+width <= 8 and off % width == 0, 'Stack access outside bounded aligned region')
        else:
            require(region in ('input', 'output') and width == 4 and off % 4 == 0 and 0 <= off < 4*len(config[region+'_fields']), 'Memory outside field schema')

    def store(addr, width, value):
        region, off = addr; check_region(region, off, width)
        require(region != 'input', 'Writes to input unsupported')
        for key in list(memory):
            r, o, w = key
            if r == region and off < o+w and o < off+width:
                require(o == off and w == width, 'Partial overlapping stack accesses unsupported')
                del memory[key]
        memory[region, off, width] = value

    def load(addr, width):
        check_region(*addr, width)
        require((*addr, width) in memory, 'Read of uninitialized/unmodeled stack slot')
        return memory[(*addr, width)]

    def read(arg, nid):
        if arg['kind'] == 'imm': return Sym(number=arg['value'] & ((1 << arg['width'])-1))
        if arg['kind'] == 'reg': return regs[arg['reg']]
        dependencies([regs[arg['reg']]], nid, 'address')
        return load(address(arg), arg['width']//8)

    def adjust_stack(delta, nid):
        current = regs['rsp']; require(current.address is not None and current.address[0] == 'stack', 'Lost stack identity')
        off = current.address[1] + delta
        require(-STACK_BYTES <= off <= 0, 'Stack exceeds modeled bound')
        # A RET updates both RAX provenance and RSP. Those are distinct
        # definitions: merging them would leak the old return's sources into
        # later stack addresses even after a field overwrite.
        pointer_id = nid + '/stack-pointer'
        nodes[pointer_id] = dict(nodes[nid], kind='stack-pointer-definition')
        dependencies([current], pointer_id, 'address')
        regs['rsp'] = Sym(refs=frozenset({pointer_id}), address=('stack', off))

    for index, step in enumerate(path):
        n = maps[step['function']][step['offset']]; nid = step['id']; op = n['op']
        nodes[nid] = dict(function=step['function'], offset=step['offset'], context=step['context'], depth=step['depth'], asm=n['asm'])
        if op in ('mov', 'lea', 'xor', 'add', 'sub', 'test', 'cmp'):
            a, b = n['args']; width = a['width']
            if a.get('reg') == 'rsp' and a['kind'] == 'reg':
                adjust_stack(b['value'] * (-1 if op == 'sub' else 1), nid); flags = Sym(refs=frozenset({nid}))
                continue
            if op == 'lea':
                values = [regs[b['reg']]] + ([regs[b['index']]] if b.get('index') else [])
                dependencies(values, nid)
                origins = frozenset().union(*(v.origins for v in values))
                if width == 64 and values[0].address is not None:
                    value = Sym(origins, address=address(b))
                else:
                    require(all(v.address is None for v in values), 'Pointer truncation unsupported')
                    number = None if any(v.number is None for v in values) else (values[0].number + (values[1].number*b['scale'] if len(values)>1 else 0) + b['offset']) & ((1<<width)-1)
                    value = Sym(origins, number=number)
            else:
                values = [read(b, nid)] if op == 'mov' else [read(a, nid), read(b, nid)]
                if op == 'xor' and a == b: values = [Sym(number=0)]
                dependencies(values, nid)
                if op == 'mov': value = values[0]
                else:
                    require(all(v.address is None for v in values), 'Pointer arithmetic unsupported')
                    number = None
                    if all(v.number is not None for v in values):
                        left, right = (values[0].number, values[1].number) if len(values)==2 else (0, 0)
                        flags = Sym(refs=frozenset({nid}), number=flags_for(op, left, right, width))
                        number = ((left^right) if op=='xor' else (left+right) if op=='add' else (left-right) if op in ('sub','cmp') else left&right) & ((1<<width)-1)
                    else: flags = Sym(refs=frozenset({nid}))
                    value = Sym(frozenset().union(*(v.origins for v in values)), number=number)
            if op in ('test', 'cmp'): continue
            value = Sym(value.origins, frozenset({nid}), value.address, value.number)
            if a['kind'] == 'reg':
                require(width == 64 or value.address is None, 'Truncated pointer unsupported')
                regs[a['reg']] = value
            else:
                dependencies([regs[a['reg']]], nid, 'address'); store(address(a), width//8, value)
        elif op == 'push':
            value = read(n['args'][0], nid); dependencies([value], nid)
            adjust_stack(-8, nid); store(regs['rsp'].address, 8, Sym(value.origins, frozenset({nid}), value.address, value.number))
        elif op == 'pop':
            value = load(regs['rsp'].address, 8); dependencies([value], nid)
            regs[n['args'][0]['reg']] = Sym(value.origins, frozenset({nid}), value.address, value.number); adjust_stack(8, nid)
        elif op == 'call':
            resume = functions[step['function']]['symbol_address'] + n['next']
            adjust_stack(-8, nid); store(regs['rsp'].address, 8, Sym(refs=frozenset({nid}), address=('code', resume)))
            returns.append(resume)
            for reg in ARG_REGS:
                value = regs[reg]; arg_id = nid + '/arg:' + reg
                nodes[arg_id] = dict(kind='argument-transfer', register=reg, callsite=nid, callee=n['callee'])
                dependencies([value], arg_id, 'argument')
                regs[reg] = Sym(value.origins, frozenset({arg_id}), value.address, value.number)
        elif op == 'ret':
            if returns:
                ret = load(regs['rsp'].address, 8)
                require(ret.address == ('code', returns.pop()), 'Return address overwritten')
                dependencies([ret], nid, 'control'); adjust_stack(8, nid)
                value = regs['rax']; dependencies([value], nid, 'return')
                regs['rax'] = Sym(value.origins, frozenset({nid}), value.address, value.number)
            else: require(regs['rsp'].address == ('stack', 0), 'Root stack unbalanced')
        elif op in BRANCHES:
            require(flags.refs, 'Branch without modeled flags'); dependencies([flags], nid, 'control')
            if flags.number is not None:
                target = n['target'] if branch_taken(op, flags.number) else n['next']
                if path[index+1]['function'] != step['function'] or path[index+1]['offset'] != target:
                    return None  # Proven infeasible from constants, not workload/oracle.
    final = memory['output', 4*config['output_fields'].index(config['sink_field']), 4]
    require(all(not s.startswith(('unmodeled:', 'initial:')) for s in final.origins), 'Unmodeled or unwritten sink origin')
    sink = path[0]['function'] + '|sink'
    nodes[sink] = dict(kind='sink', field=config['sink_field'])
    dependencies([final], sink)
    return dict(steps=path, sources=sorted(final.origins), sink_node=sink, nodes=nodes,
                edges=[dict(source=a, target=b, kind=k) for a,b,k in sorted(edges)])


def plan_program(assembly, symbols, config):
    validate_config(config)
    functions, active = {}, set()
    by_address = {}
    for name, (address, size) in symbols.items(): by_address.setdefault(address, []).append(name)

    def discover(name):
        require(name not in active, 'Recursion is unsupported')
        if name in functions: return
        require(name in symbols and len(functions) < 32, 'Unknown callee or function limit exceeded')
        active.add(name); f = decode(name, assembly, symbols)
        for n in f['instructions']:
            if n['op'] == 'call':
                names = by_address.get(n['target_address'], [])
                require(len(names) == 1, 'Call must target one known function entry; PLT/external calls unsupported')
                n['callee'] = names[0]
                require(n['callee'] not in config['functions'], 'Calls into configured roots unsupported')
                discover(n['callee'])
        functions[name] = f; active.remove(name)
    for root in config['functions']: discover(root)
    plans = [functions[n] for n in config['functions']] + [functions[n] for n in sorted(set(functions)-set(config['functions']))]
    selected = {n: {0} | {i['offset'] for i in p['instructions'] if i['op']=='ret'} for n,p in functions.items()}
    for p in plans:
        p.update(is_root=p['function'] in config['functions'], paths=[], static_sources=[])
    for root in config['functions']:
        paths = []
        for path in enumerate_paths(root, functions):
            analyzed = symbolic_path(path, functions, config)
            if analyzed is not None: paths.append(analyzed)
        require(paths, 'No feasible supported path')
        functions[root]['paths'] = paths
        functions[root]['static_sources'] = sorted({s for p in paths for s in p['sources']})
        for path in paths:
            keep = {path['sink_node']}
            for step in path['steps']:
                n = next(i for i in functions[step['function']]['instructions'] if i['offset']==step['offset'])
                if n['op'] in BRANCHES | {'call', 'ret', 'push', 'pop'} or (n['args'] and n['args'][0].get('reg')=='rsp'):
                    keep.add(step['id']); selected[step['function']].add(step['offset'])
                if n['op'] in BRANCHES | {'call'}:
                    selected[step['function']].add(n['next'])
                    if n['op'] in BRANCHES: selected[step['function']].add(n['target'])
            while True:
                before = len(keep)
                keep.update(e['source'] for e in path['edges'] if e['target'] in keep)
                if len(keep)==before: break
            for s in path['steps']:
                if s['id'] in keep: selected[s['function']].add(s['offset'])
    for p in plans:
        p['probe_offsets'] = sorted(selected[p['function']])
        p['probe_counts'] = dict(selected=len(p['probe_offsets']), all_instructions=len(p['instructions']))
        for path in p['paths']:
            path['schedule'] = [[s['function'],s['offset'],s['depth']] for s in path['steps'] if s['offset'] in selected[s['function']]]
    return plans


class Machine:
    def __init__(self, event, config):
        self.regs = dict(zip(REGS,event['regs'])); self.initial = dict(self.regs)
        self.flags = event['flags'] & CCMASK
        self.src, self.dst, self.sp = event['src_addr'], event['dst_addr'], event['root_sp']
        require(self.sp == self.regs['rsp'] and self.sp % 8 == 0, 'Invalid root stack')
        require(self.src % 4 == self.dst % 4 == 0, 'Unaligned fields')
        ranges = [(self.src,4*len(config['input_fields'])),(self.dst,4*len(config['output_fields'])),(self.sp-STACK_BYTES,STACK_BYTES+8)]
        require(all(not (a < b+nb and b < a+na) for i,(a,na) in enumerate(ranges) for b,nb in ranges[i+1:]), 'Boundary memory regions overlap')
        self.memory, self.stack_written, self.returns = {}, set(), []
        self.config = config
        for start,values,fmt in [(self.src,event['inputs'],'I'),(self.dst,event['outputs'],'I'),(self.sp-STACK_BYTES,event['stack'],'Q')]:
            self.memory.update({start+i:v for i,v in enumerate(struct.pack('<'+fmt*len(values),*values))})

    def address(self, arg):
        return (self.regs[arg['reg']] + (self.regs[arg['index']]*arg['scale'] if arg.get('index') else 0) + arg['offset']) & MASK64

    def read_mem(self, address, width):
        require(all(address+i in self.memory for i in range(width)), 'Read outside declared memory')
        return int.from_bytes(bytes(self.memory[address+i] for i in range(width)), 'little')

    def write_mem(self, address, width, value):
        output = self.dst <= address and address+width <= self.dst+4*len(self.config['output_fields'])
        stack = self.sp-STACK_BYTES <= address and address+width <= self.sp
        require(output or stack, 'Write outside output/stack regions')
        for i,b in enumerate((value & ((1<<(width*8))-1)).to_bytes(width,'little')):
            self.memory[address+i] = b
            if stack: self.stack_written.add(address+i)

    def read(self, arg):
        if arg['kind']=='imm': return arg['value'] & ((1<<arg['width'])-1)
        if arg['kind']=='reg': return self.regs[arg['reg']] & ((1<<arg['width'])-1)
        return self.read_mem(self.address(arg),arg['width']//8)

    def write(self, arg, value):
        value &= (1<<arg['width'])-1
        if arg['kind']=='reg': self.regs[arg['reg']] = value
        else: self.write_mem(self.address(arg),arg['width']//8,value)

    def check(self,event,step,bases):
        require(event['source_error']==event['destination_error']==event['stack_error']==0,'User memory read failed')
        require((event['src_addr'],event['dst_addr'],event['root_sp'])==(self.src,self.dst,self.sp),'Boundary addresses changed')
        require(event['depth']==step['depth'],'Call depth contradicts path')
        require(event['ip']==bases[step['function']]+step['offset'],'Instruction IP mismatch')
        require(event['regs']==[self.regs[r] for r in REGS],'Register state mismatch')
        require((event['flags'] & CCMASK)==self.flags,'Condition flags mismatch')
        for name,base in [('inputs',self.src),('outputs',self.dst)]:
            require(event[name]==[self.read_mem(base+4*i,4) for i in range(len(event[name]))],name+' changed unexpectedly')
        raw = struct.pack('<'+'Q'*len(event['stack']),*event['stack'])
        require(all(raw[a-(self.sp-STACK_BYTES)]==self.memory[a] for a in self.stack_written),'Written stack/return-address state mismatch')

    def step(self,node,bases):
        op,args,fn = node['op'],node['args'],node['function']
        if op=='call':
            ret = bases[fn]+node['next']; self.regs['rsp'] -= 8
            self.write_mem(self.regs['rsp'],8,ret); self.returns.append(ret)
            return bases[node['callee']]
        if op=='ret':
            if self.returns:
                ret = self.read_mem(self.regs['rsp'],8)
                require(ret==self.returns.pop(),'Return address mismatch')
                self.regs['rsp'] += 8; return ret
            require(all(self.regs[r]==self.initial[r] for r in (*SAVED_REGS,'rsp')),'Unbalanced root stack/callee-saved registers')
            return None
        if op in BRANCHES: return bases[fn]+(node['target'] if branch_taken(op,self.flags) else node['next'])
        if op=='jmp': return bases[fn]+node['target']
        if op=='push':
            value=self.read(args[0]); self.regs['rsp']-=8; self.write_mem(self.regs['rsp'],8,value)
        elif op=='pop':
            self.write(args[0],self.read_mem(self.regs['rsp'],8)); self.regs['rsp']+=8
        elif op in ('mov','lea','xor','add','sub','test','cmp'):
            a,b=args
            if op=='lea': result=self.address(b)
            elif op=='mov': result=self.read(b)
            else:
                left,right=self.read(a),self.read(b)
                self.flags=flags_for(op,left,right,a['width'])
                result=(left^right) if op=='xor' else (left+right) if op=='add' else (left-right) if op in ('sub','cmp') else left&right
            if op not in ('test','cmp'): self.write(a,result)
        require(self.sp-STACK_BYTES <= self.regs['rsp'] <= self.sp,'Dynamic stack exceeds bound')
        return bases[fn]+node['next']


def infer(events,plans,config,runtime_bases):
    require(runtime_bases is not None,'Executable mapping required for cross-function replay')
    if len({e['pid_tid'] for e in events})>1:
        return dict(results=[],issues=[dict(error='Multiple threads unsupported')],oracle_used_for_inference=False)
    groups={}
    for e in events: groups.setdefault((e['pid_tid'],e['call_id']),[]).append(e)
    results,issues=[],[]
    maps={p['function']:{n['offset']:n for n in p['instructions']} for p in plans}
    for (tid,call),rows in sorted(groups.items()):
        try:
            rows.sort(key=lambda r:r['sequence']);first=rows[0]
            require([r['sequence'] for r in rows]==list(range(len(rows))),'Missing or duplicate sequence')
            rid=first['root'];require(0<=rid<len(plans) and plans[rid]['is_root'],'Unknown root')
            require(first['function']==rid and first['offset']==0 and first['depth']==1,'Missing root entry')
            root=plans[rid]
            require(all(r['root']==rid and 0<=r['function']<len(plans) for r in rows),'Mixed roots or unknown functions')
            require(all(rows[i]['timestamp']<=rows[i+1]['timestamp'] for i in range(len(rows)-1)),'Non-monotonic sequence')
            require(all(len(r['regs'])==16 and len(r['inputs'])==len(config['input_fields']) and len(r['outputs'])==len(config['output_fields']) and len(r['stack'])==STACK_WORDS for r in rows),'Observation shape mismatch')
            schedule=[[plans[r['function']]['function'],r['offset'],r['depth']] for r in rows]
            candidates=[p for p in root['paths'] if p['schedule']==schedule]
            require(candidates,'Observed call/return path outside plan')
            survivors=[]
            for path in candidates:
                try:
                    machine=Machine(first,config);position=0
                    for i,step in enumerate(path['steps']):
                        if position<len(rows) and [step['function'],step['offset'],step['depth']]==schedule[position]:
                            machine.check(rows[position],step,runtime_bases);position+=1
                        nxt=machine.step(maps[step['function']][step['offset']],runtime_bases)
                        expected=None if i+1==len(path['steps']) else runtime_bases[path['steps'][i+1]['function']]+path['steps'][i+1]['offset']
                        require(nxt==expected,'Branch/call/return disagrees with candidate')
                    require(position==len(rows),'Unconsumed evidence');survivors.append(path)
                except ValueError: continue
            require(survivors,'All paths contradicted by machine/stack observations')
            edges={(e['source'],e['target'],e['kind']) for p in survivors for e in p['edges']}
            keep={p['sink_node'] for p in survivors};kinds={'data','address','argument','return'}
            while True:
                old=len(keep);keep.update(a for a,b,k in edges if b in keep and k in kinds)
                if old==len(keep):break
            metadata={n:m for p in survivors for n,m in p['nodes'].items()}
            prefix='%s:%s:'%(tid,call)
            nodes=[]
            points={p['function']:set(p['probe_offsets']) for p in plans}
            for n in sorted(keep):
                meta=dict(metadata.get(n,dict(kind='boundary')))
                if 'offset' in meta: meta['evidence']='observed-and-modeled' if meta['offset'] in points[meta['function']] else 'modeled'
                nodes.append(dict(id=prefix+n,static_node=n,**meta))
            graph=dict(nodes=nodes,edges=[dict(source=prefix+a,target=prefix+b,kind=k) for a,b,k in sorted(edges) if a in keep and b in keep and k in kinds],identity_scope='root invocation plus direct-call-site context; no loops/recursion or persistent heap history')
            calls=[dict(function=s['function'],context=s['context'],depth=s['depth']) for s in survivors[0]['steps'] if s['offset']==0]
            results.append(dict(pid_tid=tid,call_id=call,function=root['function'],status='resolved' if len(survivors)==1 else 'ambiguous',
                sources=sorted({s for p in survivors for s in p['sources']}),static_sources=root['static_sources'],
                value=rows[-1]['outputs'][config['output_fields'].index(config['sink_field'])],sink='output.'+config['sink_field'],
                candidate_paths=len(survivors),call_instances=calls,observed_schedule=schedule,dependency_graph=graph,
                basis='observed direct-call path, register/memory/return-address checks and bounded instruction semantics'))
        except (ValueError,KeyError,IndexError,TypeError,struct.error) as exc:
            issues.append(dict(pid_tid=tid,call_id=call,error=str(exc)))
    return dict(results=results,issues=issues,oracle_used_for_inference=False,
                scope='single-threaded acyclic direct calls; context-qualified explicit data dependencies')
