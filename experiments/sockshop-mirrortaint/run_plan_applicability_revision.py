#!/usr/bin/env python3
"""Development runs, separate from all immutable external first/C1 results."""
import argparse, hashlib, importlib, inspect, json, shutil, subprocess, sys
from pathlib import Path

HERE=Path(__file__).resolve().parent; ROOT=HERE.parents[1]
sys.path.append(str(ROOT/'scripts'))
FIRST=ROOT/'artifacts/external-frozen-transfer-20261029'
HOME=ROOT/'artifacts/plan-applicability-revision-20261029'
BASE=ROOT/'artifacts/account-semantics-20261028/final-candidate-01/frozen-base'
def load(p):return json.loads(p.read_text())
def save(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,indent=2,ensure_ascii=False)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def prepare(only_api=None,only_index=None):
    from plan_capability_policy import choose
    HOME.mkdir(parents=True,exist_ok=True)
    if (HOME/'metadata').is_symlink():raise ValueError('Refuse writing through an earlier metadata symlink; use a new candidate --home')
    for name in ('business-jars','upstream'):
        p=HOME/name
        if not p.exists():p.symlink_to((FIRST/'78a9534'/name).resolve(),target_is_directory=True)
    from contract_applicability import library_inventory
    for role in ('mall-portal','mall-admin'):
        model=load(FIRST/'78a9534/metadata'/role/'model.json')
        model['library_inventory']=library_inventory(HOME/'business-jars'/(role+'.jar'))
        save(HOME/'metadata'/role/'model.json',model)
    save(HOME/'task-seal.json',load(FIRST/'task-seal.json'))
    save(HOME/'protocol-start.json',{'TF_commit':'development from 93a5a86; Agent unchanged78a9534'})
    tools=HOME/'runtime-probe';tools.mkdir(exist_ok=True)
    subprocess.run(['/usr/lib/jvm/java-8-openjdk-amd64/bin/javac','-d',str(tools),str(HERE/'JdkContractProbe.java')],check=True)
    names=set()
    for f,key in [('kernel-contract-runtimes-20261020.json','profiles'),('foundation-value-contracts-20261028.json','jdk_profiles')]:
        for p in load(HERE/f)[key]:names.update(p['class_sha256'])
    result=subprocess.check_output(['/usr/lib/jvm/java-8-openjdk-amd64/bin/java','-cp',str(tools),'JdkContractProbe',*sorted(names)],text=True)
    (tools/'stdout.txt').write_text(result)
    values=dict(line.split('=',1)for line in result.splitlines())
    environment={'runtime':{'java_runtime_version':values.pop('java.runtime.version'),'class_sha256':values},'response_converter':{'class':'org.springframework.http.converter.json.MappingJackson2HttpMessageConverter','basis':'Original Mall application configuration; actual mapper/serializer witnesses still mandatory at runtime.'}}
    save(HOME/'deployment-environment.json',environment)
    outcomes=[]
    for q in load(HOME/'task-seal.json')['entries']:
        if not q['id'].startswith('mall-'):continue
        if only_api and q['id']!=only_api:continue
        model=load(HOME/'metadata'/q['role']/'model.json')
        for index,target in enumerate(q['return_targets']):
            if only_index is not None and index!=only_index:continue
            query={'id':q['id']+'-'+str(index),'entry':q['entry'],'target':target['target'],'path':target['path'],'role':q['role'],'source_calls':[s['callee']for s in q['read_source_candidates']]}
            dest=HOME/'planning-first'/q['id'];receipt={'query':query,'index':index}
            try:
                plan,route=choose(model,query,deployment=environment)
                planned=dest/('%03d-plan.json'%index)
                if planned.exists():assert load(planned)==plan,'Do not replace a plan after its business capture'
                else:save(planned,plan)
                receipt.update(status='accepted_conditional',profile=plan['profile'],route=route,plan_sha256=sha(dest/('%03d-plan.json'%index)))
            except ValueError as e:receipt.update(status='rejected',reason=str(e))
            save(dest/('%03d.json'%index),receipt);outcomes.append({'api':q['id'],**receipt})
    save(HOME/'planning-summary.json',outcomes)
    print([(r['query']['id'],r['status'],r.get('profile'))for r in outcomes],flush=True)

