"""Checks that compatibility repairs preserve data and reject false alignment."""
import struct
import tempfile
from pathlib import Path
import unittest

from audit_flowdist_coverage import canonical_rows, coverage
from normalize_flowdist_class_literals import normalize, canonical


class CompatibilityChecks(unittest.TestCase):
    def test_class_name_repair_preserves_shared_business_string(self):
        name = b'LLexample/Service;;'
        # Class and business String deliberately share the malformed UTF8 entry.
        pool = b'\x01' + struct.pack('>H', len(name)) + name + b'\x07\x00\x01\x08\x00\x01'
        tail = b'unchanged-bytecode-and-attributes'
        data = b'\xca\xfe\xba\xbe\x00\x00\x00\x34' + struct.pack('>H', 4) + pool + tail
        fixed, changes = normalize(data)
        self.assertEqual(len(changes), 1)
        self.assertEqual(struct.unpack_from('>H', fixed, 8)[0], 5)
        old_pool = fixed[10:10 + len(pool)]
        self.assertEqual(old_pool[:-6], pool[:-6])
        self.assertEqual(old_pool[-6:], b'\x07\x00\x04\x08\x00\x01')
        self.assertTrue(fixed.endswith(tail))
        self.assertEqual(normalize(fixed), (fixed, []))

    def test_array_descriptor(self):
        self.assertEqual(canonical('[[LLexample/Service;;'), '[[Lexample/Service;')
        self.assertEqual(canonical('[I'), '[I')

    def test_local_renaming_preserves_def_use_and_constants(self):
        a = ['<C: int f()> - i0 = 3', '<C: int f()> - i1 = i0 + 1', '<C: int f()> - return i1']
        b = ['<C: int f()> - i7 = 3', '<C: int f()> - i9 = i7 + 1', '<C: int f()> - return i9']
        self.assertEqual(canonical_rows(a), canonical_rows(b))
        self.assertNotEqual(canonical_rows(a), canonical_rows(b[:-1] + ['<C: int f()> - return i7']))
        self.assertNotEqual(canonical_rows(a), canonical_rows([b[0].replace('3', '4'), *b[1:]]))
        self.assertNotEqual(canonical_rows(['<C: void f()> - "i0"']), canonical_rows(['<C: void f()> - "i9"']))

    def test_report_must_equal_measured_branch_union(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / 'coverage.out'
            report.write_text('Statements covered (based on branch coverage): 1 2\nTotal statements covered: 2/4Branches covered: 0\nTotal branches covered: 1/2\n')
            self.assertEqual(coverage(report, [{1, 2}, {3}], 4), ({0}, {1, 2}))
            report.write_text(report.read_text().replace('coverage): 1 2', 'coverage): 1 3'))
            with self.assertRaises(ValueError):
                coverage(report, [{1, 2}, {3}], 4)

    def test_appended_shutdown_snapshot_includes_business_statements(self):
        with tempfile.TemporaryDirectory() as directory:
            report=Path(directory)/'coverage.out'
            startup='Statements covered (based on branch coverage): 1 2\nTotal statements covered: 2/4Branches covered: 0\nTotal branches covered: 1/2\n'
            shutdown='Statements covered (based on branch coverage): 1 2 3\nTotal statements covered: 3/4Branches covered: 0 1\nTotal branches covered: 2/2\n'
            report.write_text(startup+shutdown)
            self.assertEqual(coverage(report,[{1,2},{3}],4),({0,1},{1,2,3}))
            # Author cache bug: branch hits increase but statements stay stale.
            report.write_text(startup+shutdown.replace('coverage): 1 2 3','coverage): 1 2').replace('3/4','2/4'))
            with self.assertRaisesRegex(ValueError,'differs from measured'):
                coverage(report,[{1,2},{3}],4)


if __name__ == '__main__':
    unittest.main()
