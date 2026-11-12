"""Raw source facts and literal program expectations precede replay predictions."""
import argparse,json,copy
from pathlib import Path
from zipfile import ZipFile
from run_planned_service import ROOT,HERE,save,load,sha
from run_query_planner import command,JARS
from run_generic_observation_rules import metadata_build,AGENT
from tf_static_baseline import configure
from plan_capability_policy import choose
from raw_source_call_facts import RawSourceCallFacts
from audit_zlt_foundation_revision import tf_pair
from run_public_control_semantics import checked
from analysis_status import AnalysisLimit

H=ROOT/'artifacts/exception-completion-semantics-20261112'

def score(plan,rows,truth):
    result=checked(plan,rows);checks=[];normalized=[]
    for t in truth:
        ret=next(r for r in rows if r['kind']=='binding-return'and r['message']==t['message'])
        a=next(a for a in result['answers']if a['root_frame']==ret['frame']and a['path']=='/value')
        physical=[f for f in ret['fields']if f['path']=='/value'];assert len(physical)==1
        physical=physical[0];assert physical['field']=='ExceptionCompletionFixture$Out.value'and physical['version']==1
        roles={tuple(x['token']):x['role']for x in t['raw']}
        ok=(a['known']and all(a[k]==physical[k]for k in ('owner','field','version')) and set(map(tuple,a['origins']))==set(map(tuple,t['origins']))and set(map(tuple,a['selectors']))==set(map(tuple,t['selectors'])))if t['expect_known']else not a['known']
        checks.append({'scenario':t['scenario'],'input':t['input'],'complete_correct':ok,'answer':a})
        normalized.append({'scenario':t['scenario'],'input':t['input'],'known':a['known'],'version':a['version'],'origins':sorted(roles.get(tuple(x),'UNEXPECTED:'+str(x))for x in a['origins']),'selectors':sorted(roles.get(tuple(x),'UNEXPECTED:'+str(x))for x in a['selectors'])})
    return result,checks,normalized

