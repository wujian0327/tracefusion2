"""Synthetic integrity/score tests, not real Pin propagation evidence."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from compare import NAMES, parse_observation, score


class IntegrityTests(unittest.TestCase):
    def setUp(self):
        self.evidence = dict(symbols={name: [100 + i*10, 2] for i, name in enumerate(NAMES)},
                             instructions={100: dict(assembly='nop'), 101: dict(assembly='ret')})
        self.rows = [dict(kind='symbol', id=i, name=name, begin=1100+i*10, end=1102+i*10)
                     for i, name in enumerate(NAMES)]
        self.rows += [dict(kind='source', sequence=1, function=NAMES[0], tid=0, src=5000, dst=6000,
                           count=0, values=[42, 42, 99], byte_labels=[[[i]]*4 for i in (1, 2, 3)]),
                      dict(kind='instruction', step=1, tid=0, pc=1100, fid=0, opcode=1, covered=True),
                      dict(kind='instruction', step=2, tid=0, pc=1101, fid=0, opcode=2, covered=True),
                      dict(kind='sink', sequence=1, function=NAMES[0], value=42, labels=[],
                           byte_labels=[[], [], [], []], helper_calls=0),
                      dict(kind='finish', exit_code=0, bad=False, active=False, roots=24, starts=1,
                           sinks=1, steps=2, contexts=0, threads=1, performance_eligible=False)]
        self.truth = dict(sequence=1, function=NAMES[0], count=0, expected_sources=[],
                          expected_value=42, expected_helper_calls=0)

    def parse(self, rows=None):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'log.jsonl'
            path.write_text('\n'.join(json.dumps(r) for r in (self.rows if rows is None else rows)))
            return parse_observation(path, 1, self.evidence)

    def test_empty_origin_is_a_valid_query(self):
        self.assertTrue(score(self.parse(), self.truth)['matched'])

    def test_equal_numeric_value_does_not_hide_wrong_origin(self):
        self.rows[-2].update(labels=[2], byte_labels=[[2]]*4)
        self.truth['expected_sources'] = ['input.secret']
        result = score(self.parse(), self.truth)
        self.assertFalse(result['matched'])
        self.assertTrue(result['value_matched'])
        self.assertEqual((result['tp'], result['fp'], result['fn']), (0, 1, 1))

    def test_faults_fail_closed(self):
        faults = [(-1, 'bad', True), (-1, 'active', True), (-1, 'exit_code', 1),
                  (-1, 'contexts', 1), (-1, 'threads', 2), (-1, 'roots', 23),
                  (-3, 'step', 3), (-3, 'tid', 1), (-3, 'pc', 1102),
                  (-3, 'covered', False), (-2, 'sequence', 2), (-2, 'helper_calls', 1),
                  (-2, 'labels', [4]), (-2, 'labels', [1]),
                  (5, 'byte_labels', [[[1]]*4]*3), (5, 'dst', 5004), (0, 'end', 1103)]
        for index, key, value in faults:
            with self.subTest(key=key, value=value):
                rows = copy.deepcopy(self.rows)
                rows[index][key] = value
                with self.assertRaises(ValueError):
                    self.parse(rows)

    def test_missing_duplicate_reordered_events_rejected(self):
        for rows in (self.rows[:-1], self.rows[:6] + self.rows[7:], self.rows + [self.rows[-1]],
                     self.rows[:6] + [self.rows[7], self.rows[6]] + self.rows[8:]):
            with self.assertRaises(ValueError):
                self.parse(rows)

    def test_explicit_error_never_scores_empty_as_success(self):
        with self.assertRaises(ValueError):
            self.parse(self.rows[:-1] + [dict(kind='error', reason='context_change_in_query'), self.rows[-1]])

    def test_value_and_invocation_mismatches(self):
        observed = self.parse()
        observed['value'] = 43
        self.assertFalse(score(observed, self.truth)['matched'])
        observed['sequence'] = 2
        with self.assertRaises(ValueError):
            score(observed, self.truth)


if __name__ == '__main__':
    unittest.main()
