"""Independent Galette source/target adapter, no TF propagation or graph oracle."""
import argparse,json,os,subprocess
from pathlib import Path
from zipfile import ZipFile
from run_planned_service import ROOT,HERE,load,save,sha
from run_query_planner import JARS
from diagnose_galette_hosted_template import H,OLD


def build(out):
    out.mkdir(parents=True,exist_ok=False);classes=out/'classes';classes.mkdir()
    agent=OLD/'galette-original/galette-agent/target/galette-agent-1.0.0-SNAPSHOT.jar'
    java=OLD/'runtime-base/java-8-openjdk-amd64/bin/javac'
    cp=':'.join(map(str,[agent,*JARS]))
    cmd=[str(java),'-cp',cp,'-d',str(classes),str(HERE/'GaletteBoundaryAgent.java'),str(HERE/'GaletteBoundaryHooks.java')]
    save(out/'command.json',cmd)
    with(out/'compile.log').open('w')as f:r=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT)
    assert r.returncode==0
    jar=out/'boundary-adapter.jar'
    with ZipFile(jar,'w')as z:
        z.writestr('META-INF/MANIFEST.MF','Manifest-Version: 1.0\nPremain-Class: GaletteBoundaryAgent\n\n')
        for p in classes.rglob('*.class'):z.write(p,str(p.relative_to(classes)))
        # Use Galette's own relocated transformer ASM. A raw second ASM copy
        # preloaded before its agent has no JCL shadow methods.
    save(out/'receipt.json',{'adapter_sha256':sha(jar),'source_hashes':{n:sha(HERE/n)for n in ('GaletteBoundaryAgent.java','GaletteBoundaryHooks.java')},'official_Agent_sha256':sha(agent),'source_marker':'Tainter.setTag on each actual declared source leaf; no program dependency formulas','target_export':'Tainter.getTag only; does not inject expected tags','TF_imports':False})


def controlled(tier,out):
    import run_unrelated_work_scaling as old
    from run_galette_static_calibration import fixed_runtime,verify
    os.environ['TF_CALIBRATION_FIXED_RUNTIME']='1';verify();old.H=OLD;old.verify=verify
    config=load(OLD/'controlled-build-04'/tier/'mt-config.json');adapter=H/'boundary-build-06/boundary-adapter.jar'
    props=H/('boundary-'+tier+'-v3.properties')
    if not props.exists():props.write_text('entry='+config['entry']+'\nprefix='+config['prefix']+'\nsources='+'|'.join(config['source_calls'])+'\ntarget=/target\n')
    spec=old.controlled_spec;agent=OLD/'galette-original/galette-agent/target/galette-agent-1.0.0-SNAPSHOT.jar'
    def configured(dest,task,mode,diagnostic=False):
        cfg=fixed_runtime(spec(dest,task,'original',False));s=cfg['services']['app']
        s['volumes']=[v for v in s['volumes']if v.split(':')[1]!='/approved-jdk']+[
            str(H/'modified-jre8-02')+':/approved-jdk:ro',str(agent)+':/galette-agent.jar:ro',str(adapter)+':/boundary-adapter.jar:ro',str(props)+':/boundary.properties:ro']
        cmd=s['command'];cmd[cmd.index('-jar'):cmd.index('-jar')]=['-Xbootclasspath/a:/galette-agent.jar:/boundary-adapter.jar','-Dgalette.boundary.config=/boundary.properties','-Dgalette.boundary.events=/tf2/capture/galette.jsonl','-javaagent:/boundary-adapter.jar','-javaagent:/galette-agent.jar']
        save(dest/'tool-receipt.json',{'variant':'modified Galette runtime / original Galette propagation Agent','Agent_sha256':sha(agent),'adapter_sha256':sha(adapter),'runtime_rt_sha256':sha(H/'modified-jre8-02/lib/rt.jar'),'original_business_sha256':sha(OLD/'controlled-build-04'/tier/'business.jar'),'source_config':config,'provenance_scoring_separate':True})
        return cfg
    old.controlled_spec=configured
    result=old.controlled_trial(out,tier,'original',0,3,2)
    save(out/'business-result.json',result)
    if result.get('business_passed')!=6:return
    score(out,tier)


