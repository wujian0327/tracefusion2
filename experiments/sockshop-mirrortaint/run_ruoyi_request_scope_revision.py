"""Department-first development, preserving the original five-query pool."""
import argparse,copy
from pathlib import Path
from run_planned_service import ROOT,load,save,sha
import run_ruoyi_wrapper_revision as wrapper


def prepare(home,build):
    wrapper.prepare(home,build,inventory=load(build/'ruoyi/model.json')['library_inventory'])
    p=load(home/'protocol-before-runs.json');p.update(reference='d69f54a32193d8cadc4de86d199ab266082239ca',
        first_goal='Department detail full/selective positive source and request ownership controls before other entries',
        core_sources=load(build/'build.json')['sources'],driver_sha256=sha(Path(__file__)))
    save(home/'protocol-before-runs.json',p)


def run(home,build,query):
    for name,digest in load(home/'protocol-before-runs.json')['core_sources'].items():assert sha(Path(name))==digest,name
    driver,_=wrapper.install(home,build)
    q=next(q for q in load(home/'task-seal.json')['tasks']['ruoyi']if q['id']==query)
    for mode in('full','selective'):driver.trial('ruoyi',q,mode)


def score(home,out,query,mode=None):
    from audit_ruoyi_wrapper_facts import run as audit
    view=out.parent/(out.name+'-view');view.mkdir(parents=True,exist_ok=False)
    protocol=copy.deepcopy(load(home/'task-seal.json'));protocol['tasks']['ruoyi']=[q for q in protocol['tasks']['ruoyi']if q['id']==query]
    protocol['score_scope']='One prespecified query, all original cases and complete captures; five-query pool retained in parent.'
    save(view/'task-seal.json',protocol)
    for n in('runs','plans'):(view/n).symlink_to((home/n).resolve(),target_is_directory=True)
    audit(view,out,(mode,)if mode else('full','selective'))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['prepare','run','score']);p.add_argument('--home',type=Path,required=True);p.add_argument('--build',type=Path,required=True);p.add_argument('--query',default='ruoyi-1');p.add_argument('--out',type=Path);p.add_argument('--mode',choices=['full','selective']);a=p.parse_args()
    if a.stage=='prepare':prepare(a.home.resolve(),a.build.resolve())
    elif a.stage=='run':run(a.home.resolve(),a.build.resolve(),a.query)
    else:score(a.home.resolve(),a.out.resolve(),a.query,a.mode)
