import ctypes as ct
from copy import deepcopy
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from lineage_graph import backward_nodes
from value_lineage import infer
from go_string_adapter import SUMMARY, physical_probes
from string_capture import Raw, HEADER, decode_record, source
from go_string_provenance import score, negative_checks


def sample(equal=False):
    pairs=['scope','source','source','source','concat','json']
    sites=[{'id':2*p+i,'pair':p,'op':op,'phase':phase,'address':100+2*p+i,
            'values':SUMMARY[op][phase]}
           for p,op in enumerate(pairs) for i,phase in enumerate(('pre','post'))]
    sites[10]['address']=sites[9]['address']
    plan={'binary_sha256':'hash','sites':sites,'event_order':[0]+list(range(2,12))+[1]}
    def value(key,data):return {'key':key,'hex':data.encode().hex()}
    a,b,c=('SAME','SAME','SAME') if equal else ('13800138000','+86','UNUSED')
    values={2:{'path':value('p1','phone.txt')},3:{'value':value('a',a)},
            4:{'path':value('p2','prefix.txt')},5:{'value':value('b',b)},
            6:{'path':value('p3','other.txt')},7:{'value':value('c',c)},
            8:{'left':value('b',b),'right':value('a',a)},9:{'value':value('ab',b+a)},
            10:{'value':value('ab',b+a)},11:{'json':value('j',json.dumps({'result':b+a}))}}
    events=[dict(site=sid,op=sites[sid]['op'],phase=sites[sid]['phase'],pid=11,tid=22+(i%2),g=33,
                 timestamp=i,sequence=i,values=values.get(sid,{})) for i,sid in enumerate(plan['event_order'])]
    doc={'binary_sha256':'hash','capture_errors':[],'returncode':0,'events':events,
         'stats':{'submitted':12,'submit_errors':0,'read_errors':0,'lost':0}}
    oracle={'sources':['source:1','source:2'],'excluded':['source:3'],'result':b+a,
            'edges':[['source:2','concat:1','left'],['source:1','concat:1','right'],['concat:1','json:1','value'],['json:1','output:result','result']]}
    return doc,plan,oracle


class StringLineageTests(unittest.TestCase):
    def test_multisource_and_unused_read(self):
        for equal in (False,True):
            doc,plan,oracle=sample(equal)
            result=infer(doc,plan)
            self.assertEqual(result['status'],'resolved_under_configured_summaries',result)
            self.assertTrue(score(result,oracle)['passed'])
            self.assertNotIn('source:3',{n['id'] for n in result['graph']['nodes']})
            self.assertIn('source:3',{n['id'] for n in result['observed_graph']['nodes']})
            self.assertTrue(all(c['passed'] for c in negative_checks(doc,plan)))

    def test_same_value_origin_follows_observed_identity(self):
        doc,plan,oracle=sample(True)
        e=next(e for e in doc['events'] if e['op']=='concat' and e['phase']=='pre')
        e['values']['right']['key']='c'
        result=infer(doc,plan)
        self.assertEqual(result['sources'],['source:2','source:3'])
        self.assertFalse(score(result,oracle)['passed'])

    def test_alias_missing_or_changed_evidence_is_unknown(self):
        for mutation in ('alias','changed','empty','wrong_hash','other_g','lost'):
            doc,plan,_=sample(True)
            if mutation=='alias':doc['events'][6]['values']['value']['key']='a'
            elif mutation=='changed':doc['events'][7]['values']['right']['hex']=b'EDIT'.hex()
            elif mutation=='empty':doc['events']=[]
            elif mutation=='wrong_hash':doc['binary_sha256']='other'
            elif mutation=='other_g':doc['events'][2]['g']=99
            elif mutation=='lost':doc['stats']['lost']=1
            self.assertEqual(infer(doc,plan)['status'],'unknown',mutation)

    def test_coincident_positions_emit_return_before_entry(self):
        _,plan,_=sample()
        probes=physical_probes(plan)
        self.assertEqual(len(probes),11)
        shared=next(p for p in probes if len(p['sites'])==2)
        self.assertEqual([s['id'] for s in shared['sites']],[9,10])
        c=source(plan,123,SimpleNamespace(st_dev=4,st_ino=555))
        self.assertIn('logical_9(ctx); logical_10(ctx);',c)
        self.assertEqual(c.count('\nint probe_'),11)
        self.assertNotIn('__builtin_memset',c)

    def test_perf_padding_and_string_decoder(self):
        _,plan,_=sample();sites={s['id']:s for s in plan['sites']}
        raw=Raw();raw.site=8;raw.timestamp=1;raw.g=33;raw.pid_tid=(11<<32)|22
        for i,data in enumerate((b'SAME',b'SAME')):
            raw.pointer[i]=1000+i*100;raw.length[i]=len(data)
            for j,b in enumerate(data):raw.data[i][j]=b
        decoded=[]
        for padding in (b'',b'\xa5'*4):
            payload=bytes(raw)+padding;buf=ct.create_string_buffer(payload)
            decoded.append(decode_record(buf,len(payload),sites))
        self.assertEqual(decoded[0],decoded[1])
        self.assertNotEqual(decoded[0]['values']['left']['key'],decoded[0]['values']['right']['key'])
        for size in (0,ct.sizeof(Raw)-1,ct.sizeof(Raw)+1,ct.sizeof(Raw)+8):
            with self.assertRaises(ValueError):decode_record(None,size,sites)

    @unittest.skipUnless(shutil.which('gcc'),'GCC required')
    def test_c_event_layout_and_dirty_buffer_clear(self):
        structure=re.search(r'struct event_t \{.*?\n\};',HEADER,re.S).group()
        clear=HEADER[HEADER.index('typedef u64 clear_word_t'):HEADER.index('static __always_inline void snapshot')]
        code='#include <stdint.h>\n#include <stddef.h>\ntypedef uint64_t u64;typedef uint32_t u32;typedef uint8_t u8;\n'+structure+clear
        code+='\nvoid clear_test(struct event_t *e){clear_event(e);}\nsize_t sz(void){return sizeof(struct event_t);}\n'
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'c.c').write_text(code)
            subprocess.run(['gcc','-O2','-shared','-fPIC',str(p/'c.c'),'-o',str(p/'c.so')],check=True,capture_output=True)
            lib=ct.CDLL(str(p/'c.so'));lib.sz.restype=ct.c_size_t
            self.assertEqual(lib.sz(),ct.sizeof(Raw))
            self.assertEqual(ct.sizeof(Raw)%8,0)
            raw=Raw();ct.memset(ct.addressof(raw),0xa5,ct.sizeof(raw));lib.clear_test(ct.byref(raw))
            self.assertEqual(bytes(raw),bytes(ct.sizeof(raw)))
            self.assertNotIn('memset',subprocess.check_output(['nm','-u',str(p/'c.so')],text=True))

    def test_common_backward_slice_keeps_original_edge_policy(self):
        edges=[{'source':'a','target':'b','kind':'data'},{'source':'b','target':'a','kind':'data'},
               {'source':'b','target':'sink','kind':'return'},{'source':'c','target':'sink','kind':'control'}]
        self.assertEqual(backward_nodes(edges,['sink'],{'data','return'}),{'sink','a','b'})

if __name__=='__main__':unittest.main()