def run(api,mode,index):
    import portability_tool_config as config
    import run_portability_mall as env
    from sockshop import Deployment
    config.BASE=BASE
    def verify(root):
        assert sha(BASE/'distributed-observer.jar')==load(HOME/'candidate-code.json')['agent_sha256']
        protocol=load(HOME/'development-protocol-before-change.json')
        for f,h in protocol['protected'].items():assert sha(ROOT/f)==h,f
        for f,h in load(HOME/'candidate-code.json')['sources'].items():assert sha(ROOT/f)==h,f
        for f,h in load(HOME/'candidate-code.json').get('planning_inputs',{}).items():assert sha(HOME/f)==h,f
    config.verify=verify;env.verify=verify
    original_config=config.configure
    def configure(root,out,cfg,q,mode,index=None):
        original_config(root,out,cfg,q,mode,index)
        receipt=load(out/'tool-binaries.json');receipt['no_core_agent_or_contract_changes']=False;receipt['development_revision']='Preexecution routing, observed zero-advice dispatch and later-source establishment; no change to first/C1 artifacts';save(out/'tool-binaries.json',receipt)
        save(out/'revision-before-business.json',{'candidate_sources':load(HOME/'candidate-code.json'),'agent_sha256':sha(BASE/'distributed-observer.jar'),'plan_sha256':sha(HOME/'planning-first'/api/('%03d-plan.json'%index)),'first_or_C1_replaced':False})
    config.configure=configure
    native=Deployment.compose;latest={};native_save=env.save
    def witnessed_save(path,data):
        if isinstance(data,dict)and'http_status'in data and'response'in data and latest:data['message']=latest['message']
        return native_save(path,data)
    env.save=witnessed_save
    def compose(self,*args,**kwargs):
        values=list(args)
        if 'curl'in values and '--max-time'in values:
            label=inspect.currentframe().f_back.f_locals.get('label','unknown')
            n=getattr(self,'_query_seq',0);self._query_seq=n+1
            digest=hashlib.sha256((api+'|'+mode+'|'+str(index)+'|'+str(n)).encode()).hexdigest()
            latest['message']=digest[:32]+'/'+digest[32:48]
            values[-1:-1]=['-H','traceparent: 00-'+digest[:32]+'-'+digest[32:48]+'-01']
            if label.startswith(api+'-input-'):
                save(self.out/(label+'-before-request.json'),{'message':latest['message'],'argv':values})
                for phase in ('before',):
                    p=native(self,'exec','-T','mysql','mysqldump','-uroot','-ptf2-portability-fixture-only','--skip-comments','--skip-extended-insert','--no-create-info','--databases','mall',check=False)
                    (self.out/(label+'-database-'+phase+'.sql')).write_text(p.stdout)
            result=native(self,*values,**kwargs)
            if label.startswith(api+'-input-'):
                p=native(self,'exec','-T','mysql','mysqldump','-uroot','-ptf2-portability-fixture-only','--skip-comments','--skip-extended-insert','--no-create-info','--databases','mall',check=False)
                (self.out/(label+'-database-after.sql')).write_text(p.stdout)
            return result
        return native(self,*values,**kwargs)
    Deployment.compose=compose
    out=HOME/'tool-runs'/api/mode/('query-%03d'%index)
    if out.exists():raise ValueError('Never overwrite an existing development capture: '+str(out))
    env.run(HOME,mode,api,index)

def freeze():
    # Complete semantic core snapshot, not just the two modified planners.
    previous=load(ROOT/'artifacts/account-semantics-20261028/final-candidate-01/algorithm-freeze.json')['sources']
    sources={str(Path(f).relative_to(ROOT)):sha(Path(f))for f in previous}
    for name in ('plan_applicability.py','direct-dispatch-contracts-20261029.json'):
        sources[str((HERE/name).relative_to(ROOT))]=sha(HERE/name)
    receipt={'sources':sources,'agent_sha256':sha(BASE/'distributed-observer.jar'),'meaning':'Development checkpoint before business capture; preexecution routing and finite zero-advice/source reestablishment support, separate from first/C1.'}
    receipt['planning_inputs']={str(p.relative_to(HOME)):sha(p)for folder in ('planning-first','metadata')for p in (HOME/folder).rglob('*.json')}
    receipt['planning_inputs']['deployment-environment.json']=sha(HOME/'deployment-environment.json')
    if (HOME/'candidate-code.json').exists():assert load(HOME/'candidate-code.json')==receipt,'Do not overwrite a candidate freeze; use a new --home'
    else:save(HOME/'candidate-code.json',receipt)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['prepare','freeze','run']);p.add_argument('--api');p.add_argument('--mode',choices=['full','selective']);p.add_argument('--index',type=int);p.add_argument('--home',type=Path);p.add_argument('--agent-build',type=Path);a=p.parse_args()
    if a.home:HOME=a.home.resolve()
    if a.agent_build:BASE=a.agent_build.resolve()
    if a.stage=='prepare':prepare(a.api,a.index)
    elif a.stage=='freeze':freeze()
    else:run(a.api,a.mode,a.index)
