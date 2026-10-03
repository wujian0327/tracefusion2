"""Real compiled Go instructions + synthetic boundary transport, not kernel proof.

Run with GIN_PROVENANCE_BUILD pointing to a successful runner `build` directory.
Native HTTP test requires loopback sockets; no BCC is needed for these tests.
"""
import copy
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

from test_read_provenance import execute,stats,uc
import gin_api_provenance as app
import gin_api_boundaries as boundary

BUILD=os.environ.get('GIN_PROVENANCE_BUILD')


def history(binary,plans,config):
    all_events=[];oracle=[];bases=None
    tid=(321<<32)|321;g=0x6000000
    files={str(fd):dict(fd=fd,path='/fixture/'+name,device=1,inode=fd,size=16,regular=True,access_mode=0)
           for fd,name in ((4,'a.bin'),(5,'b.bin'))}
    for rid,mode in enumerate(app.MODES,1):
        value=0 if mode=='zero' else (0xffffffff if mode=='max' else 424242)
        off=8 if mode=='zero' else (12 if mode=='max' else 0)
        def event(kind,**kwargs):
            regs=[0]*16;regs[14]=g
            return dict(kind=kind,pid_tid=tid,regs=regs,request_id=rid,**kwargs)
        rows=[event(3)]
        for io,fd,offset in ((1,4,0),(2,5,4)):
            args=dict(io_id=io,fd=fd,file_offset=off,requested=4,buffer_addr=0x2000000+offset)
            rows.extend([event(1,**args),event(2,**args,returned=4,read_error=0,
                                                   read_data=list(struct.pack('<I',value))+[0]*28)])
        functions=[('main.goSelectValue',1 if mode=='left' else 0)]
        if mode=='merge':functions=[('main.goMergeValues',0)]
        if mode=='overwrite':functions=[('main.goSelectValue',1),('main.goFallbackValue',0)]
        if mode=='same':functions=[('main.goCopyLeft',0),('main.goSelectValue',0)]
        for call,(function,selector) in enumerate(functions,1):
            compute,bases=execute(binary,plans,config,function,(value,value,99),selector,call)
            rows.extend(dict(e,request_id=rid) for e in compute)
        result=rows[-1]['outputs'][0];dst=rows[-1]['dst_addr']
        body=json.dumps({'balance':result},separators=(',',':'));data=list(body.encode())+[0]*(32-len(body))
        obj=dict(object_addr=dst,object_type=0x9000000,object_value=result,read_error=0)
        payload=dict(buffer_addr=0x9100000,requested=len(body),capacity=32,read_data=data,read_error=0)
        rows.extend([event(6,**obj,writer_addr=0x9200000),event(7,**obj),
                     event(8,**payload,error_type=0),event(10,**payload,writer_addr=0x9200000),
                     event(11,returned=len(body),error_type=0),event(9,error_type=0),event(4)])
        all_events.extend(rows)
        oracle.append(dict(request_id=rid,mode=mode,status=200,body=body,content_type='application/json; charset=utf-8'))
    for i,e in enumerate(all_events):e.update(observation_sequence=i,timestamp=i+1)
    return all_events,dict(functions=bases,read_files=files),oracle


