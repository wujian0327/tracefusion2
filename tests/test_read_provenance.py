"""Native C oracle + real pread operations + independent Unicorn computation.

The combined event transport is synthesized here, never described as BPF proof.
"""
import copy
import errno
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import read_provenance as app
import read_boundaries as boundary
import interproc_model as model
from language_adapters import get_adapter
from test_interproc_provenance import uc, x86

SCENARIO=app.common.ROOT/'scenarios/read-provenance'


def execute(binary, plans, config, function, values, selector, call_id, *, memory_base=0, goroutine_address=None):
    elf=binary.read_bytes(); phoff=struct.unpack_from('<Q',elf,32)[0]
    phsize,phnum=struct.unpack_from('<HH',elf,54)
    cpu=uc.Uc(uc.UC_ARCH_X86,uc.UC_MODE_64); mapped=set(); bias=0x1000000
    for i in range(phnum):
        segment=struct.unpack_from('<IIQQQQQQ',elf,phoff+i*phsize)
        if segment[0]!=1:continue
        start=bias+segment[3]
        for page in range(start&~4095,(start+segment[6]+4095)&~4095,4096):
            if page not in mapped:cpu.mem_map(page,4096);mapped.add(page)
        cpu.mem_write(start,elf[segment[2]:segment[2]+segment[5]])
    src,dst,stack,stop=(memory_base+a for a in (0x2000000,0x3000000,0x4000000,0x5000000))
    for address in (src,dst,stack,stop):cpu.mem_map(address,4096)
    root_sp=stack+2040
    cpu.mem_write(src,struct.pack('<III',*values));cpu.mem_write(dst,struct.pack('<II',0xdeadbeef,0))
    cpu.mem_write(root_sp,struct.pack('<Q',stop))
    adapter=get_adapter(config)
    for reg,value in [(adapter.input_register,src),(adapter.output_register,dst),(adapter.selector_register,selector),('rsp',root_sp)]:
        cpu.reg_write(getattr(x86,'UC_X86_REG_'+reg.upper()),value)
    for i,r in enumerate(adapter.saved_registers):cpu.reg_write(getattr(x86,'UC_X86_REG_'+r.upper()),0xabc000+i)
    if adapter.runtime_guard_offset is not None:
        goroutine=goroutine_address or (memory_base+0x6000000);cpu.mem_map(goroutine,4096)
        cpu.mem_write(goroutine+adapter.runtime_guard_offset,struct.pack('<Q',stack+256))
        cpu.reg_write(x86.UC_X86_REG_R14,goroutine)
    stack_words=model.STACK_WORDS+adapter.stack_above//8
    bases={p['function']:bias+p['symbol_address'] for p in plans}
    points={bases[p['function']]+n['offset']:(fid,n) for fid,p in enumerate(plans) for n in p['instructions']}
    root_id=next(i for i,p in enumerate(plans) if p['function']==function)
    frames=[];events=[]
    def observe(machine,address,size,user):
        if address not in points:return
        fid,n=points[address]
        if n['offset']==0:frames.append(fid)
        assert frames[-1]==fid
        events.append(dict(kind=0,timestamp=len(events)+1,pid_tid=(321<<32)|321,call_id=call_id,sequence=len(events),
            root=root_id,depth=len(frames),function=fid,offset=n['offset'],src_addr=src,dst_addr=dst,root_sp=root_sp,ip=address,
            flags=machine.reg_read(x86.UC_X86_REG_EFLAGS),regs=[machine.reg_read(getattr(x86,'UC_X86_REG_'+r.upper())) for r in model.REGS],
            inputs=list(struct.unpack('<III',machine.mem_read(src,12))),outputs=list(struct.unpack('<II',machine.mem_read(dst,8))),
            stack=list(struct.unpack('<'+'Q'*stack_words,machine.mem_read(root_sp-model.STACK_BYTES,stack_words*8))),
            source_error=0,destination_error=0,stack_error=0))
        if adapter.runtime_guard_offset is not None:
            events[-1].update(runtime_guard=stack+256,runtime_guard_error=0)
        if n['op']=='ret':frames.pop()
    cpu.hook_add(uc.UC_HOOK_CODE,observe)
    cpu.emu_start(bases[function],stop,count=4096)
    assert not frames and cpu.reg_read(x86.UC_X86_REG_RIP)==stop
    return events,bases


def observation(kind, **kwargs):
    return dict(kind=kind,pid_tid=(321<<32)|321,**kwargs)


