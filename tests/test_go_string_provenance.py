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
from value_lineage import infer, byte_origins
from go_string_adapter import SUMMARY, physical_probes
from string_capture import Raw, HEADER, decode_record, source
from go_string_provenance import score, negative_checks, fixtures, branch_pair_checks, copy_negative_checks, copy_checks, trim_negative_checks, trim_checks


def sample(equal=False,copy_value=False,use_other=False,trim_value=False):
    pairs=['scope','source','source','source']+(['copy'] if copy_value else [])+(['trim'] if trim_value else [])+['concat','json']
    sites=[{'id':2*p+i,'pair':p,'op':op,'phase':phase,'address':100+2*p+i,
            'values':SUMMARY[op][phase]}
           for p,op in enumerate(pairs) for i,phase in enumerate(('pre','post'))]
    sites[-2]['address']=sites[-3]['address']
    order=[0]+list(range(2,len(sites)))+[1]
    plan={'binary_sha256':'hash','sites':sites,'event_order':order,
          'allowed_event_orders':[[sid for sid in order if sites[sid]['op'] not in omitted]
                                  for omitted in ({'copy','trim'},{'trim'},{'copy'},set())]}
    def value(key,data):
        if trim_value:
            pointers={'a':0x1000,'b':0x2000,'c':0x3000,'copied':0x4000,
                      'trimmed':(0x4000 if copy_value else 0x3000 if use_other else 0x1000)+2}
            if key in pointers:key=f'{pointers[key]:x}:{len(data.encode())}'
        return {'key':key,'hex':data.encode().hex()}
    a,b,c=('SAME','SAME','SAME') if equal else ('13800138000','+86','UNUSED')
    selected=c if use_other else a;key='c' if use_other else 'a'
    original=selected
    before_trim='copied' if copy_value else key
    operand='trimmed' if trim_value else before_trim
    if trim_value:selected=selected[2:]
    ci=8+2*int(copy_value)+2*int(trim_value)
    values={2:{'path':value('p1','phone.txt')},3:{'value':value('a',a)},
            4:{'path':value('p2','prefix.txt')},5:{'value':value('b',b)},
            6:{'path':value('p3','other.txt')},7:{'value':value('c',c)},
            ci:{'left':value('b',b),'right':value(operand,selected)},ci+1:{'value':value('ab',b+selected)},
            ci+2:{'value':value('ab',b+selected)},ci+3:{'json':value('j',json.dumps({'result':b+selected}))}}
    if copy_value:values.update({8:{'value':value(key,original)},9:{'value':value('copied',original)}})
    if trim_value:
        ti=8+2*int(copy_value)
        values.update({ti:{'value':value(before_trim,original),'prefix':value('prefix','SA')},ti+1:{'value':value('trimmed',selected)}})
    events=[dict(site=sid,op=sites[sid]['op'],phase=sites[sid]['phase'],pid=11,tid=22+(i%2),g=33,
                 timestamp=i,sequence=i,values=values.get(sid,{})) for i,sid in enumerate(plan['event_order'])]
    doc={'binary_sha256':'hash','capture_errors':[],'returncode':0,'events':events,
         'stats':{'submitted':len(events),'submit_errors':0,'read_errors':0,'lost':0}}
    parent='source:3' if use_other else 'source:1'
    dependency=parent;edges=[]
    if copy_value:edges.append([dependency,'copy:1','input']);dependency='copy:1'
    if trim_value:edges.append([dependency,'trim:1','input']);dependency='trim:1'
    oracle={'sources':sorted([parent,'source:2']),'excluded':['source:1' if use_other else 'source:3'],'result':b+selected,
            'edges':edges+[['source:2','concat:1','left'],[dependency,'concat:1','right'],
                     ['concat:1','json:1','value'],['json:1','output:result','result']]}
    if trim_value:oracle['source_byte_ranges']=sorted([{'source':parent,'ranges':[[2,len(original.encode())]]},
        {'source':'source:2','ranges':[[0,len(b.encode())]]}],key=lambda x:x['source'])
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

    def test_branch_pair_requires_actual_source_switch(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            self.assertEqual(len(fixtures(out)),11)
            oracle={o['case']:o for o in json.loads((out/'oracle.json').read_text())}
            names=('branch_phone','branch_other')
            requests={n:json.loads((out/'inputs'/n/'request.json').read_text()) for n in names}
            self.assertEqual(oracle[names[0]]['result'],oracle[names[1]]['result'])
            self.assertEqual(oracle[names[0]]['sources'],['source:1','source:2'])
            self.assertEqual(oracle[names[1]]['sources'],['source:2','source:3'])
            self.assertEqual(Path(requests[names[0]]['Phone']).read_bytes(),Path(requests[names[1]]['Other']).read_bytes())
            docs={};results={};outputs={}
            for name in names:
                doc,plan,_=sample(True)
                if name=='branch_other':
                    next(e for e in doc['events'] if e['op']=='concat' and e['phase']=='pre')['values']['right']['key']='c'
                docs[name]=doc;results[name]=infer(doc,plan)
                outputs[name]={'result':'SAMESAME'}
            self.assertTrue(branch_pair_checks(results,docs,requests,outputs)['passed'])
            # Identical JSON is insufficient if both runs claim the same source.
            results['branch_other']=deepcopy(results['branch_phone'])
            self.assertFalse(branch_pair_checks(results,docs,requests,outputs)['passed'])

    def test_copy_preserves_selected_origin_across_new_identity(self):
        for use_other in (False,True):
            doc,plan,oracle=sample(equal=True,copy_value=True,use_other=use_other)
            result=infer(doc,plan)
            self.assertTrue(score(result,oracle)['passed'],result)
            node=next(n for n in result['graph']['nodes'] if n['kind']=='copy')
            self.assertNotEqual(node['input_identity'],node['output_identity'])
            self.assertEqual(len(result['graph']['edges']),5)
            # Equal bytes do not fix the parent: the observed copy input does.
            before=next(e for e in doc['events'] if e['op']=='copy' and e['phase']=='pre')
            before['values']['value']['key']='a' if use_other else 'c'
            switched=infer(doc,plan)
            self.assertEqual(switched['sources'],['source:1','source:2'] if use_other else ['source:2','source:3'])
            self.assertFalse(score(switched,oracle)['passed'])

    def test_missing_copy_cannot_be_recovered_by_equal_bytes(self):
        doc,plan,_=sample(equal=True,copy_value=True,use_other=True)
        checks=copy_negative_checks(doc,plan)
        self.assertTrue(all(c['passed'] for c in checks),checks)
        missing=next(c for c in checks if c['case']=='missing_copy_pair')
        self.assertEqual(missing['actual']['reason'],'Operand has no observed definition')

    def test_trim_maps_retained_bytes_through_copy_and_concat(self):
        for copied in (False,True):
            for other in (False,True):
                doc,plan,oracle=sample(equal=True,copy_value=copied,use_other=other,trim_value=True)
                result=infer(doc,plan)
                self.assertTrue(score(result,oracle)['passed'],result)
                self.assertEqual(len(result['graph']['edges']),6 if copied else 5)
                node=next(n for n in result['graph']['nodes'] if n['kind']=='trim')
                self.assertEqual(node['input_byte_range'],[2,4])
                self.assertTrue(all(c['passed'] for c in trim_negative_checks(doc,plan)))
                # Right source/edges with the wrong byte range must fail scoring.
                next(x for x in result['source_byte_ranges'] if x['source']==('source:3' if other else 'source:1'))['ranges']=[[0,4]]
                self.assertFalse(score(result,oracle)['passed'])

    def test_trim_rejects_missing_definition_and_unsupported_prefix(self):
        doc,plan,_=sample(equal=True,trim_value=True)
        missing=next(c for c in trim_negative_checks(doc,plan) if c['case']=='missing_trim_pair')
        self.assertEqual(missing['actual']['reason'],'Operand has no observed definition')
        pre=next(e for e in doc['events'] if e['op']=='trim' and e['phase']=='pre')
        pre['values']['prefix']['hex']=b'XX'.hex()
        self.assertEqual(infer(doc,plan)['status'],'unknown')

    def test_byte_mapping_merges_ranges_and_rejects_gaps(self):
        nodes={'s':{'kind':'source','length':8},'sink':{'kind':'output-field'}}
        maps={'sink':[('s',0,2,1),('s',2,4,3)]}
        self.assertEqual(byte_origins(nodes,maps,'sink',4),[{'source':'s','ranges':[[1,5]]}])
        with self.assertRaisesRegex(ValueError,'Incomplete byte mapping'):
            byte_origins(nodes,maps,'sink',5)

    def test_trim_comparison_requires_changed_output_and_retained_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);fixtures(out)
            docs={};results={};requests={};outputs={}
            for prefix in ('branch','copy','trim','copy_trim'):
                for suffix in ('phone','other'):
                    name=prefix+'_'+suffix
                    doc,plan,_=sample(equal=True,copy_value='copy' in prefix,use_other=suffix=='other',trim_value='trim' in prefix)
                    docs[name]=doc;results[name]=infer(doc,plan)
                    requests[name]=json.loads((out/'inputs'/name/'request.json').read_text())
                    outputs[name]={'result':'SAMEME' if 'trim' in prefix else 'SAMESAME'}
            self.assertTrue(trim_checks(results,docs,requests,outputs)['passed'])
            outputs['trim_other']=outputs['branch_other']
            self.assertFalse(trim_checks(results,docs,requests,outputs)['passed'])

    def test_copy_comparison_requires_new_storage_and_unchanged_origin(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);fixtures(out)
            docs={};results={};requests={};outputs={}
            for name in ('branch_phone','branch_other','copy_phone','copy_other'):
                doc,plan,_=sample(equal=True,copy_value=name.startswith('copy_'),use_other=name.endswith('other'))
                docs[name]=doc;results[name]=infer(doc,plan)
                requests[name]=json.loads((out/'inputs'/name/'request.json').read_text())
                outputs[name]={'result':'SAMESAME'}
            self.assertTrue(copy_checks(results,docs,requests,outputs)['passed'])
            node=next(n for n in results['copy_other']['graph']['nodes'] if n['kind']=='copy')
            node['output_identity']=node['input_identity']
            self.assertFalse(copy_checks(results,docs,requests,outputs)['passed'])

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
