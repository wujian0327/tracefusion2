"""Independent literal program expectations; raw facts before replay predictions."""
import argparse
import copy
import json
from pathlib import Path
from zipfile import ZipFile
from run_planned_service import ROOT,HERE,save,load,sha
from run_query_planner import command,JARS
from run_generic_observation_rules import metadata_build,AGENT
from plan_capability_policy import choose
from tf_static_baseline import configure
from infer_execution_kernel import infer_execution
from raw_source_call_facts import RawSourceCallFacts
from audit_zlt_foundation_revision import tf_pair

H=ROOT/'artifacts/public-control-semantics-20261112'


def expected(s,n):
    a,b,g,h=(10,'value'),(11,'value'),(20,'value'),(21,'value')
    if s in (0,1):return set(),{g},int(n>0)
    if s in (2,10,11):return {a if n>0 else b},{g},7
    if s in (3,4):return {a if n>0 else b},{g}|({h}if n>0 else set()),7
    if s==5:return {a},{g}|({h}if n==0 else set()),7
    if s==6:return {a}|({b}if n else set()),{g},7+7*n
    if s in (7,8,19):return {b if n>0 else a},{g},7
    if s==9:return set()if n>0 else{a},{g},7
    if s in (12,21):return {a},set(),7
    if s in (13,15):return set(),set(),9
    if s in (14,16,17):return {b if n>0 else a},{g},7
    if s==18:return {a},{g},7
    if s==20:return {a},{(20,'nullable')},7
    raise AssertionError(s)


def checked(plan,rows):
    # Same outer integrity conditions as Reconstruction, including sticky failure.
    assert rows[0]['kind']=='start' and [r['seq']for r in rows]==list(range(1,len(rows)+1))
    assert sum(r['kind']=='metrics'for r in rows)==1
    assert not any(r['kind']=='problem'or r['kind']=='metrics'and r.get('capture_invalid')for r in rows)
    return infer_execution(plan,rows)


