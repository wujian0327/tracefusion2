"""Dependency closure, alternative producers and certificate rejection checks."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from observation_selection import select_observations,verify_selection
from selection_rules import automatic_plan,validate_plan,DEFAULT_QUERIES,CHECKS
from test_observer import cost_fixture
import observer


class ClosureTests(unittest.TestCase):
    def test_backward_closure_keeps_all_alternative_producers(self):
        observations=[dict(site_id=3,facts=['a']),dict(site_id=7,facts=['a']),
                      dict(site_id=9,facts=['b']),dict(site_id=10,facts=['unrelated'])]
        rules={'answer':['a','middle'],'middle':['b']}
        c=select_observations(observations,rules,['answer'],{})
        self.assertEqual(c['selected_site_ids'],[3,7,9])
        self.assertEqual(c['derivation']['a']['sites'],[3,7])
        self.assertEqual(c['decisions'][-1]['action'],'drop')
        self.assertEqual(verify_selection(observations,rules,['answer'],{},c),c)

    def test_missing_fact_cycle_and_ambiguous_model_rejected(self):
        for observations,rules,target in (
            ([],{},'missing'),([],{'a':['b'],'b':['a']},'a'),
            ([dict(site_id=1,facts=['a'])],{'a':['b']},'a'),
            ([dict(site_id=1,facts=['a']),dict(site_id=1,facts=['b'])],{},'a')):
            with self.subTest(target=target),self.assertRaises(ValueError):
                select_observations(observations,rules,[target],{})

    def test_modified_model_or_certificate_rejected(self):
        obs=[dict(site_id=1,facts=['a'])];rules={'q':['a']}
        c=select_observations(obs,rules,['q'],{'binary':'first'})
        with self.assertRaises(ValueError):verify_selection(obs,rules,['q'],{'binary':'second'},c)
        c['selected_site_ids']=[]
        with self.assertRaises(ValueError):verify_selection(obs,rules,['q'],{'binary':'first'},c)


class CheckoutSelectionTests(unittest.TestCase):
    def test_query_change_changes_observations_without_kind_filter(self):
        p,_=cost_fixture()
        item=automatic_plan(p,['identity.Item'])
        both=automatic_plan(p)
        checked=automatic_plan(p,DEFAULT_QUERIES+(CHECKS,))
        self.assertEqual({s['kind'] for s in item['sites']},{'entry','publication','exit'})
        self.assertEqual({s['kind'] for s in both['sites']},
                         {'entry','publication','exit','conversion_enter','conversion_return'})
        self.assertEqual(checked['sites'],p['sites'])
        validate_plan(item,executable=False);validate_plan(both);validate_plan(checked)
        with self.assertRaises(ValueError):validate_plan(item)

    def test_additional_return_branch_is_not_discarded(self):
        p,_=cost_fixture();alternative=copy.deepcopy(p['sites'][3])
        alternative.update(id=100,address=9000);p['sites'].append(alternative)
        selected=automatic_plan(p)
        self.assertEqual(selected['selection']['certificate']['derivation']['scope.exit']['sites'],[3,100])
        self.assertIn(100,[s['id'] for s in selected['sites']])

    def test_missing_evidence_inventory_rejected_before_execution(self):
        for kind in ('entry','exit','publication','conversion_enter','conversion_return'):
            p,_=cost_fixture();p['sites']=[s for s in p['sites'] if s['kind']!=kind]
            with self.subTest(kind=kind),self.assertRaises(ValueError):automatic_plan(p)

    def test_changed_binary_or_probe_and_deleted_retained_sites_rejected(self):
        p,_=cost_fixture();selected=automatic_plan(p)
        for index in range(len(selected['sites'])):
            bad=copy.deepcopy(selected);del bad['sites'][index]
            with self.subTest(index=index),self.assertRaises(ValueError):validate_plan(bad)
        for change in (lambda x:x.update(binary_sha256='another'),
                       lambda x:x['sites'][0].update(address=17),
                       lambda x:x.update(cost_offset=99)):
            bad=copy.deepcopy(selected);change(bad)
            with self.assertRaises(ValueError):validate_plan(bad)

    def test_unsupported_query_or_observation_is_not_silently_dropped(self):
        p,_=cost_fixture()
        for query in ('full_write_history','numeric_dependency','remote_database_origin'):
            with self.subTest(query=query),self.assertRaises(ValueError):automatic_plan(p,[query])
        p['sites'].append(dict(id=111,kind='unmodeled',address=99999))
        with self.assertRaises(ValueError):automatic_plan(p)

    def test_checked_query_preserves_existing_conflict_detection(self):
        p,d=cost_fixture();selected=automatic_plan(p,DEFAULT_QUERIES+(CHECKS,))
        self.assertEqual(observer.infer(selected,d),observer.infer(p,d))
        next(e for e in d['events'] if e['site']==4)['b']=777
        with self.assertRaises(ValueError):observer.infer(selected,d)


if __name__=='__main__':unittest.main()
