"""BCC transport for declared ABI string slots, separate from provenance inference."""
import ctypes as ct
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from go_string_adapter import decode, physical_probes

class Raw(ct.Structure):
    _fields_=[('timestamp',ct.c_uint64),('pid_tid',ct.c_uint64),('g',ct.c_uint64),
              ('pointer',ct.c_uint64*2),('length',ct.c_uint64*2),('site',ct.c_uint32),
              ('error',ct.c_uint32),('data',(ct.c_ubyte*512)*2)]

HEADER=r'''
#include <uapi/linux/ptrace.h>
#include <uapi/linux/bpf.h>
struct event_t {
 u64 timestamp,pid_tid,g,pointer[2],length[2];
 u32 site,error;
 u8 data[2][512];
};
BPF_PERCPU_ARRAY(scratch,struct event_t,1);
BPF_ARRAY(stats,u64,7);
BPF_PERF_OUTPUT(events);
static __always_inline void count(u32 k) {
 u64 *p=stats.lookup(&k);if(p)__sync_fetch_and_add(p,1);
}
typedef u64 clear_word_t __attribute__((may_alias));
static __always_inline void clear_event(struct event_t *e) {
 volatile clear_word_t *p=(volatile clear_word_t *)e;
 #pragma unroll
 for(int i=0;i<sizeof(*e)/8;i++)p[i]=0;
}
static __always_inline void snapshot(struct event_t *e,int slot,u64 ptr,u64 length) {
 e->pointer[slot]=ptr;e->length[slot]=length;
 if(!ptr || !length || length>512) {e->error=1;return;}
 if(bpf_probe_read_user(e->data[slot],length,(void *)ptr)<0)e->error=1;
}
static __always_inline struct event_t *begin(struct pt_regs *ctx,u32 site) {
 count(3);
 struct bpf_pidns_info ns={};
 if(bpf_get_ns_current_pid_tgid(NSDEV,NSINO,&ns,sizeof(ns))) {count(4);return 0;}
 if(ns.tgid!=TARGET_PID) {count(5);return 0;}
 if((bpf_get_current_pid_tgid()>>32)!=ns.tgid)count(6);
 u32 zero=0;struct event_t *e=scratch.lookup(&zero);
 if(!e) {count(2);return 0;}
 clear_event(e);
 e->timestamp=bpf_ktime_get_ns();e->pid_tid=((u64)ns.tgid<<32)|ns.pid;
 e->g=ctx->r14;e->site=site;return e;
}
static __always_inline void submit(struct pt_regs *ctx,struct event_t *e) {
 count(0);if(e->error)count(2);
 if(events.perf_submit(ctx,e,sizeof(*e))<0)count(1);
}
'''


def source(plan,pid,namespace):
    text=HEADER.replace('NSDEV',str(namespace.st_dev)+'ULL').replace('NSINO',str(namespace.st_ino)+'ULL').replace('TARGET_PID',str(pid))
    for s in plan['sites']:
        calls='\n'.join(f'snapshot(e,{i},ctx->{regs[0]},ctx->{regs[1]});' for i,regs in enumerate(s['values'].values()))
        text+=f'\nstatic __always_inline void logical_{s["id"]}(struct pt_regs *ctx) {{ struct event_t *e=begin(ctx,{s["id"]}); if(!e)return; {calls} submit(ctx,e); }}\n'
    # A CALL continuation can be the next CALL instruction. Attach once, then
    # emit its logical return/entry events in deterministic execution order.
    for probe in physical_probes(plan):
        calls=' '.join(f'logical_{s["id"]}(ctx);' for s in probe['sites'])
        text+=f'\nint {probe["name"]}(struct pt_regs *ctx) {{ {calls} return 0; }}\n'
    return text


def decode_record(data,size,sites):
    n=ct.sizeof(Raw);aligned=((n+4+7)//8)*8-4
    if size not in (n,aligned):raise ValueError(f'Unexpected perf size {size}; expected {n} or {aligned}')
    raw=Raw.from_buffer_copy(ct.string_at(data,n))
    if raw.site not in sites:raise ValueError('Unknown site')
    return decode(raw,sites[raw.site])


def collect(binary,plan,input_bytes,out):
    out.mkdir()
    errors=[];records=[];lost=[0];stats={};sizes={};proc=None;bpf=None
    stdout=(out/'target.stdout').open('wb');stderr=(out/'target.stderr').open('wb')
    metadata={}
    try:
        if hashlib.sha256(binary.read_bytes()).hexdigest()!=plan['binary_sha256']:raise ValueError('Binary changed')
        import bcc
        metadata.update(bcc=getattr(bcc,'__version__','unknown'),module=bcc.__file__)
        proc=subprocess.Popen([str(binary)],stdin=subprocess.PIPE,stdout=stdout,stderr=stderr)
        ns=Path(f'/proc/{proc.pid}/ns/pid').stat()
        metadata.update(target_pid=proc.pid,namespace={'dev':ns.st_dev,'ino':ns.st_ino},pinned_thread=False)
        code=source(plan,proc.pid,ns);(out/'collector.c').write_text(code)
        bpf=bcc.BPF(text=code)
        for probe in physical_probes(plan):
            # ET_EXEC: BCC addr is the virtual address, not the ELF file offset.
            bpf.attach_uprobe(name=str(binary),addr=probe['address'],fn_name=probe['name'],pid=-1)
        metadata['physical_probes']=len(physical_probes(plan))
        sites={s['id']:s for s in plan['sites']}
        def callback(cpu,data,size):
            sizes[str(size)]=sizes.get(str(size),0)+1
            try:
                e=decode_record(data,size,sites);e['sequence']=len(records);records.append(e)
            except Exception as exc:errors.append('decode: '+repr(exc))
        def lost_callback(cpu,n):lost[0]+=n
        bpf['events'].open_perf_buffer(callback,page_cnt=64,lost_cb=lost_callback)
        proc.stdin.write(input_bytes);proc.stdin.close()
        deadline=time.monotonic()+30
        while proc.poll() is None:
            bpf.perf_buffer_poll(timeout=100)
            if time.monotonic()>deadline:raise TimeoutError('Target timeout')
        for _ in range(5):bpf.perf_buffer_poll(timeout=50)
        for i,k in enumerate(('submitted','submit_errors','read_errors','probe_hits','namespace_errors','pid_rejections','namespace_differences')):
            stats[k]=int(bpf['stats'][ct.c_int(i)].value)
        stats['lost']=lost[0]
        if not records:errors.append('No events')
        if stats['submitted']!=len(records) or any(stats[k] for k in ('submit_errors','read_errors','lost')):errors.append('Incomplete capture')
    except Exception as exc:errors.append(repr(exc))
    finally:
        if proc:
            if proc.poll() is None:proc.kill()
            proc.wait()
            if proc.stdin and not proc.stdin.closed:proc.stdin.close()
        if bpf:
            try:bpf.cleanup()
            except Exception as exc:errors.append('cleanup: '+repr(exc))
        stdout.close();stderr.close()
    doc={'backend':'ebpf-bcc','binary_sha256':plan['binary_sha256'],'capture_errors':errors,
         'returncode':proc.returncode if proc else None,'stats':stats,'events':records,
         'diagnostics':dict(metadata,sample_sizes=sizes,structure_size=ct.sizeof(Raw))}
    (out/'events.json').write_text(json.dumps(doc,indent=2)+'\n')
    print(json.dumps({'events':len(records),'errors':errors,'stats':stats}),flush=True)
    return doc
