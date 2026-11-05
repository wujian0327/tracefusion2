"""Only the offline boolean transfer changed after online freeze; compare full graphs."""
import argparse, importlib.util, subprocess, sys, zipfile, hashlib
from pathlib import Path
from run_planned_service import ROOT, load, save, sha
from infer_distributed_fields import Reconstruction
import infer_remove_if


def run(home,out):
    out.mkdir(parents=True,exist_ok=False)
    online=load(home/'algorithm-freeze.json');offline=load(home/'offline-freeze.json')
    assert len(offline['changed_from_online'])==1
    name=offline['changed_from_online'][0]
    assert name.endswith('/infer_remove_if.py')
    reference=out/'reference_infer_remove_if.py'
    relative=Path(name).relative_to(ROOT).as_posix()
    reference.write_bytes(subprocess.check_output(['git','show',online['commit']+':'+relative]))
    assert sha(reference)==online['sources'][name]
    spec=importlib.util.spec_from_file_location('reference_infer_remove_if',reference)
    old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
    checks=[]
    for q in ('ruoyi-1','ruoyi-2','ruoyi-3'):
        for m in ('full','selective'):
            view=home/'audit-final-01'/q/(q+'-'+m)
            signatures=[]
            for module in (old,infer_remove_if):
                sys.modules['infer_remove_if']=module
                try:
                    graph=Reconstruction(view/'build',view/'capture',['role'])
                    signatures.append(('valid',graph.nodes,graph.edges,graph.local_queries))
                except ValueError as e: signatures.append(('rejected',str(e)))
                finally: sys.modules['infer_remove_if']=infer_remove_if
            assert signatures[0]==signatures[1],(q,m)
            checks.append({'query':q,'mode':m,'full_graph_or_rejection_equal':True,'state':signatures[0][0]})
    def classes(path):
        with zipfile.ZipFile(path) as z:
            return {n:hashlib.sha256(z.read(n)).hexdigest()for n in z.namelist()if n.endswith('.class')}
    actual=classes(home/'candidate/distributed-observer.jar')
    assert actual==classes(home/'controls-04/build/distributed-observer.jar')
    save(out/'checks.json',{'captures':checks,'all_control_business_agent_classes_equal':True,'class_count':len(actual),
         'online_commit':online['commit'],'offline_commit':offline['commit'],'new_online_deployment':False})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();run(a.home.resolve(),a.out.resolve())
