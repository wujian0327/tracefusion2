import ctypes as ct
from copy import deepcopy
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from go_byte_adapter import assembly_rows,decode_function,REGISTERS
from byte_provenance import infer
from byte_capture import Raw,HEADER,source,decode_record
from go_byte_provenance import score,negative_checks,evaluate_pairs


def evidence(reverse=False,use_c=False):
    """Independent explicit trace of the two compiled fixture loops.

    Does not call ByteMachine to generate registers, byte loads or expected
    mappings. These fixtures exercise all dynamic iterations, not just I/O.
    """
    name='reverse' if reverse else 'forward'
    rows=assembly_rows((Path(__file__).parent/'fixtures'/('go-byte-'+name+'.asm')).read_text())
    ir=decode_function(rows)
    sites=[]
    for pair,op in enumerate(['source','source','source','work','json']):
        for phase in ('pre','post'):
            sites.append({'id':len(sites),'op':op,'phase':phase,'pair':pair,'address':0x8000+len(sites),'snapshots':{}})
    for n in ir:
        n['site']=len(sites);snaps={}
        if n['op'] in ('movzx','test'):snaps={'load':{'address':n['args'][0 if n['op']=='movzx' else 1],'length':1}}
        sites.append({'id':len(sites),'op':'instruction','phase':'step','pair':-1,'address':n['address'],'snapshots':snaps})
    plan={'sites':sites,'instructions':ir,'entry':ir[0]['address'],'root_order':list(range(10)),
          'abi':{'dst_register':'rax','src_register':'rbx'},
          'event_order':list(range(len(sites))),'max_steps':256,'binary_sha256':name}
    events=[];regs={r:0 for r in REGISTERS};regs.update(rcx=123,rdx=999,rsi=777,r14=0x888)
    def value(ptr,data):return {'pointer':ptr,'hex':data.hex(),'key':f'{ptr:x}:{len(data)}'}
    def emit(sid,values=None):
        s=sites[sid];i=len(events)
        events.append(dict(site=sid,op=s['op'],phase=s['phase'],timestamp=i,sequence=i,
                           pid=1,tid=2+i%2,g=0x888,registers=dict(regs),values=values or {}))
    for i,ptr in enumerate((0x1000,0x2000,0x3000)):
        emit(2*i,{'path':value(0x7000+i*100,('read'+str(i)).encode())})
        emit(2*i+1,{'value':value(ptr,b'SAME')})
    src=0x3000 if use_c else 0x1000;dst=0x4000;data=b'SAME';output=bytearray(4)
    regs.update(rax=dst,rbx=src)
    emit(6,{'src':value(src,data),'dst':value(dst,bytes(output))})
    by_asm={n['asm']:n for n in ir}
    def step(asm,values=None):emit(by_asm[asm]['site'],values)
    emit(ir[0]['site']);regs['rcx']=0
    emit(ir[1]['site'])
    cmp_node=next(n for n in ir if n['op']=='cmp');jump=next(n for n in ir if n['op']=='jl')
    for i in range(5):
        emit(cmp_node['site']);emit(jump['site'])
        if i==4:break
        step('TESTB AL, 0(AX)',{'load':value(dst,bytes(output[:1]))})
        step('TESTB AL, 0(BX)',{'load':value(src,data[:1])})
        j=3-i if reverse else i
        if reverse:
            step('LEAQ -0x3(CX), DX');regs['rdx']=(i-3)&((1<<64)-1)
            step('MOVQ BX, SI');regs['rsi']=src
            step('SUBQ DX, SI');regs['rsi']=src+j
            step('MOVZX 0(SI), DX',{'load':value(src+j,data[j:j+1])})
        else:step('MOVZX 0(BX)(CX*1), DX',{'load':value(src+j,data[j:j+1])})
        regs['rdx']=data[j]
        step('XORL $0x20, DX');regs['rdx']=data[j]^0x20
        step('MOVB DL, 0(AX)(CX*1)');output[i]=regs['rdx']
        step('INCQ CX');regs['rcx']=i+1
        if reverse:step('NOPW')
    step('RET');emit(7)
    emit(8,{'value':value(dst,bytes(output))})
    emit(9,{'json':value(0x9000,json.dumps({'result':output.decode()}).encode())})
    doc={'binary_sha256':name,'events':events,'returncode':0,'capture_errors':[],
         'stats':{'submitted':len(events),'read_errors':0,'submit_errors':0,'lost':0}}
    sid='source:3' if use_c else 'source:1'
    oracle={'sources':[sid],'excluded':[s for s in ('source:1','source:2','source:3') if s!=sid],
            'output':{'result':'emas' if reverse else 'same'},
            'byte_sources':[{'output_byte':i,'origins':[{'source':sid,'byte':3-i if reverse else i}]} for i in range(4)]}
    return doc,plan,oracle


