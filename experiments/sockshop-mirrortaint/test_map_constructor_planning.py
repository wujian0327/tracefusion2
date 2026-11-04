"""A proof budget is an analysis limit, not an opaque constructor verdict."""
import unittest
from unittest.mock import patch
from analysis_status import AnalysisLimit
from plan_map_constructor import attach


class PlanningStatus(unittest.TestCase):
    def fixture(self):
        key='Wrapper.<init>()V'
        return {'execution_kernel':{'constructors':{key:{'kind':'opaque'}}},'map_wrapper_observation':{'candidates':{}}},{'methods':{key:{}}}

    def test_budget_is_not_swallowed(self):
        plan,model=self.fixture()
        with patch('plan_map_constructor.prove',side_effect=AnalysisLimit('static-fixed-point','proof budget exhausted')):
            with self.assertRaises(AnalysisLimit):attach(plan,model)

    def test_unsupported_shape_stays_opaque(self):
        plan,model=self.fixture()
        with patch('plan_map_constructor.prove',side_effect=ValueError('unsupported callback')):attach(plan,model)
        self.assertEqual(plan['execution_kernel']['constructors']['Wrapper.<init>()V']['kind'],'opaque')


if __name__=='__main__':unittest.main()
