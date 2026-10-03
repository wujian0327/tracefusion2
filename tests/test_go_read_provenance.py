"""Independent Go ABI/file evidence; actual compiler/BPF status kept separate."""
import copy
import json
import re
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import Mock

from test_read_provenance import make_history,stats,uc
from test_go_loop_provenance import compile_assembly
import go_read_provenance as app
import read_provenance as c_app

SCENARIO=app.go.common.ROOT/'scenarios/go-read-provenance'
ASSEMBLY=r'''
.intel_syntax noprefix
.text
.macro start name
.globl \name
.type \name,@function
\name:
.endm
.macro end name
.size \name,.-\name
.endm
start main.goSelectValue
cmp rsp,QWORD PTR [r14+0x10]
jbe .Lslow_select
push rbp
mov rbp,rsp
sub rsp,0x20
mov QWORD PTR [rsp+8],rax
mov rax,rbx
test ecx,ecx
je .Lpublic
call main.transformLeft
jmp .Ldone_select
.Lpublic:
call main.readRight
.Ldone_select:
mov rcx,QWORD PTR [rsp+8]
mov DWORD PTR [rcx],eax
add rsp,0x20
pop rbp
ret
.Lslow_select:
mov QWORD PTR [rsp+8],rax
call runtime.morestack_noctxt.abi0
jmp main.goSelectValue
end main.goSelectValue

start main.goMergeValues
cmp rsp,QWORD PTR [r14+0x10]
jbe .Lslow_merge
push rbp
mov rbp,rsp
sub rsp,0x20
mov QWORD PTR [rsp+8],rax
mov QWORD PTR [rsp+16],rbx
mov rax,rbx
call main.transformLeft
mov DWORD PTR [rsp+24],eax
mov rax,QWORD PTR [rsp+16]
call main.readRight
mov ecx,DWORD PTR [rsp+24]
add eax,ecx
mov rdx,QWORD PTR [rsp+8]
mov DWORD PTR [rdx],eax
add rsp,0x20
pop rbp
ret
.Lslow_merge:
mov QWORD PTR [rsp+8],rax
call runtime.morestack_noctxt.abi0
jmp main.goMergeValues
end main.goMergeValues

start main.goFallbackValue
mov DWORD PTR [rax],42
ret
end main.goFallbackValue
start main.transformLeft
mov eax,DWORD PTR [rax]
xor eax,0x55
add eax,3
ret
end main.transformLeft
start main.readRight
mov eax,DWORD PTR [rax+4]
ret
end main.readRight

start main.runWorkload
lea r12,[rsp-0x30]
cmp r12,QWORD PTR [r14+0x10]
jbe .Lslow_workload
push rbp
mov rbp,rsp
sub rsp,0x20
add rsp,0x20
pop rbp
ret
.Lslow_workload:
call runtime.morestack_noctxt.abi0
jmp main.runWorkload
end main.runWorkload
start runtime.morestack_noctxt.abi0
ret
end runtime.morestack_noctxt.abi0
.section .note.GNU-stack,"",@progbits
'''


def disassemble(binary):
    asm=subprocess.check_output(['objdump','-d','-M','intel','--no-show-raw-insn',str(binary)],text=True)
    symbols={}
    for line in subprocess.check_output(['nm','-S','--defined-only',str(binary)],text=True).splitlines():
        w=line.split()
        if len(w)==4 and w[2] in ('t','T'):symbols[w[3]]=(int(w[0],16),int(w[1],16))
    return asm,symbols


