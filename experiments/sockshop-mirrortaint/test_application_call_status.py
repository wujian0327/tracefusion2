import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from analysis_status import AnalysisLimit,failure_status
from plan_response_binding import plan_response
from run_planned_service import ROOT,load,save
import run_response_binding_revision as old


class ApplicationStatusTests(unittest.TestCase):
    def test_complete_analysis_budget_and_bad_evidence_have_distinct_target_states(self):
        for error,expected in [(AnalysisLimit('offline-execution','budget'),'analysis_limited'),(ValueError('Capture did not close'),'evidence_invalid')]:
            with tempfile.TemporaryDirectory() as tmp:
                dest=Path(tmp);(dest/'fixture').mkdir();(dest/'fixture/events.jsonl').write_text('')
                save(dest/'run.json',{'status':'business-completed','cleanup_returncode':0,'roles':['fixture'],'cases':[{'case':'one','message':'fixed','http_status':200,'response':{'text':'SAME'}}]})
                q={'id':'status-unit-only','application':'fixture','role':'fixture','path':'/text','entry':'Fixture.root'}
                with patch.object(old,'Reconstruction',side_effect=error),patch.object(old,'oracle',return_value=[]):result=old.evaluate(dest,dest,q)
                self.assertEqual(result[expected],1);self.assertEqual(result['N/A_requests'],0)
                self.assertEqual(result['evidence_invalid'],int(expected=='evidence_invalid'))
                self.assertEqual(result['analysis_limited'],int(expected=='analysis_limited'))

    def test_recursion_is_an_explicit_planning_boundary(self):
        key='Recursive.root(LItem;)LItem;'
        model={'classes':{'Recursive':{'access':1,'super':'java/lang/Object','interfaces':[],'fields':[],'sha256':'root'},'Item':{'access':1,'super':'java/lang/Object','interfaces':[],'fields':[{'name':'text','desc':'Ljava/lang/String;','access':1}],'sha256':'item'}},
            'methods':{key:{'owner':'Recursive','name':'root','access':8,'desc':'(LItem;)LItem;','try_catches':0,'exception_handlers':[],'instructions':[{'index':0,'op':25,'var':0},{'index':1,'op':184,'owner':'Recursive','name':'root','desc':'(LItem;)LItem;'},{'index':2,'op':176}]}}}
        with self.assertRaisesRegex(ValueError,'Recursive application call'):
            plan_response(model,key,'Item.text','/text',execution_kernel=True,application_calls=True)


if __name__=='__main__':unittest.main()
