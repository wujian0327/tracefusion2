"""Real Go code, synthetic interleaved event transport, actual concurrent HTTP.

Set GIN_CONCURRENT_BUILD to a successful concurrent runner build directory.
These tests do not replace host BPF compilation, attachment or event validation.
"""
import copy
import json
import os
from pathlib import Path
import signal
import struct
import subprocess
import tempfile
import unittest

from test_read_provenance import execute,stats,uc
import gin_concurrent_provenance as app
import gin_concurrent_boundaries as boundary

BUILD=os.environ.get('GIN_CONCURRENT_BUILD')


def history(binary,plans,config):
    rows=[];oracle=[];per_request={};bases=None
    files={str(fd):dict(fd=fd,path='/fixture/'+name,device=1,inode=fd,size=448,regular=True,access_mode=0)
           for fd,name in ((4,'a.bin'),(5,'b.bin'))}
    for ticket,mode in enumerate(app.MODES,1):
        # Client ticket, allocated request ID, entry order and completion order
        # are deliberately different. TIDs/G addresses repeat across batches.
        worker=(ticket-1)%4;rid=(ticket-1)//4*4+(4-worker)
        tid=(321<<32)|(400+worker);g=0x6000000+worker*4096
        base=ticket*0x10000000;src=base+0x2000000;dst=base+0x3000000
        value=0 if mode=='zero' else 0xffffffff if mode=='max' else 424242
        off=(ticket-1)*16+(8 if mode=='zero' else 12 if mode=='max' else 0)
        def event(kind,**kwargs):
            regs=[0]*16;regs[14]=g
            return dict(kind=kind,request_id=rid,pid_tid=tid,regs=regs,**kwargs)
        requests=[event(3)]
        for io,fd,delta in ((1,4,0),(2,5,4)):
            args=dict(io_id=io,fd=fd,file_offset=off,requested=4,buffer_addr=src+delta)
            requests.extend([event(1,**args),event(2,**args,returned=4,read_error=0,read_data=list(struct.pack('<I',value))+[0]*28)])
        functions=[('main.goSelectValue',1 if mode=='left' else 0)]
        if mode=='merge':functions=[('main.goMergeValues',0)]
        if mode=='overwrite':functions=[('main.goSelectValue',1),('main.goFallbackValue',0)]
        if mode=='same':functions=[('main.goCopyLeft',0),('main.goSelectValue',0)]
        for call,(name,selector) in enumerate(functions,1):
            compute,bases=execute(binary,plans,config,name,(value,value,99),selector,call,
                                  memory_base=base,goroutine_address=g)
            requests.extend(dict(e,request_id=rid,pid_tid=tid) for e in compute)
        value=requests[-1]['outputs'][0];body=json.dumps({'balance':value},separators=(',',':'))
        obj=dict(object_addr=dst,object_type=0x9000000,object_value=value,read_error=0)
        payload=dict(buffer_addr=base+0x9100000,requested=len(body),capacity=32,read_data=list(body.encode())+[0]*(32-len(body)),read_error=0)
        requests.extend([event(6,**obj,writer_addr=base+0x9200000),event(7,**obj),event(8,**payload,error_type=0),
                         event(10,**payload,writer_addr=base+0x9200000),event(11,returned=len(body),error_type=0),event(9,error_type=0),event(4)])
        for i,e in enumerate(requests):
            # Across CPUs, timestamp sample order need not equal atomic sequence
            # order. Each individual request's timestamps remain monotonic.
            e.update(request_sequence=i,timestamp=i*100+worker)
        per_request[ticket]=requests
        oracle.append(dict(ticket=ticket,mode=mode,input_addr=src,status=200,body=body,content_type='application/json; charset=utf-8'))
    for first in range(1,29,4):
        block=[per_request[t] for t in range(first,first+4)]
        # First scope/read from each request, then second reads, then round-robin
        # business instructions, then reverse-order JSON completion.
        for request in block:rows.extend(request[:3])
        for request in reversed(block):rows.extend(request[3:5])
        paths=[r[5:-7] for r in block]
        for i in range(max(map(len,paths))):
            for path in paths:
                if i<len(path):rows.append(path[i])
        for request in reversed(block):rows.extend(request[-7:])
    for i,e in enumerate(rows):e['observation_sequence']=i
    return rows,dict(functions=bases,read_files=files),list(reversed(oracle))


