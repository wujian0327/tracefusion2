#!/usr/bin/env python3
"""Concurrent pinned Gin scopes; per-request state and independent client matching."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import partial
import http.client
import json
from pathlib import Path
import sys

import gin_api_provenance as serial
import gin_concurrent_boundaries as boundary
from hybrid_model import require

common=serial.common
SCENARIO=common.ROOT/'scenarios/gin-concurrent-provenance'
MODES=['left','right','merge','overwrite','same','zero','max']*4
CONCURRENCY=4


def _replace(source,old,new,count=1):
    require(source.count(old)==count,'Shared collector changed: '+old[:90])
    return source.replace(old,new)


def bpf_source(plans,config):
    require(config['gin_api'].get('serial_requests') is False and config['gin_api'].get('concurrency')==4,
            'Concurrent adapter requires the explicit four-request fixture')
    source=serial.bpf_source(plans,config)
    # Keep business instruction and Go ABI handlers shared. Only scope storage,
    # identity allocation, clocks and lifecycle differ from the serial runner.
    start=source.index('int read_scope_enter(')
    end=source.index('struct read_enter_args',start)
    source=source[:start]+source[end:]
    for line in ('BPF_ARRAY(read_state, struct read_state_t, 1);',
                 'BPF_ARRAY(read_context, u64, 1);','BPF_ARRAY(boundary_current_g, u64, 1);'):
        source=_replace(source,line,'')
    source=_replace(source,'struct event_t {','struct event_t {\n    u64 request_sequence;')
    helpers=r'''
/* Keyed by kernel pid_tid only while a request is explicitly pinned. IDs are
 * globally unique invocation generations, never TID/G addresses themselves. */
struct request_context_t {
    u64 request_id, tid, g, step;
    struct read_state_t reads;
};
BPF_HASH(requests, u64, struct request_context_t, 64);
static __always_inline struct request_context_t *current_request(void) {
    u64 tid=bpf_get_current_pid_tgid(); return requests.lookup(&tid);
}
static __always_inline u64 *current_tid_ptr(void) {
    struct request_context_t *s=current_request(); return s ? &s->tid : 0;
}
static __always_inline u64 *current_g_ptr(void) {
    struct request_context_t *s=current_request(); return s ? &s->g : 0;
}
static __always_inline u64 *current_request_id(void) {
    struct request_context_t *s=current_request(); return s ? &s->request_id : 0;
}
static __always_inline struct read_state_t *current_reads(void) {
    struct request_context_t *s=current_request(); return s ? &s->reads : 0;
}
'''
    source=_replace(source,'BPF_ARRAY(observation_clock, u64, 1);','BPF_ARRAY(observation_clock, u64, 1);'+helpers)
    source=_replace(source,'/* Only the seeded thread can emit within this scope. */\n    u64 previous = *seq; *seq = previous + 1; return previous;',
                    '/* Atomic uniqueness across CPUs; not a cross-thread happens-before clock. */\n    return __sync_fetch_and_add(seq, 1);')
    source=_replace(source,'read_context.lookup(&scope_key)','current_tid_ptr()')
    source=_replace(source,'read_context.lookup(&key)','current_tid_ptr()')
    source=_replace(source,'request_clock.lookup(&key)','current_request_id()',count=2)
    source=_replace(source,'boundary_current_g.lookup(&key)','current_g_ptr()',count=3)
    source=_replace(source,'read_state.lookup(&key)','current_reads()',count=3)
    source=_replace(source,'e->request_id = *request;', '''e->request_id = *request;
    struct request_context_t *active=current_request();
    if (!active) { count(2); return 0; }
    e->request_sequence=active->step++;''',count=2)
    source+=r'''
int read_scope_enter(struct pt_regs *ctx) {
    count(3); u64 tid=bpf_get_current_pid_tgid(); u32 key=0;
    if (!ctx->r14 || requests.lookup(&tid)) { count(2); return 0; }
    struct state_t *previous=states.lookup(&tid);
    if (previous && previous->depth) { count(2); return 0; }
    states.delete(&tid);
    u64 *clock=request_clock.lookup(&key);
    if (!clock) { count(2); return 0; }
    struct request_context_t fresh={};
    fresh.request_id=__sync_fetch_and_add(clock,1)+1;
    fresh.tid=tid; fresh.g=ctx->r14;
    if (requests.update(&tid,&fresh)<0) { count(2); return 0; }
    struct event_t *e=boundary_event(3);
    return e ? emit_boundary(ctx,e) : 0;
}
int read_scope_exit(struct pt_regs *ctx) {
    count(3); u64 tid=bpf_get_current_pid_tgid();
    struct request_context_t *active=current_request();
    if (!active || active->g!=ctx->r14) { count(2); return 0; }
    struct state_t *state=states.lookup(&tid);
    if (active->reads.pending || (state && state->depth)) count(2);
    struct event_t *e=boundary_event(4);
    if (e) emit_boundary(ctx,e);
    states.delete(&tid); requests.delete(&tid);
    return 0;
}
'''
    return source


build=partial(serial.build,source_generator=bpf_source)
record=partial(serial.record,source_generator=bpf_source,client_script=__file__)


def client(out):
    ready=json.loads((out/'program.stdout.jsonl').read_text().splitlines()[0])
    require(ready['requests']==len(MODES) and ready['concurrency']==CONCURRENCY,'Unexpected concurrent fixture')
    address=ready['address'];require(address.startswith('127.0.0.1:'),'Loopback only')
    rows=[]
    def send(ticket):
        mode=MODES[ticket-1];conn=http.client.HTTPConnection(address,timeout=12)
        try:
            conn.request('GET',f'/account/summary?mode={mode}&ticket={ticket}',headers={'Connection':'close'})
            response=conn.getresponse();body=response.read()
            return dict(ticket=ticket,mode=mode,status=response.status,body=body.decode('ascii'),
                        content_type=response.getheader('Content-Type'))
        finally:conn.close()
    try:
        with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
            for first in range(1,len(MODES)+1,CONCURRENCY):
                futures=[pool.submit(send,t) for t in range(first,first+CONCURRENCY)]
                for future in as_completed(futures):rows.append(future.result())
    finally:common.save(out/'client-responses.json',rows)


def oracle(out):
    clients=json.loads((out/'client-responses.json').read_text())
    server=json.loads((out/'program.stderr.log').read_text())
    expected=set(range(1,len(MODES)+1))
    require(len(clients)==len(server)==len(expected),'Incomplete client/server observations')
    require({r['ticket'] for r in clients}=={r['ticket'] for r in server}==expected,'Missing/duplicate ticket')
    require(len({r['input_addr'] for r in server})==len(server),'Evaluation input address was reused')
    by_ticket={r['ticket']:r for r in server};result=[]
    for row in sorted(clients,key=lambda r:r['ticket']):
        observed=by_ticket[row['ticket']]
        require(row['mode']==observed['mode']==MODES[row['ticket']-1],'Mode mismatch')
        # The evaluation-only server record bridges a retained input object's
        # address to the client ticket. Inference never reads this mapping.
        result.append(dict(row,input_addr=observed['input_addr']))
    return result


if __name__=='__main__':
    if len(sys.argv)==3 and sys.argv[1]=='client':client(Path(sys.argv[2]))
    else:
        raise SystemExit(common.main(default_scenario=SCENARIO,prefix='gin-concurrent-provenance',build_fn=build,
            record_fn=record,infer_fn=boundary.bind,evaluate_fn=boundary.evaluate,oracle_loader=oracle,
            required_tools=('go','objdump')))