@unittest.skipUnless(BUILD and uc,'requires GIN_PROVENANCE_BUILD and Unicorn')
class GinBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=Path(BUILD);cls.binary=cls.root/'hybrid-demo'
        cls.plans=json.loads((cls.root/'probe-plan.json').read_text())
        cls.config=json.loads((cls.root/'config.json').read_text())
        cls.events,cls.runtime,cls.oracle=history(cls.binary,cls.plans,cls.config)

    def infer(self,events=None):
        return boundary.bind(self.events if events is None else events,self.plans,self.config,self.runtime)

    def test_actual_compiled_business_paths_and_all_sources(self):
        inferred=self.infer();self.assertEqual(inferred['issues'],[])
        report=boundary.evaluate(inferred,self.oracle,stats(self.events),self.plans)
        self.assertTrue(report['passed'],report)
        self.assertEqual(report['external_source_relations'],dict(tp=14,fp=0,fn=0,precision=1.0,recall=1.0))
        self.assertEqual(report['compute_calls'],18)

    def test_reused_thread_g_object_and_buffer_are_request_local(self):
        result=self.infer();self.assertEqual(len(result['results']),14)
        ids=[n['id'] for r in result['results'] for n in r['dependency_graph']['nodes']]
        self.assertEqual(len(ids),len(set(ids)))
        right=result['results'][1];same=result['results'][4]
        self.assertEqual(right['body'],same['body'])
        self.assertEqual([s['file_name'] for s in same['external_sources']],['b.bin'])
        self.assertEqual(result['results'][3]['external_sources'],[])
        # Same output buffer was first written from a.bin, then overwritten by
        # equal b.bin bytes: inference must select the later computation.
        earlier=[r for r in result['compute_results'] if r['request_id']==5][0]
        self.assertEqual([s['file_name'] for s in earlier['external_sources']],['a.bin'])

    def test_missing_or_duplicate_boundary_rejected(self):
        for kind in (3,6,7,8,10,11,9,4):
            with self.subTest(kind=kind):
                rows=copy.deepcopy(self.events);index=next(i for i,e in enumerate(rows) if e['kind']==kind)
                rows.pop(index)
                for i,e in enumerate(rows):e['observation_sequence']=i
                self.assertTrue(self.infer(rows)['issues'])

    def test_object_slice_writer_and_failure_evidence_checked(self):
        mutations=[(6,'object_addr',123),(7,'object_type',123),(7,'object_value',123),
                   (8,'error_type',1),(8,'read_error',-1),(8,'requested',32),
                   (10,'buffer_addr',123),(10,'writer_addr',123),(11,'returned',0),
                   (11,'error_type',1),(9,'error_type',1),(6,'request_id',2)]
        for kind,key,value in mutations:
            with self.subTest(kind=kind,key=key):
                rows=copy.deepcopy(self.events);next(e for e in rows if e['kind']==kind)[key]=value
                self.assertTrue(self.infer(rows)['issues'])

    def test_g_switch_or_missing_event_never_silently_repaired(self):
        rows=copy.deepcopy(self.events);next(e for e in rows if e['kind']==7)['regs'][14]+=8
        self.assertTrue(self.infer(rows)['issues'])
        rows=copy.deepcopy(self.events);rows.pop(10)
        self.assertTrue(self.infer(rows)['issues'])

    def test_client_body_and_capture_loss_affect_evaluation_only(self):
        inferred=self.infer();client=copy.deepcopy(self.oracle);client[0]['body']='{"balance":1}'
        self.assertFalse(boundary.evaluate(inferred,client,stats(self.events),self.plans)['passed'])
        damaged=stats(self.events);damaged['lost_events']=1
        self.assertFalse(boundary.evaluate(inferred,self.oracle,damaged,self.plans)['passed'])
        self.assertEqual(self.infer(),inferred)

    def test_boundary_plan_has_fast_entries_and_ret_instructions(self):
        scopes=json.loads((self.root/'gin-boundary-plan.json').read_text())
        assembly=(self.root/'disassembly.txt').read_text();symbols=app.go.parse_nm((self.root/'symbols.txt').read_text())
        for key,scope in scopes.items():
            self.assertGreater(scope['entry_offset'],0)
            self.assertTrue(scope['return_offsets'])
            for off in scope['return_offsets']:
                addr=symbols[scope['function']][0]+off
                self.assertRegex(assembly,rf'\s{addr:x}:\s+ret\n')
        source=app.bpf_source(self.plans,self.config)
        self.assertIn('states.delete(&current_tid)',source)
        self.assertIn('e->object_type=ctx->cx; e->object_addr=ctx->di',source)
        self.assertIn('e->requested=ctx->bx; e->capacity=ctx->cx; e->error_type=ctx->di',source)
        self.assertNotIn('attach_uretprobe',Path(app.__file__).read_text())

    def test_generated_go_abi_handlers_with_native_memory(self):
        # Native mock helpers check register decoding and bounded slice reads.
        # This is intentionally NOT a BPF verifier or attachment test.
        source=app.bpf_source(self.plans,self.config)
        handlers=source[source.index('/* Go ABIInternal, linux/amd64'):]
        shim=r'''
#include <cassert>
#include <cstring>
#include <cstdint>
using u64=uint64_t; using u32=uint32_t; using s64=int64_t;
struct pt_regs { u64 ax=0,bx=0,cx=0,di=0,r14=0; };
struct event_t {
    u64 object_addr=0,object_type=0,writer_addr=0,error_type=0,capacity=0,requested=0,buffer_addr=0;
    u32 object_value=0,kind=0; int read_error=0; s64 returned=0; unsigned char read_data[32]{};
};
template<class T> struct Map { T value{}; T *lookup(u32*) {return &value;} };
Map<u64> boundary_current_g; event_t last; bool active=true; int errors=0,submitted=0;
bool in_read_scope() {return active;}
void count(int n) {if(n==2) ++errors;}
event_t *boundary_event(u32 kind) {last={};last.kind=kind;return &last;}
int emit_boundary(void*,event_t*) {++submitted;return 0;}
int bpf_probe_read_user(void *dst,u64 size,void *src) {assert(size<=31);std::memcpy(dst,src,size);return 0;}
'''
        main=r'''
int main() {
    u32 value=424242;char data[32]="{\"balance\":424242}";
    const auto object=reinterpret_cast<u64>(&value),buffer=reinterpret_cast<u64>(data);
    pt_regs r; r.r14=7;boundary_current_g.value=7;
    r.bx=123;r.cx=456;r.di=object;gin_render_enter(&r);
    assert(last.kind==6 && last.writer_addr==123 && last.object_type==456 && last.object_addr==object && last.object_value==value);
    r.ax=456;r.bx=object;gin_marshal_enter(&r);
    assert(last.kind==7 && last.object_addr==object && last.object_type==456 && last.object_value==value);
    r.ax=buffer;r.bx=std::strlen(data);r.cx=32;r.di=0;gin_marshal_exit(&r);
    assert(last.kind==8 && last.error_type==0 && last.buffer_addr==buffer && last.requested==std::strlen(data));
    assert(std::memcmp(last.read_data,data,std::strlen(data))==0);
    r.ax=123;r.bx=buffer;r.cx=std::strlen(data);r.di=32;gin_writer_enter(&r);
    assert(last.kind==10 && last.writer_addr==123 && std::memcmp(last.read_data,data,std::strlen(data))==0);
    r.ax=std::strlen(data);r.bx=0;gin_writer_exit(&r);assert(last.kind==11 && last.returned==static_cast<s64>(std::strlen(data)) && last.error_type==0);
    r.ax=0;gin_render_exit(&r);assert(last.kind==9 && last.error_type==0);
    r.ax=buffer;r.bx=32;r.cx=32;r.di=0;gin_marshal_exit(&r);assert(last.read_error==-1);
    r.bx=17;r.cx=1;gin_marshal_exit(&r);assert(last.read_error==-1);
    r.di=99;gin_marshal_exit(&r);assert(last.error_type==99);
    const auto n=submitted;r.r14=8;gin_render_exit(&r);assert(submitted==n && errors==1);
    active=false;r.r14=7;gin_render_exit(&r);assert(submitted==n);
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);code=folder/'shim.cc';binary=folder/'shim'
            code.write_text(shim+handlers+main)
            subprocess.run(['g++','-std=c++17','-O1',str(code),'-o',str(binary)],check=True,capture_output=True)
            subprocess.run([str(binary)],check=True)

    def test_real_gin_http_responses(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with (root/'program.stdout.jsonl').open('w') as stdout,(root/'program.stderr.log').open('w') as stderr:
                process=subprocess.Popen([str(self.binary),'--wait'],cwd=root,stdout=stdout,stderr=stderr)
                try:
                    app.common.wait_stopped(process)
                    import signal
                    process.send_signal(signal.SIGCONT)
                    app.client(root)
                    self.assertEqual(process.wait(timeout=12),0)
                finally:
                    if process.poll() is None:process.kill();process.wait()
            client=app.oracle(root)
            for expected,actual in zip(self.oracle,client):
                for key in ('mode','status','body','content_type'):self.assertEqual(expected[key],actual[key])
            self.assertEqual(len(client),14)


if __name__=='__main__':unittest.main()
