#!/usr/bin/env python3
"""Fix evaluation-only Mongo _id projection; first captures/scores stay intact."""
import argparse,copy,json
from pathlib import Path
from collections import Counter
from run_planned_service import load,save,sha
import run_response_binding_revision as old


def rescore(root,out):
    out.mkdir(parents=True,exist_ok=False);receipts=[]
    for source in sorted((root/'train-first').glob('*/evaluation.json')):
        original=load(source)
        if not isinstance(original,dict)or original.get('query')!='trainticket-route-getRouteByStartAndTerminal-data-each-id':continue
        r=copy.deepcopy(original);home=source.parent;capture=home/'capture';cases={c['case']:c for c in load(capture/'run.json')['cases']};rows=[json.loads(s)for s in (capture/'route/events.jsonl').read_text().splitlines()]
        for t in r['predictions']:
            assert t.get('oracle_error')=="'id'",'Only the recorded _id/key defect may be corrected'
            c=cases[t['case']];parts=t['path'].split('/');assert len(parts)==4 and parts[-1]=='id';start,terminal=c['request_path'].split('/')[-2:];docs=c['database_documents']
            kept=[i for i,d in enumerate(docs)if start in d['stations']and terminal in d['stations']and d['stations'].index(start)<d['stations'].index(terminal)];index=kept[int(parts[2])];wanted=docs[index]['_id'];assert t['client_value']==wanted
            roots=[v for v in rows if v['kind']=='binding-return'and v.get('message')==c['message']];assert len(roots)==1
            sources=[v for v in rows if v['kind']=='binding-source'and v['frame']==roots[0]['frame']];assert len(sources)==1;s=sources[0]
            fields=[f for f in s['fields']if f['path']==f'/{index}/id'and f['field']=='route/entity/Route.id'];assert len(fields)==1 and fields[0]['observed']['value']==wanted
            expected={old.source_coord('route',s,fields[0])};actual={tuple(v)for v in t['actual']};t['expected']=sorted(expected,key=str);t.pop('oracle_error');known=t['answer']['known'];t.update(state=('known_correct'if actual==expected else 'known_wrong')if known else 'unknown',tp=len(actual&expected)if known else 0,fp=len(actual-expected)if known else 0,fn=len(expected-actual)if known else len(expected))
        r['states']=dict(Counter(t['state']for t in r['predictions']));r['oracle_unavailable']=sum('oracle_error'in t for t in r['predictions'])
        for k in ('tp','fp','fn'):r[k]=sum(t.get(k,0)for t in r['predictions'])
        dest=out/source.parent.name;dest.mkdir();save(dest/'evaluation.json',r);receipts.append({'source':str(source),'sha256':sha(source),'corrected':str(dest/'evaluation.json'),'corrected_sha256':sha(dest/'evaluation.json'),'mode':r['mode'],'targets':r['targets'],'states':r['states']})
    assert {r['mode']for r in receipts}=={'full','selective'}
    save(out/'receipt.json',{'reason':'Reviewed original Mongo field mapping Route.id <- document._id. The predeclared filter/order/physical-source rule is unchanged; only the evaluator document-key lookup was wrong.','core_and_captures_changed':False,'first_scores_overwritten':False,'changes':receipts})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();rescore(a.root.resolve(),a.out.resolve())
