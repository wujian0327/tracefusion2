"""Compiler-built fixtures and independent Unicorn execution for replay tests.

Unicorn is optional for the existing suite: pip install unicorn==2.1.4.
These are emulated instruction observations, not real uprobe evidence. Native
fixture stdout is checked separately and is read only by the evaluator.
"""
import copy
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import hybrid_model as model
import hybrid_provenance as app

try:
    import unicorn as uc
    from unicorn import x86_const as x86
except ImportError:
    uc = None

SCENARIO = app.ROOT / 'scenarios/hybrid-provenance'


def emulated_events(binary, plans, config):
    """External ISA emulator executes ELF machine bytes, not our step() model."""
    elf = binary.read_bytes()
    phoff = struct.unpack_from('<Q', elf, 32)[0]
    size, number = struct.unpack_from('<HH', elf, 54)
    segments = [struct.unpack_from('<IIQQQQQQ', elf, phoff + i * size) for i in range(number)]
    rows, bases, call = [], {}, 0
    for round_id in range(2):
        for fid, p in enumerate(plans):
            base = 0x1000000 + p['symbol_address']
            bases[p['function']] = base
            segment = next(s for s in segments if s[0] == 1 and s[3] <= p['symbol_address'] < s[3] + s[5])
            file_offset = segment[2] + p['symbol_address'] - segment[3]
            code = elf[file_offset:file_offset + p['symbol_size']]
            for select in (0, 1):
                call += 1
                cpu = uc.Uc(uc.UC_ARCH_X86, uc.UC_MODE_64)
                cpu.mem_map(base & ~4095, 8192)
                cpu.mem_write(base, code)
                src, dst, stack, stop = 0x2000000, 0x3000000, 0x4000000, 0x5000000
                for addr in (src, dst, stack, stop):
                    cpu.mem_map(addr, 4096)
                fields = {'secret': 424242 + round_id, 'public_value': 424242 + round_id, 'noise': 99}
                cpu.mem_write(src, struct.pack('<' + 'I' * len(config['input_fields']), *(fields[f] for f in config['input_fields'])))
                cpu.mem_write(dst, struct.pack('<II', 0xdeadbeef, 0))
                cpu.mem_write(stack + 2048, struct.pack('<Q', stop))
                cpu.reg_write(x86.UC_X86_REG_RSI, src); cpu.reg_write(x86.UC_X86_REG_RDI, dst)
                cpu.reg_write(x86.UC_X86_REG_RDX, select); cpu.reg_write(x86.UC_X86_REG_RSP, stack + 2048)
                sequence = [0]

                def observe(machine, address, size, user):
                    off = address - base
                    if off not in p['probe_offsets']:
                        return
                    e = dict(timestamp=len(rows) + 1, pid_tid=(123 << 32) | 123, call_id=call,
                             sequence=sequence[0], src_addr=src, dst_addr=dst, ip=address,
                             flags=machine.reg_read(x86.UC_X86_REG_EFLAGS),
                             regs=[machine.reg_read(getattr(x86, 'UC_X86_REG_' + r.upper())) for r in model.REGS],
                             function=fid, offset=off, source_error=0, destination_error=0,
                             inputs=list(struct.unpack('<' + 'I' * len(config['input_fields']), machine.mem_read(src, 4 * len(config['input_fields'])))),
                             outputs=list(struct.unpack('<' + 'I' * len(config['output_fields']), machine.mem_read(dst, 4 * len(config['output_fields'])))))
                    rows.append(e); sequence[0] += 1

                cpu.hook_add(uc.UC_HOOK_CODE, observe)
                cpu.emu_start(base, stop, timeout=1000000, count=1000)
                assert cpu.reg_read(x86.UC_X86_REG_RIP) == stop
    return rows, bases


