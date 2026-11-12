import copy,unittest
from method_value_protocol import validate,parse_descriptor

class MethodValueTests(unittest.TestCase):
    def setUp(self):
        self.key='T.work(IJLjava/lang/Object;)D'
        self.plan={'frame_methods':[self.key],'execution_kernel':{'methods':{self.key:{'desc':'(IJLjava/lang/Object;)D','instructions':[]}}}}
        self.rows=[{'kind':'start','method_value_version':1}, {'kind':'enter','frame':'f','method':self.key,'method_descriptor':'(IJLjava/lang/Object;)D','args':[{'object':None,'primitive':'I','value':1000000},{'object':None,'primitive':'J','value':9000000000000000000},{'object':'real','value':1000000}]}, {'kind':'exit','frame':'f','method_descriptor':'(IJLjava/lang/Object;)D','result':{'object':None,'primitive':'D','value':-0.0,'bits':'8000000000000000'}}]
    def check(self):return validate(self.plan,self.rows)
    def test_mixed_wide_and_reference(self):self.check()
    def test_parameter_count(self):
        self.rows[1]['args'].pop()
        with self.assertRaises(ValueError):self.check()
    def test_fake_reference_primitive(self):
        self.rows[1]['args'][0]={'object':'box','value':1000000}
        with self.assertRaises(ValueError):self.check()
    def test_fake_primitive_reference(self):
        self.rows[1]['args'][2]={'object':None,'primitive':'I','value':1000000}
        with self.assertRaises(ValueError):self.check()
    def test_wrong_descriptor(self):
        self.rows[1]['method_descriptor']='(J)V'
        with self.assertRaises(ValueError):self.check()
    def test_missing_descriptor(self):
        self.rows[2].pop('method_descriptor')
        with self.assertRaises(ValueError):self.check()
    def test_nan_bits(self):
        self.rows[2]['result']={'object':None,'primitive':'D','value':'NaN','bits':'7ff8000000000017'};self.check()
    def test_bad_range(self):
        self.rows[1]['args'][0]['value']=2**31
        with self.assertRaises(ValueError):self.check()
    def test_legacy(self):validate({},[{'kind':'start'},{'kind':'enter','args':[{'object':'old','value':1000000}]}])
    def test_unsupported_version(self):
        self.rows[0]['method_value_version']=2
        with self.assertRaises(ValueError):self.check()
    def test_unversioned_new_evidence(self):
        self.rows[0].pop('method_value_version')
        with self.assertRaises(ValueError):self.check()
    def test_descriptor_slot_and_array(self):self.assertEqual(parse_descriptor('(ZBCSIJFD[[ILjava/lang/Long;)V'),(['Z','B','C','S','I','J','F','D','[[I','Ljava/lang/Long;'],'V'))
    def test_invalid_descriptors(self):
        for d in ('(V)V','(I)','(Ljava.lang.Long;)V','([V)V','()VV','(I)Ljava/lang/Object'):
            with self.subTest(d=d),self.assertRaises(ValueError):parse_descriptor(d)
