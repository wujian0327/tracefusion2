"""Literal contradictory versions: exit evidence must survive target projection."""
import unittest
from unittest.mock import patch
from infer_execution_closure import validate_application_writes


class ExitWitness(unittest.TestCase):
    def test_projected_return_still_checks_unqueried_version(self):
        site = 'Box.setOther(I)V@2'
        plan = {'entry': 'Root.run()LBox;', 'target': 'Box.target',
                'class_sha256': {'Box': 'hash'},
                'collection_setters': {'Box.setOther(I)V': {'field': 'Box.other', 'descriptor': 'I'}},
                'execution_kernel': {'methods': {'Root.run()LBox;': {'instructions': [{'op': 182, 'owner': 'Box', 'name': 'setOther', 'desc': '(I)V'}]}}, 'class_parents': {'Box': {'super': 'java/lang/Object'}}},
                'execution_observation_closure': {'application_write_values': {'version': 1, 'required_value_fields': ['Box.target'], 'sites': {site: {'method': 'Box.setOther(I)V', 'pc': 2, 'field': 'Box.other', 'descriptor': 'I', 'method_owner': 'Box', 'method_sha256': 'hash', 'field_owner': 'Box', 'field_class_sha256': 'hash', 'kind': 'setter'}}}}}
        rows = [{'kind': 'header', 'seq': 0, 'mode': 'selective'},
                {'kind': 'enter', 'seq': 1, 'frame': 'root', 'method': plan['entry']},
                {'kind': 'collection-call-enter', 'seq': 2, 'frame': 'root', 'call_id': 9, 'callee': 'Box.setOther(I)V', 'receiver': {'object': 'o'}},
                {'kind': 'write-version', 'seq': 3, 'frame': 'root', 'owner': 'o', 'field': 'Box.other', 'version': 2, 'site': site},
                {'kind': 'collection-call-exit', 'seq': 4, 'frame': 'root', 'call_id': 9},
                {'kind': 'binding-return', 'seq': 5, 'frame': 'root', 'fields': []},
                {'kind': 'exit', 'seq': 6, 'frame': 'root', 'fields': [{'owner': 'o', 'field': 'Box.other', 'version': 2}]}]
        with patch('plan_execution_closure.application_value_fields', return_value={'Box.target'}):
            self.assertEqual(validate_application_writes(plan, rows), 1)
            rows[3]['version'] = 3
            with self.assertRaisesRegex(ValueError, 'final write version'):
                validate_application_writes(plan, rows)


if __name__ == '__main__':
    unittest.main()
