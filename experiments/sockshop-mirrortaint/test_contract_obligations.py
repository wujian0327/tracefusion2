import unittest,json
from pathlib import Path
from contract_obligations import features


class Obligations(unittest.TestCase):
    def select(self,*instructions):
        return features({'execution_kernel':{'methods':{'root':{'instructions':list(instructions)}}}},{'classes':{'Repo':{'interfaces':['org/springframework/data/repository/CrudRepository']}}})
    def call(self,owner,name,desc):return {'op':182,'owner':owner,'name':name,'desc':desc}
    def test_save_is_not_render_or_task(self):
        self.assertEqual(self.select(self.call('Repo','save','(Ljava/lang/Object;)Ljava/lang/Object;')),{'save'})
    def test_object_render_is_separate(self):
        self.assertEqual(self.select(self.call('java/lang/StringBuilder','append','(Ljava/lang/Object;)Ljava/lang/StringBuilder;')),{'render'})
        self.assertEqual(self.select(self.call('java/lang/StringBuilder','append','(Ljava/lang/String;)Ljava/lang/StringBuilder;')),set())
    def test_only_planned_invocations(self):
        self.assertEqual(self.select({'op':18,'owner':'java/lang/StringBuilder','name':'append','desc':'(Ljava/lang/Object;)Ljava/lang/StringBuilder;'}),set())
    def test_union_of_independent_apis(self):
        self.assertEqual(self.select(self.call('Repo','save','(Ljava/lang/Object;)Ljava/lang/Object;'),self.call('java/lang/StringBuilder','append','(Ljava/lang/Object;)Ljava/lang/StringBuilder;'),self.call('Worker','submit','()Ljava/util/concurrent/Future;'),self.call('org/springframework/http/RequestEntity','get','()Ljava/lang/Object;')),{'save','async','request'})
    def test_existing_conversion_renderer_is_not_replaced(self):
        p={'execution_kernel':{'request_entity_contracts':{'version':2},'methods':{'m':{'instructions':[self.call('java/lang/StringBuilder','append','(Ljava/lang/Object;)Ljava/lang/StringBuilder;')]}}}}
        self.assertEqual(features(p,{'classes':{}}),set())
    def test_render_selects_its_pinned_pack_without_save_or_task(self):
        from plan_async_dependencies import attach_async_dependencies
        contract=json.loads(Path(__file__).with_name('request-entity-contracts-20261021.json').read_text())
        p={'execution_kernel':{'version':2,'constructors':{}}}
        attach_async_dependencies(p,{'render'},{'classes':contract['class_sha256']})
        self.assertEqual(p['execution_kernel']['request_entity_contracts']['class_sha256'],contract['class_sha256'])
        self.assertNotIn('save_effect_contracts',p['execution_kernel']);self.assertNotIn('async_protocol',p)


if __name__=='__main__':unittest.main()
