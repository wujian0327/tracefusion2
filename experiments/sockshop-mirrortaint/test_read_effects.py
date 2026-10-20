import unittest
from plan_read_effects import read_effects


class ReadEffectPlanningTests(unittest.TestCase):
    def methods(self,instructions):
        code=[dict(index=i,**ins) for i,ins in enumerate(instructions)]
        model={'classes':{'D':{'fields':[]}},'methods':{'D.read()Ljava/lang/Object;':{'owner':'D','name':'read','access':1,'desc':'()Ljava/lang/Object;','exception_handlers':[],'instructions':code}}}
        return read_effects(model)['composed_methods']

    def test_unmodeled_child_is_conditional_not_a_static_readonly_whitelist(self):
        self.assertTrue(self.methods([{'op':184,'owner':'External','name':'read','desc':'()Ljava/lang/Object;'},{'op':176}]))

    def test_field_write_cannot_receive_a_composed_read_proof(self):
        self.assertFalse(self.methods([{'op':181,'owner':'D','name':'value','desc':'Ljava/lang/Object;'},{'op':176}]))

    def test_foreign_initializer_and_backedge_remain_unsupported(self):
        self.assertFalse(self.methods([{'op':178,'owner':'Other','name':'value','desc':'Ljava/lang/Object;'},{'op':176}]))
        self.assertFalse(self.methods([{'op':0},{'op':167,'target':0},{'op':176}]))

    def test_arbitrary_constructor_and_bootstrap_cannot_be_ignored(self):
        self.assertFalse(self.methods([{'op':183,'owner':'External','name':'<init>','desc':'()V'},{'op':176}]))
        self.assertFalse(self.methods([{'op':186,'bootstrap':'External.bootstrap','desc':'()Ljava/util/function/Supplier;','bootstrap_args':[]},{'op':176}]))

    def test_array_and_native_effects_not_promoted(self):
        self.assertFalse(self.methods([{'op':189,'type':'java/lang/Object'},{'op':176}]))
        self.assertFalse(self.methods([{'op':194},{'op':176}]))

if __name__=='__main__':unittest.main()
