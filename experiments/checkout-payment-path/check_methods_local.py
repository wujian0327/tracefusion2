#!/usr/bin/env python3
"""Execute original ELF interval bytes with Unicorn, then check four inferences.

Records generated here are explicitly synthetic. Runtime allocation, equality
and WB contracts are test substitutes; this is not kernel/GC evidence. Oracle
files come from the separate native Go fixture and are opened after inference.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
from types import SimpleNamespace

HERE=Path(__file__).resolve().parent; sys.path.insert(0,str(HERE))
import method_baselines as methods
from independent_machine import Graph,State,Byte,word,number,GPRS,REGS,AGG,split
from independent_replay import BASE,PLACE,MULT,SUM,VALID
from compare_methods import faults
from unicorn import Uc,UC_ARCH_X86,UC_MODE_64,UC_HOOK_CODE,__version__ as unicorn_version
from unicorn import x86_const as x86

REGISTER={r:getattr(x86,'UC_X86_REG_'+('R'+r if r in ('AX','BX','CX','DX','DI','SI','BP','SP') else r)) for r in GPRS}

def emulate(binary,plan,case,barrier):
    cpu=Uc(UC_ARCH_X86,UC_MODE_64); pages=set(); rows={r['address']:r for f in plan['independent_model']['functions'].values() for r in f['rows']}
    def write(p,data):
        for page in range(p&~4095,(p+len(data)+4095)&~4095,4096):
            if page not in pages: cpu.mem_map(page,4096); pages.add(page)
        cpu.mem_write(p,data)
    def put(p,v,size=8): write(p,int(v&((1<<(8*size))-1)).to_bytes(size,'little'))
    def get(p,size=8): return int.from_bytes(cpu.mem_read(p,size),'little')
    for row in rows.values():
        off=methods.file_offset(binary,row['address']); code=bytes.fromhex(row['code'])
        assert binary[off:off+len(code)]==code; write(row['address'],code)
    stack=0x20000000; array=0x21000000; cart_array=0x22000000; req=0x23000000; shipping=0x24000000; curr=0x25000000
    n=case['Items']; q=case['Quantity']; c=case.get('Carry',False)
    write(stack-65536,bytes(131072))
    for p in (array,cart_array,req,shipping,curr): write(p,bytes(4096))
    write(curr,b'EUR'); put(req+56,curr); put(req+64,3)
    put(stack+plan['independent_model']['functions'][PLACE]['frame']+40,req)
    for i in range(n+1):
        cost=shipping if i==0 else 0x26000000+(i-1)*4096
        write(cost,bytes(72)); put(cost+40,curr); put(cost+48,3); put(cost+56,1 if i==0 else 2)
        put(cost+64,(800000000 if i==0 else 700000000) if c else 0,4)
        if i:
            item=0x27000000+(i-1)*4096; cart=0x28000000+(i-1)*4096
            write(item,bytes(56)); write(cart,bytes(64)); put(item+40,cart); put(item+48,cost); put(cart+56,q,4)
            put(array+(i-1)*8,item); put(cart_array+(i-1)*8,cart)
    initial=dict(AX=array,BX=n,CX=n,DX=0,DI=cart_array,SI=n,R8=n,R9=shipping,R10=0,R11=0,R12=0,R13=0,R14=88,R15=0,BP=0,SP=stack)
    if case.get('PreparationFailure'): initial['R10']=1
    for r,v in initial.items(): cpu.reg_write(REGISTER[r],v)
    sites={s['address']:s for s in plan['sites']}; bykind={s['kind']:s for s in plan['sites']}; events=[]; wb_count=0; alloc=0
    def emit(site,tag=0,**kw):
        e=dict(timestamp=len(events)+1,pid_tid=(123<<32)|77,g=88,site=site['id'],kind=site['kind'],error=0,tag=tag,
               registers={r:cpu.reg_read(REGISTER[r]) for r in GPRS},flags=cpu.reg_read(x86.UC_X86_REG_EFLAGS),a=0,b=0,c=0,d=0)
        e.update(kw); events.append(e)
    source=bykind['source']; emit(source,a=n,b=initial['R10'])
    if initial['R10']:
        emit(bykind['end']); return document(plan,events),None
    for i in range(n+1):
        cost=shipping if i==0 else 0x26000000+(i-1)*4096
        registers={r:0 for r in GPRS}; registers.update(AX=curr,BX=3,CX=int.from_bytes(b'EUR','little'))
        if i: registers.update(DX=0x27000000+(i-1)*4096,DI=0x28000000+(i-1)*4096)
        emit(source,tag=i+1,a=cost,b=get(cost+56),c=get(cost+64,4),d=q if i else 0,registers=registers)
    registers={r:0 for r in GPRS}; registers.update(AX=curr,BX=3,CX=int.from_bytes(b'EUR','little'))
    emit(source,tag=n+2,a=req,registers=registers)
    def clobber(preserve=False):
        for r in GPRS:
            if r in ('SP','BP','R14') or (preserve and r!='R11'): continue
            cpu.reg_write(REGISTER[r],0)
        for i in range(15): cpu.reg_write(getattr(x86,'UC_X86_REG_XMM'+str(i)),0)
    def hook(uc,address,size,_):
        nonlocal wb_count,alloc
        assert address in rows,hex(address); row=rows[address]; op,args=split(row['asm'])
        if address in sites and address!=source['address']:
            s=sites[address]; values={}
            if s['kind']=='sum_entry':
                sp=uc.reg_read(REGISTER['SP']); sf=plan['independent_model']['functions'][SUM]['frame']
                values=dict(a=uc.reg_read(REGISTER['R10']),b=uc.reg_read(REGISTER['R11'])&0xffffffff,
                            c=get(sp+sf+16+56),d=get(sp+sf+16+64,4))
            elif s['kind']=='sum_exit':
                sp=uc.reg_read(REGISTER['SP']); values=dict(a=uc.reg_read(REGISTER['R10']),b=uc.reg_read(REGISTER['R11'])&0xffffffff,c=get(sp+80))
            elif s['kind']=='sink':
                p=uc.reg_read(REGISTER['DI']); values=dict(a=p,b=get(p+56),c=get(p+64,4))
            emit(s,**values)
        if address==plan['independent_model']['functions'][PLACE]['exit']: uc.emu_stop(); return
        if row['asm']=='CMPL runtime.writeBarrier(SB), $0x0':
            code=bytes.fromhex(row['code']); assert len(code)==7 and code[:2]==b'\x83\x3d'
            target=address+size+struct.unpack('<i',code[2:6])[0]
            value=0 if barrier=='fast' else 1 if barrier=='slow' else wb_count%2
            put(target,value,4); wb_count+=1
        if op=='CALL':
            callee=args[0]; name=callee.removesuffix('(SB)')
            if name in (SUM,MULT,VALID):
                oldsp=uc.reg_read(REGISTER['SP']); child=plan['independent_model']['functions'][name]
                put(oldsp-8,address+size); put(oldsp-16,uc.reg_read(REGISTER['BP']))
                uc.reg_write(REGISTER['BP'],oldsp-16); uc.reg_write(REGISTER['SP'],oldsp-child['frame']-16)
                uc.reg_write(x86.UC_X86_REG_RIP,child['entry'])
            elif callee=='runtime.newobject(SB)':
                alloc+=1; p=0x30000000+alloc*4096; write(p,bytes(72)); clobber(); uc.reg_write(REGISTER['AX'],p)
                uc.reg_write(x86.UC_X86_REG_RIP,address+size)
            elif callee=='runtime.memequal(SB)':
                a,b,length=(uc.reg_read(REGISTER[r]) for r in ('AX','BX','CX'))
                equal=int(bytes(uc.mem_read(a,length))==bytes(uc.mem_read(b,length))); clobber(); uc.reg_write(REGISTER['AX'],equal)
                uc.reg_write(x86.UC_X86_REG_RIP,address+size)
            elif callee=='runtime.wbMove(SB)': clobber(); uc.reg_write(x86.UC_X86_REG_RIP,address+size)
            elif 'gcWriteBarrier' in callee:
                write(0x31000000,bytes(128)); clobber(preserve=True); uc.reg_write(REGISTER['R11'],0x31000000)
                uc.reg_write(x86.UC_X86_REG_RIP,address+size)
            else: raise AssertionError('Unsupported emulator call '+callee)
    cpu.hook_add(UC_HOOK_CODE,hook)
    cpu.emu_start(plan['independent_model']['functions'][PLACE]['entry'],0xffffffffffffffff,count=200000)
    assert events[-1]['kind']=='sink','ELF execution did not reach target'
    emit(bykind['end'])
    return document(plan,events),wb_count

def document(plan,events):
    return dict(backend='unicorn-unit-test',synthetic=True,binary_sha256=plan['binary_sha256'],returncode=0,capture_errors=[],events=events,
                stats=dict(submitted=len(events),lost=0,read_errors=0,submit_errors=0,namespace_errors=0))

def check_c(plan,work):
    # Native syntax only; BCC rewriting/kernel verifier must be tested on host.
    prefix='''
typedef unsigned long long u64; typedef unsigned int u32; typedef unsigned char u8;
struct pt_regs {u64 ax,bx,cx,dx,si,di,bp,sp,r8,r9,r10,r11,r12,r13,r14,r15,flags;};
struct bpf_pidns_info {u32 pid,tgid;};
int bpf_probe_read_user(void *,u64,void *);
int bpf_get_ns_current_pid_tgid(u64,u64,struct bpf_pidns_info *,u64);
u64 bpf_get_current_pid_tgid(void); u64 bpf_ktime_get_ns(void);
#define __always_inline inline __attribute__((always_inline))
#define BPF_PERCPU_ARRAY(n,t,c) struct {t *(*lookup)(u32 *);} n
#define BPF_ARRAY(n,t,c) struct {t *(*lookup)(u32 *);} n
#define BPF_HASH(n,k,v,c) struct {v *(*lookup)(k *);int (*update)(k *,v *);int (*delete)(k *);} n
#define BPF_PERF_OUTPUT(n) struct {int (*perf_submit)(struct pt_regs *,void *,u64);} n
'''
    probes=methods.physical_probes(plan)
    assert len(probes)==len(plan['sites']) and len({s['address'] for s in probes})==len(probes)
    source=methods.source(plan,123,SimpleNamespace(st_dev=1,st_ino=2))
    source='\n'.join(l for l in source.splitlines() if not l.startswith('#include'))
    f=work/(plan['strategy']+'.c'); f.write_text(prefix+source)
    subprocess.run(['gcc','-fsyntax-only','-Werror','-Wno-attributes',str(f)],capture_output=True,check=True)

def machine_checks():
    g=Graph(); s=State(g); a=g.make(None,label='A'); b=g.make(None,label='B')
    s.reg['AX']=word(7,8,a); s.reg['BX']=word(7,8,b)
    s.apply(dict(address=1,asm='MOVQ AX, 0(SP)')); s.apply(dict(address=2,asm='MOVQ BX, 0(SP)'))
    assert g.backward(x.definition for x in s.read('0(SP)',8))['origins']==['B']
    s.apply(dict(address=3,asm='ADDQ AX, BX')); assert s.rnum('BX')==14
    assert g.backward(x.definition for x in s.reg['BX'])['origins']==['A','B']
    s.apply(dict(address=4,asm='XORL BX, BX')); assert g.backward(x.definition for x in s.reg['BX'])['origins']==[]
    s.region(0x1000,4,clean=True); s.reg['DI']=word(0x1000,8)
    try: s.read('0(DI)',8)
    except ValueError: pass
    else: raise AssertionError('Cross-region read accepted')
    return ['same_value_last_write','arithmetic_union','constant_kills_definition','region_width_bound']

def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--results',type=Path,required=True); args=p.parse_args()
    common=json.loads((args.results/'plan.json').read_text()); binary=(args.results/'checkout-identity').read_bytes()
    assert hashlib.sha256(binary).hexdigest()==common['binary_sha256']
    cases=json.loads((args.results/'cases.json').read_text()); checks=[]; negatives=[]; event_counts=[]
    for case in cases:
        for barrier in ('fast','slow','alternating'):
            full=methods.strategy_plan(common,'all_branches'); doc,branches=emulate(binary,full,case,barrier)
            counts={}
            for strategy in methods.STRATEGIES:
                plan=methods.strategy_plan(common,strategy); keep={s['id'] for s in plan['sites']}
                d=copy.deepcopy(doc); d['events']=[e for e in d['events'] if e['site'] in keep]; d['stats']['submitted']=len(d['events'])
                answer=methods.infer(plan,d)
                truth=json.loads((args.results/case['Name']/'native/truth.json').read_text())
                evaluated=methods.evaluate(plan,answer,truth)
                assert evaluated['passed'],(case['Name'],barrier,strategy,answer)
                counts[strategy]=len(d['events']); checks.append(dict(case=case['Name'],barrier=barrier,strategy=strategy,passed=True))
                if case['Name']=='one-repeated' and barrier=='fast' and strategy in ('boundary_replay','path_sensitive_slice'):
                    rows=faults(plan,d); assert all(r['passed'] for r in rows),rows
                    negatives.extend(dict(strategy=strategy,**r) for r in rows)
                    d2=copy.deepcopy(d); d2['events'][1]['registers']['BX']=9
                    assert methods.infer(plan,d2)['status']=='unknown'
                    negatives.append(dict(strategy=strategy,name='currency_snapshot_bound',passed=True,kind='offline_fault_injection'))
                    if strategy=='boundary_replay':
                        p2=copy.deepcopy(plan)
                        target=next(r for r in p2['independent_model']['functions'][PLACE]['rows'] if r['asm']=='MOVQ DX, 0(R11)')
                        target['asm']='MOVQ DX, 0x8(SP)'
                        rejected=methods.infer(p2,d)
                        assert rejected['status']=='unknown' and 'WB alternatives mutate application stack' in rejected['reason'],rejected
                        negatives.append(dict(strategy=strategy,name='WB_alternative_application_write',passed=True,kind='offline_fault_injection'))
            event_counts.append(dict(case=case['Name'],barrier=barrier,counts=counts,wb_condition_evaluations=branches))
    with tempfile.TemporaryDirectory() as folder:
        for s in methods.STRATEGIES: check_c(methods.strategy_plan(common,s),Path(folder))
    summary=dict(all_passed=True,bpf_executed=False,synthetic_events=True,unicorn_version=unicorn_version,
                 binary_sha256=common['binary_sha256'],native_fixture_runs=len(cases),elf_inference_checks=checks,
                 method_source_sha256={n:hashlib.sha256((HERE/n).read_bytes()).hexdigest() for n in
                    ('compare_methods.py','check_methods_local.py','method_baselines.py','independent_machine.py','independent_replay.py')},
                 negative_checks=negatives,machine_checks=machine_checks(),c_syntax_methods=list(methods.STRATEGIES),
                 synthetic_event_counts=event_counts,
                 scope='Unicorn executes actual ELF bytes; external runtime contracts are substituted. These are not host event/performance results.')
    (args.results/'method-local-checks.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(dict(all_passed=True,native_runs=len(cases),elf_inference_checks=len(checks),negative_checks=len(negatives),bpf_executed=False)))

if __name__=='__main__': main()
