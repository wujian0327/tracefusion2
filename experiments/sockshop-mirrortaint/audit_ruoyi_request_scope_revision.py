"""Separate new scope/effect results from immutable previous invalid captures."""
import argparse,collections,csv,json
from pathlib import Path
from run_planned_service import ROOT,load,save,sha
from infer_distributed_fields import Reconstruction


def audit(home,out):
    out.mkdir(parents=True,exist_ok=False);freeze=load(home/'algorithm-freeze.json')
    for name,digest in freeze['sources'].items():assert sha(Path(name))==digest,name
    before=load(home/'protocol-before-change.json')
    for name,digest in before['old_captures'].items():assert sha(ROOT/name)==digest,name
    previous=ROOT/'artifacts/ruoyi-zlt-refinement-20261103/final-attempt-05'
    old=load(previous/'facts-ruoyi-C1/instances.json');new=load(home/'facts-final-C1/instances.json');paired=[]
    lookup={(r['query'],r['mode'],r['case'],r['path']):r for r in old}
    for r in new:
        key=(r['query'],r['mode'],r['case'],r['path']);assert key in lookup
        paired.append({**r,'reference_state':lookup[key]['state']})
    assert len(paired)==len(old)==178
    rejected=[];old_files={}
    for q in load(previous/'ruoyi-C1/task-seal.json')['tasks']['ruoyi']:
        for mode in('full','selective'):
            source=previous/'ruoyi-C1/runs'/q['id']/mode/'capture/events.jsonl';plan=previous/'ruoyi-C1/plans'/q['id']/'plan.json';old_files[str(source)]=sha(source)
            rows=[json.loads(x)for x in source.read_text().splitlines()]
            # Deliberately damaged DERIVED copy, not the original record.
            altered=[r for r in rows if r['kind']!='problem']
            for seq,r in enumerate(altered,1):r['seq']=seq
            d=out/'sticky-old'/q['id']/mode;(d/'build/role').mkdir(parents=True);(d/'capture/role').mkdir(parents=True)
            (d/'build/role/plan.json').write_bytes(plan.read_bytes());(d/'capture/role/events.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n'for r in altered))
            try:Reconstruction(d/'build',d/'capture',['role'])
            except ValueError as e:assert str(e)=='Collector problem';rejected.append({'query':q['id'],'mode':mode,'reason':str(e)})
            else:raise AssertionError('Old invalid capture was certified')
    for name,digest in old_files.items():assert sha(Path(name))==digest
    protected=0;older=ROOT/'artifacts/target-closure-revision-20261103'
    for line in(older/'external-before-read-permission.sha256').read_text().splitlines():
        digest,name=line.split('  ',1);p=older/'external-first-01/runs'/Path(name).relative_to('/work');assert sha(p)==digest,p;protected+=1
    retained=load(older/'final-compatibility-pass-02/audit-mall/captures-manifest.json')['files']
    for name,digest in retained.items():assert sha(older/'final-candidate-02/mall'/name)==digest,name
    summary={'candidate':freeze['commit'],'Agent_SHA256':freeze['Agent_SHA256'],'core_sources':len(freeze['sources']),
      'C1':{m:{'states':dict(collections.Counter(r['state']for r in paired if r['mode']==m)),
           'targets':sum(r['mode']==m for r in paired)}for m in('full','selective')},
      'C2':load(home/'facts-final-C2/summary.json'),
      'old_RuoYi_invalid_batches_still_rejected':len(rejected),'older_first_files_unchanged':protected,'older_Mall_files_unchanged':len(retained),
      'scope_controls':load(home/('scope-controls-05'if(home/'scope-controls-05/results.json').exists()else'scope-controls-04')/'results.json'),'constructor_controls':load(home/'map-constructor-controls-04/results.json'),
      'scope_guards':load(home/'final-guards/results.json'),'old_captures':old_files,
      'no_performance':True,'historical_full_deployments_repeated':False,'scope':'Exposed RuoYi return tasks; C1/C2 separate; no claim of all-application support.'}
    save(out/'summary.json',summary);save(out/'paired.json',paired)
    with(out/'paired.csv').open('w')as f:
        keys=list(dict.fromkeys(k for r in paired for k in r));w=csv.DictWriter(f,keys,lineterminator='\n');w.writeheader();w.writerows(paired)
    save(out/'old-rejections.json',rejected)
    print(summary['C1'],summary['C2']['states'],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();audit(a.home.resolve(),a.out.resolve())
