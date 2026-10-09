"""Synthetic transport/inference checks; these are explicitly NOT BPF runs."""
import copy
import ctypes as ct
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import observer as o


def fixture(inputs=(101,),outputs=(101,),error=False):
    kinds=('entry','field_operand','publication','exit')
    plan=dict(binary_sha256='test-sha',item_offset=40,cost_offset=48,sites=[
        dict(id=i,kind=k,address=4096+i*16,base='AX' if k=='field_operand' else 'R8',value='R10',index='DX')
        for i,k in enumerate(kinds)],event_order=list(range(4)))
    events=[]
    def add(kind,**kw):
        e=dict(site=kinds.index(kind),kind=kind,timestamp=len(events)+1,pid_tid=(10<<32)|11,
               g=512,a=0,b=0,c=0,n=0,values=[],items=[])
        e.update(kw);events.append(e)
    add('entry',a=1000,n=len(inputs),values=list(inputs))
    for i,v in enumerate(outputs):
        add('field_operand',a=2000+i*64,b=v)
        add('publication',a=3000,n=i,b=2000+i*64,c=v)
    add('exit',a=3000,n=0 if error else len(outputs),b=99 if error else 0,
        values=[] if error else [2000+i*64 for i in range(len(outputs))],items=[] if error else list(outputs))
    stats=dict(submitted=len(events),lost=0,read_errors=0,submit_errors=0,
               probe_hits=len(events),pid_rejections=0,namespace_errors=0)
    return plan,dict(binary_sha256='test-sha',returncode=0,capture_errors=[],events=events,stats=stats)


def cost_fixture(results=(801,802),costs=(802,801)):
    plan,doc=fixture((101,102),(101,102))
    plan['schema_version']=2
    plan['sites'][1]['field']='Item'
    for kind in ('field_operand','conversion_enter','conversion_return'):
        i=len(plan['sites'])
        plan['sites'].append(dict(id=i,kind=kind,address=4096+i*16,field='Cost',base='AX',value='R12'))
        plan['event_order'].append(i)
    template=copy.deepcopy(doc['events'][0])
    conversion_events=[]
    for i,result in enumerate(results):
        for site,kind,a,b in ((5,'conversion_enter',900+i*64,0),(6,'conversion_return',result,0 if result else 88)):
            e=dict(template,site=site,kind=kind,a=a,b=b,n=0,values=[],items=[],costs=[],d=0)
            conversion_events.append(e)
    events=[doc['events'][0],*conversion_events]
    for i in range(2):
        item=copy.deepcopy(doc['events'][1+i*2]);publication=copy.deepcopy(doc['events'][2+i*2])
        cost=dict(item,site=4,b=costs[i])
        publication['d']=costs[i]
        events.extend((item,cost,publication))
    exit=dict(doc['events'][-1],costs=list(costs))
    events.append(exit)
    for i,e in enumerate(events):e['timestamp']=i+1
    doc['events']=events;doc['stats'].update(submitted=len(events),probe_hits=len(events))
    return plan,doc


class IdentityTests(unittest.TestCase):
    def test_distinct_equal_values_do_not_merge_objects(self):
        plan,doc=fixture((101,102),(102,101))
        got=o.infer(plan,doc)
        self.assertEqual([v['source_candidates'] for v in got['outputs']],[[1],[0]])

    def test_alias_preserves_position_ambiguity(self):
        p,d=fixture((101,102,101),(101,))
        result=o.infer(p,d)['outputs'][0]
        self.assertEqual(result['source_candidates'],[0,2])
        self.assertEqual(result['status'],'ambiguous_input_position')

    def test_unrecognized_reference_is_unknown(self):
        p,d=fixture((101,),(999,))
        self.assertEqual(o.infer(p,d)['outputs'][0]['status'],'unknown')

    def test_empty(self):
        p,d=fixture((),())
        self.assertEqual(o.infer(p,d)['outputs'],[])

    def test_error_discards_partial_publications(self):
        p,d=fixture(error=True)
        got=o.infer(p,d)
        self.assertTrue(got['error']);self.assertEqual(got['outputs'],[])
        self.assertEqual(got['publications'],1)

    def test_callback_order_is_not_execution_order(self):
        p,d=fixture()
        d['events'].reverse()
        self.assertEqual(o.infer(p,d)['outputs'][0]['source_candidates'],[0])

    def test_os_thread_change_preserves_goroutine_identity(self):
        p,d=fixture()
        d['events'][-1]['pid_tid']=(10<<32)|12
        self.assertEqual(o.infer(p,d)['observed_threads'],2)

    def test_missing_evidence_is_rejected(self):
        for index in (0,1,2,3):
            with self.subTest(index=index):
                p,d=fixture();del d['events'][index];d['stats']['submitted']-=1;d['stats']['probe_hits']-=1
                with self.assertRaises(ValueError):o.infer(p,d)

    def test_corrupt_or_incomplete_capture_rejected(self):
        changes=(lambda d:d.update(binary_sha256='wrong'),
                 lambda d:d['stats'].update(lost=1),
                 lambda d:d['stats'].update(submitted=99),
                 lambda d:d['stats'].update(namespace_errors=1),
                 lambda d:d['events'][-1].update(g=999),
                 lambda d:d['events'][-1].update(items=[102]),
                 lambda d:d['events'][1].update(b=102),
                 lambda d:d['events'][2].update(timestamp=2),
                 lambda d:d['events'][1].update(site=99))
        for i,change in enumerate(changes):
            with self.subTest(i=i):
                p,d=fixture();change(d)
                with self.assertRaises(ValueError):o.infer(p,d)

    def test_later_conflicting_operand_not_hidden_by_old_equal_value(self):
        p,d=fixture()
        newer=copy.deepcopy(d['events'][1]);newer.update(timestamp=2.5,b=999)
        d['events'].insert(2,newer);d['stats']['submitted']+=1;d['stats']['probe_hits']+=1
        with self.assertRaises(ValueError):o.infer(p,d)

    def test_independent_truth_comparison_catches_wrong_relation(self):
        p,d=fixture();r=o.infer(p,d)
        truth=dict(case='unit',inputs=[101],error=False,outputs=[dict(object=2000,item=101,source_candidates=[1])])
        with self.assertRaises(ValueError):o.evaluate(r,truth)

    def test_perf_padding_and_layout(self):
        self.assertEqual(ct.sizeof(o.Raw),840)
        raw=o.Raw();raw.site=0;raw.n=1;raw.values[0]=123
        sites={0:dict(kind='entry')}
        for n in (840,844):
            buf=ct.create_string_buffer(bytes(raw)+b'\x00'*4)
            self.assertEqual(o.decode_record(ct.addressof(buf),n,sites)['values'],[123])
        with self.assertRaises(ValueError):o.decode_record(ct.addressof(buf),580,sites)

    def test_generated_source_uses_pointer_layout_and_bound(self):
        p,_=fixture();s=o.source(p,100,SimpleNamespace(st_dev=1,st_ino=2))
        self.assertIn('u64 values[32],items[32],costs[32]',s)
        self.assertNotIn('e->pointer',s)
        self.assertIn('e->values[i]+40',s)
        self.assertEqual(s.count('int probe_'),4)
        self.assertNotIn('TARGET_PID',s)


