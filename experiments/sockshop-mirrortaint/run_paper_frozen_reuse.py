"""Two sealed queries, unchanged bcdf059 core/Agent and fixed MT B2.2.

Only task declarations, original environment reuse and independent scoring are
new. Planning rejection and first-run failure never replace a sealed query.
"""
import argparse
import copy
import shutil
import sys
from pathlib import Path

from run_planned_service import ROOT, load, save, sha

BASE = ROOT/'artifacts/pruning-contribution-audit-20261106/final-candidate/historical/frozen-base'


def verify(home):
    seal = load(home/'task-seal-before-tools.json')
    for name, digest in seal['frozen_core_sources'].items(): assert sha(Path(name)) == digest, name
    for name, digest in seal['artifacts'].items(): assert sha(Path(name)) == digest, name
    return {'commit': seal['reference']}


def prepare(home):
    verify(home); seal = load(home/'task-seal-before-tools.json')
    save(home/'task-seal.json', seal)
    dest = home/'metadata/ruoyi'; dest.mkdir(parents=True)
    shutil.copyfile(seal['model'], dest/'model.json'); shutil.copyfile(seal['schema'], dest/'schema.json')
    shutil.copyfile(seal['deployment'], home/'deployment-environment.json')
    save(home/'protocol-before-tools.json', {'seal_sha256': sha(home/'task-seal-before-tools.json'),
         'core': seal['reference'], 'Agent': seal['frozen_agent_sha256'], 'driver': sha(Path(__file__)),
         'first_planning_starts_after_this_receipt': True, 'no_performance': True})
    from plan_capability_policy import choose
    model = load(dest/'model.json'); environment = load(home/'deployment-environment.json')
    for q in seal['tasks']['ruoyi']:
        path = home/'plans'/q['id']; path.mkdir(parents=True)
        try:
            target, pointer = q['target'].split('@', 1)
            plan, route = choose(model, {'entry':q['entry'], 'target':target, 'path':pointer,
                                        'source_calls':q['source_calls']}, deployment=environment)
            save(path/'plan.json', plan); save(path/'route.json', route)
            save(path/'result.json', {'state':'conditional', 'not_an_answer':True})
        except Exception as e:
            save(path/'result.json', {'state':'planning_rejected', 'reason':str(e), 'no_model_change':True})
    verify(home)


def run(home):
    import run_target_external_first as driver
    from sockshop import Deployment
    driver.OUT = home; driver.BASE = BASE; driver.verify = lambda: verify(home)
    diagnostics = Deployment.diagnostics
    def own_database(self):
        diagnostics(self)
        if not str(self.out).startswith(str(home/'runs')): return
        sql = "SELECT 'post' AS table_name,CAST(post_id AS CHAR) AS id,post_name AS name,DATE_FORMAT(create_time,'%Y-%m-%d %H:%i:%s') AS createTime,status FROM sys_post UNION ALL SELECT 'dict_type',CAST(dict_id AS CHAR),dict_name,DATE_FORMAT(create_time,'%Y-%m-%d %H:%i:%s'),status FROM sys_dict_type"
        result = self.compose('exec','-T','mysql','mysql','-uroot','-ptf2-disposable-fixture',
                              '--default-character-set=utf8mb4','--batch','-D','ry-cloud','-e',sql,check=False)
        (self.out/'independent-database.tsv').write_text((result.stdout or '')+(result.stderr or ''))
        save(self.out/'database-receipt.json', {'returncode':result.returncode, 'SQL':sql,
             'physical_coordinate_oracle':False})
    Deployment.diagnostics = own_database
    progress = []
    try:
        for q in load(home/'task-seal.json')['tasks']['ruoyi']:
            for mode in ('original','full','selective','mirrortaint'):
                planned = load(home/'plans'/q['id']/'result.json')
                reused=load(home/'task-seal.json').get('compatible_reuse',{}).get(mode)
                if reused:
                    source=Path(reused);before=load(source.parents[2]/'task-seal.json')
                    old=next(v for v in before['tasks']['ruoyi']if v['id']==q['id'])
                    for key in ('entry','target','source_calls','http','inputs'):assert old[key]==q[key]
                    dest=home/'runs'/q['id']/mode;dest.parent.mkdir(parents=True,exist_ok=True)
                    dest.symlink_to(source,target_is_directory=True)
                    save(home/('reuse-'+mode+'.json'), {'new_deployment':False,'query':q['id'],
                         'source':str(source),'input_and_scope_identical':True,
                         'files':{str(p.relative_to(source)):sha(p)for p in source.rglob('*')if p.is_file()}})
                    progress.append({'query':q['id'],'mode':mode,'state':'compatible_capture_reused'})
                    save(home/'matrix-progress.json', {'complete':False,'results':progress})
                    continue
                if mode in ('full','selective') and not(home/'plans'/q['id']/'plan.json').exists():
                    progress.append({'query':q['id'],'mode':mode,**planned})
                else:
                    driver.trial('ruoyi', copy.deepcopy(q), mode)
                    progress.append({'query':q['id'],'mode':mode,
                                     'state':load(home/'runs'/q['id']/mode/'result.json')['state']})
                save(home/'matrix-progress.json', {'complete':False,'results':progress})
    finally: Deployment.diagnostics = diagnostics
    verify(home); save(home/'matrix-progress.json', {'complete':True,'results':progress,'core_unchanged':True})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['prepare','run']);p.add_argument('--home',required=True,type=Path)
    a=p.parse_args();(prepare if a.stage=='prepare' else run)(a.home.resolve())
