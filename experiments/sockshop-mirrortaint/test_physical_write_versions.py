"""Literal physical clocks, including gaps with no complete writer coverage."""
import unittest
from infer_execution_closure import validate_application_writes

class PhysicalVersions(unittest.TestCase):
    def check(self,versions):
        rows=[{'kind':'write','seq':i+1,'owner':'o','field':'B.x','version':v,'frame':'root'+str(i)} for i,v in enumerate(versions)]
        return validate_application_writes({},rows)
    def test_decrease_across_roots(self):
        with self.assertRaisesRegex(ValueError,'did not increase'):self.check([4,3])
    def test_equal_same_value_still_invalid(self):
        with self.assertRaisesRegex(ValueError,'did not increase'):self.check([4,4])
    def test_unknown_intervals_allow_gaps(self):
        self.assertEqual(self.check([4,6,9]),0)
    def test_other_field_independent(self):
        self.assertEqual(validate_application_writes({},[{'kind':'write','owner':'a','field':'B.x','version':4},{'kind':'write','owner':'b','field':'B.x','version':3}]),0)

if __name__=='__main__':unittest.main()
