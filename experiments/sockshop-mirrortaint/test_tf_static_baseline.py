import copy
import unittest
from tf_static_baseline import configure


class StaticBaselineTests(unittest.TestCase):
    def test_fixed_permissions_shared_without_mutation(self):
        plan = {'selected_read_sites': ['A.m@2'],
                'target_observation_closure': {'omittable_scalar_fields': {'A.other': 'J'}},
                'execution_observation_closure': {'application_write_values': {'sites': {'A.m@4': {'field': 'A.other'}}}},
                'execution_kernel': {'body_observation': {'candidates': {'A.m@5': {'callee': 'B.log()V'}}}}}
        before = copy.deepcopy(plan)
        static, selective = (configure(plan, m) for m in ('static', 'selective'))
        self.assertEqual(static['fixed_permissions'], selective['fixed_permissions'])
        self.assertEqual(static['runtime_extra_candidates'], selective['runtime_extra_candidates'])
        self.assertIn('-Dservice.body.observation=false', static['jvm_options'])
        self.assertIn('-Dservice.body.observation=true', selective['jvm_options'])
        self.assertEqual(plan, before)
        static['fixed_permissions']['read_sites'].clear()
        self.assertEqual(plan, before)

    def test_full_and_empty_candidate_are_explicit(self):
        self.assertIn('-Dservice.mode=full', configure({}, 'full')['jvm_options'])
        self.assertEqual(configure({}, 'static')['runtime_extra_candidates'], {})
        with self.assertRaises(ValueError):
            configure({}, 'boundary')


if __name__ == '__main__':
    unittest.main()
