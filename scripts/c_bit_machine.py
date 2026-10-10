"""Bounded x86-64 explicit bit routing for a configured C function.

No GIF knowledge, inferred source indexes, or oracle answers live here.
Per-bit origin sets survive partial registers, memory overwrites, shifts and
constant masks. Arithmetic conservatively unions operand origins. Address and
branch operands are tracked separately from returned explicit data origins.
Unsupported instructions/regions/undefined branch flags raise ValueError.
"""
from dataclasses import dataclass
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_REG, X86_OP_IMM, X86_OP_MEM
from interproc_model import flags_for
from hybrid_model import branch_taken

REGS = ['rax', 'rbx', 'rcx', 'rdx', 'rsi', 'rdi', 'rbp', 'rsp'] + ['r'+str(i) for i in range(8, 16)]
ALIASES = {}
for full, d, w, b in [('rax','eax','ax','al'),('rbx','ebx','bx','bl'),('rcx','ecx','cx','cl'),
                       ('rdx','edx','dx','dl'),('rsi','esi','si','sil'),('rdi','edi','di','dil'),
                       ('rbp','ebp','bp','bpl'),('rsp','esp','sp','spl')]:
    for name, size in ((full,64),(d,32),(w,16),(b,8)):
        ALIASES[name] = (full, size)
for i in range(8, 16):
    for suffix, size in (('',64),('d',32),('w',16),('b',8)):
        ALIASES['r'+str(i)+suffix] = ('r'+str(i), size)
UNKNOWN = frozenset({'<unknown>'})
EMPTY = frozenset()


def check(ok, message):
    if not ok:
        raise ValueError(message)


@dataclass(frozen=True)
class Value:
    number: int
    bits: tuple

    @property
    def width(self):
        return len(self.bits)

    @property
    def origins(self):
        return frozenset().union(*self.bits)

    def low(self, width):
        check(0 < width <= self.width, 'Invalid partial value width')
        return Value(self.number & ((1 << width)-1), self.bits[:width])


def value(n, width, origins=EMPTY):
    return Value(n & ((1 << width)-1), (origins,) * width)


def decode(code, start):
    engine = Cs(CS_ARCH_X86, CS_MODE_64)
    engine.detail = True
    result = {}
    supported = {'mov','movzx','lea','push','pop','add','sub','xor','or','and','shl','shr','sar',
                 'cmp','test','je','jne','jle','jg','jbe','ja','jl','jge','jb','jae','jmp','call','ret','nop','endbr64'}
    for ins in engine.disasm(code, start):
        check(ins.mnemonic in supported, 'Unsupported C instruction: '+ins.mnemonic+' '+ins.op_str)
        args = []
        for arg in ins.operands:
            if arg.type == X86_OP_REG:
                name = ins.reg_name(arg.reg)
                check(name in ALIASES, 'Unsupported register '+name)
                args.append(dict(kind='reg', name=name, width=arg.size*8))
            elif arg.type == X86_OP_IMM:
                args.append(dict(kind='imm', value=arg.imm, width=arg.size*8))
            else:
                check(arg.type == X86_OP_MEM and arg.mem.segment == 0, 'Unsupported memory operand')
                base, index = ins.reg_name(arg.mem.base), ins.reg_name(arg.mem.index)
                check((not base or base in REGS) and (not index or index in REGS), 'Unsupported effective address')
                args.append(dict(kind='mem', base=base, index=index, scale=arg.mem.scale,
                                 offset=arg.mem.disp, width=arg.size*8))
        result[ins.address] = dict(address=ins.address, next=ins.address+ins.size, op=ins.mnemonic,
                                  asm=ins.mnemonic+' '+ins.op_str, code=bytes(ins.bytes).hex(), args=args)
    check(result and sum(len(bytes.fromhex(r['code'])) for r in result.values()) == len(code),
          'Incomplete function disassembly')
    for row in result.values():
        if row['op'].startswith('j') or row['op'] == 'call':
            check(len(row['args']) == 1 and row['args'][0]['kind'] == 'imm', 'Indirect transfer unsupported')
            if row['op'] != 'call':
                check(row['args'][0]['value'] in result, 'Branch leaves configured function')
    return result


