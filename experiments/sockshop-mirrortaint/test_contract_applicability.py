import copy,json,unittest
from pathlib import Path
from plan_async_dependencies import attach_async_dependencies
from plan_collection_service import plan_collection
from infer_collection_service import infer_collection
from analysis_status import AnalysisLimit,failure_status
from finite_string_values import utf16_length,literal_split,decimal_int

HERE=Path(__file__).parent

class ContractApplicabilityTests(unittest.TestCase):
    def plan(self):return {'execution_kernel':{'version':8,'constructors':{}}}
    def profile(self):return json.loads((HERE/'save-provided-id-contracts-20261023.json').read_text())

    def test_save_only_does_not_load_absent_hateoas_or_tasks(self):
        result=attach_async_dependencies(self.plan(),{'save'},{'classes':self.profile()['class_sha256']})
        self.assertTrue(result['execution_kernel']['save_effect_contracts']['provided_id_only'])
        self.assertNotIn('async_protocol',result)
        self.assertNotIn('request_entity_contracts',result['execution_kernel'])

    def test_missing_or_changed_one_of_all_library_classes_keeps_save_opaque(self):
        classes=self.profile()['class_sha256'];key=next(iter(classes))
        for inventory in (None,{'classes':{}},{'classes':{**classes,key:'wrong'}},{'classes':{k:v for k,v in classes.items()if k!=key}}):
            result=attach_async_dependencies(self.plan(),{'save'},inventory)
            self.assertNotIn('save_effect_contracts',result['execution_kernel'])
            self.assertEqual(result['execution_kernel']['unavailable_library_contracts'][0]['feature'],'save')

    def test_do_not_attach_request_model_just_because_save_model_matches(self):
        result=attach_async_dependencies(self.plan(),{'save','request'},{'classes':self.profile()['class_sha256']})
        self.assertIn('save_effect_contracts',result['execution_kernel'])
        self.assertNotIn('request_entity_contracts',result['execution_kernel'])
        self.assertEqual([v['feature']for v in result['execution_kernel']['unavailable_library_contracts']],['request'])

    def field_method(self):
        return {'access':0,'owner':'Box','name':'root','desc':'()Ljava/lang/String;','try_catches':0,'exception_handlers':[],
                'instructions':[{'op':25,'var':0,'index':0},{'op':180,'owner':'Box','name':'value','desc':'Ljava/lang/String;','index':1},{'op':176,'index':2}]}

    def test_static_transfers_do_not_imply_specialized_replay_support(self):
        key='Box.root()Ljava/lang/String;';model={'classes':{'Box':{'fields':[{'name':'value','access':1,'desc':'Ljava/lang/String;'}]}},'methods':{key:self.field_method()}}
        with self.assertRaisesRegex(ValueError,'Specialized replay semantic unsupported: opcode 180'):plan_collection(model,key,'Box.value',True)

    def test_unsupported_old_replay_is_analysis_limit_not_invalid_evidence(self):
        key='Box.root()Ljava/lang/String;';rows=[{'kind':'enter','method':key,'frame':1,'receiver':'o1','args':[]},{'kind':'exit','frame':1,'result':{'value':'x'}}]
        with self.assertRaises(AnalysisLimit)as result:infer_collection({'entry':key,'collection_method':self.field_method()},rows)
        self.assertEqual(failure_status(result.exception),'analysis_limited')

    def test_literal_split_keeps_positions_and_jvm_trailing_empty_rules(self):
        self.assertEqual(literal_split('A,B,A,',','),['A','B','A'])
        self.assertEqual(literal_split('',','),[''])
        self.assertEqual(literal_split(',,',','),[])
        with self.assertRaises(AnalysisLimit):literal_split('A.B','.')

    def test_jvm_length_and_decimal_domain(self):
        self.assertEqual(utf16_length('a\U00010400'),3)
        self.assertEqual(decimal_int('-2147483648'),-2147483648)
        self.assertEqual(decimal_int('+00'),0)
        for value in ('2147483648',' 12','\u0661',''):
            with self.assertRaises(AnalysisLimit):decimal_int(value)

if __name__=='__main__':unittest.main()