def run(out,exceptions=False,implicit=False,interfaces=False,agent=AGENT):
    out.mkdir(parents=True,exist_ok=False)
    original=load(H/'protocol-before-implementation.json')
    if agent==AGENT:assert sha(agent)==original['Agent_sha256']
    save(out/'candidate.json',{'core_sources':{p:sha(Path(p))for p in [*original['core_sources'],str(HERE/'control_dependencies.py')]},'Agent_sha256':sha(agent),'fixture_sha256':sha(HERE/'PublicControlFixture.java')})
    java=str(ROOT/'artifacts/galette-static-baselines-20261111/runtime-base/java-8-openjdk-amd64/bin/java')
    classes=out/'classes';classes.mkdir()
    deps=sorted((ROOT/'artifacts/ruoyi-request-scope-20261104/scope-controls-02/deps').glob('*.jar'))
    cp=':'.join(map(str,[classes,agent,*JARS,*deps]))
    command([java[:-4]+'javac','-cp',cp,'-d',str(classes),str(HERE/'PublicControlFixture.java')],out/'compile.log')
    jar=out/'fixture.jar'
    with ZipFile(jar,'w')as z:
        for f in classes.glob('*.class'):z.write(f,'BOOT-INF/classes/'+f.name)
    metadata_build(out/'build',{'fixture':{'jar':str(jar),'targets':['PublicControlFixture$Out.value']}})
    entry='PublicControlFixture.rootInterface(LPublicControlFixture$Store;LPublicControlFixture$Assignment;I)LPublicControlFixture$Out;'if interfaces else'PublicControlFixture.rootImplicit(LPublicControlFixture$Store;II)LPublicControlFixture$Out;'if implicit else'PublicControlFixture.rootException(LPublicControlFixture$Store;IILjava/lang/IllegalArgumentException;)LPublicControlFixture$Out;'if exceptions else'PublicControlFixture.root(LPublicControlFixture$Store;II)LPublicControlFixture$Out;'
    plan,route=choose(load(out/'build/fixture/model.json'),{'entry':entry,'target':'PublicControlFixture$Out.value','path':'/value','source_calls':['PublicControlFixture$Store.read(II)LPublicControlFixture$Datum;']},deployment=load(ROOT/'artifacts/target-closure-revision-20261103/external-first-01/deployment-environment.json'))
    save(out/'plan.json',plan);plan=load(out/'plan.json');save(out/'route.json',route)
    mainargs=['interface-controls']if interfaces else['implicit-controls']if implicit else['exception-controls']if exceptions else[]
    baseline=json.loads(command([java,'-cp',cp,'PublicControlFixture',*mainargs],out/'original.log').stdout.splitlines()[-1])
    reports={};normalized={}
    for mode in ('full','static','selective'):
        d=out/mode;d.mkdir();policy=configure(plan,mode);save(d/'policy.json',policy)
        cmd=[java,'-javaagent:'+str(agent),'-Dfixture.observe=true','-Dservice.plan='+str(out/'plan.json'),'-Dservice.events='+str(d/'events.jsonl'),*policy['jvm_options'],'-cp',cp,'PublicControlFixture',*mainargs]
        save(d/'command.json',cmd)
        cases=json.loads(command(cmd,d/'stdout.log').stdout.splitlines()[-1])
        assert [{k:v for k,v in c.items()if k!='message'}for c in cases]==[{k:v for k,v in c.items()if k!='message'}for c in baseline]
        rows=[json.loads(l)for l in(d/'events.jsonl').read_text().splitlines()]
        assert not (d/'events.jsonl.invalid').exists()
        facts=RawSourceCallFacts(rows);truth=[]
        for c in cases:
            sources=[r for r in rows if r['kind']=='binding-source'and r['message']==c['message']]
            fields={};raw=[]
            for source in sources:
                tf_pair(facts.matching(rows,source),source)
                start=next(r for r in rows if r['kind']=='collection-call-enter'and r.get('call_id')==source['source_call_id'])
                key=start['args'][0]['value']
                for i,f in enumerate(source['fields']):
                    role=(key,f['field'].rsplit('.',1)[-1]);assert role not in fields
                    fields[role]=('field',source['seq'],i);raw.append({'role':list(role),**f})
            if implicit:
                s,n=c['scenario'],c['input'];origins=set()if s==1 else{(11 if s==3 or n==0 else 10,'value')};selectors=set()if s in(1,3)else{(30,'nullable')};value=9 if s==1 else 7
            else:origins,selectors,value=expected(7,c['input'])if interfaces else expected(15 if c['scenario']==2 else 14,c['input'])if exceptions else expected(c['scenario'],c['input'])
            assert c['value']==value and origins|selectors<=fields.keys()
            expected_keys={10,11,30}if implicit else{10,11,20}|({21}if not(exceptions or interfaces)and((c['scenario']in(3,4)and c['input']>0)or(c['scenario']==5 and c['input']==0))else set())
            assert {r['role'][0]for r in raw}==expected_keys
            truth.append({'scenario':c['scenario'],'input':c['input'],'message':c['message'],'origins':[fields[x]for x in sorted(origins)],'selectors':[fields[x]for x in sorted(selectors)],'raw_fields':raw,'expected_value':value,'expected_target_version':2 if not(exceptions or implicit)and c['scenario']==9 and c['input']>0 else 1})
        save(d/'truth-before-prediction.json',truth)
        try:prediction=checked(plan,rows)
        except Exception as e:
            save(d/'replay-failure.json',{'type':type(e).__name__,'error':str(e)});reports[mode]={'replay_failed':str(e),'gate':False};continue
        checks=[];norm=[]
        for t in truth:
            ret=next(r for r in rows if r['kind']=='binding-return'and r['message']==t['message']);answers=[a for a in prediction['answers']if a['root_frame']==ret['frame']and a['path']=='/value'];assert len(answers)==1;a=answers[0]
            roles={}
            for source in [r for r in rows if r['kind']=='binding-source'and r['message']==t['message']]:
                start=next(r for r in rows if r['kind']=='collection-call-enter'and r.get('call_id')==source['source_call_id']);key=start['args'][0]['value']
                for i,f in enumerate(source['fields']):roles[('field',source['seq'],i)]=str(key)+'.'+f['field'].rsplit('.',1)[-1]
            ok={'known':a['known'],'data':set(map(tuple,a['origins']))==set(map(tuple,t['origins'])),'selection':set(map(tuple,a['selectors']))==set(map(tuple,t['selectors'])),'version':a['version']==t['expected_target_version']}
            checks.append({'scenario':t['scenario'],'input':t['input'],'ok':ok,'answer':a})
            norm.append({'scenario':t['scenario'],'input':t['input'],'known':a['known'],'version':a['version'],'origins':sorted(roles.get(tuple(x),'unexpected:'+str(x))for x in a['origins']),'selectors':sorted(roles.get(tuple(x),'unexpected:'+str(x))for x in a['selectors'])})
        save(d/'prediction.json',prediction);save(d/'checks.json',checks);save(d/'normalized.json',norm);normalized[mode]=norm
        guards=[]
        target=next(t for t in truth if t['scenario']==(0 if exceptions or implicit or interfaces else 2) and t['input']==1)
        for fault in ('missing-condition-source','ambiguous-condition-source','wrong-source-call','wrong-source-PC','wrong-source-version','wrong-physical-write-version','missing-branch','duplicate-branch','contradictory-branch','wrong-branch-frame','wrong-branch-PC','wrong-parent','sticky-invalid'):
            altered=copy.deepcopy(rows);src=next(r for r in altered if r['kind']=='binding-source'and r['seq']==target['selectors'][0][1]);idx=target['selectors'][0][2]
            field=src['fields'][idx]
            if implicit:branch=next(r for r in altered if r['kind']=='branch'and r.get('frame')==src['frame']and r['site'].startswith(entry+'@'))
            else:
                read=next(r for r in altered if r['kind']=='read'and r['owner']==field['owner']and r['field']==field['field']and r['seq']>src['seq'])
                branch=next(r for r in altered if r['kind']=='branch'and r.get('frame')==src['frame']and r['site'].startswith('PublicControlFixture.root')and r['seq']>read['seq'])
            if fault=='missing-condition-source':src['fields'].pop(idx)
            elif fault=='ambiguous-condition-source':src['fields'].append(copy.deepcopy(src['fields'][idx]))
            elif fault=='wrong-source-call':src['source_call_id']=-1
            elif fault=='wrong-source-PC':src['source_pc']+=1
            elif fault=='wrong-source-version':src['fields'][idx]['version']+=1
            elif fault=='wrong-physical-write-version':
                previous={}
                for w in altered:
                    if w['kind']!='write':continue
                    key=(w['owner'],w['field'])
                    if key in previous:w['version']=previous[key];break
                    previous[key]=w['version']
                else:next(r for r in altered if r['kind']=='write')['version']=0
            elif fault=='missing-branch':altered.remove(branch)
            elif fault=='duplicate-branch':altered.insert(altered.index(branch),copy.deepcopy(branch))
            elif fault=='contradictory-branch':branch['taken']=not branch['taken']
            elif fault=='wrong-branch-frame':branch['frame']='wrong'
            elif fault=='wrong-branch-PC':branch['site']=branch['site'].rsplit('@',1)[0]+'@9999'
            elif fault=='wrong-parent':next(r for r in altered if r['kind']=='enter'and r.get('parent'))['parent']='wrong'
            else:next(r for r in altered if r['kind']=='metrics')['capture_invalid']=True
            for i,r in enumerate(altered,1):r['seq']=i
            try:
                bad=checked(plan,altered);answer=next(a for a in bad['answers']if a['root_frame']==next(r['frame']for r in altered if r['kind']=='binding-return'and r['message']==target['message']))
                state='incorrect-known'if answer['known']else'unknown'
            except (ValueError,AssertionError,KeyError):state='rejected'
            guards.append({'fault':fault,'state':state})
        save(d/'guards.json',guards)
        if exceptions:
            for input_ in (0,1):
                t=next(t for t in truth if t['scenario']==3 and t['input']==input_)
                altered=copy.deepcopy(rows);token=t['selectors'][0]
                source=next(r for r in altered if r['kind']=='binding-source'and r['seq']==token[1]);source['fields'].pop(token[2])
                try:
                    bad=checked(plan,altered)
                    frame=next(r['frame']for r in altered if r['kind']=='binding-return'and r['message']==t['message'])
                    state='incorrect-known'if next(a for a in bad['answers']if a['root_frame']==frame)['known']else'unknown'
                except (ValueError,AssertionError,KeyError):state='rejected'
                guards.append({'fault':'missing-callee-condition-source-'+str(input_),'state':state})
            save(d/'guards.json',guards)
        reports[mode]={'business_preserved':True,'targets':len(checks),'correct':sum(all(c['ok'].values())for c in checks),'failed':[{'scenario':c['scenario'],'input':c['input'],'ok':c['ok']}for c in checks if not all(c['ok'].values())],'guards':guards,'gate':all(all(c['ok'].values())for c in checks)and all(g['state']!='incorrect-known'for g in guards)}
    equal=len(normalized)==3 and normalized['full']==normalized['static']==normalized['selective']
    save(out/'results.json',{'modes':reports,'normalized_equal':equal,'gate':equal and all(r['gate']for r in reports.values()),'Agent_unchanged':sha(agent)==original['Agent_sha256'],'performance':None})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--exception-controls',action='store_true');p.add_argument('--implicit-controls',action='store_true');p.add_argument('--interface-controls',action='store_true');p.add_argument('--agent',type=Path,default=AGENT);a=p.parse_args();run(a.out.resolve(),a.exception_controls,a.implicit_controls,a.interface_controls,a.agent.resolve())
