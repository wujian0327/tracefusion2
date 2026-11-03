"""Freeze shared developed candidate plans; new-app planning remains separate."""
import argparse
import subprocess
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save,sha


def prepare(root):
    import run_zlt_slice_revision as existing
    existing.prepare(root)
    commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    freeze=load(root/'historical/algorithm-freeze.json')
    freeze.update(parent_algorithm='7e4ad0b900a64871259a5fac008968128cc5ec28',
      scope='Conservative target-related boundary scalar/member value closure and reference-only future-state qualification of effect-body cuts; public contracts unchanged.')
    save(root/'historical/algorithm-freeze.json',freeze)
    protocol=load(root/'final-protocol-before-business.json')
    protocol.update(reference='7e4ad0b900a64871259a5fac008968128cc5ec28',candidate_commit=commit,
      no_new_applications='This directory contains development regressions only. Sealed RuoYi/TeaStore first runs use a separate directory after this candidate freezes.',
      external_seal_sha256=sha(root.parent/'external-query-seal-v3-before-tools.json'),
      driver_sources={str(HERE/'prepare_target_closure_final.py'):sha(HERE/'prepare_target_closure_final.py'),**protocol['driver_sources']})
    save(root/'final-protocol-before-business.json',protocol)
    for p,h in freeze['sources'].items():assert sha(Path(p))==h
    save(root/'target-closure-candidate.json',{'commit':commit,'source_files':len(freeze['sources']),
       'agent_sha256':sha(root/'historical/frozen-base/distributed-observer.jar'),
       'plans':protocol['plans'],'first_new_app_query_planned':False})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);prepare(p.parse_args().root.resolve())
