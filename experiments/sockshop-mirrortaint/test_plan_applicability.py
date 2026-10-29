import copy
import unittest
from unittest.mock import patch
from plan_applicability import check
from plan_capability_policy import choose


class ApplicabilityTests(unittest.TestCase):
    def setUp(self):
        self.source='Store.read()Ljava/lang/Object;'
        self.entry='Entry.root()Ljava/lang/Object;'
        self.query={'entry':self.entry,'target':'Box.value','path':'/value','source_calls':[self.source]}
        self.model={'methods':{self.entry:{'instructions':[{'index':0,'op':185,'owner':'Store','name':'read','desc':'()Ljava/lang/Object;'}]}}}
        self.plan={'profile':'response-forward','frame_methods':[self.entry],
                   'response_binding':{'source_calls':[self.source]},
                   'read_forward_contracts':{'composed_methods':[self.entry],'runtime_profiles':[{'java_runtime_version':'jdk','class_sha256':{'JDK/Class':'hash'}}]}}
        self.environment={'runtime':{'java_runtime_version':'jdk','class_sha256':{'JDK/Class':'hash'}},'response_converter':{'class':'org.springframework.http.converter.json.MappingJackson2HttpMessageConverter'}}

    def test_runtime_hash_and_version_are_both_necessary(self):
        for mutation in ({'java_runtime_version':'other'},{'class_sha256':{}},{'class_sha256':{'JDK/Class':'wrong'}}):
            env=copy.deepcopy(self.environment);env['runtime'].update(mutation)
            self.assertEqual(check(self.plan,self.model,self.query,env)['status'],'rejected')

    def test_declaration_is_not_a_source_observation(self):
        result=check(self.plan,self.model,self.query,self.environment)
        self.assertTrue(result['source_coverage'][0]['has_observable_callsite'])
        self.assertFalse(result['answer_certified'])
        self.plan['frame_methods']=[];self.plan['read_forward_contracts']['composed_methods']=[]
        result=check(self.plan,self.model,self.query,self.environment)
        self.assertFalse(result['source_coverage'][0]['has_observable_callsite'])
        self.assertEqual(result['status'],'conditional')

    def test_missing_declaration_fails_instead_of_silently_omitting(self):
        self.plan['response_binding']['source_calls']=[]
        with self.assertRaisesRegex(ValueError,'dropped declared'):check(self.plan,self.model,self.query,self.environment)

    def test_missing_environment_cannot_certify_executability(self):
        self.assertEqual(check(self.plan,self.model,self.query)['status'],'conditional')

    def test_unmodeled_gson_is_not_a_jackson_binding(self):
        self.environment['response_converter']['class']='org.springframework.http.converter.json.GsonHttpMessageConverter'
        self.assertEqual(check(self.plan,self.model,self.query,self.environment)['status'],'rejected')

    def test_every_candidate_receives_sources_before_route_is_chosen(self):
        # Both candidates rejected before postprocessing; verifies boundary
        # delivery even to the non-selected strategy, rather than a later patch.
        calls=[]
        def planner(*args,**kwargs):
            calls.append(kwargs);plan=copy.deepcopy(self.plan)
            if kwargs.get('execution_kernel'):
                plan['execution_kernel']={'methods':{},'runtime_profiles':plan['read_forward_contracts']['runtime_profiles']}
            return plan
        env=copy.deepcopy(self.environment);env['runtime']['class_sha256']={}
        with patch('plan_capability_policy.plan_response',side_effect=planner):
            with self.assertRaisesRegex(ValueError,'No supported static plan'):choose(self.model,self.query,deployment=env)
        self.assertEqual(len(calls),2)
        self.assertTrue(all(c['source_calls']==[self.source]for c in calls))


if __name__=='__main__':unittest.main()
