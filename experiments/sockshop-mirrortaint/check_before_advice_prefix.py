"""Replay closed helper prefixes and reject corrupted frame ancestry."""
import argparse,copy,json
from pathlib import Path
from run_planned_service import load,save,sha
from infer_execution_kernel import infer_execution

def run(home,out):
    out.mkdir(parents=True,exist_ok=False);checks=[];original={}
    plan=load(home/'build/fixture/plan.json')
    for mode in ('full','selective'):
        path=home/mode/'fixture/events.jsonl';original[str(path)]=sha(path)
        rows=[json.loads(s)for s in path.read_text().splitlines()]
        baseline=infer_execution(plan,rows)
        assert sum(a['known']for a in baseline['answers'])==4
        for fault in ('early-target-frame','missing-helper-exit','wrong-helper-parent'):
            changed=copy.deepcopy(rows)
            dispatch=next(r for r in changed if r['kind']=='execution-direct-dispatch'and r.get('before_only'))
            helper=next(r for r in changed if r['kind']=='enter'and '$Helper.'in r['method']and r['seq']<dispatch['seq'])
            if fault=='early-target-frame':
                target=next(r for r in changed if r['kind']=='enter'and r['seq']>dispatch['seq']and '$Target.fetch('in r['method'])
                helper['method']=target['method']
            elif fault=='missing-helper-exit':
                next(r for r in changed if r['kind']=='exit'and r['frame']==helper['frame'])['kind']='diagnostic-missing-exit'
            else:helper['parent']='unrelated'
            try:infer_execution(plan,changed)
            except ValueError as error:checks.append({'mode':mode,'fault':fault,'state':'rejected','reason':str(error)})
            else:raise AssertionError((mode,fault))
    assert all(sha(Path(p))==v for p,v in original.items())
    save(out/'checks.json',{'checks':checks,'original_hashes_unchanged':original})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.home.resolve(),a.out.resolve())
