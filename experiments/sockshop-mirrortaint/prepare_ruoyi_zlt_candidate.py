"""Freeze one Map-observation/index candidate before final new deployments."""
import argparse,subprocess
from pathlib import Path
from run_planned_service import HERE,load,save,sha


def prepare(root):
    from run_zlt_slice_revision import prepare as existing
    existing(root)
    f=load(root/'historical/algorithm-freeze.json');f.update(parent_algorithm='130858947f3eabc1dbee8693f11c926f37f289e9',
      scope='Readonly finite HashMap target wrappers and capture-local initialized-class lookup; no new propagation source, JDK runtime expansion, sink or Gson support.')
    save(root/'historical/algorithm-freeze.json',f)
    p=load(root/'final-protocol-before-business.json');p.update(reference=f['parent_algorithm'],
      scope=f['scope'],no_new_applications=True,candidate_commit=f['commit'],
      RuoYi='Separate exposed-query C1 wrapper revision and explicit C2 mapper calibration, never first unseen transfer.')
    save(root/'final-protocol-before-business.json',p)
    save(root/'target-closure-candidate.json',{'commit':f['commit'],'agent_sha256':p['agent_sha256'],'source_files':f['sources'],'plans':p['plans']})
    print('Prepared',f['commit'],len(f['sources']),p['agent_sha256'],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();prepare(a.root.resolve())
