"""Derived fault copies only: retain sticky invalidity and exact ownership."""
import argparse,copy,json
from pathlib import Path
from run_planned_service import load,save,sha
from infer_distributed_fields import Reconstruction


def run(home,out):
    out.mkdir(parents=True,exist_ok=False);reports=[]
    for mode in('full','selective'):
        source=home/'runs/ruoyi-1'/mode/'capture/events.jsonl';rows=[json.loads(x)for x in source.read_text().splitlines()]
        for fault in('coverage','framework','dispatch-end','duplicate-dispatch','root-missing','root-message','root-dispatch','excluded-carrier','excluded-message','excluded-completion','excluded-duplicate','parented','async','formal-exclusion','source-call','source-missing','target-missing','sticky'):
            altered=copy.deepcopy(rows);pick=lambda kind:next(r for r in altered if r['kind']==kind)
            if fault=='coverage':altered.remove(pick('query-scope-coverage'))
            elif fault=='framework':altered.remove(pick('query-scope-framework'))
            elif fault=='dispatch-end':altered.remove(pick('query-scope-dispatch-exit'))
            elif fault=='duplicate-dispatch':altered.insert(altered.index(pick('query-scope-dispatch-enter'))+1,copy.deepcopy(pick('query-scope-dispatch-enter')))
            elif fault=='root-missing':altered.remove(pick('query-scope-root'))
            elif fault=='root-message':pick('query-scope-root')['message']='wrong'
            elif fault=='root-dispatch':pick('query-scope-root')['dispatch_id']=-1
            elif fault=='excluded-carrier':pick('query-scope-output-excluded')['carrier_object']='foreign'
            elif fault=='excluded-message':pick('query-scope-output-excluded')['message']=pick('query-scope-root')['message']
            elif fault=='excluded-completion':altered.remove(pick('query-scope-output-excluded-end'))
            elif fault=='excluded-duplicate':altered.insert(altered.index(pick('query-scope-output-excluded'))+1,copy.deepcopy(pick('query-scope-output-excluded')))
            elif fault=='parented':pick('query-scope-output-excluded')['parent_span_id']='1111111111111111'
            elif fault=='async':pick('query-scope-output-excluded')['synchronous']=False
            elif fault=='formal-exclusion':
                root=pick('query-scope-root');d=next(r for r in altered if r['kind']=='query-scope-dispatch-enter'and r['dispatch_id']==root['dispatch_id'])
                for kind in('query-scope-output-excluded','query-scope-output-excluded-end'):
                    r=pick(kind)
                    for key in('dispatch_id','message','handler_method','handler_class_sha256','request_object','response_object','framework_loader','web_type','thread'):r[key]=d[key]
            elif fault=='source-call':pick('binding-source')['source_call_id']=-1
            elif fault=='source-missing':altered.remove(pick('binding-source'))
            elif fault=='target-missing':pick('binding-return')['fields']=[]
            elif fault=='sticky':pick('metrics')['capture_invalid']=True
            for seq,row in enumerate(altered,1):row['seq']=seq
            case=out/(mode+'-'+fault);(case/'build/role').mkdir(parents=True);(case/'capture/role').mkdir(parents=True)
            (case/'build/role/plan.json').write_bytes((home/'plans/ruoyi-1/plan.json').read_bytes())
            (case/'capture/role/events.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n'for r in altered))
            try:
                graph=Reconstruction(case/'build',case/'capture',['role'])
                # Missing source facts may conservatively give unknown rather than
                # invalid; neither is allowed to manufacture a certified answer.
                answers=[graph.query(r['message'],'/data/deptName','role',boundary=[{'kind':'binding-source'},{'kind':'argument'}])for r in altered if r['kind']=='binding-return']
                assert fault in('source-missing','target-missing')and not answers[0]['known'],(mode,fault)
                state='unknown'
            except ValueError as e:state='rejected';reason=str(e)
            reports.append({'mode':mode,'fault':fault,'state':state,'reason':reason if state=='rejected'else None})
    save(out/'results.json',{'checks':reports,'original_hashes':{m:sha(home/'runs/ruoyi-1'/m/'capture/events.jsonl')for m in('full','selective')},'scope':'Derived fault copies; no new business samples.'});print('Ownership/evidence guards:',len(reports))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.home.resolve(),a.out.resolve())
