import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import uprobe_assignment as app


ASM = '''0000000000001000 <copy_secret>:
    1000: mov eax,DWORD PTR [rsi]
    1002: mov DWORD PTR [rdi],eax
    1004: ret

0000000000001010 <copy_public>:
    1010: mov eax,DWORD PTR [rsi+0x4]
    1013: mov DWORD PTR [rdi],eax
    1015: ret

0000000000001020 <transform_secret>:
    1020: mov eax,DWORD PTR [rsi]
    1022: xor eax,0x55
    1025: mov DWORD PTR [rdi],eax
    1027: ret
'''


def fixture_events(plans):
    rows = []
    for fid, plan in enumerate(plans):
        for stage in range(len(plan['instructions'])):
            value = 424242
            if plan['xor_mask'] is not None and stage >= plan['store_stage']:
                value ^= plan['xor_mask']
            rows.append({'timestamp': 100 * fid + stage, 'pid_tid': 123, 'call_id': fid + 1,
                         'function': fid, 'stage': stage, 'src_addr': 1000, 'dst_addr': 2000,
                         'source_error': 0, 'destination_error': 0,
                         'secret': 424242, 'public_value': 424242, 'eax': value,
                         'output': value if stage == plan['post_store_stage'] else 0xdeadbeef})
    return rows


class InstructionTests(unittest.TestCase):
    def setUp(self):
        self.plans = [app.plan_function(name, ASM) for name in app.FUNCTIONS]
        self.events = fixture_events(self.plans)

    def test_equal_values_have_different_instruction_sources_and_transform(self):
        result = app.infer(self.events, self.plans)
        self.assertEqual(result['issues'], [])
        rows = result['assignments']
        self.assertEqual([r['source_field'] for r in rows], ['secret', 'public_value', 'secret'])
        self.assertEqual(rows[0]['new_value'], rows[1]['new_value'])
        self.assertNotEqual(rows[0]['source_address'], rows[1]['source_address'])
        self.assertEqual(rows[2]['new_value'], 424242 ^ 0x55)
        self.assertFalse(result['oracle_used_for_inference'])

    def test_decoder_uses_load_operand_not_function_name(self):
        changed = ASM.replace('1000: mov eax,DWORD PTR [rsi]', '1000: mov eax,DWORD PTR [rsi+0x4]')
        self.assertEqual(app.plan_function('copy_secret', changed)['source_field'], 'public_value')

    def test_unrecognized_instruction_region_is_refused(self):
        cases = [ASM.replace('xor eax,0x55', 'add eax,0x55'),
                 ASM.replace('mov DWORD PTR [rdi],eax', 'mov DWORD PTR [rdi],edx'),
                 ASM.replace('1022: xor', '1021: call 5000\n    1022: xor')]
        for asm in cases:
            with self.subTest(asm=asm), self.assertRaises(ValueError):
                app.plan_function('transform_secret', asm)

    def test_missing_and_contradictory_events_are_not_assignments(self):
        for kind in ('missing', 'read_error', 'register', 'memory', 'pointer', 'duplicate'):
            rows = copy.deepcopy(self.events)
            if kind == 'missing':
                rows.pop(1)
            elif kind == 'read_error':
                rows[1]['source_error'] = -14
            elif kind == 'register':
                rows[1]['eax'] = 0
            elif kind == 'memory':
                rows[2]['output'] = 0
            elif kind == 'pointer':
                rows[1]['src_addr'] += 4
            else:
                rows.insert(1, rows[1].copy())
            with self.subTest(kind=kind):
                result = app.infer(rows, self.plans)
                self.assertEqual(len(result['assignments']), 2)
                self.assertEqual(len(result['issues']), 1)

    def test_event_loss_and_absent_oracle_prevent_success(self):
        inferred = app.infer(self.events, self.plans)
        oracle = [{'sequence': i + 1, 'function': name, 'expected_field': field, 'output': value}
                  for i, (name, field, value) in enumerate(zip(app.FUNCTIONS,
                    ('secret', 'public_value', 'secret'), (424242, 424242, 424242 ^ 0x55)))]
        stats = dict(lost_events=0, submit_errors=0, state_errors=0, attempted_events=10,
                     received_events=10, process_returncode=0)
        self.assertEqual(app.evaluate(inferred, oracle, stats)['status'], 'selected_assignment_checks_passed')
        self.assertEqual(app.evaluate(inferred, [], stats)['status'], 'incomplete')
        for key in ('lost_events', 'submit_errors', 'state_errors', 'process_returncode'):
            with self.subTest(key=key):
                self.assertEqual(app.evaluate(inferred, oracle, dict(stats, **{key: 1}))['status'], 'incomplete')

    @unittest.skipUnless(shutil.which('gcc') and shutil.which('objdump'), 'gcc/binutils required')
    def test_actual_optimized_binary_and_independent_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary, plans = app.build(Path(tmp))
            oracle = [json.loads(line) for line in subprocess.check_output([str(binary)], text=True).splitlines()]
            self.assertEqual(len(oracle), 6)
            self.assertEqual([p['source_field'] for p in plans], ['secret', 'public_value', 'secret'])
            for row in oracle:
                expected = row['secret'] ^ 0x55 if row['function'] == 'transform_secret' else row['secret']
                self.assertEqual(row['output'], expected)
                self.assertEqual(row['secret'], row['public_value'])


if __name__ == '__main__':
    unittest.main()
