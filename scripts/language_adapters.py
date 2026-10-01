"""Native-language boundary contracts, separate from dependency propagation.

V1 is deliberately uint32-only. Layout, ABI and execution identity live here;
the x86 instruction interpreter and provenance graph remain shared. This is
not a source-language frontend or a generic runtime decoder.
"""
from dataclasses import dataclass
import re


def require(ok, message):
    if not ok: raise ValueError(message)


@dataclass(frozen=True)
class Field:
    name: str
    offset: int
    width: int = 4


@dataclass(frozen=True)
class FieldLayout:
    fields: tuple

    @property
    def size(self): return max(f.offset + f.width for f in self.fields)

    def field(self, name):
        return next(f for f in self.fields if f.name == name)

    def at(self, offset, width=4):
        matches = [f for f in self.fields if f.offset == offset and f.width == width]
        require(len(matches) == 1, 'Memory outside declared field layout')
        return matches[0]


@dataclass(frozen=True)
class ExecutionPolicy:
    name: str
    identity_register: str | None = None
    attach_existing_tasks: bool = False

    def identity(self, event, registers):
        identity = (event['pid_tid'],)
        if self.identity_register:
            value = event['regs'][registers.index(self.identity_register)]
            require(value != 0, 'Missing goroutine identity')
            identity += (value,)
        return identity

    def validate(self, events, registers):
        # Both V1 adapters deliberately permit only one logical execution
        # context. Go additionally checks G, not just the OS thread number.
        identities = {self.identity(e, registers) for e in events}
        require(len(identities) <= 1, 'Multiple execution contexts unsupported by ' + self.name)

    def group(self, events):
        # After validate(), thread+call is unique for the supported scope.
        groups = {}
        for e in events: groups.setdefault((e['pid_tid'], e['call_id']), []).append(e)
        return groups

    def bpf_key(self):
        return 'bpf_get_current_pid_tgid()'


@dataclass(frozen=True)
class NativeAdapter:
    name: str
    abi: str
    input_register: str
    output_register: str
    selector_register: str
    argument_registers: tuple
    saved_registers: tuple
    context: ExecutionPolicy
    function_pattern: str
    leaf_only: bool = False
    return_register: str = 'rax'

    def validate(self, config):
        require(config['abi'] == self.abi, 'ABI does not match selected language adapter')
        for region in ('input', 'output'):
            fields = config[region + '_fields']
            require(0 < len(fields) <= 8 and len(set(fields)) == len(fields), 'Invalid field schema')
            require(all(re.fullmatch(r'[A-Za-z_]\w*', f) for f in fields), 'Invalid field name')
        require(config['sink_field'] in config['output_fields'], 'Unknown sink field')
        require(set(config['sensitive_fields']) <= set(config['input_fields']), 'Unknown sensitive field')
        names = config['functions']
        require(0 < len(names) <= 16 and len(set(names)) == len(names), 'Invalid function scope')
        require(all(re.fullmatch(self.function_pattern, n) for n in names), 'Invalid function symbol')
        require(config.get('field_layout', 'packed-u32') == 'packed-u32', 'Only contiguous uint32 fields supported')

    def layout(self, config, region):
        return FieldLayout(tuple(Field(n, i*4) for i,n in enumerate(config[region+'_fields'])))

    def seeds(self, include_stack=False):
        result = {
            self.input_register: dict(refs=frozenset({'arg.input'}), address=('input', 0)),
            self.output_register: dict(refs=frozenset({'arg.output'}), address=('output', 0)),
            self.selector_register: dict(origins=frozenset({'arg.select'}), refs=frozenset({'arg.select'})),
        }
        if include_stack: result['rsp'] = dict(refs=frozenset({'arg.stack'}), address=('stack', 0))
        return result

    def check_entry(self, event, registers):
        require(event['regs'][registers.index(self.input_register)] == event['src_addr'] and
                event['regs'][registers.index(self.output_register)] == event['dst_addr'],
                'Boundary pointers contradict adapter ABI')

    def bpf_pointer(self, which):
        if self.name == 'c-sysv-u32':
            return 'PT_REGS_PARM2(ctx)' if which == 'input' else 'PT_REGS_PARM1(ctx)'
        reg = self.input_register if which == 'input' else self.output_register
        fields = {'rax': 'ax', 'rbx': 'bx', 'rcx': 'cx', 'rdi': 'di', 'rsi': 'si', 'rdx': 'dx'}
        return 'ctx->' + fields.get(reg, reg)

    def describe(self, config):
        return dict(name=self.name, abi=self.abi, context_policy=self.context.name,
                    input_register=self.input_register, output_register=self.output_register,
                    selector_register=self.selector_register, return_register=self.return_register, leaf_only=self.leaf_only,
                    fields={r:[vars(f) for f in self.layout(config,r).fields] for r in ('input','output')})


C = NativeAdapter('c-sysv-u32', 'linux-x86_64-sysv', 'rsi', 'rdi', 'rdx',
    ('rdi','rsi','rdx','rcx','r8','r9'), ('rbx','rbp','r12','r13','r14','r15'),
    ExecutionPolicy('single-os-thread'), r'[A-Za-z_]\w*')
GO = NativeAdapter('go-amd64-u32-leaf', 'go-amd64-abiinternal', 'rbx', 'rax', 'rcx',
    ('rax','rbx','rcx','rdi','rsi','r8','r9','r10','r11'), ('rbp','r14'),
    ExecutionPolicy('single-pinned-goroutine', 'r14', True), r'main\.[A-Za-z_]\w*', leaf_only=True)
ADAPTERS = {a.name: a for a in (C, GO)}


def get_adapter(config):
    name = config.get('adapter', C.name)
    require(name in ADAPTERS, 'Unknown language adapter: ' + str(name))
    adapter = ADAPTERS[name]
    adapter.validate(config)
    return adapter
