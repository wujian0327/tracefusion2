from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from test_go_byte_provenance import assignment_evidence
from gin_byte_boundaries import bind
from gin_byte_provenance import negative_checks,evaluate
import gin_byte_capture


def evidence(variant='partial',use_c=False,g=0x888,offset=0,ticket=1):
    doc,plan=assignment_evidence(variant=='overwrite',use_c,variant=='partial')
    plan['json_model']='gin-byte-array-v1'
    plan['root_order']=list(range(9))
    sites=plan['sites']
    def site(op,phase):
        sid=len(sites);sites.append(dict(id=sid,op=op,phase=phase,pair=-1,address=0x9000+sid,snapshots={}))
        return sid
    scope_pre=site('scope','pre');scope_post=site('scope','post')
    marshal_pre=site('marshal','pre');writer_pre=site('writer','pre');writer_post=site('writer','post');render_post=site('render','post')
    plan.update(scope_entry=scope_pre,scope_exits=[scope_post])
    events=doc['events']
    def val(p,b):return dict(pointer=p,hex=b.hex(),key=f'{p:x}:{len(b)}')
    def make(sid):
        s=sites[sid];e=deepcopy(events[0]);e.update(site=sid,op=s['op'],phase=s['phase'],values={});return e
    encoded=b'{"result":[83,65,77,69]}'
    for i in range(3):events[2*i]['values']['path']=val(0x7000+i*100,f'/fixture/{ticket}/{"ABC"[i]}.txt'.encode())
    render=events[-2];ret=events[-1]
    render['registers'].update(rcx=0x1111,rbx=0x2222)
    marshal=make(marshal_pre);marshal['registers'].update(rax=0x1111,rbx=0x4000);marshal['values']=deepcopy(render['values'])
    ret['values']['json']=val(0x9000,encoded);ret['registers'].update(rax=0x9000,rbx=len(encoded),rcx=len(encoded),rdi=0)
    writer=make(writer_pre);writer['registers'].update(rax=0x2222,rbx=0x9000,rcx=len(encoded),rdi=len(encoded));writer['values']={'json':val(0x9000,encoded)}
    wret=make(writer_post);wret['registers'].update(rax=len(encoded),rbx=0)
    rret=make(render_post);rret['registers']['rax']=0
    combined=[make(scope_pre)]+events[:-2]+[render,marshal,ret,writer,wret,rret,make(scope_post)]
    # Request-private address spaces. Only known ABI address-bearing slots are
    # shifted; scalar registers (loop counters and bytes) are unchanged.
    pointers={0x1000,0x2000,0x3000,0x4000,0x7000,0x7064,0x70c8,0x9000,0x1111,0x2222}
    for i,e in enumerate(combined):
        for k,v in e['registers'].items():
            if v in pointers:e['registers'][k]=v+offset
        e['g']=g;e['registers']['r14']=g;e['tid']=2+i%2
        e['sequence']=i;e['timestamp']=i
        for v in e['values'].values():
            v['pointer']+=offset;v['key']=f'{v["pointer"]:x}:{len(bytes.fromhex(v["hex"]))}'
    doc['events']=combined;doc['stats']['submitted']=len(combined)
    return doc,plan


def combine(documents):
    d=deepcopy(documents[0]);rows=[]
    for idx,doc in enumerate(documents):
        for e in deepcopy(doc['events']):
            e['timestamp']=e['timestamp']*len(documents)+idx;rows.append(e)
    rows.sort(key=lambda e:e['timestamp'])
    for i,e in enumerate(rows):e['sequence']=i
    d['events']=rows;d['stats']['submitted']=len(rows);return d


