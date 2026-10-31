"""Independent raw mapper/target identities for one exposed development pilot."""
import argparse,json
from pathlib import Path
from run_planned_service import load,save,sha,ROOT
from audit_zlt_foundation_revision import ancestor,fields_equal,tf_pair
from query_observation_planner import require


def audit(home,api,mode,out):
    from infer_distributed_fields import Reconstruction
    from external_transfer_oracle import require_complete_raw_capture
    out.mkdir(parents=True,exist_ok=False)
    task=next(q for q in load(home/'task-seal.json')['entries'] if q['id']==api)
    folder=home/'runs'/api/mode
    original=load(ROOT/'artifacts/offline-zlt-revision-20261031/final-zlt-03/runs'/api/'original/selected-requests.json')
    cases=load(folder/'selected-requests.json');raw=folder/'capture/events.jsonl'
    rows=[json.loads(s) for s in raw.read_text().splitlines()];require_complete_raw_capture(rows)
    frames={r['frame']:r for r in rows if r['kind']=='enter'}
    build=out/'view/build'/task['role'];build.mkdir(parents=True)
    (build/'plan.json').write_bytes((home/'planning-first'/api/'000-plan.json').read_bytes())
    capture=out/'view/capture'/task['role'];capture.mkdir(parents=True)
    (capture/'events.jsonl').symlink_to(raw.resolve())
    graph=Reconstruction(build.parent,capture.parent,[task['role']]);records=[]
    for case,baseline in zip(cases,original):
        require(case['case']==baseline['case'] and case['http_status']==baseline['http_status']
                and case['response']==baseline['response'],'Original business response differs')
        targets=[r for r in rows if r['kind']=='binding-return' and r.get('message')==case['message']]
        require(len(targets)==1,'Target root absent/ambiguous');target=targets[0]
        if not baseline['response']['data']:continue
        source=[r for r in rows if r['kind']=='binding-source' and r['callee']==task['oracle']['source']
                and ancestor(r['frame'],target['frame'],frames)]
        require(len(source)==1,'Mapper occurrence absent/ambiguous');source=source[0];pair=tf_pair(rows,source)
        leaf=task['return_targets'][0]['path'].split('/')[-1]
        for index,item in enumerate(baseline['response']['data']):
            path='/data/'+str(index)+'/'+leaf
            field=fields_equal(source['fields'],target['fields'],path[len('/data'):],path)
            require(field['observed']['value']==item[leaf],'Original data value differs')
            expected=(source['callee'],source['frame'],source['seq'],field['path'],field['owner'],field['field'],field['version'])
            answer=graph.query(case['message'],path,task['role'],boundary=[{'kind':'binding-source'},{'kind':'argument'}])
            got={(s.get('callee'),s.get('root_frame'),s['seq'],s.get('path'),s['owner'],s['field'],s['version']) for s in answer['sources']}
            require(answer['known'] and got=={expected},'Positive instance source not recovered')
            records.append({'case':case['case'],'path':path,'state':'known_correct','expected':expected,'source_pair':pair})
    save(out/'results.json',{'api':api,'mode':mode,'pilot_only':True,'independent_positive_matches':len(records),
        'business_equal':True,'agent_receipt':load(folder/'revision-receipt.json'),
        'raw_sha256':sha(raw),'instances':records})
    print(api,mode,len(records),'independently matched')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);p.add_argument('--api',required=True)
    p.add_argument('--mode',choices=['full','selective'],required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();audit(a.home.resolve(),a.api,a.mode,a.out.resolve())
