#!/usr/bin/env python3
"""Pinned Gin/Go fixture: actual c.JSON boundaries plus shared machine provenance."""
import hashlib
import http.client
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import go_read_provenance as go_read
import go_provenance as go
import read_provenance as read
import gin_api_boundaries as boundary
from hybrid_model import require

common = go.common
SCENARIO = common.ROOT/'scenarios/gin-api-provenance'
BOUNDARIES = {
    'render': 'github.com/gin-gonic/gin/render.WriteJSON',
    'marshal': 'encoding/json.Marshal',
    'writer': 'github.com/gin-gonic/gin.(*responseWriter).Write',
}
MODES = ['left', 'right', 'merge', 'overwrite', 'same', 'zero', 'max'] * 2


def bpf_source(plans, config):
    source = go_read.bpf_source(plans, config)
    source = source.replace('struct event_t {', '''struct event_t {
    u64 request_id, object_addr, object_type, writer_addr, error_type, capacity;
    u32 object_value;''')
    source = source.replace('BPF_ARRAY(read_context, u64, 1);',
                            'BPF_ARRAY(read_context, u64, 1);\nBPF_ARRAY(request_clock, u64, 1);')
    source = source.replace('e->observation_sequence = next_observation();', '''e->observation_sequence = next_observation();
    u64 *request = request_clock.lookup(&key);
    if (!request || !*request) { count(2); return 0; }
    e->request_id = *request;''')
    source = source.replace('    if (!tid || *tid) { count(2); return 0; }', '''    if (!tid || *tid) { count(2); return 0; }
    u64 current_tid = bpf_get_current_pid_tgid();
    struct state_t *previous = states.lookup(&current_tid);
    struct read_state_t *reads = read_state.lookup(&key);
    u64 *request = request_clock.lookup(&key);
    if (!reads || reads->pending || !request || (previous && previous->depth)) { count(2); return 0; }
    states.delete(&current_tid);
    __builtin_memset(reads, 0, sizeof(*reads));
    *request += 1;''')
    source += r'''
/* Go ABIInternal, linux/amd64, Go 1.25.4, no inlining. These are
 * instruction uprobes at fast-path entry and RET, never Go uretprobes. */
static __always_inline struct event_t *gin_event(struct pt_regs *ctx, u32 kind) {
    if (!in_read_scope()) return 0;
    count(3); u32 key=0; u64 *g=boundary_current_g.lookup(&key);
    if (!g || !ctx->r14 || *g!=ctx->r14) { count(2); return 0; }
    return boundary_event(kind);
}
static __always_inline void copy_json(struct event_t *e) {
    u64 n=e->requested;
    if (!e->buffer_addr || n==0 || n>=32 || e->capacity<n) { e->read_error=-1; return; }
    /* Keep an explicit verifier-visible bound; don't read beyond slice len. */
    asm volatile("" : "+r"(n));
    n &= 31;
    e->read_error=bpf_probe_read_user(e->read_data,n,(void *)e->buffer_addr);
}
int gin_render_enter(struct pt_regs *ctx) {
    struct event_t *e=gin_event(ctx,6); if (!e) return 0;
    e->writer_addr=ctx->bx; e->object_type=ctx->cx; e->object_addr=ctx->di;
    e->read_error=bpf_probe_read_user(&e->object_value,4,(void *)e->object_addr);
    return emit_boundary(ctx,e);
}
int gin_marshal_enter(struct pt_regs *ctx) {
    struct event_t *e=gin_event(ctx,7); if (!e) return 0;
    e->object_type=ctx->ax; e->object_addr=ctx->bx;
    e->read_error=bpf_probe_read_user(&e->object_value,4,(void *)e->object_addr);
    return emit_boundary(ctx,e);
}
int gin_marshal_exit(struct pt_regs *ctx) {
    struct event_t *e=gin_event(ctx,8); if (!e) return 0;
    e->buffer_addr=ctx->ax; e->requested=ctx->bx; e->capacity=ctx->cx; e->error_type=ctx->di;
    if (!e->error_type) copy_json(e);
    return emit_boundary(ctx,e);
}
int gin_render_exit(struct pt_regs *ctx) {
    struct event_t *e=gin_event(ctx,9); if (!e) return 0;
    e->error_type=ctx->ax;
    return emit_boundary(ctx,e);
}
int gin_writer_enter(struct pt_regs *ctx) {
    struct event_t *e=gin_event(ctx,10); if (!e) return 0;
    e->writer_addr=ctx->ax; e->buffer_addr=ctx->bx; e->requested=ctx->cx; e->capacity=ctx->di;
    copy_json(e);
    return emit_boundary(ctx,e);
}
int gin_writer_exit(struct pt_regs *ctx) {
    struct event_t *e=gin_event(ctx,11); if (!e) return 0;
    e->returned=(s64)ctx->ax; e->error_type=ctx->bx;
    return emit_boundary(ctx,e);
}
'''
    return source


