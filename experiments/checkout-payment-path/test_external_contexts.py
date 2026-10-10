"""Synthetic log checks only; these do not establish real Pin/Go correctness."""
import copy
import unittest

from inspect_external_flow import inspect_contexts


def context(pc, value):
    return dict(pc=pc, registers=dict(R10=value, R11=0))


def fixture():
    tagged = dict(R10=[3]*8, R11=[4]*8)
    empty = dict(R10=[0]*8, R11=[0]*8)
    return [
        dict(kind='context_change', id=1, tid=2, step=10, reason='signal', info=23,
             **{'from': context(100, 2), 'to': context(200, 99)}, shadow_at_callback=tagged),
        dict(kind='context_resume', id=1, tid=2, step=10, actual=context(200, 99),
             shadow_before_instruction=tagged),
        dict(kind='context_change', id=2, tid=2, step=10, reason='sigreturn', info=0,
             **{'from': context(210, 99), 'to': context(100, 2)}, shadow_at_callback=empty),
        dict(kind='context_resume', id=2, tid=2, step=10, actual=context(100, 2),
             shadow_before_instruction=empty),
        dict(kind='flow_finish', context_diagnostics=True, context_events=2, context_resumes=2),
    ]


def labels(tags):
    return set(tags) - {0}


class ContextLogTests(unittest.TestCase):
    def test_restored_value_does_not_restore_provenance(self):
        report = inspect_contexts(fixture(), labels)
        reg = report['signal_pairs'][0]['registers'][0]
        self.assertTrue(reg['interrupted_value_restored'])
        self.assertEqual(reg['labels_lost'], [3])
        self.assertEqual(report['events'][1]['registers']['R10']['resumed_labels'], [])

    def test_incomplete_resume_rejected(self):
        rows = fixture()
        del rows[3]
        rows[-1]['context_resumes'] = 1
        with self.assertRaisesRegex(ValueError, 'lacks first-instruction'):
            inspect_contexts(rows, labels)

    def test_wrong_thread_resume_rejected(self):
        rows = fixture()
        rows[3]['tid'] = 9
        with self.assertRaisesRegex(ValueError, 'changed thread'):
            inspect_contexts(rows, labels)

    def test_modified_return_values_not_claimed_restored(self):
        rows = copy.deepcopy(fixture())
        rows[2]['to']['registers']['R10'] = 7
        report = inspect_contexts(rows, labels)
        self.assertFalse(report['signal_pairs'][0]['registers'][0]['interrupted_value_restored'])
        self.assertFalse(report['events'][1]['next_instruction_matches_to'])

    def test_unpaired_return_is_explicit(self):
        rows = fixture()[2:]
        rows[0]['id'] = rows[1]['id'] = 1
        rows[-1]['context_events'] = rows[-1]['context_resumes'] = 1
        report = inspect_contexts(rows, labels)
        self.assertEqual(report['signal_pairs'], [])
        self.assertEqual(report['unpaired_signal_returns'], 1)

    def test_old_archive_has_no_context_evidence(self):
        self.assertFalse(inspect_contexts([dict(kind='flow_finish')], labels)['enabled'])

    def test_simd_tag_loss_without_recorded_values(self):
        rows = fixture()
        rows[0]['shadow_at_callback']['X0'] = [1, 2] * 8
        rows[2]['shadow_at_callback']['X0'] = [0] * 16
        report = inspect_contexts(rows, labels)
        reg = next(r for r in report['signal_pairs'][0]['registers'] if r['register'] == 'X0')
        self.assertEqual(reg['labels_lost'], [1, 2])
        self.assertIsNone(reg['interrupted_value_restored'])


if __name__ == '__main__':
    unittest.main()
