"""C1 return-observation revision; explicit separate C2 source calibration."""
import argparse,copy,json,shutil,subprocess
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save,sha
H=ROOT/'artifacts/ruoyi-zlt-refinement-20261103'
PREVIOUS=ROOT/'artifacts/target-closure-revision-20261103'


def prepare(out,build,calibrated=False):
    out.mkdir(parents=True,exist_ok=False)
    protocol=load(PREVIOUS/'external-first-01/task-seal.json');qs=[copy.deepcopy(q)for q in protocol['tasks']['ruoyi']if q['id']!='ruoyi-6']
    if calibrated:
        qs=[q for q in qs if q['id']=='ruoyi-4'];qs[0]['source_calls']=['com/ruoyi/system/mapper/SysConfigMapper.selectConfig(Lcom/ruoyi/system/domain/SysConfig;)Lcom/ruoyi/system/domain/SysConfig;']
    protocol['tasks']={'ruoyi':qs};save(out/'task-seal.json',protocol)
    for name in('model.json','schema.json','original-bytecode.json'):
        d=out/'metadata/ruoyi';d.mkdir(parents=True,exist_ok=True);shutil.copyfile(PREVIOUS/'external-first-01/metadata/ruoyi'/name,d/name)
    shutil.copyfile(PREVIOUS/'external-first-01/deployment-environment.json',out/'deployment-environment.json')
    from plan_capability_policy import choose
    model=load(out/'metadata/ruoyi/model.json')
    for q in qs:
        target,path=q['target'].split('@');p,route=choose(model,{'entry':q['entry'],'target':target,'path':path,'source_calls':q['source_calls']},deployment=load(out/'deployment-environment.json'))
        dest=out/'plans'/q['id'];dest.mkdir(parents=True);save(dest/'plan.json',p);save(dest/'route.json',route);save(dest/'result.json',{'state':'conditional','scope':'No answer asserted by planning.'})
    version=load(build.parent/'algorithm-freeze.json')['commit']if(build.parent/'algorithm-freeze.json').exists()else subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    save(out/'protocol-before-runs.json',{'reference':'130858947f3eabc1dbee8693f11c926f37f289e9','candidate_commit':version,'Agent':sha(build/'distributed-observer.jar'),
      'configuration':'C2 explicit actual mapper for BOTH tools'if calibrated else'C1 original five source declarations unchanged',
      'source_rules':'Same original identity-preserving mapper-return rule, never TF graph/native labels as truth.','calibrated':calibrated,
      'no_dynamic_code':True,'old_first_immutable':True,'driver_sha256':sha(Path(__file__)),
      'clock_business_check':'After requests, before disposable DB removal: independently read original table IDs/create_time, compare each returned unqueried createTime to its own DB. This is not a source oracle or cross-JVM input identity.'})


def install(out,build):
    import run_target_external_first as driver
    driver.OUT=out;driver.BASE=build
    def verify():
        assert sha(build/'distributed-observer.jar')==load(out/'protocol-before-runs.json')['Agent']
        version=load(build.parent/'algorithm-freeze.json')['commit']if(build.parent/'algorithm-freeze.json').exists()else load(out/'protocol-before-runs.json').get('candidate_commit','development-source-hash-checkpoint')
        return {'commit':version}
    driver.verify=verify;original=driver.attach
    def attach(*args,**kwargs):
        original(*args,**kwargs);dest=args[1];r=load(dest/'binary-receipt.json');r['core_agent_contract_changes']=dest.name!='mirrortaint';r['reference']='1308589';save(dest/'binary-receipt.json',r)
    driver.attach=attach
    from sockshop import Deployment
    previous=Deployment.diagnostics
    def diagnostics(self):
        previous(self)
        if str(self.out).startswith(str(out/'runs')):
            tables=[('sys_dept','dept_id'),('sys_dict_data','dict_code'),('sys_config','config_id'),('sys_post','post_id')]
            sql=' UNION ALL '.join("SELECT '%s' AS table_name,CAST(%s AS CHAR) AS id,DATE_FORMAT(create_time,'%%Y-%%m-%%d %%H:%%i:%%s') AS createTime FROM %s"%(t,key,t)for t,key in tables)
            r=self.compose('exec','-T','mysql','mysql','-uroot','-ptf2-disposable-fixture','--batch','-D','ry-cloud','-e',sql,check=False)
            (self.out/'independent-db-times.tsv').write_text((r.stdout or'')+(r.stderr or''));save(self.out/'independent-db-times-receipt.json',{'returncode':r.returncode,'SQL':sql,'source_truth':False})
    Deployment.diagnostics=diagnostics
    return driver,verify


def run(out,build,pilot=False,reuse_mt=None):
    driver,verify=install(out,build);qs=load(out/'task-seal.json')['tasks']['ruoyi'];done=[]
    for q in qs[:1]if pilot else qs:
        modes=('full',)if pilot else('full','selective','mirrortaint')if load(out/'protocol-before-runs.json')['calibrated']else('full','selective')
        for mode in modes:
            if mode=='mirrortaint'and reuse_mt:
                old=load(reuse_mt/'task-seal.json')['tasks']['ruoyi'];assert old==qs
                source=(reuse_mt/'runs'/q['id']/mode).resolve();dest=out/'runs'/q['id']/mode
                assert(source/'result.json').exists()and not dest.exists()
                dest.parent.mkdir(parents=True,exist_ok=True);dest.symlink_to(source,target_is_directory=True)
                save(out/'native-baseline-reuse.json',{'original':str(source),'new_deployment':False,
                    'task_and_source_declarations_identical':True,'files':{str(p.relative_to(source)):sha(p)for p in source.rglob('*')if p.is_file()},
                    'reason':'TF-only observer change; native MT, adapter, inputs and actual source configuration unchanged.'})
                done.append({'query':q['id'],'mode':mode,'state':'compatible_native_capture_reused'});continue
            driver.trial('ruoyi',q,mode);done.append({'query':q['id'],'mode':mode,'state':load(out/'runs'/q['id']/mode/'result.json')['state']})
            save(out/'matrix-progress.json',{'complete':False,'results':done})
    save(out/'matrix-progress.json',{'complete':not pilot,'results':done})


def score(out,dest,build):
    import audit_target_external_first as audit
    _,verify=install(out,build);audit.OUT=out;audit.verify=verify
    # Preserve original B2.2 calibration only for C1; not a new MT run.
    if not load(out/'protocol-before-runs.json')['calibrated']:
        for q in load(out/'task-seal.json')['tasks']['ruoyi']:
            (out/'runs'/q['id']/'mirrortaint').symlink_to((PREVIOUS/'external-first-01/runs'/q['id']/'mirrortaint').resolve(),target_is_directory=True)
    audit.audit(dest)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['prepare','run','pilot','score']);p.add_argument('--out',type=Path,required=True);p.add_argument('--build',type=Path,required=True);p.add_argument('--calibrated',action='store_true');p.add_argument('--audit',type=Path);p.add_argument('--reuse-mt',type=Path);a=p.parse_args()
    out=a.out.resolve();build=a.build.resolve()
    if a.stage=='prepare':prepare(out,build,a.calibrated)
    elif a.stage=='score':score(out,a.audit.resolve(),build)
    else:run(out,build,a.stage=='pilot',a.reuse_mt)
