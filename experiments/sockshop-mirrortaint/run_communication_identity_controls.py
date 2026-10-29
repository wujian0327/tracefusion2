#!/usr/bin/env python3
"""Real HTTP/Feign identity controls; values never define the expected identity."""
import argparse,copy,json,sys
from pathlib import Path
from zipfile import ZipFile
from build_distributed_plans import build
from run_query_planner import command,JARS
from run_planned_service import HERE,ROOT,load,save,sha
from plan_capability_policy import choose
from contract_applicability import library_inventory
from transport_context import validate_protocol
from infer_execution_kernel import infer_execution

def output(path):
    # Shutdown problem diagnostics may follow the business JSON on stdout.
    rows=[]
    for line in path.read_text().splitlines():
        try:value=json.loads(line)
        except ValueError:continue
        if isinstance(value,dict)and'cases'in value:rows.append(value)
    assert len(rows)==1,'Business result missing/duplicated'
    return rows[0]

def run(out,agent,client='default',network_failure=False):
    out.mkdir(parents=True,exist_ok=False);classes=out/'classes';classes.mkdir();deps=out/'deps';deps.mkdir()
    business=ROOT/'artifacts/external-frozen-transfer-20261029/78a9534/business-jars/mall-admin.jar'
    with ZipFile(business)as z:
        for n in z.namelist():
            if n.startswith('BOOT-INF/lib/')and n.endswith('.jar'):(deps/Path(n).name).write_bytes(z.read(n))
    with ZipFile(business.with_name('mall-portal.jar'))as z:
        for n in z.namelist():
            if n.startswith('BOOT-INF/lib/spring-retry-')and n.endswith('.jar'):(deps/Path(n).name).write_bytes(z.read(n))
    cp=':'.join(map(str,[agent,*deps.glob('*.jar')]));java='/usr/lib/jvm/java-8-openjdk-amd64/bin/java';javac='/usr/lib/jvm/java-8-openjdk-amd64/bin/javac'
    command([javac,'-cp',cp,'-d',str(classes),str(HERE/'CommunicationIdentityFixture.java')],out/'compile.log')
    fixture=out/'fixture.jar'
    with ZipFile(fixture,'w')as z:
        for f in classes.glob('*.class'):z.write(f,'BOOT-INF/classes/'+f.name)
    b=out/'build';build(b,{'fixture':{'jar':str(fixture),'targets':['CommunicationIdentityFixture$Box.text']}})
    model=load(b/'fixture/model.json');model['library_inventory']=library_inventory(business)
    query={'entry':'CommunicationIdentityFixture.root(Ljava/lang/String;)LCommunicationIdentityFixture$Box;','target':'CommunicationIdentityFixture$Box.text','path':'/text','source_calls':['CommunicationIdentityFixture$Remote.get(Ljava/lang/String;)LCommunicationIdentityFixture$Box;']}
    environment=load(ROOT/'artifacts/plan-applicability-revision-20261029/deployment-environment.json')
    plan,route=choose(model,query,deployment=environment);assert plan['communication_identity']['version']==2
    save(b/'fixture/plan.json',plan);save(out/'route.json',route);classpath=str(classes)+':'+cp
    options=['-Dfixture.okhttp='+str(client!='default').lower(),'-Dfixture.retryable.lb='+str(client=='retryable-lb-okhttp').lower(),'-Dfixture.network.failure='+str(network_failure).lower()]
    command([java,*options,'-cp',classpath,'CommunicationIdentityFixture'],out/'baseline.txt');baseline=output(out/'baseline.txt')
    assert all(r.get('same_cause')is True for r in baseline['cases']if r['status']=='business-exception')
    reports={}
    for mode in ('full','selective'):
        cap=out/mode;cap.mkdir();command([java,*options,'-javaagent:'+str(agent),'-Dfixture.observe=true','-Dservice.plan='+str(b/'fixture/plan.json'),'-Dservice.events='+str(cap/'events.jsonl'),'-Dservice.mode='+mode,'-cp',classpath,'CommunicationIdentityFixture'],cap/'stdout.txt')
        actual=output(cap/'stdout.txt');expected=[{k:v for k,v in r.items()if k not in('clean_frames','clean_calls','clean_rpc')}for r in actual['cases']]
        assert expected==baseline['cases'],(mode,expected,baseline['cases'])
        assert all(r['clean_frames']and r['clean_calls']and r['clean_rpc']for r in actual['cases'])
        rows=[json.loads(s)for s in (cap/'events.jsonl').read_text().splitlines()];assert not any(r['kind']=='problem'for r in rows),[r for r in rows if r['kind']=='problem']
        validate_protocol(rows,2,plan['communication_identity'])
        entered=[r for r in rows if r['kind']=='http-rpc-enter'];sent=[r for r in rows if r['kind']=='http-client-send'];received=[r for r in rows if r['kind']=='http-client-receive']
        assert len({r['message']for r in entered})==len(entered)
        assert {r['wire_traceparent']for r in sent}=={r['traceparent']for r in actual['wire']}
        assert any(r['kind']=='http-rpc-abort'for r in rows)
        root_messages={r['message']for r in actual['cases']};assert any(r['parent_message']not in root_messages for r in entered),'Nested call not distinguished'
        replay=infer_execution(plan,rows);known=[a for a in replay['answers']if a['known']];assert len(known)==4
        for case in actual['cases']:
            if case['status']!='normal':continue
            returned=next(r for r in rows if r['kind']=='binding-return'and r['message']==case['message'])
            root=next(r for r in rows if r['kind']=='enter'and r['method']==query['entry']and r['frame']==returned['frame'])
            calls=[r for r in rows if r['kind']=='collection-call-enter'and r['frame']==root['frame']and r['callee']==query['source_calls'][0]and r['args'][0].get('value')==case['key']];assert len(calls)==1
            source=[r for r in rows if r['kind']=='binding-source'and r.get('source_call_id')==calls[0]['call_id']];assert len(source)==1
            field=[i for i,f in enumerate(source[0]['fields'])if f['field']=='CommunicationIdentityFixture$Box.text'];assert len(field)==1
            answer=next(a for a in known if a['root_frame']==root['frame']);assert set(map(tuple,answer['origins']))=={('field',source[0]['seq'],field[0])},'Same-valued earlier/nested source substituted for returned call'
        faults={}
        for label in ('wrong-response','duplicate-new-sequence','missing-completion','wrong-parent','reuse-attempt','legacy-missing-coordinates','missing-carrier-link'):
            changed=copy.deepcopy(rows)
            if label=='wrong-response':next(r for r in changed if r['kind']=='http-json'and r.get('direction')=='response')['response_object']='foreign-response'
            elif label=='duplicate-new-sequence':
                row=next(r for r in changed if r['kind']=='http-json');duplicate=copy.deepcopy(row);duplicate['seq']=len(changed)+1;changed.insert(changed.index(row)+1,duplicate)
            elif label=='missing-completion':changed.remove(next(r for r in changed if r['kind']=='http-rpc-exit'))
            elif label=='wrong-parent':next(r for r in changed if r['kind']=='http-client-receive')['parent_message']='foreign-parent'
            elif label=='reuse-attempt':
                starts=[r for r in changed if r['kind']=='http-rpc-enter'];starts[1]['rpc_call_id']=starts[0]['rpc_call_id']
            elif label=='legacy-missing-coordinates':next(r for r in changed if r['kind']=='http-json').pop('communication_version')
            else:next(r for r in changed if r['kind']=='http-json')['carrier_chain']=[]
            try:validate_protocol(changed,2,plan['communication_identity'])
            except ValueError:faults[label]=True
            else:raise AssertionError('Bad communication evidence accepted: '+label)
        negative=out/(mode+'-wrong-response');negative.mkdir();command([java,*options,'-javaagent:'+str(agent),'-Dfixture.observe=true','-Dfixture.wrong.response=true','-Dservice.plan='+str(b/'fixture/plan.json'),'-Dservice.events='+str(negative/'events.jsonl'),'-Dservice.mode='+mode,'-cp',classpath,'CommunicationIdentityFixture'],negative/'stdout.txt')
        bad=[json.loads(s)for s in(negative/'events.jsonl').read_text().splitlines()];bad_result=output(negative/'stdout.txt');assert [r['value']for r in bad_result['cases']]==['SAME']*3
        assert all(r['clean_frames']and r['clean_calls']and r['clean_rpc']for r in bad_result['cases']);assert any(r['kind']=='problem'for r in bad)and bad[-1]['capture_invalid']
        reports[mode]={'root_requests':len(actual['cases']),'actual_attempts':len(entered),'actual_client_sends':len(sent),'actual_responses':len(received),'business_equal':True,'state_clean':True,'negative_business_preserved_capture_invalid':True,'known_execution_targets':len(known),'faults':faults}
    save(out/'results.json',{'all_passed':True,'modes':reports,'agent_sha256':sha(agent),'scope':'Protocol and execution controls, not new application coverage or performance.'});print(reports,flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--agent',type=Path,required=True);p.add_argument('--client',choices=('default','okhttp','retryable-lb-okhttp'),default='default');p.add_argument('--network-failure',action='store_true');a=p.parse_args();run(a.out.resolve(),a.agent.resolve(),a.client,a.network_failure)
