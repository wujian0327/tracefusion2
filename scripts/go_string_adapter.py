"""Go1.25.4/1.25.5 amd64 string ABI adapter and bounded direct-call planner."""
import hashlib
import re
import struct
import subprocess
from go_provenance import parse_nm

# Byte-string registers: (pointer, length), in Go ABIInternal.
SUMMARY = {
 'source': {'pre': {'path':('ax','bx')}, 'post': {'value':('ax','bx')}},
 'concat': {'pre': {'left':('bx','cx'),'right':('di','si')}, 'post': {'value':('ax','bx')}},
 'json': {'pre': {'value':('ax','bx')}, 'post': {'json':('ax','bx')}},
 'scope': {'pre':{},'post':{}},
}
CALLS = {'main.main': {'main.run':'scope'}, 'main.run': {
 'main.readValue':'source', 'runtime.concatstring2':'concat', 'main.marshalResult':'json'}}

def physical_probes(plan):
    groups={}
    sites={s['id']:s for s in plan['sites']}
    for sid in plan['event_order']:
        site=sites[sid]
        groups.setdefault(site['address'],[]).append(site)
    return [{'address':address,'name':'probe_'+str(sites[0]['id']),'sites':sites}
            for address,sites in groups.items()]


def file_offset(data, address):
    if data[:6] != b'\x7fELF\x02\x01' or struct.unpack_from('<HH',data,16)!=(2,62):
        raise ValueError('Requires Linux amd64 non-PIE ELF')
    phoff=struct.unpack_from('<Q',data,32)[0]
    size,count=struct.unpack_from('<HH',data,54)
    for i in range(count):
        typ,flags,off,va,_,length,_,_=struct.unpack_from('<IIQQQQQQ',data,phoff+i*size)
        if typ==1 and flags&1 and va<=address<va+length:return off+address-va
    raise ValueError('Instruction outside executable file segment')


def plan_binary(binary, go, env, out):
    data=binary.read_bytes()
    nm=subprocess.check_output([go,'tool','nm','-size',str(binary)],env=env,text=True)
    (out/'symbols.txt').write_text(nm)
    symbols=parse_nm(nm)
    sites=[]; all_assembly=[]; root_ops=[]; calls=[]
    for caller,targets in CALLS.items():
        asm=subprocess.check_output([go,'tool','objdump','-s','^'+re.escape(caller)+'$',str(binary)],env=env,text=True)
        all_assembly.append(asm)
        instructions=[]
        for line in asm.splitlines():
            m=re.match(r'\s*(\S+:\d+)\s+(0x[0-9a-f]+)\s+([0-9a-f]+)\s+(.+)',line)
            if m: instructions.append((m[1],int(m[2],16),bytes.fromhex(m[3]),m[4].strip()))
        addresses={a for _,a,_,_ in instructions}
        for loc,addr,code,ins in instructions:
            parts=ins.split(None,1)
            if not parts or parts[0]!='CALL':continue
            callee=parts[1].strip().removesuffix('(SB)').removeprefix('local.')
            calls.append({'caller':caller,'callee':callee,'address':addr,'location':loc})
            if caller=='main.run' and callee not in targets and callee!='runtime.morestack_noctxt.abi0':
                raise ValueError('Unmodeled root call: '+callee)
            if callee not in targets:continue
            if code[0]!=0xe8 or addr+len(code) not in addresses:raise ValueError('Expected direct CALL/continuation')
            if caller=='main.run':root_ops.append(targets[callee])
            pair=len(sites)//2
            for phase,address in [('pre',addr),('post',addr+len(code))]:
                offset=file_offset(data,address)
                if phase=='pre' and data[offset:offset+len(code)]!=code:raise ValueError('ELF bytes mismatch')
                sites.append({'id':len(sites),'pair':pair,'op':targets[callee],'phase':phase,
                              'caller':caller,'callee':callee,'address':address,'file_offset':offset,
                              'caller_address':symbols[caller][0],'location':loc,
                              'values':SUMMARY[targets[callee]][phase]})
    (out/'disassembly.txt').write_text('\n'.join(all_assembly))
    if len(sites)!=12 or root_ops!=['source','source','source','concat','json']:
        raise ValueError('Root operation shape changed; review binary before changing contract')
    order=[0]+list(range(2,12))+[1]
    return {'adapter':'go-amd64-string-summaries-v1','binary':str(binary),
            'binary_sha256':hashlib.sha256(data).hexdigest(),'sites':sites,'event_order':order,
            'calls':calls,'summaries':SUMMARY,'json_field':'result','snapshot_limit':512,
            'scope':'Three source API returns; nonempty immutable strings; concatstring2 and fixed JSON wrapper; one root/goroutine'}


def decode(raw, spec):
    values={}
    for i,name in enumerate(spec['values']):
        n=int(raw.length[i]);ptr=int(raw.pointer[i])
        if not 0<n<=512 or not ptr:raise ValueError('Invalid string snapshot')
        values[name]={'key':f'{ptr:x}:{n}', 'hex':bytes(raw.data[i])[:n].hex()}
    if raw.error:raise ValueError('BPF memory read failed')
    return {'site':int(raw.site),'op':spec['op'],'phase':spec['phase'], 'timestamp':int(raw.timestamp),
            'pid':int(raw.pid_tid>>32),'tid':int(raw.pid_tid&0xffffffff),'g':int(raw.g),'values':values}