def score(out,tier):
    d=out/'independent-score';d.mkdir(exist_ok=False)
    cap=out/'capture/galette.jsonl';rows=[json.loads(l)for l in cap.read_text().splitlines()]
    assert not cap.with_name(cap.name+'.invalid').exists()
    assert [r['seq']for r in rows]==list(range(1,len(rows)+1))
    assert sum(r['kind']=='closed'for r in rows)==1 and not any(r['kind']=='problem'or r['kind']=='closed'and r['capture_invalid']for r in rows)
    cases=load(out/'measure.json')['requests'];truth=[]
    # Raw fields and actual paired calls are the oracle inputs. Tags are not read here.
    for c in cases:
        source=[r for r in rows if r['kind']=='source'and r['message']==c['message']];assert len(source)==1;s=source[0]
        starts=[r for r in rows if r['kind']=='source-call-enter'and r.get('source_call_id')==s['source_call_id']];ends=[r for r in rows if r['kind']=='source-call-exit'and r.get('source_call_id')==s['source_call_id']]
        assert len(starts)==len(ends)==1;a,b=starts[0],ends[0]
        assert a['seq']<s['seq']<b['seq']and all(a[k]==s[k]==b[k]for k in ('source_call_id','caller','pc','callee','caller_frame','thread','root','message'))
        fields=[f for f in s['fields']if f['path']=='/target'or tier=='related-high'and f['path'].startswith('/f')]
        assert len(fields)==(257 if tier=='related-high'else 1)
        assert len({(f['owner'],f['field'],f['version'])for f in fields})==len(fields)
        truth.append({'message':c['message'],'source_call_id':s['source_call_id'],'raw_fields':fields,'expected_labels':[f['label']for f in fields]})
    save(d/'truth-before-prediction.json',truth)
    results=[]
    for c,t in zip(cases,truth):
        targets=[r for r in rows if r['kind']=='target'and r['message']==c['message']];assert len(targets)==1
        target=[f for f in targets[0]['fields']if f['path']=='/target'];assert len(target)==1;f=target[0]
        assert f['value']==c['response']['target']
        if tier!='related-high':assert all(f[k]==t['raw_fields'][0][k]for k in ('owner','field','version'))
        results.append({'message':c['message'],'known':True,'correct':set(f['labels'])==set(t['expected_labels']),'expected_count':len(t['expected_labels']),'actual_count':len(set(f['labels'])),'target':f})
    save(d/'scores.json',results);save(d/'summary.json',{'targets':len(cases),'correct':sum(r['correct']for r in results),'wrong_known':sum(not r['correct']for r in results),'source_calls_paired':len(truth),'physical_truth_independent':True,'selectors':'not compared; explicit data only'})


def mall(out):
    import run_frozen_locality_cost as run
    import run_sockshop_cost as cost
    from run_galette_static_calibration import fixed_runtime,verify
    os.environ['TF_CALIBRATION_FIXED_RUNTIME']='1';verify()
    assert load(H/'final-high-02/independent-score/summary.json')['correct']==6
    task=load(OLD/'protocol-before-calibration.json')['tasks']['mall']
    props=H/'boundary-mall-v1.properties'
    if not props.exists():props.write_text('entry='+load(Path(task['plan']))['entry']+'\nprefix=com/macro/mall/\nsources='+'|'.join(task['source_calls_exact'])+'\ntarget=/data/expiresIn\n')
    agent=OLD/'galette-original/galette-agent/target/galette-agent-1.0.0-SNAPSHOT.jar';adapter=H/'boundary-build-06/boundary-adapter.jar'
    original=run.spec
    def configured(dest,mode):
        cfg=fixed_runtime(original(dest,'original'));s=cfg['services']['admin']
        s['volumes']=[v for v in s['volumes']if v.split(':')[1]!='/approved-jdk']+[str(H/'modified-jre8-02')+':/approved-jdk:ro',str(agent)+':/galette-agent.jar:ro',str(adapter)+':/boundary-adapter.jar:ro',str(props)+':/boundary.properties:ro',str(dest/'capture')+':/tf2/capture:rw']
        (dest/'capture').mkdir(exist_ok=True);(dest/'capture').chmod(0o777)
        cmd=s['command'];cmd[cmd.index('-jar'):cmd.index('-jar')]=['-Xbootclasspath/a:/galette-agent.jar:/boundary-adapter.jar','-Dgalette.boundary.config=/boundary.properties','-Dgalette.boundary.events=/tf2/capture/galette.jsonl','-javaagent:/boundary-adapter.jar','-javaagent:/galette-agent.jar']
        save(dest/'tool-receipt.json',{'variant':'modified Galette; official propagation Agent','Agent_sha256':sha(agent),'adapter_sha256':sha(adapter),'target':'/data/expiresIn','source_calls':task['source_calls_exact'],'TF_core_unchanged':True})
        return cfg
    run.spec=configured;run.verify=verify
    sampler=cost.Sampler
    class ShortSampler(sampler):
        def summary(self,*args,**kwargs):return {'short_correctness_only':True,'performance_summary_not_applicable':True}
    cost.Sampler=ShortSampler
    result=run.trial(out.parent,out.name,'original',0,3);save(out/'business-result.json',result)
    if result.get('business_passed')!=6:return
    cases=load(out/'measure.json')['requests']
    import math,copy
    for c in cases:
        v=copy.deepcopy(c['response']);assert c['http_status']==200
        for key in ('token','refreshToken'):assert isinstance(v['data'][key],str)and v['data'][key];v['data'][key]='<generated>'
        ttl=v['data']['expiresIn'];assert 86400-math.ceil(c['http_seconds'])-1<=ttl<=86400;v['data']['expiresIn']='<bounded-TTL>'
        assert v=={'code':200,'message':'操作成功','data':{'token':'<generated>','refreshToken':'<generated>','tokenHead':'Bearer ','expiresIn':'<bounded-TTL>'}}
    lines=(out/'database-after.txt').read_text().splitlines();assert int(lines[lines.index('login_log_count')+1])==6
    score_mall(out,cases)


