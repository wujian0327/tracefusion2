"""Controls for association/estimation only; no production omission is enabled."""
import copy
from collections import defaultdict
import unittest

from analyze_ruoyi_postcopy_payload import COPY, byte_model, member_at, same_slot_and_reference, select_point


class PostCopyChecks(unittest.TestCase):
    def fixture(self):
        method = 'Helper.forward()Ljava/util/List;'
        plan = {'execution_kernel': {'methods': {method: {'instructions': [{'op': 185}, {'op': 176}]}}}}
        members = [{'object': 'a'}, {'object': 'b'}]
        field = {'path': '/0/n', 'owner': 'a', 'field': 'DTO.n', 'version': 1,
                 'observed': {'object': 'box', 'value': 1}}
        outer = {'seq': 1, 'kind': 'collection-call-enter', 'frame': 'p', 'method': 'Controller.run()V',
                 'pc': 0, 'call_id': 1, 'callee': method, 'thread': 7}
        entry = {'seq': 2, 'kind': 'enter', 'frame': 'f', 'parent': 'p', 'method': method,
                 'callsite': 'Controller.run()V@0'}
        start = {'seq': 3, 'kind': 'collection-call-enter', 'frame': 'f', 'method': method,
                 'pc': 0, 'call_id': 2, 'callee': COPY, 'collection': members,
                 'collection_epoch': 4, 'receiver': {'object': 'json'}, 'thread': 7}
        before = {'seq': 4, 'kind': 'binding-opaque-result', 'frame': 'f', 'callee': COPY,
                  'fields': [copy.deepcopy(field)]}
        done = {'seq': 5, 'kind': 'collection-call-exit', 'frame': 'f', 'method': method,
                'pc': 0, 'call_id': 2, 'result': {'object': 'out'}, 'result_type': 'java.util.ArrayList',
                'collection_after': members, 'collection_epoch': 4, 'thread': 7,
                'json_list_copy': {'result_epoch': 0, 'members': members}}
        finish = {'seq': 6, 'kind': 'exit', 'frame': 'f', 'result': {'object': 'out'}, 'thread': 7}
        snapshot = {'seq': 7, 'kind': 'binding-opaque-result', 'frame': 'p', 'callee': method,
                    'fields': [copy.deepcopy(field)], 'thread': 7}
        outer_end = {'seq': 8, 'kind': 'collection-call-exit', 'frame': 'p', 'call_id': 1,
                     'result': {'object': 'out'}, 'thread': 7}
        rows = [outer, entry, start, before, done, finish, snapshot, outer_end]
        calls, ends, enters, frame_ends = (defaultdict(list) for _ in range(4))
        calls[('p', 1)].append(outer); calls[('f', 2)].append(start)
        ends[('p', 1)].append(outer_end); ends[('f', 2)].append(done)
        enters['f'].append(entry); frame_ends['f'].append(finish)
        return plan, rows, done, calls, ends, enters, frame_ends

    def test_exact_outer_snapshot_is_selected_not_precompletion_snapshot(self):
        args = self.fixture(); selected, before, _, _ = select_point(*args)
        self.assertEqual((selected['seq'], before['seq']), (7, 4))

    def test_same_members_do_not_authorize_a_different_return_list(self):
        args = self.fixture(); args[4][('p', 1)][0]['result']['object'] = 'other-list'
        with self.assertRaises(AssertionError): select_point(*args)

    def test_duplicate_completion_not_overwritten(self):
        args = self.fixture(); args[4][('f', 2)].append(copy.deepcopy(args[2]))
        with self.assertRaises(ValueError): select_point(*args)

    def test_wrong_caller_or_pc_is_not_resolved_by_later_sequence(self):
        for key, value in [('callsite', 'Controller.run()V@9'), ('parent', 'wrong-parent')]:
            args = self.fixture(); args[5]['f'][0][key] = value
            with self.assertRaises(ValueError): select_point(*args)

    def test_intervening_write_or_callback_disqualifies_immediate_forward(self):
        for kind in ('write', 'enter', 'collection-call-enter'):
            args = self.fixture(); args[1].append({'kind': kind, 'seq': 6.5})
            with self.assertRaises(AssertionError): select_point(*args)

    def test_member_order_owner_and_path_must_all_match(self):
        field = self.fixture()[1][6]['fields'][0]
        self.assertTrue(member_at(field, [{'object': 'a'}, {'object': 'b'}]))
        self.assertFalse(member_at(field, [{'object': 'b'}, {'object': 'a'}]))
        self.assertFalse(member_at(dict(field, path='/data/0/n'), [{'object': 'a'}]))

    def test_same_value_overwrite_or_same_value_new_box_not_reused(self):
        field = self.fixture()[1][6]['fields'][0]
        self.assertFalse(same_slot_and_reference(field, dict(field, version=2)))
        other = copy.deepcopy(field); other['observed']['object'] = 'other-box'
        self.assertFalse(same_slot_and_reference(field, other))

    def test_null_or_boolean_is_not_the_finite_long_model(self):
        args = self.fixture(); snapshot, before, outer, _ = select_point(*args)
        for observed in ({'object': None, 'value': None}, {'object': 'bool', 'value': True}):
            bad = copy.deepcopy(snapshot); bad['fields'][0]['observed'] = observed
            with self.assertRaises(AssertionError): byte_model(bad, [0], args[2], before, outer)

    def test_byte_model_cannot_hide_new_stage_samples(self):
        args = self.fixture(); snapshot, before, outer, _ = select_point(*args)
        old = copy.deepcopy(snapshot); result = byte_model(snapshot, [0], args[2], before, outer)
        self.assertEqual(result['tag_delta_with_minimum_stage_samples'] - result['tag_delta_without_new_stage_samples'], 10)
        self.assertEqual(result['grouped_delta_with_minimum_stage_samples'] - result['grouped_delta_without_new_stage_samples'], 10)
        self.assertTrue(result['stage_samples_are_missing_not_synthesized_evidence'])
        self.assertEqual(snapshot, old)


if __name__ == '__main__': unittest.main()