class GinByteTests(unittest.TestCase):
    def test_interleaved_requests_keep_distinct_origins_and_accept_tid_changes(self):
        for variant in ('assign','partial','overwrite'):
            a,p=evidence(variant,ticket=1);c,_=evidence(variant,True,g=0x999,offset=0x10000,ticket=2)
            d=combine([a,c]);result=bind(d,p)
            self.assertEqual(result['status'],'resolved',result)
            self.assertEqual(result['concurrency']['max_active_scopes'],2)
            self.assertEqual(result['concurrency']['migrated_requests'],2)
            expected=[['source:1'],['source:3']] if variant=='assign' else [['source:1','source:2'],['source:2','source:3']] if variant=='partial' else [['source:2'],['source:2']]
            self.assertEqual([r['local_sources'] for r in result['results']],expected)
            ids=[n['id'] for r in result['results'] for n in r['provenance']['graph']['nodes']]
            self.assertEqual(len(ids),len(set(ids)))
            self.assertTrue(all(c['passed'] for c in negative_checks(d,p)))

    def test_reused_g_and_addresses_start_new_scope_generation(self):
        a,p=evidence();b,_=evidence(use_c=True,ticket=2)
        events=deepcopy(a['events']+b['events'])
        for i,e in enumerate(events):e['timestamp']=i;e['sequence']=i
        a['events']=events;a['stats']['submitted']=len(events)
        result=bind(a,p)
        self.assertEqual(result['status'],'resolved',result)
        self.assertEqual([r['request_id'] for r in result['results']],[1,2])
        self.assertEqual(result['concurrency']['max_active_scopes'],1)
        self.assertEqual([r['local_sources'] for r in result['results']],[['source:1','source:2'],['source:2','source:3']])

    def test_framework_identity_and_partial_writes_rejected(self):
        for failure in ('type','pointer','partial_write','nested_scope','error','cross_request'):
            d,p=evidence();e=d['events']
            if failure=='type':next(x for x in e if x['op']=='marshal')['registers']['rax']+=1
            elif failure=='pointer':next(x for x in e if x['op']=='marshal')['values']['value']['pointer']+=1
            elif failure=='partial_write':next(x for x in e if x['op']=='writer' and x['phase']=='post')['registers']['rax']-=1
            elif failure=='nested_scope':
                e[1]=deepcopy(e[0]);e[1]['sequence']=1;e[1]['timestamp']=1
            elif failure=='error':next(x for x in e if x['op']=='render')['registers']['rax']=1
            else:
                x=next(x for x in e if x['op']=='instruction');x['g']=0x999;x['registers']['r14']=0x999
            self.assertEqual(bind(d,p)['status'],'unknown',failure)

    def test_evaluation_separates_provenance_from_concurrency_coverage(self):
        docs=[]
        for ticket in range(1,9):
            d,p=evidence(use_c=ticket%2==0,g=0x888+ticket,offset=ticket*0x10000,ticket=ticket);docs.append(d)
        combined=combine(docs);result=bind(combined,p)
        self.assertEqual(result['status'],'resolved',result)
        responses=[dict(ticket=i,body='{"result":[83,65,77,69]}',status=200,content_type='application/json; charset=utf-8') for i in range(1,9)]
        meta=dict(gomaxprocs=2,num_cpu=2,gomaxprocs_env_set=False,scheduler_override_flags=[])
        stdout=json.dumps({'scheduler':meta})+'\n'+json.dumps({'scheduler_final':meta})
        report=evaluate(result,responses,stdout,'partial',Path('/fixture'))
        self.assertTrue(report['passed'],report)
        result['concurrency']['max_active_scopes']=1
        report=evaluate(result,responses,stdout,'partial',Path('/fixture'))
        self.assertFalse(report['passed']);self.assertTrue(report['provenance_checks_passed'])

    def test_collector_scope_filter_uses_observed_g(self):
        _,p=evidence();generated=gin_byte_capture.source(p,123,SimpleNamespace(st_dev=4,st_ino=55))
        self.assertIn('gin_active.lookup(&g)',generated)
        self.assertIn('gin_active.delete(&g)',generated)
        self.assertNotIn('gin_active.lookup(&tid)',generated)
        self.assertNotIn('IS_EXIT',generated)

if __name__=='__main__':unittest.main()