class ByteProvenanceTests(unittest.TestCase):
    def test_both_compiled_loops_and_runtime_source_choices(self):
        results={};documents={};outputs={}
        for reverse in (False,True):
            for use_c in (False,True):
                doc,plan,oracle=evidence(reverse,use_c);result=infer(doc,plan)
                self.assertTrue(score(result,oracle)['passed'],result)
                self.assertEqual(len(result['instruction_steps']),53 if reverse else 37)
                name=('reverse' if reverse else 'forward')+('_c' if use_c else '_a')
                results[name]=result;documents[name]=doc;outputs[name]=result['output']
                self.assertTrue(all(c['passed'] for c in negative_checks(doc,plan)))
        self.assertTrue(evaluate_pairs(results,documents,outputs)['passed'])

    def test_equal_output_does_not_make_wrong_byte_mapping_correct(self):
        doc,plan,oracle=evidence(True,True);result=infer(doc,plan)
        result['byte_sources'][0]['origins'][0]['byte']=0
        self.assertFalse(score(result,oracle)['passed'])

    def test_rejects_unsupported_instruction_and_external_branch(self):
        _,plan,_=evidence();rows=[{k:n[k] for k in ('address','code','asm','location')} for n in plan['instructions']]
        changed=deepcopy(rows);changed[3]['asm']='CALL main.unknown(SB)'
        with self.assertRaisesRegex(ValueError,'Unsupported leaf instruction'):decode_function(changed)
        changed=deepcopy(rows);changed[1]['asm']='JMP 0x123'
        with self.assertRaisesRegex(ValueError,'Branch leaves'):decode_function(changed)

    def test_rejects_aliased_regions_and_execution_identity_changes(self):
        for change in ('overlap','goroutine','extra_ret','wrong_branch','uninitialized_register'):
            doc,plan,_=evidence()
            if change=='overlap':
                work=next(e for e in doc['events'] if e['op']=='work' and e['phase']=='pre')
                work['values']['dst']=dict(work['values']['src'])
            elif change=='goroutine':doc['events'][12]['g']=9
            elif change=='extra_ret':
                ret=next(e for e in doc['events'] if e['site']==plan['instructions'][-1]['site'])
                extra=deepcopy(ret);extra['sequence']=999;extra['timestamp']+=0.5
                doc['events'].append(extra)
            elif change=='wrong_branch':
                event=doc['events'][9];event['site']=plan['instructions'][2]['site']
            else:plan['instructions'][5]['args'][0]={'kind':'reg','reg':'r15','width':32}
            doc['stats']['submitted']=len(doc['events'])
            self.assertEqual(infer(doc,plan)['status'],'unknown',change)

    def test_record_padding_registers_and_generated_load_address(self):
        _,plan,_=evidence(True);site=next(n['site'] for n in plan['instructions'] if n['op']=='movzx')
        raw=Raw();raw.site=site;raw.pid_tid=(1<<32)|2;raw.g=0x888
        raw.registers[REGISTERS.index('rsi')]=0x1003;raw.pointer[0]=0x1003;raw.length[0]=1;raw.data[0][0]=ord('E')
        specs={s['id']:s for s in plan['sites']};decoded=[]
        for pad in (b'',b'\xa5'*4):
            payload=bytes(raw)+pad;buf=ct.create_string_buffer(payload)
            decoded.append(decode_record(buf,len(payload),specs))
        self.assertEqual(decoded[0],decoded[1]);self.assertEqual(decoded[0]['registers']['rsi'],0x1003)
        self.assertEqual(decoded[0]['values']['load']['hex'],'45')
        with self.assertRaises(ValueError):decode_record(None,1,specs)
        generated=source(plan,123,SimpleNamespace(st_dev=4,st_ino=55))
        self.assertIn('snapshot(e,0,ctx->si+(0),1)',generated)
        self.assertIn('e->registers[0]=ctx->ax;',generated)

    @unittest.skipUnless(shutil.which('gcc'),'GCC required')
    def test_c_and_python_event_layout_agree(self):
        structure=re.search(r'struct event_t \{.*?\n\};',HEADER,re.S).group()
        code='#include <stdint.h>\n#include <stddef.h>\ntypedef uint64_t u64;typedef uint32_t u32;typedef uint8_t u8;\n'+structure
        code+='\nsize_t size(void){return sizeof(struct event_t);}\nsize_t regs(void){return offsetof(struct event_t,registers);}\nsize_t bytes(void){return offsetof(struct event_t,data);}\n'
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'c.c').write_text(code)
            subprocess.run(['gcc','-shared','-fPIC',str(p/'c.c'),'-o',str(p/'c.so')],check=True,capture_output=True)
            lib=ct.CDLL(str(p/'c.so'))
            self.assertEqual(lib.size(),ct.sizeof(Raw));self.assertEqual(lib.regs(),Raw.registers.offset);self.assertEqual(lib.bytes(),Raw.data.offset)

if __name__=='__main__':unittest.main()
