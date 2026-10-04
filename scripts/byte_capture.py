"""Full-register transport reusing the established BCC collection lifecycle."""
import ctypes as ct
from go_byte_adapter import REGISTERS, PT_REGS, physical_probes
from string_capture import Raw as StringRaw, HEADER as STRING_HEADER

class Raw(ct.Structure):
    _fields_=StringRaw._fields_[:5]+[('registers',ct.c_uint64*len(REGISTERS))]+StringRaw._fields_[5:]

HEADER=STRING_HEADER.replace('g,pointer[2],length[2];','g,pointer[2],length[2],registers[16];')
HEADER=HEADER.replace('e->g=ctx->r14;e->site=site;',
    'e->g=ctx->r14;e->site=site;'+''.join(f'e->registers[{i}]=ctx->{PT_REGS[r]};' for i,r in enumerate(REGISTERS)))


def source(plan,pid,namespace):
    code=HEADER.replace('NSDEV',str(namespace.st_dev)+'ULL').replace('NSINO',str(namespace.st_ino)+'ULL').replace('TARGET_PID',str(pid))
    for s in plan['sites']:
        calls=[]
        for i,snap in enumerate(s['snapshots'].values()):
            if 'address' in snap:
                a=snap['address'];ptr='ctx->'+PT_REGS[a['base']]
                if a.get('index'):ptr+=f'+ctx->{PT_REGS[a["index"]]}*{a["scale"]}'
                ptr+=f'+({a["offset"]})'
            else:ptr='ctx->'+PT_REGS[snap['pointer']]
            length='ctx->'+PT_REGS[snap['length_reg']] if 'length_reg' in snap else str(snap['length'])
            calls.append(f'snapshot(e,{i},{ptr},{length});')
        code+=f'\nstatic __always_inline void logical_{s["id"]}(struct pt_regs *ctx) {{ struct event_t *e=begin(ctx,{s["id"]});if(!e)return; {" ".join(calls)} submit(ctx,e); }}\n'
    for probe in physical_probes(plan):
        calls=' '.join(f'logical_{s["id"]}(ctx);' for s in probe['sites'])
        code+=f'\nint {probe["name"]}(struct pt_regs *ctx) {{ {calls} return 0; }}\n'
    return code


def decode_record(data,size,sites):
    n=ct.sizeof(Raw);padded=((n+4+7)//8)*8-4
    if size not in (n,padded):raise ValueError(f'Unexpected byte event size {size}; expected {n} or {padded}')
    raw=Raw.from_buffer_copy(ct.string_at(data,n))
    if raw.site not in sites or raw.error:raise ValueError('Unknown site or failed memory read')
    spec=sites[raw.site];values={}
    for i,name in enumerate(spec['snapshots']):
        ptr,length=int(raw.pointer[i]),int(raw.length[i])
        if not ptr or not 0<length<=512:raise ValueError('Invalid snapshot')
        values[name]={'key':f'{ptr:x}:{length}','pointer':ptr,'hex':bytes(raw.data[i])[:length].hex()}
    return {'site':int(raw.site),'op':spec['op'],'phase':spec['phase'],'timestamp':int(raw.timestamp),
            'pid':int(raw.pid_tid>>32),'tid':int(raw.pid_tid&0xffffffff),'g':int(raw.g),
            'registers':dict(zip(REGISTERS,map(int,raw.registers))),'values':values}