@unittest.skipUnless(uc and shutil.which('gcc'),'Requires GCC and optional Unicorn')
class GoReadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();folder=Path(cls.tmp.name)
        cls.config=json.loads((SCENARIO/'config.json').read_text())
        cls.binary,cls.plans=compile_assembly(folder/'go-abi',ASSEMBLY,cls.config,planner=app.plan_program)
        cls.events,cls.runtime=make_history(cls.binary,cls.plans,cls.config)
        cdir=folder/'c';cdir.mkdir()
        cb,cp,cc=c_app.build(c_app.common.ROOT/'scenarios/read-provenance',cdir)
        cls.c_events,cls.c_runtime=make_history(cb,cp,cc)
        cls.c_result=app.boundaries.bind(cls.c_events,cp,cc,cls.c_runtime)
        cls.truth=[json.loads(l) for l in subprocess.check_output([str(cb)],text=True).splitlines()]
        for row in cls.truth:row['function']=cls.config['functions'][cc['functions'].index(row['function'])]
        cls.result=app.boundaries.bind(cls.events,cls.plans,cls.config,cls.runtime)

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def test_shared_binder_same_case_results_as_native_c_oracle(self):
        self.assertEqual(self.result['issues'],[])
        score=app.boundaries.evaluate(self.result,self.truth,stats(self.events),self.plans)
        self.assertTrue(score['passed'],score)
        self.assertEqual(len(self.result['results']),18)
        self.assertEqual(len(self.result['read_operations']),34)
        self.assertEqual(score['external_source_relations']['tp'],18)
        def signature(result):
            return [(r['value'],r['sources'],[(s['io_id'],s['file_name'],s['file_offset'],s['length']) for s in r['external_sources']]) for r in result['results']]
        self.assertEqual(signature(self.result),signature(self.c_result))

    def test_g_identity_covers_syscalls_scope_and_compute_not_just_thread(self):
        for kind in (0,1,2,3,4):
            events=copy.deepcopy(self.events)
            event=next(e for e in events if e['kind']==kind);event['regs'][14]+=8
            result=app.boundaries.bind(events,self.plans,self.config,self.runtime)
            self.assertIn('execution contexts',result['issues'][0]['error'])
        events=copy.deepcopy(self.events);events[1]['regs'][14]=0
        self.assertIn('Missing goroutine',app.boundaries.bind(events,self.plans,self.config,self.runtime)['issues'][0]['error'])

    def test_missing_read_partial_overwrite_and_wrong_fd_fail_in_go_too(self):
        events=copy.deepcopy(self.events);del events[1]
        self.assertTrue(app.boundaries.bind(events,self.plans,self.config,self.runtime)['issues'])
        events=copy.deepcopy(self.events)
        next(e for e in events if e.get('io_id')==17 and e['kind']==2)['returned']=2
        self.assertIn('mixed-version',app.boundaries.bind(events,self.plans,self.config,self.runtime)['issues'][0]['error'])
        runtime=copy.deepcopy(self.runtime);runtime['read_files']={}
        self.assertTrue(app.boundaries.bind(self.events,self.plans,self.config,runtime)['issues'])

    def test_guard_read_failure_and_incomplete_compute_rejected(self):
        events=copy.deepcopy(self.events)
        next(e for e in events if e['kind']==0)['runtime_guard_error']=-14
        self.assertTrue(app.boundaries.bind(events,self.plans,self.config,self.runtime)['issues'])
        events=copy.deepcopy(self.events)
        index=next(i for i,e in enumerate(events) if e['kind']==0)
        del events[index+1]
        self.assertTrue(app.boundaries.bind(events,self.plans,self.config,self.runtime)['issues'])

    def test_scope_uses_fast_guard_edge_and_ret_uprobes_without_uretprobe(self):
        asm,symbols=disassemble(self.binary)
        scope=app.scope_plan(asm,symbols,self.config)
        self.assertGreater(scope['entry_offset'],4)
        self.assertTrue(scope['return_offsets'])
        out=Path(self.tmp.name)/'attach';out.mkdir()
        (out/'read-scope-plan.json').write_text(json.dumps(scope))
        bpf=Mock();process=Mock(pid=123)
        app.attach_scope(bpf,process,self.binary,self.plans,self.config,out)
        bpf.attach_uretprobe.assert_not_called()
        self.assertEqual(bpf.attach_uprobe.call_count,1+len(scope['return_offsets']))
        self.assertEqual(bpf.attach_uprobe.call_args_list[0].kwargs['sym_off'],scope['entry_offset'])
        self.assertFalse(json.loads((out/'read-boundary-attachments.json').read_text())['uretprobe'])

    def test_unknown_scope_guard_rejected(self):
        asm,symbols=disassemble(self.binary)
        broken=re.sub(r'(cmp\s+r12,QWORD PTR \[r14\+)0x10',r'\g<1>0x18',asm)
        with self.assertRaises(ValueError):app.scope_plan(broken,symbols,self.config)

    @unittest.skipUnless(shutil.which('g++'),'C++ compiler unavailable')
    def test_generated_raw_handlers_decode_actual_syscall_abi_and_g(self):
        # Execute the generated raw-handler C code in a native shim. Helpers
        # and maps are mocked: this checks argument/context wiring, not BPF.
        generated=app.bpf_source(self.plans,self.config)
        handlers=generated[generated.index('static __always_inline int read_user_regs'):]
        shim=r'''
#include <cassert>
#include <cstring>
#include <cstdint>
#include <sys/syscall.h>
using u64=uint64_t; using u32=uint32_t; using s64=int64_t; using s32=int32_t;
struct pt_regs { u64 r14,di,si,dx,r10,cx,orig_ax; };
struct bpf_raw_tracepoint_args { u64 args[2]; };
struct read_state_t { u32 pending; };
template<class T> struct Map { T value{}; T *lookup(u32*) { return &value; } };
Map<u64> boundary_current_g; Map<read_state_t> read_state;
struct read_enter_args { s32 fd; u64 buf,count; s64 pos; };
struct read_exit_args { s64 ret; };
read_enter_args observed{}; s64 observed_return; void *observed_context;
int entries=0,exits=0,rejected=0,errors=0; bool active=true,read_failure=false;
bool in_read_scope() { return active; }
void count(int k) { assert(k==2); ++errors; }
int bpf_probe_read_kernel(void *dst, unsigned n, void *src) {
    if(read_failure) return -1; std::memcpy(dst,src,n); return 0;
}
int traced_pread_enter(void *ctx,read_enter_args *args) {
    ++entries; observed=*args; observed_context=ctx; read_state.value.pending=1; return 0;
}
int traced_pread_exit(void *ctx,read_exit_args *args) {
    ++exits; observed_return=args->ret; observed_context=ctx; read_state.value.pending=0; return 0;
}
int reject_lifecycle(void*) { ++rejected; return 0; }
// Match BCC v0.29.1 src/cc/export/helpers.h, including its ctx parameter.
#define RAW_TRACEPOINT_PROBE(event) \
int raw_tracepoint__##event(struct bpf_raw_tracepoint_args *ctx)
'''
        main=r'''
int main() {
    pt_regs regs{0x6000000,static_cast<u64>(-1),0x2000000,4,8,0xdeadbeef,__NR_pread64};
    bpf_raw_tracepoint_args ctx{{reinterpret_cast<u64>(&regs),__NR_pread64}};
    raw_tracepoint__sys_enter(&ctx);
    assert(entries==1 && observed.fd==-1 && observed.buf==0x2000000);
    assert(observed.count==4 && observed.pos==8 && observed_context==&ctx);
    assert(boundary_current_g.value==0x6000000);
    regs.r14=0x7000000; ctx.args[1]=static_cast<u64>(-9);
    raw_tracepoint__sys_exit(&ctx);
    assert(exits==1 && observed_return==-9 && observed_context==&ctx);
    assert(boundary_current_g.value==0x7000000); // sampled again, not copied
    ctx.args[1]=__NR_write;raw_tracepoint__sys_enter(&ctx);assert(entries==1);
    ctx.args[1]=__NR_close;raw_tracepoint__sys_enter(&ctx);assert(rejected==1);
    active=false;raw_tracepoint__sys_enter(&ctx);assert(rejected==1);active=true;
    ctx.args[1]=__NR_pread64;read_failure=true;raw_tracepoint__sys_enter(&ctx);
    assert(errors==1 && entries==1);read_failure=false;
    regs.r14=0;raw_tracepoint__sys_enter(&ctx);assert(errors==2 && entries==1);
    regs.r14=0x6000000;read_state.value.pending=1;regs.orig_ax=__NR_write;
    raw_tracepoint__sys_exit(&ctx);assert(errors==3 && exits==1);
}
'''
        folder=Path(self.tmp.name)/'raw-shim';folder.mkdir()
        source=folder/'shim.cc';source.write_text(shim+handlers+main)
        binary=folder/'shim'
        subprocess.run(['g++','-std=c++17','-O1',str(source),'-o',str(binary)],check=True,capture_output=True)
        subprocess.run([str(binary)],check=True)

    @unittest.skipUnless(shutil.which('go'),'Real Go compiler unavailable')
    def test_actual_go_compilation_native_oracle_and_instruction_execution(self):
        out=Path(self.tmp.name)/'native-go';out.mkdir()
        binary,plans,config=app.build(SCENARIO,out)
        truth=[json.loads(l) for l in subprocess.check_output([str(binary)],text=True).splitlines()]
        self.assertEqual(truth,self.truth)
        events,runtime=make_history(binary,plans,config)
        result=app.boundaries.bind(events,plans,config,runtime)
        self.assertTrue(app.boundaries.evaluate(result,truth,stats(events),plans)['passed'],result['issues'])


if __name__=='__main__':unittest.main()
