"""Log integrity gates; these synthetic records are NOT Pin execution evidence."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from external_compare import compare_truth, parse_observation


class ExternalLogTests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            dict(kind='source_boundary', g=100, tid=1, preparation_error=False),
            dict(kind='source_field_pair', index=0, pointer=200, units=1, nanos=0),
            dict(kind='source_field_pair', index=1, pointer=300, units=2, nanos=0),
            dict(kind='sink', output=[3, 0], Units=[1, 2, 3, 4], Nanos=[2, 4]),
            dict(kind='finish', exit_code=0, source_hits=1, sink_hits=1, end_hits=1,
                 bad=False, unhandled_opcode_kinds=0, performance_eligible=False)]

    def parse(self, rows):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'events.jsonl'
            p.write_text('\n'.join(json.dumps(r) for r in rows))
            return parse_observation(p)

    def test_distinct_labels_preserved_despite_equal_values(self):
        self.rows[1]['units'] = self.rows[2]['units'] = 2
        result = self.parse(self.rows)
        self.assertEqual(result['origins']['Nanos'], ['items[0].Cost.Nanos', 'shipping.Nanos'])

    def test_truncated_tool_output_rejected(self):
        with self.assertRaises(ValueError):
            self.parse(self.rows[:-1])

    def test_missing_source_packet_rejected(self):
        rows = copy.deepcopy(self.rows)
        del rows[1]
        with self.assertRaises(ValueError):
            self.parse(rows)

    def test_unknown_label_rejected(self):
        self.rows[-2]['Units'].append(5)
        with self.assertRaises(ValueError):
            self.parse(self.rows)

    def test_uncovered_instruction_rejected(self):
        self.rows.insert(-1, dict(kind='unhandled_opcode', pc=123, opcode=999))
        with self.assertRaises(ValueError):
            self.parse(self.rows)

    def test_reordered_sink_rejected(self):
        self.rows[0], self.rows[-2] = self.rows[-2], self.rows[0]
        with self.assertRaises(ValueError):
            self.parse(self.rows)

    def test_failed_preparation_requires_no_sink(self):
        self.rows[0]['preparation_error'] = True
        with self.assertRaises(ValueError):
            self.parse(self.rows)
        self.rows[-1]['sink_hits'] = 0
        result = self.parse([self.rows[0], self.rows[-1]])
        self.assertEqual(result['status'], 'no_sink')

    def test_wrong_set_not_accepted_from_correct_value(self):
        result = self.parse(self.rows)
        truth = dict(sink_present=True, output=result['output'], origins=copy.deepcopy(result['origins']))
        truth['origins']['Units'].remove('shipping.Units')
        self.assertFalse(compare_truth(result, truth)['matched'])


if __name__ == '__main__':
    unittest.main()
