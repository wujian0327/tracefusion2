"""Policy and measurement-accounting tests; no fabricated performance claims."""
import copy
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import observer as o
import benchmark as b
from test_observer import cost_fixture


def reaccount(doc):
    doc['stats'].update(submitted=len(doc['events']),probe_hits=len(doc['events']))


class PolicyTests(unittest.TestCase):
    def test_boundaries_same_reference_query_without_operand_events(self):
        p,d=cost_fixture();expected=o.infer(p,d)
        reduced=o.strategy_plan(p,'boundaries')
        d['events']=[e for e in d['events'] if e['kind']!='field_operand'];reaccount(d)
        self.assertEqual(o.infer(reduced,d),expected)
        self.assertTrue(any(s['kind']=='field_operand' for s in p['sites']))

    def test_boundaries_still_requires_publication_and_complete_capture(self):
        for failure in ('publication','lost'):
            p,d=cost_fixture();p=o.strategy_plan(p,'boundaries')
            d['events']=[e for e in d['events'] if e['kind']!='field_operand'];reaccount(d)
            if failure=='publication':
                index=next(i for i,e in enumerate(d['events']) if e['kind']=='publication')
                del d['events'][index];reaccount(d)
            else:d['stats']['lost']=1
            with self.subTest(failure=failure),self.assertRaises(ValueError):o.infer(p,d)

    def test_dense_deduplicates_addresses_and_accepts_extra_events(self):
        p,d=cost_fixture();expected=o.infer(p,d)
        inventory=dict(address=9999,file_offset=99,asm='MOVQ AX, 8(SP)',kind='store_operand',
                       memory=dict(base='SP',index=None,scale=1,offset=8),value='AX')
        p['store_inventory']=[inventory,dict(inventory,address=p['sites'][0]['address'])]
        dense=o.strategy_plan(p,'dense_stores')
        self.assertEqual(len(dense['sites']),len(p['sites'])+1)
        self.assertEqual(len({s['address'] for s in dense['sites']}),len(dense['sites']))
        extra=dict(d['events'][0],kind='store_operand',site=dense['sites'][-1]['id'],timestamp=1.5)
        d['events'].insert(1,extra);reaccount(d)
        self.assertEqual(o.infer(dense,d),expected)
        source=o.source(dense,100,SimpleNamespace(st_dev=1,st_ino=2))
        self.assertIn('e->a=ctx->sp+(8);e->b=ctx->ax;',source)

    def test_unknown_policy_and_undeclared_evidence_omission_rejected(self):
        p,d=cost_fixture()
        with self.assertRaises(ValueError):o.strategy_plan(p,'minimum-proven')
        p['operand_witnesses']=False
        with self.assertRaises(ValueError):o.infer(p,d)

    def test_current_policy_retains_conflict_checks(self):
        p,d=cost_fixture();p=o.strategy_plan(p,'current')
        next(e for e in d['events'] if e['site']==4)['b']=12345
        with self.assertRaises(ValueError):o.infer(p,d)


class BenchmarkTests(unittest.TestCase):
    def rows(self):
        values={'native':(100,0),'boundaries':(120,10),'current':(150,20),'dense_stores':(200,40)}
        return [dict(strategy=s,phase='measure',round=r,call_elapsed_ns=ns,
                     events=events,perf_payload_bytes=events*844,probe_sites=events,inference_ns=10)
                for r in range(3) for s,(ns,events) in values.items()]

    def test_balanced_seeded_schedule(self):
        a=b.schedule(5,1,99)
        self.assertEqual(a,b.schedule(5,1,99));self.assertNotEqual(a,b.schedule(5,1,98))
        self.assertEqual(len(a),24)
        for i in range(0,len(a),4):self.assertEqual({r['strategy'] for r in a[i:i+4]},set(b.STRATEGIES))

    def test_paired_ratios_and_warmup_exclusion(self):
        rows=self.rows()
        warmup=dict(rows[0],phase='warmup',call_elapsed_ns=99999999)
        report=b.summarize(rows+[warmup])
        self.assertEqual(report['current']['median_paired_native_ratio'],1.5)
        self.assertEqual(report['boundaries']['event_reduction_vs_current_percent'],50)
        self.assertEqual(report['dense_stores']['event_reduction_vs_current_percent'],-100)
        self.assertEqual(report['native']['call_ns_median'],100)

    def test_missing_or_duplicate_trial_rejected(self):
        rows=self.rows()
        for bad in (rows[:-1],rows+[copy.deepcopy(rows[-1])]):
            with self.assertRaises(ValueError):b.summarize(bad)


if __name__=='__main__':unittest.main()
