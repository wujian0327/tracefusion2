import copy
import unittest
from execution_dependency_state import Value
from jvm_semantic_rules import RULES,compute,field_transfer,field_event,write_payload_eligible,specification,validate_plan

class PrimitiveRules(unittest.TestCase):
    def value(self,n,occurrence,unknown=False):
        return Value({'value':n},frozenset({('field',occurrence,0)}),frozenset({('choice',occurrence)}),unknown)
    def test_ladd_extremes_and_two_occurrences(self):
        for a,b,want in [(2**63-1,1,-2**63),(-2**63,-1,2**63-1),(7,7,14)]:
            v=compute(97,[self.value(a,1),self.value(b,2,True)])
            self.assertEqual(v.observed,{'value':want});self.assertEqual(len(v.origins),2);self.assertEqual(len(v.selectors),2);self.assertTrue(v.unknown)
    def test_iadd_overflow(self):
        self.assertEqual(compute(96,[self.value(2**31-1,1),self.value(1,2)]).observed['value'],-2**31)
    def test_i2l_witness(self):
        v=compute(133,[self.value(-2**31,1)],{'method':'m','input':-2**31,'result':-2**31},'m')
        self.assertEqual(v.origins,self.value(0,1).origins)
        with self.assertRaises(ValueError):compute(133,[self.value(1,1)],{'method':'m','input':1,'result':2},'m')
    def test_operand_types(self):
        for n in (True,2**63,None):
            with self.assertRaises(ValueError):compute(97,[Value({'value':n}),Value({'value':0})])
    def test_shared_demand_and_effect(self):
        self.assertEqual(RULES[97].demand()['values'],[0,1]);self.assertTrue(RULES[180].demand()['field_value'])
        self.assertFalse(write_payload_eligible('B.target',{'B.target'},'J'));self.assertTrue(write_payload_eligible('B.other',{'B.target'},'J'))
        self.assertTrue(RULES[181].demand(False,True)['effects'])
    def test_field_identity_null_and_payload(self):
        ins={'owner':'B','name':'x'};r={'kind':'write-version','owner':'o','field':'B.x','version':4}
        field_event(181,Value({'object':'o'}),ins,r)
        field_event(181,Value(allocation=7),ins,r,actual_identity='o')
        with self.assertRaises(ValueError):field_event(181,Value({'object':'other'}),ins,r)
        self.assertTrue(field_transfer(181,Value({'value':None}),{},True).unknown)
        sourced=self.value(None,5);self.assertEqual(field_transfer(180,sourced,{'value':None}).origins,sourced.origins)
    def test_rule_plan_tampering(self):
        import json
        p={'execution_kernel':{'semantic_primitive_rules':json.loads(json.dumps(specification()))}};validate_plan(p)
        p['execution_kernel']['semantic_primitive_rules']['rules']['97']['bits']=32
        with self.assertRaises(ValueError):validate_plan(p)
    def test_field_values_keep_existing_choice_and_unknown(self):
        original=self.value(7,8,True)
        for op in (180,181):
            copied=field_transfer(op,original,{'value':7})
            self.assertEqual(copied.origins,original.origins)
            self.assertEqual(copied.selectors,original.selectors)
            self.assertTrue(copied.unknown)
        omitted=field_transfer(181,original,{},True)
        self.assertTrue(omitted.unknown)
        self.assertFalse(omitted.origins)

if __name__=='__main__':unittest.main()