class StaticTests(unittest.TestCase):
    def test_unsupported_control_flow_is_explicit(self):
        for asm in ('1000: call 2000 <other>\n1005: ret',
                    '1000: jmp 1000 <loop>', '1000: push rbp\n1001: ret',
                    '1000: mov eax,DWORD PTR [rsi+rcx*4]\n1003: ret'):
            with self.subTest(asm=asm), self.assertRaises(ValueError):
                model.decode_function('any_name', asm, {'any_name': (0x1000, 16)})

    def test_unknown_pointer_is_not_silently_ignored(self):
        raw = model.decode_function('any_name', '1000: mov eax,DWORD PTR [r8]\n1003: mov DWORD PTR [rdi],eax\n1005: ret', {'any_name': (0x1000, 6)})
        with self.assertRaisesRegex(ValueError, 'Unresolved memory'):
            model.static_plan(raw, json.loads((SCENARIO / 'config.json').read_text()))

    def test_attach_requires_child_pid(self):
        with self.assertRaises(ValueError):
            app.attach_probes(mock.Mock(), Path('/unused'), [], -1)

    def test_pointer_join_keeps_path_specific_dependencies(self):
        asm = '''1000: lea rax,[rsi+0x4]
1004: test edx,edx
1006: jle 100b <arbitrary+0xb>
1008: mov rax,rsi
100b: mov eax,DWORD PTR [rax]
100d: mov DWORD PTR [rdi],eax
100f: ret'''
        raw = model.decode_function('arbitrary', asm, {'arbitrary': (0x1000, 16)})
        plan = model.static_plan(raw, json.loads((SCENARIO / 'config.json').read_text()))
        self.assertEqual(set(plan['static_sources']), {'input.secret', 'input.public_value'})
        for path in plan['paths']:
            self.assertEqual(len(path['sources']), 1)
            source_edges = {e['source'] for e in path['edges'] if e['target'] == 'i:b' and e['source'].startswith('input.')}
            self.assertEqual(source_edges, set(path['sources']))