def score_mall(out,cases):
    d=out/'independent-score';d.mkdir(exist_ok=False);cap=out/'capture/galette.jsonl'
    rows=[json.loads(l)for l in cap.read_text().splitlines()]
    assert not cap.with_name(cap.name+'.invalid').exists()and not any(r['kind']=='problem'or r['kind']=='closed'and r['capture_invalid']for r in rows)
    assert [r['seq']for r in rows]==list(range(1,len(rows)+1))and sum(r['kind']=='closed'for r in rows)==1
    truth=[]
    for c in cases:
        source=[r for r in rows if r['kind']=='source'and r['message']==c['message']and 'AuthService.getAccessToken' in r['callee']];assert len(source)==1;s=source[0]
        a=[r for r in rows if r['kind']=='source-call-enter'and r['source_call_id']==s['source_call_id']];b=[r for r in rows if r['kind']=='source-call-exit'and r['source_call_id']==s['source_call_id']]
        assert len(a)==len(b)==1 and a[0]['seq']<s['seq']<b[0]['seq']
        assert all(a[0][k]==s[k]==b[0][k]for k in ('source_call_id','caller','pc','callee','caller_frame','thread','root','message'))
        fields=[f for f in s['fields']if f['path']=='/data/expiresIn'];assert len(fields)==1
        truth.append({'message':c['message'],'source_call_id':s['source_call_id'],'raw_field':fields[0]})
    save(d/'truth-before-prediction.json',truth);scores=[]
    for c,t in zip(cases,truth):
        targets=[r for r in rows if r['kind']=='target'and r['message']==c['message']];assert len(targets)==1
        fs=[f for f in targets[0]['fields']if f['path']=='/data/expiresIn'];assert len(fs)==1;f=fs[0];s=t['raw_field']
        assert all(f[k]==s[k]for k in ('owner','field','version','value'))and f['value']==c['response']['data']['expiresIn']
        scores.append({'message':c['message'],'known':True,'correct':set(f['labels'])=={s['label']},'expected_count':1,'actual_count':len(f['labels']),'target':f})
    save(d/'scores.json',scores);save(d/'summary.json',{'targets':6,'correct':sum(r['correct']for r in scores),'wrong_known':sum(not r['correct']for r in scores),'source_calls_paired':6,'login_log_rows':6,'physical_truth_independent':True,'selectors':'not compared; explicit data only'})