def make_history(binary,plans,config):
    rows=[observation(boundary.SCOPE_ENTER)]; io=0; call=0; memory=bytearray(struct.pack('<III',0,0,99))
    with tempfile.TemporaryDirectory() as tmp:
        paths=[Path(tmp)/n for n in ('a.bin','b.bin')]
        for p in paths:p.write_bytes(struct.pack('<II',424242,424243))
        a,b=[os.open(p,os.O_RDONLY) for p in paths]
        files={str(fd):dict(fd=fd,path=str(path),device=path.stat().st_dev,inode=path.stat().st_ino,size=8,regular=True,access_mode=0) for fd,path in zip((a,b),paths)}
        def read(fd,slot,offset):
            nonlocal io
            io+=1
            args=dict(io_id=io,fd=fd,file_offset=offset,requested=4,buffer_addr=0x2000000+slot)
            rows.append(observation(boundary.READ_ENTER,**args))
            try:data=os.pread(fd,4,offset);returned=len(data)
            except OSError as exc:data=b'';returned=-exc.errno
            memory[slot:slot+max(0,returned)]=data
            rows.append(observation(boundary.READ_EXIT,**args,returned=returned,read_error=0,read_data=list(data)+[0]*(32-len(data))))
        try:
            for round_id in range(2):
                off=round_id*4
                for case in range(9):
                    if case<=2:
                        read(a,0,off);read(b,4,off)
                    elif case==7:read(-1,0,off)
                    else:
                        read(a,0,off)
                        if case==3:read(b,0,off)
                        elif case==4:read(a,0,(1-round_id)*4)
                        elif case==5:read(-1,0,off)
                        elif case==6:read(b,0,8)
                        elif case==8:read(a,0,off)
                    function=config['functions'][1 if case==2 else 2 if case==7 else 0]
                    call+=1
                    events,bases=execute(binary,plans,config,function,struct.unpack('<III',memory),0 if case==1 else 1,call)
                    rows.extend(events)
        finally:os.close(a);os.close(b)
    rows.append(observation(boundary.SCOPE_EXIT))
    for i,event in enumerate(rows):
        event.update(observation_sequence=i,timestamp=i+1)
        if get_adapter(config).context.identity_register and event['kind']!=0:
            event['regs']=[0]*16;event['regs'][14]=0x6000000
    return rows,dict(functions=bases,read_files=files)


def stats(events):
    return dict(backend='real-pread-plus-unicorn-test-only',received_events=len(events),attempted_events=len(events),raw_probe_hits=len(events),
                lost_events=0,submit_errors=0,state_errors=0,process_returncode=0)