class Machine:
    def __init__(self, registers):
        check(set(registers) == set(REGS), 'Incomplete entry register snapshot')
        self.reg = {r: value(registers[r],64,UNKNOWN) for r in REGS}
        self.mem = {}
        self.regions = []
        self.flags = None
        self.flag_origins = EMPTY
        self.control_origins = set()
        self.address_origins = set()
        self.memory_writes = 0
        self.steps = []

    def region(self, address, size):
        check(0 < address < address+size < 1 << 64, 'Invalid region')
        check(all(address+size <= a or a+n <= address for a,n in self.regions), 'Overlapping regions')
        self.regions.append((address,size))

    def range(self, address, size):
        check(any(a <= address and address+size <= a+n for a,n in self.regions), 'Memory outside declared region')

    def load(self, address, width):
        self.range(address, width//8)
        check(all(address+i in self.mem for i in range(width//8)), 'Uninitialized memory read')
        data = [self.mem[address+i] for i in range(width//8)]
        return Value(sum(v.number << (8*i) for i,v in enumerate(data)), sum((v.bits for v in data), ()))

    def store(self, address, v):
        check(v.width in (8,16,32,64), 'Unsupported memory width')
        self.range(address, v.width//8)
        for i in range(v.width//8):
            self.mem[address+i] = Value((v.number >> (8*i)) & 255, v.bits[i*8:i*8+8])
        self.memory_writes += 1

    def seed(self, address, data, unknown=False):
        for i,b in enumerate(data):
            self.store(address+i, value(b,8,UNKNOWN if unknown else EMPTY))

    def regread(self, name):
        full, width = ALIASES[name]
        return self.reg[full].low(width)

    def regwrite(self, name, v):
        full, width = ALIASES[name]
        check(width == v.width, 'Register write width mismatch')
        if width == 64:
            self.reg[full] = v
        elif width == 32:
            self.reg[full] = Value(v.number, v.bits+(EMPTY,)*32)
        else:
            old = self.reg[full]
            self.reg[full] = Value((old.number & ~((1 << width)-1)) | v.number, v.bits+old.bits[width:])

    def address(self, arg):
        base = self.reg[arg['base']] if arg['base'] else value(0,64)
        index = self.reg[arg['index']] if arg['index'] else value(0,64)
        self.address_origins.update(base.origins | index.origins)
        check('<unknown>' not in base.origins | index.origins, 'Unmodeled address dependency')
        return value(base.number+index.number*arg['scale']+arg['offset'],64,base.origins|index.origins)

    def read(self, arg):
        if arg['kind'] == 'imm':
            return value(arg['value'],arg['width'])
        if arg['kind'] == 'reg':
            return self.regread(arg['name'])
        return self.load(self.address(arg).number,arg['width'])

    def write(self, arg, v):
        if arg['kind'] == 'reg':
            self.regwrite(arg['name'],v)
        else:
            check(arg['kind'] == 'mem', 'Invalid destination')
            self.store(self.address(arg).number,v)

    def step(self, row):
        op, args = row['op'], row['args']
        self.steps.append(row['address'])
        next_pc = row['next']
        if op in ('nop','endbr64'):
            return next_pc
        if op == 'ret':
            return None
        if op == 'call':
            raise ValueError('Call requires an explicit observed summary')
        if op.startswith('j'):
            if op == 'jmp':
                return args[0]['value']
            check(self.flags is not None and '<unknown>' not in self.flag_origins, 'Branch reads undefined/unmodeled flags')
            return args[0]['value'] if branch_taken(op,self.flags) else next_pc
        if op == 'push':
            v = self.read(args[0]); sp = self.reg['rsp'].number-8
            self.reg['rsp'] = value(sp,64); self.store(sp,v)
            return next_pc
        if op == 'pop':
            sp = self.reg['rsp'].number
            self.write(args[0],self.load(sp,64)); self.reg['rsp'] = value(sp+8,64)
            return next_pc
        dst, src = args
        if op == 'lea':
            self.write(dst,self.address(src).low(dst['width']))
            return next_pc
        b = self.read(src)
        if op in ('mov','movzx'):
            if op == 'movzx':
                check(dst['width'] >= b.width, 'Invalid zero extension')
                b = Value(b.number,b.bits+(EMPTY,)*(dst['width']-b.width))
            self.write(dst,b)
            return next_pc
        a = self.read(dst)
        if op in ('cmp','test'):
            self.flags = flags_for(op,a.number,b.number,a.width)
            self.flag_origins = a.origins | b.origins
            self.control_origins.update(a.origins | b.origins)
            return next_pc
        mask = (1 << a.width)-1
        if op in ('shl','shr','sar'):
            n = b.number & (63 if a.width == 64 else 31)
            if n == 0:
                # A 32-bit destination still clears the upper register half.
                # The low operand and arithmetic flags remain unchanged.
                self.write(dst,a)
                return next_pc
            if op == 'shl':
                bits = ((EMPTY,)*n+a.bits)[:a.width]
                number = a.number << n
            else:
                fill = a.bits[-1] if op == 'sar' else EMPTY
                bits = (a.bits[n:]+(fill,)*n)[:a.width]
                signed = a.number-(1 << a.width) if op == 'sar' and a.number >> (a.width-1) else a.number
                number = signed >> n
            bits = tuple(x | b.origins for x in bits)
            self.flags = None  # reject a subsequent condition until CMP/TEST
        elif op in ('and','or','xor'):
            check(a.width == b.width, 'Bitwise width mismatch')
            if op == 'xor' and dst == src:
                bits = (EMPTY,)*a.width
                number = 0
            else:
                number = a.number & b.number if op == 'and' else a.number | b.number if op == 'or' else a.number ^ b.number
                routed = []
                for k,(aa,bb) in enumerate(zip(a.bits,b.bits)):
                    av,bv = (a.number>>k)&1,(b.number>>k)&1
                    # Only a proven untainted constant may mask a source bit;
                    # equal observed source values never establish independence.
                    killed = op == 'and' and ((not aa and not av) or (not bb and not bv))
                    killed |= op == 'or' and ((not aa and av) or (not bb and bv))
                    routed.append(EMPTY if killed else aa | bb)
                bits = tuple(routed)
            self.flags = flags_for('test',number,number,a.width)
        elif op in ('add','sub'):
            number = a.number+b.number if op == 'add' else a.number-b.number
            bits = (a.origins | b.origins,)*a.width
            self.flags = flags_for(op,a.number,b.number,a.width)
        else:
            raise ValueError('Unsupported execution '+op)
        self.flag_origins = frozenset().union(*bits)
        self.write(dst,Value(number & mask,bits))
        return next_pc