class CostIdentityTests(unittest.TestCase):
    def test_matches_reference_not_output_position(self):
        p,d=cost_fixture()
        r=o.infer(p,d)
        self.assertEqual([v['cost_source_candidates'] for v in r['outputs']],[[1],[0]])
        self.assertEqual([v['cost_status'] for v in r['outputs']],['exact_reference']*2)

    def test_same_reference_in_multiple_returns_is_ambiguous(self):
        p,d=cost_fixture((801,801),(801,801))
        r=o.infer(p,d)['outputs'][0]
        self.assertEqual(r['cost_source_candidates'],[0,1])
        self.assertEqual(r['cost_status'],'ambiguous_conversion_instance')

    def test_unknown_cost_does_not_borrow_loop_index(self):
        p,d=cost_fixture(costs=(999,801))
        r=o.infer(p,d)['outputs'][0]
        self.assertEqual(r['cost_status'],'unknown')
        self.assertEqual(r['cost_source_candidates'],[])

    def test_failed_conversion_not_a_successful_source(self):
        p,d=cost_fixture((0,802),(802,802))
        r=o.infer(p,d)
        self.assertTrue(r['conversions'][0]['error'])
        self.assertEqual(r['outputs'][0]['cost_source_candidates'],[1])

    def test_missing_conversion_or_cost_evidence_rejected(self):
        for site in (4,5,6):
            p,d=cost_fixture()
            index=next(i for i,e in enumerate(d['events']) if e['site']==site)
            del d['events'][index]
            d['stats']['submitted']-=1;d['stats']['probe_hits']-=1
            with self.subTest(site=site),self.assertRaises(ValueError):o.infer(p,d)

    def test_final_cost_and_operand_conflicts_rejected(self):
        for target in ('final','operand'):
            p,d=cost_fixture()
            if target=='final':d['events'][-1]['costs'][0]=999
            else:next(e for e in d['events'] if e['site']==4)['b']=999
            with self.subTest(target=target),self.assertRaises(ValueError):o.infer(p,d)

    def test_future_return_cannot_explain_prior_publication(self):
        p,d=cost_fixture()
        # Move the second conversion after first publication; output[0] refers
        # to its pointer but that future event cannot be evidence for this write.
        enter,ret=d['events'][3:5]
        del d['events'][3:5]
        index=next(i for i,e in enumerate(d['events']) if e['kind']=='publication')+1
        d['events'][index:index]=[enter,ret]
        for i,e in enumerate(d['events']):e['timestamp']=i+1
        r=o.infer(p,d)
        self.assertEqual(r['outputs'][0]['cost_status'],'unknown')

    def test_truth_checks_conversion_input_and_output_mapping(self):
        p,d=cost_fixture();r=o.infer(p,d)
        keys=('object','item','source_candidates','cost','cost_source_candidates')
        truth=dict(case='synthetic',inputs=[101,102],error=False,conversions=copy.deepcopy(r['conversions']),
                   outputs=[{k:v[k] for k in keys} for v in r['outputs']])
        self.assertTrue(o.evaluate(r,truth)['passed'])
        truth['conversions'][0]['input']=999
        with self.assertRaises(ValueError):o.evaluate(r,truth)

    def test_cost_snapshot_decoding_and_abi(self):
        raw=o.Raw();raw.site=3;raw.n=1;raw.costs[0]=801;raw.d=777
        buf=ct.create_string_buffer(bytes(raw)+b'\x00'*4)
        event=o.decode_record(ct.addressof(buf),844,{3:dict(kind='exit')})
        self.assertEqual(event['costs'],[801]);self.assertEqual(event['d'],777)
        p,_=cost_fixture();source=o.source(p,100,SimpleNamespace(st_dev=1,st_ino=2))
        self.assertIn('e->a=ctx->di;',source)
        self.assertIn('e->a=ctx->ax;e->b=ctx->bx;e->c=ctx->cx;',source)
        self.assertIn('e->values[i]+48',source)


if __name__=='__main__':unittest.main()
