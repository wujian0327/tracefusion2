"""Independent checks of the *analysis*, not new provenance capability tests."""
import copy
import unittest

from analyze_target_demand_shadow import available_before, bucket, coordinate, inspect


class ShadowChecks(unittest.TestCase):
    def fixture(self):
        plan = {'entry': 'C.query()Ljava/util/List;', 'target': 'DTO.label',
                'response_graph_schema': {'DTO': [{'field': 'DTO.label', 'descriptor': 'Ljava/lang/String;'}]},
                'response_binding': {'path': '/data/*/label'},
                'target_observation_closure': {'required_fields': ['DTO.label']}}
        field = {'path': '/0/label', 'owner': 'a', 'field': 'DTO.label', 'version': 1,
                 'observed': {'object': 's', 'value': 'same'}}
        rows = [{'kind': 'enter', 'frame': 'f', 'parent': None, 'method': plan['entry']},
                {'kind': 'binding-source', 'frame': 'f', 'fields': [copy.deepcopy(field)], 'callee': 'Store.read'},
                {'kind': 'binding-source', 'frame': 'f', 'fields': [dict(copy.deepcopy(field), owner='b')], 'callee': 'Store.read'},
                {'kind': 'binding-return', 'frame': 'f', 'fields': [dict(copy.deepcopy(field), path='/data/0/label')]},
                {'kind': 'metrics', 'capture_invalid': False}]
        for seq, row in enumerate(rows, 1): row['seq'] = seq
        return plan, rows

    def test_future_missing_duplicate_or_equal_time_proof_is_unavailable(self):
        for candidates in ([], [[]], [[9]], [[8]], [[6, 7]]):
            self.assertFalse(available_before(8, candidates))
        self.assertTrue(available_before(8, [[4], [7]]))

    def test_same_value_is_not_an_identity_route(self):
        p, rows = self.fixture(); before = copy.deepcopy(rows)
        result = inspect(p, rows)
        witness = result['target_identity_witnesses'][0]
        self.assertEqual([v['seq'] for v in witness['co_coordinate_sources']], [2])
        self.assertFalse(witness['certified_dependency'])
        self.assertEqual(before, rows)

    def test_duplicate_sources_are_not_overwritten(self):
        p, rows = self.fixture(); rows[2]['fields'][0]['owner'] = 'a'
        self.assertEqual(len(inspect(p, rows)['target_identity_witnesses'][0]['co_coordinate_sources']), 2)

    def test_same_value_overwrite_is_a_different_version(self):
        p, rows = self.fixture(); rows[3]['fields'][0]['version'] = 2
        self.assertEqual(inspect(p, rows)['target_identity_witnesses'][0]['co_coordinate_sources'], [])

    def test_null_shape_is_not_a_boxed_numeric_payload(self):
        field = {'field': 'DTO.other', 'observed': {'object': None, 'value': None}}
        self.assertEqual(bucket(field, 'Ljava/lang/Long;', set(), 'DTO.label'),
                         'null_shape_not_an_unused_numeric_payload')
        # Null as a source vs constant cannot be decided from null itself.
        self.assertNotEqual(coordinate(dict(field, owner='a', version=1)),
                            coordinate(dict(field, owner='b', version=1)))

    def test_missing_frame_is_not_an_independent_request(self):
        p, rows = self.fixture(); rows[0]['parent'] = 'absent'; rows[0]['method'] = 'helper'
        with self.assertRaises(ValueError): inspect(p, rows)

    def test_problem_and_sticky_failure_still_rejected(self):
        p, rows = self.fixture(); rows[-1]['capture_invalid'] = True
        with self.assertRaises(ValueError): inspect(p, rows)
        rows[-1]['capture_invalid'] = False; rows[2]['kind'] = 'problem'
        with self.assertRaises(ValueError): inspect(p, rows)

    def test_no_footer_or_sequence_gap(self):
        p, rows = self.fixture()
        with self.assertRaises(ValueError): inspect(p, rows[:-1])
        rows[2]['seq'] = 99
        with self.assertRaises(ValueError): inspect(p, rows)

    def test_naively_dropping_boxed_payload_changes_public_transfer_branch(self):
        from execution_dependency_state import Value
        from member_state_transfer import read_members
        origin = lambda field, before: Value(field['observed'], frozenset({('read', 7, 0)}))
        source = read_members('list', 1, [{'object': 'cached-box', 'value': 1}], 9, origin)[0]
        # Deliberately invalid proposed encoding, NOT a captured/accepted rule.
        stripped = read_members('list', 1, [{'object': 'cached-box'}], 9, origin)[0]
        self.assertEqual(source.origins, frozenset({('read', 7, 0)}))
        self.assertFalse(stripped.origins)
        self.assertFalse(stripped.unknown)
        self.assertNotEqual(source.origins, stripped.origins)

    def test_null_source_and_constant_need_distinct_transfer_state(self):
        from execution_dependency_state import Value
        from member_state_transfer import read_members, copy_member
        null = {'object': None, 'value': None}
        source = read_members('list', 1, [null], 9,
                              lambda f, before: Value(f['observed'], frozenset({('read', 1, 0)})))[0]
        constant = copy_member(Value(null))
        self.assertEqual(source.observed, constant.observed)
        self.assertNotEqual(source.origins, constant.origins)


if __name__ == '__main__': unittest.main()