@unittest.skipUnless(uc and shutil.which('gcc') and shutil.which('objdump'),'requires GCC and Unicorn')
class ReadBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();out=Path(cls.tmp.name)
        cls.binary,cls.plans,cls.config=app.build(SCENARIO,out)
        cls.truth=[json.loads(l) for l in subprocess.check_output([str(cls.binary)],text=True).splitlines()]
        cls.events,cls.runtime=make_history(cls.binary,cls.plans,cls.config)
        cls.inferred=boundary.bind(cls.events,cls.plans,cls.config,cls.runtime)

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def replay(self,events=None,runtime=None):
        return boundary.bind(self.events if events is None else events,self.plans,self.config,self.runtime if runtime is None else runtime)

    def test_native_oracle_real_files_and_independent_machine_execution(self):
        self.assertEqual(self.inferred['issues'],[])
        result=boundary.evaluate(self.inferred,self.truth,stats(self.events),self.plans)
        self.assertTrue(result['passed'],result)
        self.assertEqual(len(self.inferred['results']),18)
        self.assertEqual(len(self.inferred['read_operations']),34)
        self.assertEqual(result['external_source_relations'],dict(tp=18,fp=0,fn=0,precision=1.0,recall=1.0))

    def test_equal_values_different_files_and_merge_graph(self):
        a,b,merged=self.inferred['results'][:3]
        self.assertEqual(a['external_sources'][0]['file_name'],'a.bin')
        self.assertEqual(b['external_sources'][0]['file_name'],'b.bin')
        self.assertEqual({s['file_name'] for s in merged['external_sources']},{'a.bin','b.bin'})
        self.assertTrue(any(e['kind']=='read-result' for e in merged['dependency_graph']['edges']))
        self.assertEqual(len({s['operation_id'] for s in merged['external_sources']}),2)

    def test_overwrite_new_read_instance_and_file_offset(self):
        overwritten,other_offset=self.inferred['results'][3:5]
        self.assertEqual(overwritten['external_sources'][0]['io_id'],8)
        self.assertEqual(overwritten['external_sources'][0]['file_name'],'b.bin')
        self.assertEqual(other_offset['external_sources'][0]['file_offset'],4)
        repeated=self.inferred['results'][8]['external_sources'][0]
        self.assertEqual(repeated['io_id'],17)
        self.assertEqual(repeated['file_offset'],0)

    def test_failure_eof_and_fallback_do_not_invent_new_sources(self):
        rows=self.inferred['results']
        self.assertEqual(rows[5]['external_sources'][0]['io_id'],11)
        self.assertEqual(rows[6]['external_sources'][0]['io_id'],13)
        self.assertEqual(rows[7]['external_sources'],[])
        ops=self.inferred['read_operations']
        self.assertEqual(ops[11]['returned'],-errno.EBADF)
        self.assertEqual(ops[13]['returned'],0)

    def test_missing_duplicate_or_unpaired_evidence_rejected(self):
        bad=copy.deepcopy(self.events);del bad[1]
        self.assertTrue(self.replay(bad)['issues'])
        bad=copy.deepcopy(self.events);bad.insert(2,copy.deepcopy(bad[1]))
        self.assertTrue(self.replay(bad)['issues'])
        bad=copy.deepcopy(self.events);bad[2]['io_id']=999
        self.assertTrue(self.replay(bad)['issues'])
        bad=copy.deepcopy(self.events);del bad[1:3]
        for i,e in enumerate(bad):e['observation_sequence']=i
        self.assertTrue(self.replay(bad)['issues'])

    def test_unknown_descriptor_failed_snapshot_and_mutated_input_rejected(self):
        bad=copy.deepcopy(self.events);bad[1]['fd']=bad[2]['fd']=999
        self.assertTrue(self.replay(bad)['issues'])
        bad=copy.deepcopy(self.events);bad[2]['read_error']=-1
        self.assertTrue(self.replay(bad)['issues'])
        # Actual machine values are unchanged; falsifying the observed bytes
        # must not pass just because the inferred field name still matches.
        bad=copy.deepcopy(self.events);bad[2]['read_data'][0]^=1
        self.assertTrue(self.replay(bad)['issues'])

    def test_short_read_and_descriptor_lifecycle_rejected(self):
        bad=copy.deepcopy(self.events);bad[2]['returned']=2
        self.assertTrue(self.replay(bad)['issues'])
        bad=copy.deepcopy(self.events);bad[1]['kind']=boundary.INVALIDATE
        self.assertTrue(self.replay(bad)['issues'])
        # A two-byte overwrite of an existing four-byte version cannot be
        # silently relabeled as a complete new field, even if bytes are equal.
        bad=copy.deepcopy(self.events)
        e=next(e for e in bad if e.get('io_id')==17 and e['kind']==boundary.READ_EXIT);e['returned']=2
        self.assertIn('mixed-version',self.replay(bad)['issues'][0]['error'])

    def test_thread_change_read_during_compute_and_capture_loss_rejected(self):
        bad=copy.deepcopy(self.events);bad[1]['pid_tid']+=1
        self.assertTrue(self.replay(bad)['issues'])
        bad=copy.deepcopy(self.events)
        index=next(i for i,e in enumerate(bad) if e['kind']==0)
        extra=copy.deepcopy(bad[1]);extra['io_id']=3;bad.insert(index+1,extra)
        for i,e in enumerate(bad):e.update(observation_sequence=i,timestamp=i+1)
        self.assertTrue(self.replay(bad)['issues'])
        capture=stats(self.events);capture['submit_errors']=1
        self.assertFalse(boundary.evaluate(self.inferred,self.truth,capture,self.plans)['passed'])

    def test_oracle_operation_identity_cannot_be_replaced_by_value_match(self):
        truth=copy.deepcopy(self.truth);truth[8]['expected_external_sources'][0]['io_id']-=1
        self.assertFalse(boundary.evaluate(self.inferred,truth,stats(self.events),self.plans)['passed'])

    def test_descriptor_snapshot_preserves_identity_and_access_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/'sample';path.write_bytes(b'1234')
            proc=root/'proc';fds=proc/'123'/'fd';info=proc/'123'/'fdinfo'
            fds.mkdir(parents=True);info.mkdir()
            (fds/'3').symlink_to(path);(info/'3').write_text('pos:\t0\nflags:\t0100000\n')
            (fds/'4').symlink_to(path);(info/'4').write_text('pos:\t0\nflags:\t0100002\n')
            (fds/'5').symlink_to(root)  # directories are not read sources
            snapshot=app.snapshot_files(123,proc_root=proc)
            self.assertEqual(set(snapshot),{'3','4'})
            self.assertEqual(snapshot['3']['inode'],path.stat().st_ino)
            self.assertEqual(snapshot['3']['device'],path.stat().st_dev)
            self.assertEqual(snapshot['3']['access_mode'],0)
            self.assertEqual(snapshot['4']['access_mode'],2)



if __name__=='__main__':unittest.main()
