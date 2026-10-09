"""Semantic regression tests, NOT kernel captures or original-business results.

The small explicit instruction/event fixture exercises two outer iterations,
two nested Sum iterations, equal-valued distinct sources, frame relocation,
thread migration, final overwrite, and damaged evidence.
"""
import copy
import ctypes as ct
import unittest
import payment_adapter as a


def fixture():
    place=[(100,'NOPL'),(101,'MOVUPS X15, 0x38(SP)'),(102,'MOVQ 0x38(DX), R10'),(103,'MOVL 0x40(DX), R11'),
           (104,'CALL '+a.SUM+'(SB)'),(105,'MOVQ R10, 0x38(DI)'),(106,'MOVL R11, 0x40(DI)'),
           (110,'MOVQ 0x38(DX), R10'),(111,'MOVL 0x40(DX), R11'),(112,'CALL '+a.MULT+'(SB)'),
           (113,'MOVQ R10, 0x38(SP)'),(114,'MOVL R11, 0x40(SP)'),(115,'MOVQ 0x38(DI), R10'),
           (116,'MOVL 0x40(DI), R11'),(117,'CALL '+a.SUM+'(SB)'),(118,'MOVQ R10, 0x38(DI)'),
           (119,'MOVL R11, 0x40(DI)'),(120,'JNE 0x6e'),(121,'CALL '+a.PAY+'(SB)')]
    mult=[(200,'MOVQ R10, 0x80(SP)'),(201,'MOVL R11, 0x88(SP)'),(202,'MOVQ 0x80(SP), DX'),
          (203,'MOVQ DX, 0x38(SP)'),(204,'MOVL 0x88(SP), CX'),(205,'MOVL CX, 0x40(SP)'),
          (206,'CALL '+a.SUM+'(SB)'),(207,'JNE 0xca'),(208,'RET')]
    def fn(rows):return dict(frame=256,entry=rows[0][0],exit=rows[-1][0],rows=[
        dict(address=pc,asm=asm,next=rows[i+1][0] if i+1<len(rows) else None) for i,(pc,asm) in enumerate(rows)])
    sites=[]
    kinds={100:'source',121:'sink',122:'end',1000:'sum_entry',1010:'sum_exit'}
    for pc,asm in place+mult+[(122,'RET'),(1000,'NOPL'),(1010,'RET')]:
        kind=kinds.get(pc,'branch' if asm.startswith('JNE') else 'memory')
        sites.append(dict(id=pc,address=pc,kind=kind,roles=[kind],asm=asm,op='JNE'))
    sp=dict(flow=dict(entry=1000,paths=[dict(id=0,return_address=1010,branches=[],
            origins={'Units':['l.Units','l.Nanos','r.Units','r.Nanos'],'Nanos':['l.Nanos','r.Nanos']})]))
    plan=dict(binary_sha256='semantic-fixture',strategy='selected',functions={a.PLACE:fn(place),a.MULT:fn(mult)},sites=sites,sum_model=sp)
    events=[]
    def emit(pc,dx=0x10000,flags=0,**kw):
        n=len(events);regs={r:0 for r in a.GPRS};regs.update(DX=dx,DI=0x50000,SP=0x8000 if n%2 else 0x9000)
        e=dict(site=pc,kind=kinds.get(pc,'branch' if pc in (120,207) else 'memory'),timestamp=n+1,
               g=99,pid_tid=(42<<32)|(100+n%2),registers=regs,flags=flags,a=0,b=0,c=0,d=0,tag=0,error=0)
        e.update(kw);events.append(e)
    def sum_events():emit(1000);emit(1010)
    emit(100,a=2)
    emit(100,tag=1,a=0x10000,b=1,c=0)
    emit(100,tag=2,a=0x20000,b=2,c=0,d=3)
    emit(100,tag=3,a=0x30000,b=2,c=0,d=3)
    for pc in (101,102,103,104):emit(pc)
    sum_events()
    for pc in (105,106):emit(pc)
    for index in range(2):
        for pc in (110,111,112):emit(pc,dx=0x20000+index*0x10000)
        emit(200);emit(201)
        for iteration in range(2):
            for pc in (202,203,204,205,206):emit(pc)
            sum_events();emit(207,flags=0 if iteration==0 else 64)
        emit(208)
        for pc in (113,114,115,116,117):emit(pc)
        sum_events()
        for pc in (118,119):emit(pc)
        emit(120,flags=0 if index==0 else 64)
    emit(121,a=0x50000,b=13,c=0);emit(122)
    stats={k:0 for k in ('lost','read_errors','submit_errors','namespace_errors')};stats['submitted']=len(events)
    doc=dict(binary_sha256=plan['binary_sha256'],events=events,stats=stats,capture_errors=[],returncode=0)
    return plan,doc


class ReplayTests(unittest.TestCase):
    def test_nested_loops_equal_sources_and_migration(self):
        p,d=fixture();r=a.infer(p,d)
        self.assertEqual(r['status'],'exact_data_origins',r)
        self.assertEqual(r['origins']['Units'],sorted(prefix+'.'+field for prefix in ('shipping','items[0].Cost','items[1].Cost') for field in ('Units','Nanos')))
        self.assertEqual(r['origins']['Nanos'],['items[0].Cost.Nanos','items[1].Cost.Nanos','shipping.Nanos'])
        self.assertEqual(len([c for c in r['calls'] if c['kind']=='Sum']),7)
        self.assertEqual(len([c for c in r['calls'] if c['kind']=='MultiplySlow']),2)
        self.assertEqual(r['threads'],2)

    def test_last_write_kills_old_sources(self):
        p,d=fixture()
        next(r for r in p['functions'][a.PLACE]['rows'] if r['address']==118)['asm']='MOVQ $0x7, 0x38(DI)'
        r=a.infer(p,d);self.assertEqual(r['status'],'exact_data_origins',r)
        self.assertEqual(r['origins']['Units'],[])
        self.assertEqual(len(r['origins']['Nanos']),3)

    def test_missing_nested_call_rejected_with_consistent_counts(self):
        p,d=fixture();del d['events'][next(i for i,e in enumerate(d['events']) if e['kind']=='sum_entry')]
        d['stats']['submitted']-=1
        self.assertEqual(a.infer(p,d)['status'],'unknown')

    def test_unmodeled_call_rejected(self):
        p,d=fixture();next(r for r in p['functions'][a.PLACE]['rows'] if r['address']==112)['asm']='CALL unknown.writer(SB)'
        self.assertEqual(a.infer(p,d)['status'],'unknown')

    def test_aliasing_source_objects_rejected(self):
        p,d=fixture();d['events'][3]['a']=d['events'][2]['a']
        self.assertEqual(a.infer(p,d)['status'],'unknown')

    def test_cross_g_event_rejected(self):
        p,d=fixture();d['events'][20]['g']+=1
        self.assertEqual(a.infer(p,d)['status'],'unknown')

    def test_perf_padding(self):
        r=a.Raw();r.site=4;r.tag=3;r.registers[15]=123
        n=ct.sizeof(r);buf=ct.create_string_buffer(ct.string_at(ct.byref(r),n)+b'\0'*4)
        for size in (n,((n+11)//8)*8-4):
            e=a.decode_record(buf,size,{4:{'kind':'source'}})
            self.assertEqual(e['tag'],3);self.assertEqual(e['registers']['SP'],123)
        with self.assertRaises(ValueError):a.decode_record(buf,n-4,{4:{'kind':'source'}})


if __name__=='__main__':unittest.main()