@unittest.skipUnless(uc and shutil.which('gcc') and shutil.which('objdump'), 'Requires GCC/binutils and optional unicorn==2.1.4')
class HybridTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.temp.name) / 'build'; cls.out.mkdir()
        cls.binary, cls.plans, cls.config = app.build(SCENARIO, cls.out)
        cls.events, cls.bases = emulated_events(cls.binary, cls.plans, cls.config)
        cls.oracle = [json.loads(l) for l in subprocess.check_output([str(cls.binary)], text=True).splitlines()]
        cls.stats = dict(received_events=len(cls.events), attempted_events=len(cls.events), lost_events=0,
                         submit_errors=0, state_errors=0, process_returncode=0, backend='unicorn-test-only')

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def inference(self, events=None):
        return model.infer(self.events if events is None else events, self.plans, self.config, self.bases)

    def test_actual_machine_bytes_and_native_oracle_agree(self):
        inferred = self.inference()
        result = app.evaluate(inferred, self.oracle, self.stats, self.plans)
        self.assertEqual(inferred['issues'], [])
        self.assertTrue(result['passed'], result)
        self.assertEqual(result['dynamic_source_relations']['precision'], 1.0)
        self.assertEqual(result['dynamic_source_relations']['recall'], 1.0)
        self.assertLess(result['static_source_relations']['precision'], 1.0)

    def test_overwrite_kills_old_origin_and_irrelevant_audit_is_pruned(self):
        p = self.plans[1]
        self.assertEqual(p['static_sources'], ['input.public_value'])
        self.assertLess(p['probe_counts']['selected'], p['probe_counts']['all_instructions'])
        self.assertNotIn('input.noise', self.plans[0]['static_sources'])
        rows = self.inference()['results']
        self.assertEqual(rows[0]['value'], rows[1]['value'])
        self.assertNotEqual(rows[0]['sources'], rows[1]['sources'])
        self.assertEqual(set(rows[6]['sources']), {'input.secret', 'input.public_value'})
        for r in rows:
            graph_sources = {n['static_node'] for n in r['dependency_graph']['nodes'] if n['static_node'].startswith('input.')}
            self.assertEqual(graph_sources, set(r['sources']))

    def test_missing_duplicate_corrupt_read_and_wrong_build_are_rejected(self):
        call_rows = [e for e in self.events if e['call_id'] == 1]
        for kind in ('missing', 'duplicate', 'read', 'register', 'memory', 'ip', 'flags', 'sequence'):
            events = copy.deepcopy(call_rows)
            if kind == 'missing': events.pop(2)
            elif kind == 'duplicate': events.insert(2, copy.deepcopy(events[2]))
            elif kind == 'read': events[-1]['source_error'] = -14
            elif kind == 'register': events[-1]['regs'][0] ^= 1
            elif kind == 'memory': events[-1]['outputs'][0] ^= 1
            elif kind == 'ip':
                for e in events: e['ip'] += 16
            elif kind == 'flags': events[-1]['flags'] ^= 64
            elif kind == 'sequence': events[-1]['sequence'] += 1
            result = self.inference(events)
            with self.subTest(kind=kind):
                self.assertEqual(result['results'], [])
                self.assertTrue(result['issues'])

    def test_loss_absent_call_and_no_events_cannot_pass(self):
        badstats = dict(self.stats, lost_events=1)
        self.assertFalse(app.evaluate(self.inference(), self.oracle, badstats, self.plans)['passed'])
        remaining = [e for e in self.events if e['call_id'] != 1]
        result = app.evaluate(self.inference(remaining), self.oracle, self.stats, self.plans)
        self.assertFalse(result['passed'])
        self.assertEqual(result['static_source_relations']['recall'], 1.0)
        self.assertLess(result['dynamic_source_relations']['recall'], 1.0)
        self.assertFalse(app.evaluate(self.inference([]), self.oracle, dict(self.stats, received_events=0), self.plans)['passed'])

    def test_multiple_threads_are_outside_declared_scope(self):
        events = copy.deepcopy(self.events)
        events[-1]['pid_tid'] += 1
        self.assertTrue(self.inference(events)['issues'])
        self.assertEqual(self.inference(events)['results'], [])

    def test_renamed_relocated_reordered_schema_and_changed_transform(self):
        scenario = Path(self.temp.name) / 'variant'
        scenario.mkdir()
        for f in SCENARIO.iterdir(): shutil.copyfile(f, scenario / f.name)
        names = self.config['functions']
        for name in ('model.h', 'main.c', 'operations.c'):
            p = scenario / name; text = p.read_text().replace('0x55u', '0x66u')
            for old in names: text = text.replace(old, 'renamed_' + old)
            if name == 'model.h': text = text.replace('secret, public_value, noise', 'public_value, secret, noise')
            if name == 'operations.c': text = 'int unrelated_helper(int n) { return n * n + 3; }\n' + text
            p.write_text(text)
        config = copy.deepcopy(self.config)
        config['functions'] = ['renamed_' + n for n in names]
        config['input_fields'] = ['public_value', 'secret', 'noise']
        app.save(scenario / 'config.json', config)
        out = Path(self.temp.name) / 'variant-build'; out.mkdir()
        binary, plans, config = app.build(scenario, out)
        events, bases = emulated_events(binary, plans, config)
        oracle = [json.loads(l) for l in subprocess.check_output([str(binary)], text=True).splitlines()]
        result = model.infer(events, plans, config, bases)
        self.assertTrue(app.evaluate(result, oracle, dict(self.stats, received_events=len(events), attempted_events=len(events)), plans)['passed'])
        self.assertNotEqual(plans[0]['symbol_address'], self.plans[0]['symbol_address'])
        self.assertNotEqual(result['results'][6]['value'], self.inference()['results'][6]['value'])


if __name__ == '__main__':
    unittest.main()
