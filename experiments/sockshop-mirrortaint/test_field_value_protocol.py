import unittest
from field_value_protocol import validate

class FieldValueTests(unittest.TestCase):
    def check(self,desc,value,observed=None):
        observation=observed or {'object':None,'primitive':desc,'value':value}
        return validate({},[{'kind':'start','field_value_version':1},{'kind':'read','owner':'o','field':'T.f','version':1,'descriptor':desc,'observed':observation}])
    def test_signed_big_integer(self):self.check('J',9000000000000000000)
    def test_boolean_not_integer(self):
        with self.assertRaises(ValueError):self.check('Z',1)
    def test_primitive_cannot_have_identity(self):
        with self.assertRaises(ValueError):self.check('I',1000000,{'object':'box','primitive':'I','value':1000000})
    def test_boxed_reference_keeps_identity(self):self.check('Ljava/lang/Integer;',1000000,{'object':'box','value':1000000})
    def test_null_reference(self):self.check('Ljava/lang/Integer;',None,{'object':None,'value':None})
    def test_primitive_marker_on_reference_rejected(self):
        with self.assertRaises(ValueError):self.check('Ljava/lang/Integer;',1000000,{'object':None,'primitive':'I','value':1000000})
    def test_missing_new_type_rejected(self):
        with self.assertRaises(ValueError):self.check('I',1000000,{'object':None,'value':1000000})
    def test_wrong_descriptor_rejected(self):
        with self.assertRaises(ValueError):self.check('J',1000000,{'object':None,'primitive':'I','value':1000000})
    def test_legacy_wrapper_accepted(self):validate({},[{'kind':'start'},{'kind':'read','descriptor':'I','observed':{'object':'old-box','value':1000000}}])
    def test_new_marker_without_header_rejected(self):
        with self.assertRaises(ValueError):validate({},[{'kind':'start'},{'kind':'read','descriptor':'I','observed':{'object':None,'primitive':'I','value':1}}])
    def test_double_bits(self):self.check('D',1000000.25,{'object':None,'primitive':'D','value':1000000.25,'bits':'412e848080000000'})
    def test_wrong_double_bits(self):
        with self.assertRaises(ValueError):self.check('D',1000000.25,{'object':None,'primitive':'D','value':1000000.25,'bits':'0'})
    def test_reference_scalar_requires_object_identity(self):
        with self.assertRaises(ValueError):self.check('Ljava/lang/Integer;',1000000,{'value':1000000})
    def test_double_negative_zero(self):self.check('D',-0.0,{'object':None,'primitive':'D','value':-0.0,'bits':'8000000000000000'})
    def test_double_nan_payload(self):self.check('D','NaN',{'object':None,'primitive':'D','value':'NaN','bits':'7ff8000000000001'})
    def test_character_range(self):self.check('C',8192)
    def test_integer_overflow(self):
        with self.assertRaises(ValueError):self.check('I',2**31)
    def test_old_http_primitive_flag_is_metadata(self):validate({},[{'kind':'start'},{'kind':'source','primitive':False,'observed':{'object':'ref','value':3}}])