def zlt(out):
    import run_target_closure_cost as run
    from run_shared_work_business import verify_business
    from run_galette_static_calibration import fixed_runtime,verify
    os.environ['TF_CALIBRATION_FIXED_RUNTIME']='1';verify()
    assert load(H/'final-mall-01/independent-score/summary.json')['correct']==6
    ref=ROOT/'artifacts/shared-transfer-optimization-20261106/final-candidate';run.FINAL=ref;run.verify=verify;run.fresh=lambda *a:None
    task=load(OLD/'protocol-before-calibration.json')['tasks']['zlt-user'];props=H/'boundary-zlt-v1.properties'
    if not props.exists():props.write_text('entry='+load(Path(task['plan']))['entry']+'\nprefix=com/central/\nsources='+'|'.join(task['source_calls_exact'])+'\ntarget=/data/*/username\n')
    agent=OLD/'galette-original/galette-agent/target/galette-agent-1.0.0-SNAPSHOT.jar';adapter=H/'boundary-build-06/boundary-adapter.jar';spec=run.zlt_spec
    def configured(home,dest,which,mode,projection_off=False):
        cfg,q=spec(home,dest,which,'original',False);cfg=fixed_runtime(cfg);s=cfg['services'][q['role']]
        s['volumes']=[v for v in s['volumes']if v.split(':')[1]!='/approved-jdk']+[str(H/'modified-jre8-02')+':/approved-jdk:ro',str(agent)+':/galette-agent.jar:ro',str(adapter)+':/boundary-adapter.jar:ro',str(props)+':/boundary.properties:ro',str(dest/'capture')+':/tf2/capture:rw']
        cmd=s['command'];cmd[cmd.index('-jar'):cmd.index('-jar')]=['-Xbootclasspath/a:/galette-agent.jar:/boundary-adapter.jar','-Dgalette.boundary.config=/boundary.properties','-Dgalette.boundary.events=/tf2/capture/galette.jsonl','-javaagent:/boundary-adapter.jar','-javaagent:/galette-agent.jar']
        save(dest/'tool-receipt.json',{'variant':'modified Galette, original propagation Agent','Agent_sha256':sha(agent),'adapter_sha256':sha(adapter),'original_six_inputs':q['inputs'],'source_calls':task['source_calls_exact'],'target':'/data/*/username'})
        return cfg,q
    run.zlt_spec=configured;run.zlt_trial(out.parent,out.name,'zlt-user','original',0,3,sample=False);verify_business(out,'zlt-user')
    cases=load(out/'measure.json')['requests'];d=out/'independent-score';d.mkdir(exist_ok=False)
    cap=out/'capture/galette.jsonl';rows=[json.loads(l)for l in cap.read_text().splitlines()]
    assert not cap.with_name(cap.name+'.invalid').exists()and not any(r['kind']=='problem'or r['kind']=='closed'and r['capture_invalid']for r in rows)
    assert [r['seq']for r in rows]==list(range(1,len(rows)+1))and sum(r['kind']=='closed'for r in rows)==1
    truth=[]
    for c in cases:
        sources=[r for r in rows if r['kind']=='source'and r['message']==c['message']and r['callee']==task['source_calls_exact'][0]];assert len(sources)==1;s=sources[0]
        starts=[r for r in rows if r['kind']=='source-call-enter'and r['source_call_id']==s['source_call_id']];ends=[r for r in rows if r['kind']=='source-call-exit'and r['source_call_id']==s['source_call_id']]
        assert len(starts)==len(ends)==1 and starts[0]['seq']<s['seq']<ends[0]['seq']
        assert all(starts[0][k]==s[k]==ends[0][k]for k in ('source_call_id','caller','pc','callee','caller_frame','thread','root','message'))
        for i,item in enumerate(c['response']['data']):
            fields=[f for f in s['fields']if f['path']=='/'+str(i)+'/username'];assert len(fields)==1 and fields[0]['value']==item['username']
            truth.append({'message':c['message'],'path':'/data/'+str(i)+'/username','raw_field':fields[0]})
    save(d/'truth-before-prediction.json',truth);scores=[]
    for t in truth:
        targets=[r for r in rows if r['kind']=='target'and r['message']==t['message']];assert len(targets)==1
        fields=[f for f in targets[0]['fields']if f['path']==t['path']];assert len(fields)==1;f=fields[0];s=t['raw_field']
        assert all(f[k]==s[k]for k in ('owner','field','version','value'))
        scores.append({'message':t['message'],'path':t['path'],'known':True,'correct':set(f['labels'])=={s['label']},'expected_count':1,'actual_count':len(f['labels']),'target':f})
    save(d/'scores.json',scores);save(d/'summary.json',{'targets':len(truth),'correct':sum(r['correct']for r in scores),'wrong_known':sum(not r['correct']for r in scores),'source_calls_paired':6,'physical_truth_independent':True,'selectors':'not compared; explicit data only'})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--build',type=Path);p.add_argument('--tier',choices=('low','medium','high','related-high','mall','zlt-user'));p.add_argument('--out',type=Path)
    a=p.parse_args()
    if a.build:build(a.build.resolve())
    elif a.tier=='mall':mall(a.out.resolve())
    elif a.tier=='zlt-user':zlt(a.out.resolve())
    else:controlled(a.tier,a.out.resolve())
