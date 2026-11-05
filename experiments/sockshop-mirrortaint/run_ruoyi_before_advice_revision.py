"""One exposed input value before the complete fixed department/dictionary tasks."""
import argparse,copy
from pathlib import Path
from run_planned_service import ROOT,load,save,sha
from run_ruoyi_request_scope_revision import prepare
from run_ruoyi_wrapper_revision import install
from audit_ruoyi_wrapper_facts import run as score

def execute(home,phase):
    build=home/'candidate';out=home/phase
    freeze=load(home/'algorithm-freeze.json')
    for n,digest in freeze['sources'].items():assert sha(Path(n))==digest,n
    names=('ruoyi-2',)if phase=='pilot-final'else('ruoyi-2','ruoyi-3','ruoyi-1')
    if phase!='pilot-final':
        gate=load(home/'pilot-score/summary.json')['states']
        assert all(gate[m].get('known_correct',0)>0 for m in ('full','selective')),'No expansion before both positive-source pilot gates pass'
    prepare(out,build);driver,_=install(out,build);queries=load(out/'task-seal.json')['tasks']['ruoyi']
    for name in names:
        q=copy.deepcopy(next(q for q in queries if q['id']==name))
        if phase=='pilot-final':q['inputs']=[q['inputs'][i]for i in(0,5)]
        save(out/('execution-'+name+'.json'),{'original_case_indices':[0,5]if phase=='pilot-final'else list(range(6)),'query':q,'original_source_declarations_unchanged':True})
        for mode in ('full','selective'):driver.trial('ruoyi',q,mode)

def evaluate(home,phase,query,out):
    raw=home/phase;view=out.parent/(out.name+'-view');view.mkdir(parents=True,exist_ok=False)
    protocol=copy.deepcopy(load(raw/'task-seal.json'));protocol['tasks']['ruoyi']=[q for q in protocol['tasks']['ruoyi']if q['id']==query]
    save(view/'task-seal.json',protocol);(view/'plans').symlink_to((raw/'plans').resolve(),target_is_directory=True)
    mapping={0:0,1:5}if phase=='pilot-final'else{i:i for i in range(6)}
    receipts=[]
    for mode in ('full','selective'):
        source=raw/'runs'/query/mode;dest=view/'runs'/query/mode;dest.mkdir(parents=True)
        result=load(source/'result.json');assert len(result['cases'])==len(mapping)
        for row in result['cases']:
            original=mapping[row['case']];assert row['input']==protocol['tasks']['ruoyi'][0]['inputs'][original]
            row['case']=original  # derived labels only; the actual message and input remain untouched
        save(dest/'result.json',result)
        for name in ('capture','independent-db-times.tsv','independent-db-times-receipt.json'):
            if(source/name).exists():(dest/name).symlink_to((source/name).resolve(),target_is_directory=(source/name).is_dir())
        receipts.append({'mode':mode,'raw_result_sha256':sha(source/'result.json'),'raw_capture_sha256':sha(source/'capture/events.jsonl'),'derived_case_label_mapping':mapping})
    score(view,out,case_indices=set(mapping.values()))
    save(out/'subset-receipts.json',{'phase':phase,'raw_files_not_modified':True,'labels_only':receipts,'no_filter_by_answer_state':True})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=('run','score'));p.add_argument('--home',type=Path,required=True);p.add_argument('--phase',choices=('pilot-final','final-C1'),required=True);p.add_argument('--query',default='ruoyi-2');p.add_argument('--out',type=Path);a=p.parse_args()
    if a.stage=='run':execute(a.home.resolve(),a.phase)
    else:evaluate(a.home.resolve(),a.phase,a.query,a.out.resolve())