def build(scenario, out):
    config = json.loads((scenario/'config.json').read_text())
    require(config['gin_api']['model']=='gin-struct-u32-v1', 'Unknown Gin summary model')
    copied=out/'sources';copied.mkdir()
    for name in ('config.json','go.mod','go.sum','main.go','operations.go'):
        shutil.copyfile(scenario/name,copied/name)
    (copied/'layout_check.go').write_text(go.layout_assertions(config))
    env=dict(os.environ,GOOS='linux',GOARCH='amd64',CGO_ENABLED='0',GO111MODULE='on',
             GOTOOLCHAIN='local',GOFLAGS='',GOEXPERIMENT='')
    version=subprocess.check_output(['go','env','GOVERSION'],env=env,text=True).strip()
    require(version==config['gin_api']['go_version'], 'Use the pinned Go '+config['gin_api']['go_version']+' toolchain; found '+version)
    command=['go','build','-buildvcs=false','-mod=readonly','-tags=nomsgpack','-buildmode=pie',
             '-gcflags=all=-l','-o',str(out/'hybrid-demo'),'.']
    result=subprocess.run(command,cwd=copied,env=env,capture_output=True,text=True,timeout=600)
    common.save(out/'build.json',dict(command=command,returncode=result.returncode,stdout=result.stdout,stderr=result.stderr,compiler=version))
    result.check_returncode();binary=out/'hybrid-demo'
    nm=subprocess.check_output(['go','tool','nm','-size',str(binary)],env=env,text=True)
    (out/'symbols.txt').write_text(nm)
    assembly=subprocess.check_output(['objdump','-d','-M','intel','--no-show-raw-insn',str(binary)],text=True)
    (out/'disassembly.txt').write_text(assembly)
    symbols=go.parse_nm(nm)
    plans=go_read.plan_program(assembly,symbols,config)
    scopes={'request':go_read.scope_plan(assembly,symbols,config)}
    scopes.update({key:go_read.scope_plan(assembly,symbols,config,function=name) for key,name in BOUNDARIES.items()})
    common.save(out/'gin-boundary-plan.json',scopes)
    modules=subprocess.check_output(['go','list','-m','-json','all'],cwd=copied,env=env,text=True)
    (out/'modules.jsonl').write_text(modules)
    gin=json.loads(subprocess.check_output(['go','list','-m','-json','github.com/gin-gonic/gin'],cwd=copied,env=env,text=True))
    require(gin['Version']==config['gin_api']['gin_version'] and 'Replace' not in gin,'Unexpected Gin dependency')
    root=Path(gin['Dir'])
    dependency_hashes={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in [root/'render/json.go',root/'response_writer.go',*(root/'codec/json').glob('*.go')]}
    common.save(out/'build-identity.json',dict(binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),go=version,
        gin=gin['Version'],sources={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in copied.iterdir()},
        gin_source_sha256=dependency_hashes,build_tags=['nomsgpack'],inlining=False))
    common.save(out/'adapter.json',dict(go.get_adapter(config).describe(config),compiler=version,
        framework='Gin '+gin['Version'],capture_status='requires host BPF validation'))
    common.save(out/'probe-plan.json',plans);common.save(out/'config.json',config)
    (out/'collector.bpf.c').write_text(bpf_source(plans,config))
    return binary,plans,config


def client(out):
    ready=json.loads((out/'program.stdout.jsonl').read_text().splitlines()[0])
    require(ready['requests']==len(MODES),'Unexpected fixture request count')
    address=ready['address']; require(address.startswith('127.0.0.1:'),'Loopback fixture only')
    conn=None;rows=[]
    try:
        for index,mode in enumerate(MODES,1):
            if conn is None:conn=http.client.HTTPConnection(address,timeout=10)
            close=index>7
            conn.request('GET','/account/summary?mode='+mode,headers={'Connection':'close' if close else 'keep-alive'})
            response=conn.getresponse();body=response.read()
            rows.append(dict(request_id=index,mode=mode,status=response.status,body=body.decode('ascii'),
                             content_type=response.getheader('Content-Type'),connection='close' if close else 'keep-alive'))
            if close:conn.close();conn=None
    finally:
        if conn:conn.close()
        common.save(out/'client-responses.json',rows)


def record(binary,plans,config,out):
    manifest={};driver=None
    with (out/'client.log').open('w') as log:
        def setup(bpf,process,binary,plans,config,out):
            nonlocal driver
            manifest.update(read.snapshot_files(process.pid));require(manifest,'No input files')
            common.save(out/'read-files.json',manifest)
            scopes=json.loads((out/'gin-boundary-plan.json').read_text())
            attached=[]
            for key,p in scopes.items():
                prefix='read_scope' if key=='request' else 'gin_'+key
                for off,handler in [(p['entry_offset'],prefix+'_enter')]+[(o,prefix+'_exit') for o in p['return_offsets']]:
                    bpf.attach_uprobe(name=str(binary),sym=p['function'],sym_off=off,fn_name=handler,pid=process.pid)
                    attached.append(dict(function=p['function'],offset=off,handler=handler,pid=process.pid))
            common.save(out/'gin-attachments.json',attached)
            # The listener exists before SIGSTOP; the serial client blocks until
            # the common collector opens perf buffers and resumes the server.
            driver=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'client',str(out)],stdout=log,stderr=log)
        try:
            events,stats,bases=common.record_bpf(binary,plans,config,out,source_generator=bpf_source,setup_fn=setup)
            require(driver.wait(timeout=12)==0,'HTTP client failed; see client.log')
        finally:
            if driver is not None and driver.poll() is None:driver.kill();driver.wait()
    runtime=dict(functions=bases,read_files=manifest)
    common.save(out/'runtime-bases.json',runtime)
    return events,stats,runtime


def oracle(out):
    clients=json.loads((out/'client-responses.json').read_text())
    observed=json.loads((out/'program.stderr.log').read_text())
    require([r['mode'] for r in clients]==[r['mode'] for r in observed]==MODES,'Client/server fixture order mismatch')
    return clients


if __name__=='__main__':
    if len(sys.argv)==3 and sys.argv[1]=='client':client(Path(sys.argv[2]))
    else:
        raise SystemExit(common.main(default_scenario=SCENARIO,prefix='gin-api-provenance',build_fn=build,
            record_fn=record,infer_fn=boundary.bind,evaluate_fn=boundary.evaluate,oracle_loader=oracle,
            required_tools=('go','objdump')))
