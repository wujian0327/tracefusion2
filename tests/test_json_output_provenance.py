"""Independent native JSON oracle, real pread and Unicorn; no kernel claim."""
import copy
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

from test_read_provenance import execute,stats,uc
import json_output_provenance as app
import json_output_boundaries as boundary

SCENARIO=app.read.common.ROOT/'scenarios/json-output-provenance'


def make_history(binary,plans,config):
    events=[];read_id=call_id=format_id=write_id=0
    memory=bytearray(struct.pack('<III',0,0,99));last_value=0;last_payload=b'';bases={}
    def emit(kind,**kw):
        events.append(dict(kind=kind,pid_tid=(321<<32)|321,**kw))
    emit(3)
    with tempfile.TemporaryDirectory() as tmp:
        paths=[Path(tmp)/name for name in ('a.bin','b.bin')]
        for p in paths:p.write_bytes(struct.pack('<IIII',424242,424243,0,0xffffffff))
        a,b=[os.open(p,os.O_RDONLY) for p in paths]
        files={str(fd):dict(fd=fd,path=str(p),device=p.stat().st_dev,inode=p.stat().st_ino,size=16,regular=True,access_mode=0) for fd,p in zip((a,b),paths)}
        def read(fd,slot,off):
            nonlocal read_id
            read_id+=1;kw=dict(io_id=read_id,fd=fd,file_offset=off,requested=4,buffer_addr=0x2000000+slot)
            emit(1,**kw)
            try:data=os.pread(fd,4,off);n=len(data)
            except OSError as exc:data=b'';n=-exc.errno
            memory[slot:slot+max(0,n)]=data
            emit(2,**kw,returned=n,read_error=0,read_data=list(data)+[0]*(32-len(data)))
        def compute(name,selector=1):
            nonlocal call_id,last_value,bases
            call_id+=1
            machine,bases=execute(binary,plans,config,name,struct.unpack('<III',memory),selector,call_id)
            events.extend(machine);last_value=machine[-1]['outputs'][0]
        def serialize():
            nonlocal format_id,last_payload
            format_id+=1
            # Independent JSON library, not the inference serializer model.
            last_payload=(json.dumps({'value':last_value},separators=(',',':'))+'\n').encode()
            kw=dict(io_id=format_id,src_addr=0x3000000,buffer_addr=0x7000000,outputs=[last_value,0],source_error=0,requested=32)
            emit(6,**kw)
            emit(7,**kw,returned=len(last_payload),read_error=0,read_data=list(last_payload)+[0]*(32-len(last_payload)))
        def write(fd=1):
            nonlocal write_id
            write_id+=1;kw=dict(io_id=write_id,fd=fd,buffer_addr=0x7000000,requested=len(last_payload))
            emit(8,**kw,read_error=0,read_data=list(last_payload)+[0]*(32-len(last_payload)))
            emit(9,**kw,returned=len(last_payload) if fd==1 else -9)
        try:
            for round_id in range(2):
                off=round_id*4
                for case in range(9):
                    if case<=2:read(a,0,off);read(b,4,off)
                    elif case==7:read(-1,0,off)
                    else:
                        read(a,0,off)
                        if case==3:read(b,0,off)
                        elif case==4:read(a,0,(1-round_id)*4)
                        elif case==5:read(-1,0,off)
                        elif case==6:read(b,0,16)
                        elif case==8:read(a,0,off)
                    compute('merge_values' if case==2 else 'fallback_value' if case==7 else 'select_value',0 if case==1 else 1)
                    serialize();write()
            read(a,0,0);read(b,4,0)
            compute('select_value');compute('fallback_value');serialize();write()
            read(a,0,0);read(b,4,0)
            compute('copy_left');serialize();compute('select_value',0);serialize();write()
            read(a,0,0);read(b,4,0)
            compute('select_value');serialize();write(-1)
            for off in (8,12):
                read(b,4,off);compute('select_value',0);serialize();write()
        finally:os.close(a);os.close(b)
    emit(4)
    for i,e in enumerate(events):e.update(observation_sequence=i,timestamp=i+1)
    return events,dict(functions=bases,read_files=files)