@unittest.skipUnless(BUILD and uc,'requires GIN_CONCURRENT_BUILD and Unicorn')
class ConcurrentGinTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=Path(BUILD);cls.binary=cls.root/'hybrid-demo'
        cls.plans=json.loads((cls.root/'probe-plan.json').read_text());cls.config=json.loads((cls.root/'config.json').read_text())
        cls.events,cls.runtime,cls.oracle=history(cls.binary,cls.plans,cls.config)

    def infer(self,events=None):
        return boundary.bind(self.events if events is None else events,self.plans,self.config,self.runtime)

    def test_interleaved_actual_go_instructions_and_independent_client_matching(self):
        inferred=self.infer();self.assertEqual(inferred['issues'],[])
        report=boundary.evaluate(inferred,self.oracle,stats(self.events),self.plans)
        self.assertTrue(report['passed'],report)
        self.assertEqual(report['concurrency']['max_active_scopes'],4)
        self.assertEqual(report['external_source_relations'],dict(tp=28,fp=0,fn=0,precision=1.0,recall=1.0))
        self.assertTrue(all(c['ticket']!=c['observed_request_id'] for c in report['checks']))
        ids=[n['id'] for r in inferred['results'] for n in r['dependency_graph']['nodes']]
        self.assertEqual(len(ids),len(set(ids)))

    def test_perf_delivery_order_and_cross_cpu_timestamps_not_used_as_causality(self):
        self.assertEqual(self.infer(list(reversed(self.events))),self.infer())
        self.assertTrue(any(a['timestamp']>b['timestamp'] for a,b in zip(self.events,self.events[1:])))

    def test_cross_request_event_and_local_sequence_corruption_rejected(self):
        for key in ('request_id','pid_tid','request_sequence'):
            rows=copy.deepcopy(self.events);e=next(e for e in rows if e['kind']==2);e[key]+=1
            self.assertTrue(self.infer(rows)['issues'],key)
        rows=copy.deepcopy(self.events);next(e for e in rows if e['kind']==7)['regs'][14]+=4096
        self.assertTrue(self.infer(rows)['issues'])

    def test_missing_scope_exit_and_missing_global_event_rejected(self):
        for kind in (0,3,4):
            rows=copy.deepcopy(self.events);rows.pop(next(i for i,e in enumerate(rows) if e['kind']==kind))
            self.assertTrue(self.infer(rows)['issues'])
        rows=copy.deepcopy(self.events);rows.pop(next(i for i,e in enumerate(rows) if e['kind']==4))
        for i,e in enumerate(rows):e['observation_sequence']=i
        self.assertTrue(self.infer(rows)['issues'])

    def test_same_bytes_from_wrong_request_offset_fail_evaluation(self):
        rows=copy.deepcopy(self.events)
        # Same bytes, same file, same operation ID, but another request's offset.
        rid=next(e['request_id'] for e in rows if e['kind']==1 and e['file_offset']==0)
        for e in rows:
            if e['request_id']==rid and e['kind'] in (1,2):e['file_offset']+=16
        inferred=self.infer(rows);self.assertFalse(inferred['issues'])
        self.assertFalse(boundary.evaluate(inferred,self.oracle,stats(rows),self.plans)['passed'])

    def test_shared_live_input_object_is_explicitly_rejected(self):
        rows=copy.deepcopy(self.events)
        starts=[e for e in rows if e['kind']==0 and e['sequence']==0 and e['call_id']==1]
        first,second=starts[:2];old=second['src_addr'];new=first['src_addr'];rid=second['request_id']
        def relocate(value):
            if isinstance(value,list):return [relocate(v) for v in value]
            if isinstance(value,dict):return {k:relocate(v) for k,v in value.items()}
            if isinstance(value,int) and old<=value<old+12:return value-old+new
            return value
        rows=[relocate(e) if e['request_id']==rid else e for e in rows]
        result=self.infer(rows)
        self.assertTrue(result['issues'])
        self.assertIn('Overlapping private request objects',result['issues'][0]['error'])

    def test_serialized_trace_cannot_claim_concurrent_validation(self):
        rows=[copy.deepcopy(e) for request in boundary.groups(self.events) for e in request]
        for i,e in enumerate(rows):e['observation_sequence']=i
        inferred=self.infer(rows);self.assertFalse(inferred['issues'])
        self.assertEqual(inferred['concurrency']['max_active_scopes'],1)
        self.assertFalse(boundary.evaluate(inferred,self.oracle,stats(rows),self.plans)['passed'])

    def test_client_mapping_and_capture_errors_fail_evaluation(self):
        inferred=self.infer();wrong=copy.deepcopy(self.oracle)
        wrong[0]['input_addr'],wrong[1]['input_addr']=wrong[1]['input_addr'],wrong[0]['input_addr']
        self.assertFalse(boundary.evaluate(inferred,wrong,stats(self.events),self.plans)['passed'])
        for key in ('lost_events','state_errors','submit_errors'):
            capture=stats(self.events);capture[key]=1
            self.assertFalse(boundary.evaluate(inferred,self.oracle,capture,self.plans)['passed'])

    def test_actual_concurrent_http_and_evaluation_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with (root/'program.stdout.jsonl').open('w') as stdout,(root/'program.stderr.log').open('w') as stderr:
                process=subprocess.Popen([str(self.binary),'--wait'],cwd=root,stdout=stdout,stderr=stderr)
                try:
                    app.common.wait_stopped(process);process.send_signal(signal.SIGCONT)
                    app.client(root);self.assertEqual(process.wait(timeout=12),0)
                finally:
                    if process.poll() is None:process.kill();process.wait()
            oracle=app.oracle(root);self.assertEqual(len(oracle),28)
            expected={r['ticket']:r for r in self.oracle}
            for row in oracle:
                for key in ('mode','status','body','content_type'):self.assertEqual(row[key],expected[row['ticket']][key])
            self.assertEqual(len({r['input_addr'] for r in oracle}),28)


class ConcurrentCollectorTests(unittest.TestCase):
    def test_generated_collector_isolates_pending_reads_calls_and_scope_reuse(self):
        config=json.loads((app.SCENARIO/'config.json').read_text())
        generated=app.bpf_source([],config)
        generated='\n'.join(line for line in generated.splitlines() if not line.startswith('#include'))
        # BCC's map.delete extension is named erase in this native C++ shim.
        generated=generated.replace('.delete(','.erase(')
        fixtures=Path(__file__).parent/'fixtures'
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);source=folder/'collector.cc';binary=folder/'collector'
            source.write_text((fixtures/'gin_concurrent_shim.hpp').read_text()+generated+(fixtures/'gin_concurrent_shim_main.cc').read_text())
            compiled=subprocess.run(['g++','-std=c++17','-O1',str(source),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(compiled.returncode,0,compiled.stderr)
            subprocess.run([str(binary)],check=True)


if __name__=='__main__':unittest.main()
