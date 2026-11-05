"""Dictionary positive pilot, followed by fixed C1 regression; no new query pool."""
import argparse,copy
from pathlib import Path
from run_planned_service import load,save,sha
from run_ruoyi_request_scope_revision import prepare
from run_ruoyi_wrapper_revision import install
from audit_ruoyi_wrapper_facts import run as score

def run(home,build,pilot=False):
 prepare(home,build);driver,_=install(home,build)
 names=('ruoyi-3',)if pilot else('ruoyi-3','ruoyi-2','ruoyi-1','ruoyi-5','ruoyi-4')
 for name in names:
  query=copy.deepcopy(next(q for q in load(home/'task-seal.json')['tasks']['ruoyi']if q['id']==name))
  if pilot:query['inputs']=query['inputs'][:1]
  save(home/('execution-'+name+'.json'),{'original_case_indices':[0]if pilot else list(range(6)),'query':query})
  for mode in('full','selective'):driver.trial('ruoyi',query,mode)

def audit(home,out,pilot=False):
 view=out.parent/(out.name+'-view');view.mkdir(parents=True,exist_ok=False)
 seal=copy.deepcopy(load(home/'task-seal.json'))
 if pilot:seal['tasks']['ruoyi']=[q for q in seal['tasks']['ruoyi']if q['id']=='ruoyi-3']
 save(view/'task-seal.json',seal)
 for name in('runs','plans'):(view/name).symlink_to((home/name).resolve(),target_is_directory=True)
 score(view,out,case_indices={0}if pilot else None)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('stage',choices=('run','audit'));p.add_argument('--home',type=Path,required=True);p.add_argument('--build',type=Path);p.add_argument('--pilot',action='store_true');p.add_argument('--out',type=Path);a=p.parse_args()
 if a.stage=='run':run(a.home.resolve(),a.build.resolve(),a.pilot)
 else:audit(a.home.resolve(),a.out.resolve(),a.pilot)
