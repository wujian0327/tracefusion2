#!/usr/bin/env python3
"""Disclosed secondary profiles; never replace primary first results.

read-only-network moves dispatch into the HTTP handler and keeps the same cache
operations. direct-B gives B a real external request: no fictitious HTTP source
transfer. Its local-source results are NOT full A->B lineage results.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import shutil
import sys
import traceback
from run import HERE, ROOT, CORE, load, save, sha, now, command, build, capture
from analyze import tf, rows


def local_tf(build_dir,cap,dest):
    sys.path.insert(0,str(CORE))
    from infer_execution_kernel import infer_execution
    plan=load(build_dir/'tf/B/plan.json');rs=rows(cap/'B/events.jsonl')
    try:
        result=infer_execution(plan,rs)
        # No new source inference: export the existing core's raw origin tuples.
        save(dest/'local-core.json',result)
        targets=[r for r in rs if r['kind']=='binding-return']
        a=next(a for a in result['answers'] if a['seq']==targets[-1]['seq'] and a['path']=='/text')
        sources=[]
        for origin in a['origins']:
            if origin[0]!='field':raise ValueError('Unexpected raw origin '+str(origin))
            _,seq,index=origin;s=next(r for r in rs if r['seq']==seq);f=s['fields'][index]
            if s['kind']!='binding-input':raise ValueError('Local diagnostic is only for external input fields')
            # Verify this is the same decoded field seen at the external HTTP boundary.
            matches=[r for r in rs if r['kind']=='http-json' and r['phase']=='read' and r['direction']=='request' and r['message']==s['message']]
            assert len(matches)==1 and any((x['owner'],x['field'],x['version'])==(f['owner'],f['field'],f['version']) for x in matches[0]['fields'])
            sources.append({'message':s['message'],'path':f['path']})
        return {'known':a['known'],'sources':sources,'raw':a}
    except Exception as e:return {'known':False,'error':str(e),'traceback':traceback.format_exc()}


def run(out,java,repeats):
    out.mkdir(parents=True,exist_ok=False);snapshot=out/'experiment-source';snapshot.mkdir()
    for p in HERE.iterdir():
        if p.is_file():shutil.copyfile(p,snapshot/p.name)
    shutil.copyfile(HERE/'expected.json',out/'expected.json');shutil.copyfile(HERE/'workload.json',out/'workload.json')
    save(out/'freeze.json',{'frozen_at':now(),'expected_sha256':sha(out/'expected.json'),'source_boundary_by_profile':{'read-only-network':'A external HTTP','direct-B':'B real external HTTP'},'primary_replacement':False,
         'core_sources':{str(p.relative_to(ROOT)):sha(p) for p in CORE.iterdir() if p.suffix in ('.py','.java','.json')}})
    command([java,'-version'],out/'java-version.log');build(out/'build',entry='read')
    workload=load(out/'workload.json');captures=[]
    for mode in ('plain','tracefusion','mirrortaint'):
        for profile,ingress in (('read-only-network','A'),('direct-B','B')):
            for repeat in range(1,repeats+1):
                for case in workload['cases']:
                    cap=out/'captures'/profile/mode/str(repeat)/case['id'];r=capture(cap,out/'build',mode,case,java,ingress=ingress,dispatch='split')
                    captures.append((profile,mode,repeat,case['id'],cap));print(profile,mode,repeat,case['id'],r['business_completed'],flush=True)
                    if mode=='plain' and not r['business_completed']:raise RuntimeError('Diagnostic plain gate failed')
    # Predict before opening independent expectations. Both analyzers consume events only.
    predictions=[]
    for profile,mode,repeat,cid,cap in captures:
        if mode=='plain':continue
        dest=out/'predictions'/profile/mode/str(repeat)/cid;dest.mkdir(parents=True)
        if mode=='tracefusion':
            if profile=='read-only-network':tf(out/'build/tf',cap,dest);a=load(dest/'prediction.json')
            else:a=local_tf(out/'build',cap,dest);save(dest/'prediction.json',a)
        else:
            a={'native':{r:rows(cap/r/'native.jsonl') if (cap/r/'native.jsonl').exists() else [] for r in ('A','B')}};save(dest/'prediction.json',a)
        predictions.append((profile,mode,repeat,cid,cap,a))
    expected={c['id']:c for c in load(out/'expected.json')['cases']};scored=[]
    for profile,mode,repeat,cid,cap,prediction in predictions:
        receipt=load(cap/'run.json');plain=load(out/'captures'/profile/'plain'/str(repeat)/cid/'run.json')
        e=expected[cid];r={'profile':profile,'mode':mode,'repeat':repeat,'case':cid,'expected':e['source']}
        r['business_equal']=receipt['business_completed'] and plain['business_completed'] and receipt['state']==plain['state']==e['state'] and [v['response']for v in receipt['requests']]==[v['response']for v in plain['requests']]
        mapping={v['traceparent']:i+1 for i,v in enumerate(receipt['requests'])}
        if mode=='tracefusion':
            if profile=='read-only-network':
                if prediction['status']=='analysis_error':a={'known':False,'error':prediction['error']}
                else:
                    requests=[v for v in rows(cap/'B/http.jsonl') if v['path']=='/call'];p=requests[-1]['traceparent'].split('-');m=p[1]+'/'+p[2]
                    q=next(q for q in prediction['queries'] if q['role']=='B' and q['message']==m);a=q['answer']
            else:a=prediction
            message_mapping={'/'.join(k.split('-')[1:3]):v for k,v in mapping.items()}
            r.update(known=a['known'],actual=sorted([[message_mapping.get(s.get('message'),'unmapped'),s['path']] for s in a.get('sources',[])],key=str),reason=a.get('error','core unknown' if not a['known'] else 'core result'))
        else:
            native=prediction['native'];role='B' if profile=='direct-B' else 'A';source=[s for s in native[role] if s['kind']=='source']
            ids={t:[mapping[s['message']],s['path']] for s in source for t in s['native_ids']}
            sink=[s for s in native['B'] if s['kind']=='sink']
            labels=sink[-1]['native_ids'] if sink else []
            r.update(known=bool(sink),actual=sorted([ids.get(t,['unmapped',t]) for t in labels],key=str),reason='native IDs only; no strict version query')
        r['state']=('correct' if r['actual']==r['expected'] else 'wrong') if r['known'] else 'unknown';scored.append(r)
    save(out/'score.json',{'rows':scored,'summary':{p:{m:dict(Counter(r['state'] for r in scored if r['profile']==p and r['mode']==m)) for m in ('tracefusion','mirrortaint')} for p in ('read-only-network','direct-B')}})
    save(out/'completion.json',{'core_changed':[p for p,h in load(out/'freeze.json')['core_sources'].items() if sha(ROOT/p)!=h], 'oracle_still_frozen':sha(out/'expected.json')==load(out/'freeze.json')['expected_sha256'],'completed_at':now()})
    save(out/'files.sha256.json',{str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.name!='files.sha256.json'})


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);p.add_argument('--repeats',type=int,default=2)
    p.add_argument('--java',default=str(ROOT/'artifacts/galette-static-baselines-20261111/runtime-base/java-8-openjdk-amd64/bin/java'))
    a=p.parse_args();run(a.out.resolve(),a.java,a.repeats)
