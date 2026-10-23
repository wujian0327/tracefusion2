#!/usr/bin/env python3
"""Real HTTP, Spring decoder and Future integration with independent message truth."""
import argparse,json,threading,copy
from pathlib import Path
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from zipfile import ZipFile
from build_distributed_plans import build
from experiment_environment import java8_target
from run_query_planner import command,JARS
from run_planned_service import ROOT,HERE,save,load
from infer_distributed_fields import Reconstruction
from infer_execution_kernel import infer_execution
import run_response_binding_revision as old

def run(out,libs):
    out.mkdir(parents=True,exist_ok=False);classes=out/'classes';classes.mkdir()
    cp=':'.join(map(str,[*JARS,*sorted(libs.glob('*.jar'))]));compile_cp=cp+':'+str(ROOT/'artifacts/orders-end-to-end-revision-20261021/semantics-development-01/build/tools')
    command(['javac',*java8_target()[1],'-cp',compile_cp,'-d',str(classes),str(HERE/'RequestAsyncFixture.java')],out/'compile.log')
    jar=out/'fixture.jar'
    with ZipFile(jar,'w') as z:
        for f in classes.glob('*.class'):z.write(f,'BOOT-INF/classes/'+f.name)
    b=out/'build';build(b,{'fixture':{'jar':str(jar),'entry':'RequestAsyncFixture.root(LRequestAsyncFixture$Worker;Ljava/net/URI;Ljava/net/URI;Lorg/springframework/core/ParameterizedTypeReference;I)LRequestAsyncFixture$Out;','targets':['RequestAsyncFixture$Out.text'],'response_path':'/text','execution_kernel':True,'application_calls':True,'async_dependencies':True}})
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            data=b'{"id":"WIRE-ID"}' if self.path.endswith('/missing') else b'{"id":"WIRE-ID","text":null}' if self.path.endswith('/null') else b'{"text":"SAME","text":"SAME","id":"WIRE-ID"}' if self.path.endswith('/duplicate') else b'{"id":"WIRE-ID","text":"SAME"}';self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start();reports={}
    try:
        for mode in ('full','selective'):
            cap=out/mode;(cap/'fixture').mkdir(parents=True)
            command(['java','-javaagent:'+str(b/'distributed-observer.jar'),'-Dservice.plan='+str(b/'fixture/plan.json'),'-Dservice.mode='+mode,'-Dservice.events='+str(cap/'fixture/events.jsonl'),'-cp',str(classes)+':'+cp,'RequestAsyncFixture','http://127.0.0.1:'+str(server.server_port)+'/item'],cap/'stdout.log')
            g=Reconstruction(b,cap,['fixture']);cases=json.loads((cap/'stdout.log').read_text().splitlines()[-1]);checks=[]
            for c in cases:
                a=g.query(c['message'],'/text','fixture',boundary=old.BOUNDARY);reads=[r for r in g.rows['fixture'] if r['kind']=='http-json' and r.get('phase')=='read' and r.get('parent_message')==c['message']]
                assert len(reads)==2
                # Root bytecode returns the second explicit URI's response;
                # both servers emit identical values. Select actual raw URI,
                # without the TF task validator or graph determining truth.
                expected_known=c['mode'] in (0,1,2,4,6,9,10);assert a['known']==expected_known,(mode,c,a)
                truth=set()
                if expected_known and c['mode'] not in (2,6,9):
                    suffix='/first' if c['mode']==1 else '/null' if c['mode']==10 else '/second';read=next(r for r in reads if r['uri'].endswith(suffix));f=next(f for f in read['fields'] if f['path']=='/text');truth={old.source_coord('fixture',read,f)}
                if expected_known:assert {old.predicted_coord(s) for s in a['sources']}==truth,(mode,c,a,truth)
                assert all(f['path']!='/id' for r in reads for f in r['fields']),'Ignored wire id became a decoded source'
                checks.append({'case':c,'answer':a,'truth':sorted(truth,key=str) if expected_known else None})
            faults={};rows=g.rows['fixture'];plan=g.plans['fixture']
            for label in ('missing-request-proof','request-library-hash','same-value-wrong-wrapper','missing-decoder-proof','missing-fresh-allocation','wrong-decoder-content','wrong-RPC-message','missing-render-callback','wrong-source-role','missing-default-role','duplicate-promoted'):
                changed=copy.deepcopy(rows)
                if label=='missing-request-proof':del next(r for r in changed if r.get('request_entity_contract',{}).get('kind')=='request-builder')['request_entity_contract']
                elif label=='request-library-hash':next(r for r in changed if r.get('request_entity_contract'))['request_entity_contract']['class_sha256']['org/springframework/http/RequestEntity']='wrong'
                elif label=='same-value-wrong-wrapper':next(r for r in changed if r.get('request_entity_contract',{}).get('kind')=='request-exchange')['request_entity_contract']['response_body']['object']='different-wrapper'
                elif label=='missing-decoder-proof':del next(r for r in changed if r.get('resource_decoder'))['resource_decoder']
                elif label=='missing-fresh-allocation':changed.remove(next(r for r in changed if r['kind']=='execution-decoder-birth'))
                elif label=='wrong-decoder-content':next(r for r in changed if r.get('resource_decoder'))['resource_decoder']['content']['object']='wrong-content'
                elif label=='wrong-RPC-message':next(r for r in changed if r.get('resource_decoder'))['parent_message']='wrong-parent'
                elif label=='missing-render-callback':changed.remove(next(r for r in changed if r['kind']=='enter' and '$Item.toString' in r['method']))
                elif label=='wrong-source-role':next(r for r in changed if r.get('resource_decoder',{}).get('source_properties'))['resource_decoder']['source_properties']=[]
                elif label=='missing-default-role':next(r for r in changed if r.get('resource_decoder') and '/missing' in r.get('uri',''))['resource_decoder']['default_properties']=[]
                else:next(r for r in changed if r.get('resource_decoder') and '/duplicate' in r.get('uri',''))['resource_decoder']['valid']=True
                try:infer_execution(plan,changed)
                except ValueError:faults[label]=True
                else:raise AssertionError('Accepted '+label)
            reports[mode]={'targets':len(checks),'known_exact':sum(x['answer']['known'] for x in checks),'expected_unknown':sum(not x['answer']['known'] for x in checks),'faults':faults,'checks':checks};save(out/'results.json',{'all_passed':True,'modes':reports});print(mode,len(checks),flush=True)
    finally:server.shutdown();server.server_close()
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--libs',type=Path,required=True);a=p.parse_args();run(a.out.resolve(),a.libs.resolve())
