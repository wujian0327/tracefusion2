"""Freeze shared acceptance inputs including the unchanged RuoYi original JAR."""
import argparse
from pathlib import Path
from run_planned_service import ROOT,load,save,sha
from run_zlt_slice_revision import prepare

def run(home):
 pilot=load(home/'pilot-score-02/summary.json')['states']
 assert all(pilot[m]=={'known_correct':3}for m in ('full','selective'))
 root=home/'final-candidate'
 prepare(root,extra_inputs={'ruoyi':{'jar':str(ROOT/'artifacts/ruoyi-removeif-20261105/candidate/ruoyi/original.jar'),'targets':['com/ruoyi/system/api/domain/SysDept.deptName']}})
 freeze=load(root/'historical/algorithm-freeze.json')
 save(root/'target-closure-candidate.json',freeze)
 save(home/'final-freeze.json',{'commit':freeze['commit'],'sources':freeze['sources'],'agent_sha256':sha(root/'historical/frozen-base/distributed-observer.jar'),'pilot_gate':pilot,'no_cost_experiments':True})
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);run(p.parse_args().home.resolve())
