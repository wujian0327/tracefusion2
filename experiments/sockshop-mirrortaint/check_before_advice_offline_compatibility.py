"""Compare complete captured graphs across the two offline-only revisions."""
import argparse,subprocess,sys,types
from pathlib import Path
from run_planned_service import save,sha
from infer_distributed_fields import Reconstruction
import infer_application_execution as current

def run(home,out):
    out.mkdir(parents=True,exist_ok=False);checks=[]
    module_name='infer_application_execution';relative='experiments/sockshop-mirrortaint/infer_application_execution.py'
    versions={}
    for version in ('f8fd38f','e433b94'):
        code=subprocess.check_output(['git','show',version+':'+relative],text=True)
        module=types.ModuleType(module_name);exec(compile(code,version+':'+relative,'exec'),module.__dict__);versions[version]=module
    versions['final']=current
    for q in ('ruoyi-1','ruoyi-2','ruoyi-3'):
        for mode in ('full','selective'):
            view=home/'audit-final-03'/q/(q+'-'+mode);capture=view/'capture/role/events.jsonl';before=sha(capture);results={}
            for version,module in versions.items():
                sys.modules[module_name]=module
                try:
                    graph=Reconstruction(view/'build',view/'capture',['role'])
                    results[version]={'nodes':graph.nodes,'edges':graph.edges,'local_queries':graph.local_queries}
                except ValueError as e:results[version]={'rejected':str(e)}
                finally:sys.modules[module_name]=current
            assert results['e433b94']==results['final'],(q,mode,'parent guard changed intact graph')
            if q=='ruoyi-1':assert 'rejected'in results['f8fd38f']and 'rejected'not in results['final']
            else:assert results['f8fd38f']==results['final']
            assert sha(capture)==before
            checks.append({'query':q,'mode':mode,'capture_sha256':before,'e433_to_final_full_graph_equal':True,
                'f8_to_final_full_graph_equal':q!='ruoyi-1','f8_rejection':results['f8fd38f'].get('rejected')})
    save(out/'checks.json',{'checks':checks,'scope':'Same complete online captures; no additional Agent deployment or timing.'})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.home.resolve(),a.out.resolve())
