import unittest
from constructor_effect_scope_audit import summarize


def method(owner,code,desc='()V',access=0,name='<init>'):
    return dict(owner=owner,name=name,desc=desc,access=access,try_catches=0,exception_handlers=[],instructions=code)

def fixture(code,desc='()V'):
    obj=method('java/lang/Object',[{'op':177}]);m=method('A',code,desc)
    return {'classes':{'A':{'sha256':'app'},'java/lang/Object':{'sha256':'object'}},'methods':{'java/lang/Object.<init>()V':obj,'A.<init>'+desc:m}}

PARENT=[{'op':25,'var':0},{'op':183,'owner':'java/lang/Object','name':'<init>','desc':'()V'}]

class ConstructorReviewTests(unittest.TestCase):
    def test_plain_this_is_candidate_not_runtime_license(self):
        m=fixture(PARENT+[{'op':25,'var':0},{'op':21,'var':1},{'op':181,'owner':'A','name':'x','desc':'I'},{'op':177}],'(I)V')
        r=summarize(m,'A.<init>(I)V');self.assertTrue(r['static_local_candidate']);self.assertFalse(r['runtime_license'])
        self.assertEqual(r['write_addresses'],[{'root':'this','fields':[['A.x','I']]}])
    def test_parameter_write_cannot_be_local(self):
        m=fixture(PARENT+[{'op':25,'var':1},{'op':4},{'op':181,'owner':'D','name':'x','desc':'I'},{'op':177}],'(LD;)V')
        r=summarize(m,'A.<init>(LD;)V');self.assertFalse(r['static_local_candidate']);self.assertEqual(r['parameter_or_nested_writes'][0]['root'],'argument:0')
    def test_reference_store_does_not_grant_private_ownership(self):
        m=fixture(PARENT+[{'op':25,'var':0},{'op':25,'var':1},{'op':181,'owner':'A','name':'external','desc':'LD;'},{'op':177}],'(LD;)V')
        r=summarize(m,'A.<init>(LD;)V');self.assertTrue(r['reference_stores'][0]['external_alias_must_remain_reachable']);self.assertFalse(r['runtime_license'])
    def test_static_publication_is_not_local(self):
        m=fixture(PARENT+[{'op':25,'var':0},{'op':179,'owner':'A','name':'saved','desc':'LA;'},{'op':177}])
        r=summarize(m,'A.<init>()V');self.assertTrue(r['global_stores']);self.assertFalse(r['static_local_candidate'])
    def test_virtual_callback_even_with_body_needs_dispatch_and_effect_proof(self):
        m=fixture(PARENT+[{'op':25,'var':0},{'op':182,'owner':'A','name':'call','desc':'()V'},{'op':177}])
        m['methods']['A.call()V']=method('A',[{'op':177}],name='call')
        r=summarize(m,'A.<init>()V');self.assertTrue(r['unclosed']);self.assertFalse(r['static_local_candidate'])
    def test_unknown_call_cannot_become_empty_pure_effect(self):
        m=fixture(PARENT+[{'op':184,'owner':'Missing','name':'touch','desc':'()V'},{'op':177}])
        self.assertFalse(summarize(m,'A.<init>()V')['static_local_candidate'])
    def test_nontrivial_initialization_remains_obligation(self):
        m=fixture(PARENT+[{'op':177}]);m['methods']['A.<clinit>()V']=method('A',[{'op':3},{'op':179,'owner':'A','name':'g','desc':'I'},{'op':177}],access=8,name='<clinit>')
        r=summarize(m,'A.<init>()V');self.assertEqual(r['initialization_obligations'],['A']);self.assertFalse(r['static_local_candidate'])
    def test_parent_constructor_maps_same_this(self):
        m=fixture([{'op':25,'var':0},{'op':21,'var':1},{'op':183,'owner':'B','name':'<init>','desc':'(I)V'},{'op':177}],'(I)V')
        m['classes']['B']={'sha256':'parent'};m['methods']['B.<init>(I)V']=method('B',PARENT+[{'op':25,'var':0},{'op':21,'var':1},{'op':181,'owner':'B','name':'x','desc':'I'},{'op':177}],'(I)V')
        r=summarize(m,'A.<init>(I)V');self.assertTrue(r['static_local_candidate']);self.assertEqual(r['write_addresses'][0]['root'],'this')
    def test_native_body_absence_is_not_certified(self):
        m=fixture([])
        r=summarize(m,'A.<init>()V');self.assertFalse(r['runtime_license']);self.assertFalse(r['static_local_candidate'])
    def test_absent_bytecode_never_licensed(self):
        r=summarize({'classes':{},'methods':{}},'Missing.<init>()V');self.assertFalse(r['runtime_license']);self.assertFalse(r['static_local_candidate'])

if __name__=='__main__':unittest.main()
