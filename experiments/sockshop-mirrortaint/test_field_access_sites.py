import copy
import unittest
from infer_field_access_sites import storage_projection
from compare_field_accesses import project, summarize


GET='<Item: int getQuantity()>'
SET='<Item: void setQuantity(int)>'
OTHER='<Item: void restoreQuantity(int)>'


def row(kind,seq,owner='a',version=1,value=5,method=None,boxed='boxed'):
    return {'kind':kind,'seq':seq,'owner':owner,'field':'quantity','version':version,
            'observed':{'value':value,'object':boxed},'declared_field':'Item.quantity',
            'access_method':method or (SET if kind=='write' else GET)}


def predict(rows,primitive=True):
    model={'owner':'Item','getters':{'getQuantity()I':{'field':'Item.quantity','primitive':primitive}},'setters':{}}
    block=storage_projection(rows,model)
    query={'role':'carts','source_method':SET,'sink_method':GET,'source_field':'Item.quantity','expected_dependency':True}
    return project(query,{'storage':{'carts':block}},{}),block,query


class FieldAccessTests(unittest.TestCase):
    def test_equal_values_on_different_objects_do_not_create_an_edge(self):
        result,_,_=predict([row('write',1),row('read',2,owner='different')])
        self.assertIsNone(result[0])

    def test_primitive_box_identity_is_not_field_identity(self):
        result,_,_=predict([row('write',1,boxed='box1'),row('read',2,boxed='box2')])
        self.assertIs(result[0],True)

    def test_equal_reference_values_without_reference_identity_are_unknown(self):
        result,_,_=predict([row('write',1,value='same',boxed='s1'),row('read',2,value='same',boxed='s2')],False)
        self.assertIsNone(result[0])

    def test_unobserved_mutation_stays_unknown(self):
        result,_,_=predict([row('write',1),row('read',2,value=9)])
        self.assertIsNone(result[0])

    def test_overwritten_version_is_not_attributed_to_old_setter(self):
        result,_,_=predict([row('write',1),row('write',2,version=2,method=OTHER),row('read',3,version=2)])
        self.assertIs(result[0],False)

    def test_duplicate_field_version_fails(self):
        with self.assertRaisesRegex(ValueError,'Duplicate observed field version'):
            predict([row('write',1),row('write',2)])

    def test_expected_label_does_not_change_prediction(self):
        result,block,query=predict([row('write',1),row('read',2)])
        changed=copy.deepcopy(query);changed['expected_dependency']=False
        self.assertEqual(result,project(changed,{'storage':{'carts':block}},{}))

    def test_unknowns_remain_in_denominator_and_positive_misses(self):
        report=summarize([{'prediction':None,'expected_dependency':True},{'prediction':None,'expected_dependency':False}])
        self.assertEqual((report['queries'],report['unknown'],report['fn_including_unknown_positive'],report['tn']),(2,2,1,0))
        self.assertEqual((report['exact_rate'],report['coverage'],report['f1']),(0,0,0))


if __name__=='__main__':unittest.main()
