"""Unknowns stay in denominators and are never counted as true negatives."""
import unittest
from compare_flowdist_total_queries import summarize


class QueryScoringChecks(unittest.TestCase):
    def test_unknowns_fail_exact_and_positive_recall(self):
        report=summarize([{'prediction':None,'expected_dependency':True},
            {'prediction':None,'expected_dependency':False},
            {'prediction':True,'expected_dependency':True},
            {'prediction':False,'expected_dependency':False}])
        self.assertEqual(report['queries'],4)
        self.assertEqual(report['answered'],2)
        self.assertEqual(report['unknown'],2)
        self.assertEqual(report['correct'],2)
        self.assertEqual(report['exact_rate'],.5)
        self.assertEqual(report['recall'],.5)
        self.assertEqual(report['tn'],1)
        self.assertEqual(report['fn_answered'],0)
        self.assertEqual(report['missed_positive_including_unknown'],1)

    def test_no_reported_positive_has_undefined_precision(self):
        report=summarize([{'prediction':False,'expected_dependency':True},
            {'prediction':False,'expected_dependency':False}])
        self.assertIsNone(report['precision'])
        self.assertEqual(report['recall'],0)
        self.assertEqual(report['fn_answered'],1)


if __name__=='__main__':unittest.main()
