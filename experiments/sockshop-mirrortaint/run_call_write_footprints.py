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

H=ROOT/'artifacts/call-write-footprints-20261112'

def score(plan,rows,truth):
    result=checked(plan,rows);checks=[];normalized=[]
    for t in truth:
        ret=next(r for r in rows if r['kind']=='binding-return'and r['message']==t['message'])
        a=next(a for a in result['answers']if a['root_frame']==ret['frame']and a['path']=='/value')
        roles={tuple(x['token']):x['role']for x in t['raw']}
        ok=a['known']and a['version']==1 and set(map(tuple,a['origins']))==set(map(tuple,t['origins']))and set(map(tuple,a['selectors']))==set(map(tuple,t['selectors']))
        checks.append({'scenario':t['scenario'],'input':t['input'],'complete_correct':ok,'answer':a})
        normalized.append({'scenario':t['scenario'],'input':t['input'],'known':a['known'],'version':a['version'],'origins':sorted(roles.get(tuple(x),'UNEXPECTED:'+str(x))for x in a['origins']),'selectors':sorted(roles.get(tuple(x),'UNEXPECTED:'+str(x))for x in a['selectors'])})
    return result,checks,normalized

def run(out,limited=False):
    out.mkdir(parents=True,exist_ok=False)
    spec=HERE/'CALL-WRITE-FOOTPRINT-SPEC-20261112.md'
    save(out/'protocol-before-jvm.json',{'source_sha256':sha(HERE/'CallWriteFootprintFixture.java'),'spec_sha256':sha(spec),'Agent_sha256':sha(AGENT),'literal_expectation':'s<8: chosen 10/11 and selector20; s8,9: source11 no selector; s10: constant9 no sources; version1. Path-rewrite control: AnalysisLimit.'})
    java=str(ROOT/'artifacts/galette-static-baselines-20261111/runtime-base/java-8-openjdk-amd64/bin/java')
    classes=out/'classes';classes.mkdir()
    deps=sorted((ROOT/'artifacts/ruoyi-request-scope-20261104/scope-controls-02/deps').glob('*.jar'))
    cp=':'.join(map(str,[classes,AGENT,*JARS,*deps]))
    command([java[:-4]+'javac','-cp',cp,'-d',str(classes),str(HERE/'CallWriteFootprintFixture.java')],out/'compile.log')
    jar=out/'fixture.jar'
    with ZipFile(jar,'w')as z:
        for f in classes.glob('*.class'):z.write(f,'BOOT-INF/classes/'+f.name)
    metadata_build(out/'build',{'fixture':{'jar':str(jar),'targets':['CallWriteFootprintFixture$Out.value']}})
    entry='CallWriteFootprintFixture.unclosed(LCallWriteFootprintFixture$Store;I)LCallWriteFootprintFixture$Out;'if limited else'CallWriteFootprintFixture.root(LCallWriteFootprintFixture$Store;LCallWriteFootprintFixture$Worker;II)LCallWriteFootprintFixture$Out;'
    plan,route=choose(load(out/'build/fixture/model.json'),{'entry':entry,'target':'CallWriteFootprintFixture$Out.value','path':'/value','source_calls':['CallWriteFootprintFixture$Store.read(II)LCallWriteFootprintFixture$Datum;']},deployment=load(ROOT/'artifacts/target-closure-revision-20261103/external-first-01/deployment-environment.json'))
    save(out/'plan.json',plan);plan=load(out/'plan.json');save(out/'route.json',route)
    args=['limited']if limited else[]
    baseline=json.loads(command([java,'-cp',cp,'CallWriteFootprintFixture',*args],out/'original.log').stdout.splitlines()[-1])
    reports={};norm={}
    for mode in ('full','static','selective'):
        d=out/mode;d.mkdir();policy=configure(plan,mode);save(d/'policy.json',policy)
        cmd=[java,'-javaagent:'+str(AGENT),'-Dfixture.observe=true','-Dservice.plan='+str(out/'plan.json'),'-Dservice.events='+str(d/'events.jsonl'),*policy['jvm_options'],'-cp',cp,'CallWriteFootprintFixture',*args]
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
                    assert f['field']=='CallWriteFootprintFixture$Datum.value'and key not in tokens
                    tokens[key]=('field',source['seq'],i);raw.append({'role':str(key),'token':tokens[key],'call':start,**f})
            assert set(tokens)=={10,11,20}
            s,n=c['scenario'],c['input'];wanted=set()if s==10 else{11 if s in(8,9)or n else 10};selection={20}if s<8 else set()
            if limited and n:wanted=set()  # replace() then writes literal 7
            assert c['value']==(9 if s==10 else 7)
            truth.append({'scenario':s,'input':n,'message':c['message'],'origins':[tokens[x]for x in wanted],'selectors':[tokens[x]for x in selection],'raw':raw})
        save(d/'truth-before-prediction.json',truth)
        try:
            result,checks,normalized=score(plan,rows,truth)
            save(d/'prediction.json',result);save(d/'checks.json',checks);save(d/'normalized.json',normalized);norm[mode]=normalized
            reports[mode]={'business_preserved':True,'targets':len(checks),'correct':sum(c['complete_correct']for c in checks),'gate':not limited and all(c['complete_correct']for c in checks)}
        except (ValueError,KeyError,AssertionError)as e:
            save(d/'replay-failure.json',{'type':type(e).__name__,'error':str(e)})
            reports[mode]={'business_preserved':True,'targets':len(truth),'error':str(e),'gate':limited and isinstance(e,AnalysisLimit)}
    equal=None if limited else len(norm)==3 and norm['full']==norm['static']==norm['selective']
    save(out/'results.json',{'modes':reports,'normalized_equal':equal,'gate':(limited or equal) and all(r['gate']for r in reports.values()),'new_JVM_controls':True,'new_Agent':False,'performance':None})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--limited',action='store_true');a=p.parse_args();run(a.out.resolve(),a.limited)