def run(out,case=None,supported=False):
    limited=False
    out.mkdir(parents=True,exist_ok=False)
    spec=HERE/'EXCEPTION-COMPLETION-SPEC-20261112.md'
    save(out/'protocol-before-jvm.json',{'source_sha256':sha(HERE/'ExceptionCompletionFixture.java'),'spec_sha256':sha(spec),'Agent_sha256':sha(AGENT),'literal_expectation':'15 predefined completion shapes x two inputs; source keys10/11 data,20/21/30 guards. Unrelated payloads never become selectors. Actual null is a source field. No original native model changes.'})
    java=str(ROOT/'artifacts/galette-static-baselines-20261111/runtime-base/java-8-openjdk-amd64/bin/java')
    classes=out/'classes';classes.mkdir()
    deps=sorted((ROOT/'artifacts/ruoyi-request-scope-20261104/scope-controls-02/deps').glob('*.jar'))
    cp=':'.join(map(str,[classes,AGENT,*JARS,*deps]))
    command([java[:-4]+'javac','-cp',cp,'-d',str(classes),str(HERE/'ExceptionCompletionFixture.java')],out/'compile.log')
    jar=out/'fixture.jar'
    with ZipFile(jar,'w')as z:
        for f in classes.glob('*.class'):z.write(f,'BOOT-INF/classes/'+f.name)
    metadata_build(out/'build',{'fixture':{'jar':str(jar),'targets':['ExceptionCompletionFixture$Out.value']}})
    entry='ExceptionCompletionFixture.root(LExceptionCompletionFixture$Store;IILjava/lang/IllegalArgumentException;)LExceptionCompletionFixture$Out;'
    plan,route=choose(load(out/'build/fixture/model.json'),{'entry':entry,'target':'ExceptionCompletionFixture$Out.value','path':'/value','source_calls':['ExceptionCompletionFixture$Store.read(II)LExceptionCompletionFixture$Datum;']},deployment=load(ROOT/'artifacts/target-closure-revision-20261103/external-first-01/deployment-environment.json'))
    save(out/'plan.json',plan);plan=load(out/'plan.json');save(out/'route.json',route)
    args=['supported']if supported else[]if case is None else[str(case)]
    baseline=json.loads(command([java,'-cp',cp,'ExceptionCompletionFixture',*args],out/'original.log').stdout.splitlines()[-1])
    reports={};norm={}
    for mode in ('full','static','selective'):
        d=out/mode;d.mkdir();policy=configure(plan,mode);save(d/'policy.json',policy)
        cmd=[java,'-javaagent:'+str(AGENT),'-Dfixture.observe=true','-Dservice.plan='+str(out/'plan.json'),'-Dservice.events='+str(d/'events.jsonl'),*policy['jvm_options'],'-cp',cp,'ExceptionCompletionFixture',*args]
        save(d/'command.json',cmd)
        cases=json.loads(command(cmd,d/'stdout.log').stdout.splitlines()[-1])
        assert [{k:v for k,v in c.items()if k!='message'}for c in cases]==[{k:v for k,v in c.items()if k!='message'}for c in baseline]
        rows=[json.loads(l)for l in(d/'events.jsonl').read_text().splitlines()];facts=RawSourceCallFacts(rows);truth=[]
        for c in cases:
            raw=[];tokens={}
            for source in (r for r in rows if r['kind']=='binding-source'and r['message']==c['message']):
                tf_pair(facts.matching(rows,source),source)
                start=next(r for r in rows if r['kind']=='collection-call-enter'and r.get('call_id')==source['source_call_id'])
                key=start['args'][0]['value']
                for i,f in enumerate(source['fields']):
                    role=(key,f['field'].rsplit('.',1)[-1]);assert role not in tokens
                    tokens[role]=('field',source['seq'],i);raw.append({'role':str(key)+'.'+role[1],'token':tokens[role],'call':start,**f})
            assert {x[0]for x in tokens}=={10,11,20}|({30}if c['scenario']==4 else{21}if c['scenario']==9 else set())
            s,n=c['scenario'],c['input']
            if s==11:wanted=set();selection=set()
            elif s==13:wanted={(10,'value')};selection=set()
            elif s==4:wanted={(11,'value')};selection={(30,'nullable')}
            elif s==9:wanted={(10 if n else 11,'value')};selection={(20,'value')}|({(21,'value')}if n else set())
            elif s in(0,3,5,12):wanted={(11,'value')};selection={(20,'value')}
            elif s==6:wanted={(11 if n else 10,'value')};selection={(20,'value')}
            else:wanted={(11 if n else 10,'value')};selection={(20,'value')}
            assert c['value']==(9 if s==11 else 7)
            target=next(r for r in rows if r['kind']=='binding-return'and r['message']==c['message'])
            truth.append({'scenario':s,'input':n,'message':c['message'],'origins':[tokens[x]for x in wanted],'selectors':[tokens[x]for x in selection],'raw':raw,'raw_target':target['fields'],'expect_known':True})
        save(d/'truth-before-prediction.json',truth)
        try:
            result,checks,normalized=score(plan,rows,truth)
            save(d/'prediction.json',result);save(d/'checks.json',checks);save(d/'normalized.json',normalized);norm[mode]=normalized
            reports[mode]={'business_preserved':True,'targets':len(checks),'matched_expectation':sum(c['complete_correct']for c in checks),'known':sum(c['answer']['known']for c in checks),'required_unknown':sum(not c['answer']['known']for c in checks),'gate':not limited and all(c['complete_correct']for c in checks)}
        except (ValueError,KeyError,AssertionError)as e:
            save(d/'replay-failure.json',{'type':type(e).__name__,'error':str(e)})
            reports[mode]={'business_preserved':True,'targets':len(truth),'error':str(e),'gate':limited and isinstance(e,AnalysisLimit)}
    equal=None if limited else len(norm)==3 and norm['full']==norm['static']==norm['selective']
    save(out/'results.json',{'modes':reports,'normalized_equal':equal,'gate':(limited or equal) and all(r['gate']for r in reports.values()),'new_JVM_controls':True,'new_Agent':False,'performance':None})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--case',type=int,choices=range(15));p.add_argument('--supported-sequence',action='store_true');a=p.parse_args();run(a.out.resolve(),a.case,a.supported_sequence)
