"""Existing register transport with Gin scope filtering; no TID-keyed state."""
from byte_capture import Raw, decode_record, physical_probes
import byte_capture
from hybrid_model import require


def source(plan,pid,namespace):
    ids=[s['id'] for s in plan['sites']];order=plan.get('event_order',[])
    require(len(ids)==len(set(ids)) and len(order)==len(ids) and set(order)==set(ids),
            'Gin attachment order must include every logical site exactly once')
    code=byte_capture.source(plan,pid,namespace)
    code=code.replace('BPF_PERF_OUTPUT(events);','BPF_PERF_OUTPUT(events);\nBPF_HASH(gin_active,u64,u64,128);')
    entry=plan['scope_entry'];exits=' || '.join('site==%d'%s for s in plan['scope_exits'])
    needle='u32 zero=0;struct event_t *e=scratch.lookup(&zero);'
    guard='''u64 g=ctx->r14, one=1;
 if(!g) {count(2);return 0;}
 if(site==ENTRY) {
   if(gin_active.lookup(&g) || gin_active.update(&g,&one)<0) {count(2);return 0;}
 } else if(!gin_active.lookup(&g)) {
   /* Global framework probes also see bootstrap/metadata calls outside scope. */
   if(IS_EXIT)count(2);
   return 0;
 }
 if(IS_EXIT)gin_active.delete(&g);
 '''.replace('ENTRY',str(entry)).replace('IS_EXIT',exits)
    assert code.count(needle)==1
    return code.replace(needle,guard+needle)
