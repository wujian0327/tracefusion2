"""Retain the already declared C2 mapper calibration separately from original C1."""
import argparse
from pathlib import Path
from run_planned_service import load,sha
from run_ruoyi_wrapper_revision import prepare,install
from run_ruoyi_request_scope_revision import score

def run(home,build,out):
 prepare(home,build,calibrated=True,inventory=load(build/'ruoyi/model.json')['library_inventory'])
 driver,_=install(home,build);query=load(home/'task-seal.json')['tasks']['ruoyi'][0]
 assert query['id']=='ruoyi-4'
 for mode in('full','selective'):driver.trial('ruoyi',query,mode)
 score(home,out,'ruoyi-4')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);p.add_argument('--build',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.home.resolve(),a.build.resolve(),a.out.resolve())
