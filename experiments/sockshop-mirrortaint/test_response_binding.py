import unittest
from plan_distributed_fields import json_schema
from query_observation_planner import resolve_target
from infer_response_binding import matches


class ResponseBindingTests(unittest.TestCase):
    def test_public_field_with_computing_getter_is_not_a_wire_identity(self):
        model={'classes':{'D':{'fields':[{'name':'text','desc':'Ljava/lang/String;','access':1}]}},
               'methods':{'D.getText()Ljava/lang/String;':{'owner':'D','access':1,'desc':'()Ljava/lang/String;','name':'getText',
                   'instructions':[{'op':18,'constant':'SAME'},{'op':176}]}}}
        schema,rejected=json_schema(model)
        self.assertNotIn('D',schema)
        self.assertEqual(rejected[0]['field'],'D.text')

    def test_present_non_scalar_target_has_distinct_error(self):
        model={'classes':{'D':{'fields':[{'name':'list','desc':'Ljava/util/List;','access':1}]}}}
        with self.assertRaisesRegex(ValueError,'Target type unsupported'):
            resolve_target(model,'D.list')
        with self.assertRaisesRegex(ValueError,'absent or ambiguous'):
            resolve_target(model,'D.absent')

    def test_element_wildcard_cannot_bind_another_map_key_or_depth(self):
        self.assertTrue(matches('/data/*/text','/data/1/text'))
        self.assertFalse(matches('/data/*/text','/data/key/text'))
        self.assertFalse(matches('/data/*/text','/data/1/nested/text'))


if __name__=='__main__':unittest.main()
