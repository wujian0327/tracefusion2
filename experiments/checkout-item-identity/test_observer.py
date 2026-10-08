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
    plan=dict(binary_sha256='test-sha',item_offset=40,sites=[
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
        self.assertEqual(ct.sizeof(o.Raw),576)
        raw=o.Raw();raw.site=0;raw.n=1;raw.values[0]=123
        sites={0:dict(kind='entry')}
        for n in (576,580):
            buf=ct.create_string_buffer(bytes(raw)+b'\x00'*4)
            self.assertEqual(o.decode_record(ct.addressof(buf),n,sites)['values'],[123])
        with self.assertRaises(ValueError):o.decode_record(ct.addressof(buf),575,sites)

    def test_generated_source_uses_pointer_layout_and_bound(self):
        p,_=fixture();s=o.source(p,100,SimpleNamespace(st_dev=1,st_ino=2))
        self.assertIn('u64 values[32],items[32]',s)
        self.assertNotIn('e->pointer',s)
        self.assertIn('e->values[i]+40',s)
        self.assertEqual(s.count('int probe_'),4)
        self.assertNotIn('TARGET_PID',s)


if __name__=='__main__':unittest.main()