@unittest.skipUnless(uc and shutil.which('gcc'),'Requires GCC and optional Unicorn')
class JsonOutputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();out=Path(cls.tmp.name)
        cls.binary,cls.plans,cls.config=app.build(SCENARIO,out)
        native=subprocess.run([str(cls.binary)],capture_output=True,check=True)
        cls.oracle=dict(**json.loads(native.stderr),stdout_bytes=list(native.stdout))
        cls.events,cls.runtime=make_history(cls.binary,cls.plans,cls.config)
        cls.result=boundary.bind(cls.events,cls.plans,cls.config,cls.runtime)

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def replay(self,events):return boundary.bind(events,self.plans,self.config,self.runtime)

    def test_native_json_independent_oracle_and_instruction_execution(self):
        self.assertEqual(self.result['issues'],[])
        score=boundary.evaluate(self.result,self.oracle,stats(self.events),self.plans)
        self.assertTrue(score['passed'],score)
        self.assertEqual((len(self.result['results']),len(self.result['read_operations']),score['formats'],score['writes'],score['emitted_json_fields']),(25,42,24,23,22))
        self.assertEqual(score['output_source_relations'],dict(tp=21,fp=0,fn=0,precision=1.0,recall=1.0))
        self.assertEqual([json.loads(line) for line in bytes(self.result['stdout_bytes']).splitlines()][-2:],[{'value':0},{'value':4294967295}])

    def test_real_output_graph_links_summary_and_accepted_write(self):
        r=self.result['output_fields'][2]
        self.assertEqual({s['file_name'] for s in r['external_sources']},{'a.bin','b.bin'})
        edges=r['dependency_graph']['edges']
        self.assertEqual(len([e for e in edges if e['kind']=='serialization-summary']),1)
        self.assertEqual(len([e for e in edges if e['kind']=='accepted-write']),1)
        n=next(n for n in r['dependency_graph']['nodes'] if n.get('kind')=='stdout-json-field')
        self.assertEqual(bytes(r['data'])[n['offset']:n['offset']+n['length']],str(r['value']).encode())

    def test_overwrite_before_format_and_reuse_json_buffer(self):
        constant=self.result['output_fields'][18]
        self.assertEqual((constant['call_id'],constant['value'],constant['external_sources']),(20,42,[]))
        self.assertEqual(self.result['formats'][19]['data'],self.result['formats'][20]['data'])
        self.assertEqual(self.result['formats'][19]['external_sources'][0]['file_name'],'a.bin')
        reused=self.result['output_fields'][19]
        self.assertEqual((reused['call_id'],reused['format_id']),(22,21))
        self.assertEqual(reused['external_sources'][0]['file_name'],'b.bin')
        self.assertNotIn(20,{o['format_id'] for o in self.result['output_fields']})

    def test_failed_write_has_no_emitted_field(self):
        failed=self.result['write_operations'][20]
        self.assertEqual((failed['returned'],failed['data'],failed['status']),(-9,[],'not-written'))
        self.assertNotIn(failed['write_id'],{r['write_id'] for r in self.result['output_fields']})

    def test_matching_value_or_bytes_cannot_replace_address_identity(self):
        for kind,key in ((6,'src_addr'),(8,'buffer_addr')):
            events=copy.deepcopy(self.events);next(e for e in events if e['kind']==kind)[key]+=4
            self.assertTrue(self.replay(events)['issues'])

    def test_missing_duplicate_or_unpaired_output_evidence_rejected(self):
        for kind in (6,7,8,9):
            events=copy.deepcopy(self.events);i=next(i for i,e in enumerate(events) if e['kind']==kind);del events[i]
            self.assertTrue(self.replay(events)['issues'])
            for i,e in enumerate(events):e.update(observation_sequence=i,timestamp=i+1)
            self.assertTrue(self.replay(events)['issues'])
        events=copy.deepcopy(self.events);events.insert(1,copy.deepcopy(events[1]))
        self.assertTrue(self.replay(events)['issues'])

    def test_mutation_truncation_and_partial_write_rejected(self):
        for kind,field,value in ((6,'source_error',-14),(7,'returned',1),(7,'read_error',-14),(8,'read_error',-14),(9,'returned',1)):
            events=copy.deepcopy(self.events);next(e for e in events if e['kind']==kind)[field]=value
            self.assertTrue(self.replay(events)['issues'])
        for kind in (7,8):
            events=copy.deepcopy(self.events);next(e for e in events if e['kind']==kind)['read_data'][10]^=1
            self.assertTrue(self.replay(events)['issues'])
        events=copy.deepcopy(self.events);next(e for e in events if e['kind']==6)['outputs'][0]+=1
        self.assertTrue(self.replay(events)['issues'])

    def test_unknown_descriptor_and_execution_context_rejected(self):
        for kind in (8,9):
            events=copy.deepcopy(self.events);next(e for e in events if e['kind']==kind)['fd']=3
            self.assertTrue(self.replay(events)['issues'])
        events=copy.deepcopy(self.events);next(e for e in events if e['kind']==7)['pid_tid']+=1
        self.assertTrue(self.replay(events)['issues'])

    def test_true_stdout_and_oracle_only_affect_evaluation(self):
        oracle=copy.deepcopy(self.oracle);oracle['stdout_bytes'][0]^=1
        self.assertFalse(boundary.evaluate(self.result,oracle,stats(self.events),self.plans)['passed'])
        oracle=copy.deepcopy(self.oracle);oracle['writes'][0]['call_id']=2
        self.assertFalse(boundary.evaluate(self.result,oracle,stats(self.events),self.plans)['passed'])
        capture=stats(self.events);capture['lost_events']=1
        self.assertFalse(boundary.evaluate(self.result,self.oracle,capture,self.plans)['passed'])
        self.assertFalse(self.result['oracle_used_for_inference'])

    @unittest.skipUnless(shutil.which('g++'),'C++ compiler unavailable')
    def test_generated_boundary_handlers_in_native_shim(self):
        # Execute actual generated callbacks. Stubs cover helper/map wiring,
        # not the kernel verifier or BCC compilation pipeline.
        generated=app.bpf_source(self.plans,self.config)
        generated=generated[generated.index('/* A bounded serializer SUMMARY'):]
        shim=r"""
#include <cassert>
#include <cstring>
#include <cstdint>
#include <cstdio>
#include <vector>
using u64=uint64_t;using u32=uint32_t;using s64=int64_t;using s32=int32_t;
struct pt_regs { u64 di,si,ax; };
struct event_t { u64 io_id,src_addr,buffer_addr,requested;u32 kind,outputs[8];s32 source_error,read_error,fd;s64 returned;unsigned char read_data[32]; };
template<class T> struct Map { T value{};T *lookup(u32*) {return &value;} };
#define BPF_ARRAY(name,type,size) Map<type> name
// BCC's ordinary tracepoint macro exposes args (unlike its raw macro).
#define TRACEPOINT_PROBE(category,event) int tracepoint__##category##__##event(struct tracepoint__##category##__##event *args)
struct tracepoint__syscalls__sys_enter_write { u64 fd,buf,count; };
struct tracepoint__syscalls__sys_exit_write { s64 ret; };
bool active=true,read_failure=false;int hits=0,errors=0;event_t scratch{};std::vector<event_t> emitted;
bool in_read_scope() {return active;}
void count(u32 key) {if(key==3)++hits;else if(key==2)++errors;else assert(false);}
int bpf_probe_read_user(void *dst,unsigned size,void *src) {if(read_failure)return -14;std::memcpy(dst,src,size);return 0;}
event_t *boundary_event(u32 kind) {scratch={};scratch.kind=kind;return &scratch;}
int emit_boundary(void *,event_t *e) {emitted.push_back(*e);return 0;}
"""
        main=r"""
int main() {
    u32 value=4294967295U;char buffer[32]={};
    pt_regs ctx{reinterpret_cast<u64>(buffer),reinterpret_cast<u64>(&value),0};
    json_format_enter(&ctx);
    assert(emitted.back().kind==6 && emitted.back().outputs[0]==value);
    assert(emitted.back().src_addr==ctx.si && emitted.back().buffer_addr==ctx.di);
    int n=std::snprintf(buffer,32,"{\"value\":%u}\n",value);ctx.ax=n;
    json_format_exit(&ctx);
    assert(emitted.back().kind==7 && emitted.back().returned==n);
    assert(std::memcmp(emitted.back().read_data,buffer,n+1)==0);
    struct tracepoint__syscalls__sys_enter_write entry{1,ctx.di,static_cast<u64>(n)};
    struct tracepoint__syscalls__sys_exit_write exit{n};
    tracepoint__syscalls__sys_enter_write(&entry);tracepoint__syscalls__sys_exit_write(&exit);
    assert(emitted.back().kind==9 && emitted.back().returned==n && emitted.back().fd==1);
    entry.fd=static_cast<u64>(-1);exit.ret=-9;
    tracepoint__syscalls__sys_enter_write(&entry);tracepoint__syscalls__sys_exit_write(&exit);
    assert(emitted.back().fd==-1 && emitted.back().returned==-9);
    json_format_enter(&ctx);ctx.ax=static_cast<u64>(-1);json_format_exit(&ctx);
    assert(emitted.back().returned==-1 && emitted.back().read_error==-1);
    read_failure=true;json_format_enter(&ctx);assert(emitted.back().source_error==-14);
    ctx.ax=n;json_format_exit(&ctx);assert(emitted.back().read_error==-14);
    read_failure=false;json_format_exit(&ctx);assert(errors==1);
    entry.count=33;tracepoint__syscalls__sys_enter_write(&entry);assert(emitted.back().read_error==-1);
    tracepoint__syscalls__sys_exit_write(&exit);
    auto before=emitted.size();active=false;json_format_enter(&ctx);
    tracepoint__syscalls__sys_enter_write(&entry);assert(emitted.size()==before);
}
"""
        folder=Path(self.tmp.name)/'boundary-shim';folder.mkdir()
        source=folder/'shim.cc';source.write_text(shim+generated+main)
        binary=folder/'shim'
        compiled=subprocess.run(['g++','-std=c++17','-O1',str(source),'-o',str(binary)],capture_output=True,text=True)
        self.assertEqual(compiled.returncode,0,compiled.stderr)
        subprocess.run([str(binary)],check=True)

    def test_serializer_model_numeric_boundaries(self):
        for value in (0,9,10,99,100,2147483648,4294967295):
            self.assertEqual(boundary.encode_u32(value),(json.dumps({'value':value},separators=(',',':'))+'\n').encode())
        for value in (-1,4294967296):
            with self.assertRaises(ValueError):boundary.encode_u32(value)


if __name__=='__main__':unittest.main()
